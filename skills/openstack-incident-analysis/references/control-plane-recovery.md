# Control-plane recovery: what was observed on a lab

Concrete diagnosis and recovery for the shared control-plane components
(RabbitMQ, Galera, HAProxy and keepalived, database connections, Keystone
Fernet keys, Nova conductor and scheduler), distilled from the OzarLand
`openstack-vm-runbooks` repository at commit `babdd8c`. Everything in this
file is an `[Addition]` to the book unless it carries a book citation; the book's
method in `SKILL.md` and failure-patterns.md still decides *whether* to act.
Each procedure carries its validation tag (rule 12 of the safety rules).

Two sources below record their lab runs only in the page text, without a
named executor or a `confirmed_by` record; their findings are given as
*reported from a lab run* and tagged `DOCUMENTED-UNVERIFIED` (policy: the
executor of a validating run must be recorded). They are still the best
available warning about what can go wrong.

Lab context for every `LAB-VALIDATED` item below unless stated otherwise:
OpenStack 2026.1, Kolla-Ansible 22.2.0, Docker, 3 controllers and 2 computes
nested in an OpenStack cloud, ML2/OVS, RabbitMQ 4.2.9 with **Khepri** and
quorum queues, Galera (MariaDB 11.4) behind ProxySQL. Commands are the
Kolla-Ansible forms: on Kolla-Ansible every container runs from a systemd
unit `kolla-<container>-container.service` with `Restart=always`, so a
`docker stop` is undone by systemd after `RestartSec` (11 s with the Kolla
defaults); stop and start through the unit. Other deployment tools: the
diagnosis applies, the commands and paths do not.

## Contents

- RabbitMQ: node missing, partition, alarm, consumers gone
- RabbitMQ: resetting state, and what failed on the lab
- Controlled degradation and reopening provisioning, as run on a lab
- Galera: one node, quorum lost, every node stopped
- HAProxy and keepalived: 503, backend DOWN, VIP flapping
- Database connections exhausted
- Keystone 401 for valid tokens: Fernet keys or clock
- nova-conductor or nova-scheduler down

## RabbitMQ: node missing, partition, alarm, consumers gone

**Recognize.** `MessagingTimeout: Timed out waiting for a reply` in several
services; builds stay `BUILD`, volumes `creating`; computes `down` although
`nova-compute` runs (`Lost connection to nova-conductor for reporting service
status.`); Neutron agents flap. Running instances keep running.

**Read-only checks**, on **every** RabbitMQ node (Kolla-Ansible: prefix
`sudo docker exec rabbitmq`):
- `rabbitmq-diagnostics cluster_status` — nodes this node sees, partitions, alarms.
- `rabbitmq-diagnostics check_local_alarms`.
- `rabbitmqctl list_queues name type messages consumers --silent | sort -k3 -n -r | head -20`.
- `rabbitmqctl list_feature_flags name state --silent | grep khepri` — enabled
  means Khepri, otherwise Mnesia.
- `rabbitmqctl list_connections name state` — `blocked` / `blocking`.

| Observation | Points to |
|---|---|
| Every node lists all others running, no partition, no alarm, no queue growing | RabbitMQ healthy: look at services and the database |
| One node stopped or missing; the others agree | node missing (cause 1) |
| Nodes disagree on the running nodes; log `node '<node>' down: net_tick_timeout` | partition (cause 2) |
| An alarm; connections `blocked`; clients log `The broker has blocked the connection` | memory or disk alarm (cause 3) |
| RPC queues (`conductor`, `scheduler`, `compute.<host>`, `q-plugin`) growing with 0 consumers | consumers gone: the service, not the bus (cause 4) |
| Many ready messages in a `stream` queue | expected, not a backlog |

[LAB-VALIDATED: IA-CP-01] Diagnosis above. Lab: one node stopped 29 s; one
node cut from the others on port 25672 for 2.5 min; a memory alarm forced
with `set_vm_memory_high_watermark absolute 10MB` for 4.5 min; conductors
stopped for cause 4. Not run: a disk alarm, Mnesia, a partition of more than
one node.

[LAB-VALIDATED: IA-CP-02] Behaviour observed with **Khepri** (RabbitMQ
4.2.9): during a partition `cluster_status` showed `Network Partitions
(none)` on both sides; the minority node did **not** pause and kept accepting
AMQP connections; a build sent meanwhile failed with `MessagingTimeout` after
60 s; the partition healed by itself 4 s after the network returned. A
memory alarm on **one** node blocked publishers on the whole cluster: both
computes went `down`, every Neutron agent dead; `server create` got `502` from
HAProxy after 60 s while `nova-api` still completed the request once the alarm
cleared, **so a client that retries can create a second instance**. Not
observed: Mnesia, where `cluster_partition_handling` (`pause_minority` as
Kolla-Ansible 2026.1 sets it) applies and partitions are listed. RabbitMQ
4.3 removes Mnesia and the partition handling strategies.

**Fix the cause first**; oslo.messaging reconnects once RabbitMQ is reachable.
1. Node missing. *State-changing*: `sudo systemctl start
   kolla-rabbitmq-container.service`; it rejoins and quorum replicas catch up
   (about 40 s on the lab). Undo: stop the unit. Streams do not get a replica
   back on a node that was down when they were declared.
2. Partition: repair the network and let it heal (observed with Khepri).
3. Alarm: free memory or disk, or fix the consumer behind the backlog; the
   alarm clears by itself below the limit.
4. Consumers gone: find the service from the queue name and its log.
   *State-changing*: `sudo systemctl restart kolla-<service>-container.service`;
   its in-flight requests fail and are not retried.

[LAB-VALIDATED: IA-CP-03] Fixes 1, 3 and 4 as above (node started through
its unit; alarm undone and every service back within 16 s, the stuck build
`ACTIVE` within 26 s; conductors restarted). Fix 2 observed only with Khepri
(healed by itself).

5. Partition that does not heal (Mnesia, or a node that was suspended and
   resumed). *Destructive*: choose the side the services use (where their
   queues have consumers), export definitions from a trusted node
   (`rabbitmqctl export_definitions <file>`), stop **every** node of the
   other side before starting any, then start them, then restart the trusted
   nodes one at a time. Changes made on the untrusted side are lost. No undo.
   [DOCUMENTED-UNVERIFIED: IA-CP-04]

Do not restart Nova or Neutron services while RabbitMQ is partitioned or
blocked: they reconnect and wait again.

## RabbitMQ: resetting state, and what failed on the lab

The book's incident purged and recovered the bus [Book: Ch. 19]. On a
current Kolla-Ansible platform with Khepri, the reset path did **not** behave
as written:

[DOCUMENTED-UNVERIFIED: IA-CP-05] Reported from one lab run (2026.1,
Kolla-Ansible 22.2.0, RabbitMQ 4.2.9 with Khepri, quorum queues and stream
fanout), recorded in a draft source page without a named executor:
- `rabbitmqctl force_reset` is refused with Khepri (`Forced reset is
  unsupported with Khepri`).
- `kolla-ansible rabbitmq-reset-state` **failed**: the fallback
  `rabbitmqctl reset` timed out on one node, which was left with its
  application stopped and outside the cluster, and the two others failed
  waiting for three nodes (`Not enough nodes joined ...'s cluster`). Users,
  vhosts and queues were kept on the two others.
- That node came back with `rabbitmqctl reset`, `rabbitmqctl join_cluster
  rabbit@<other-node>`, `rabbitmqctl start_app` (*destructive* for that
  node's data).
- The re-joined node was a member of **no** quorum queue or stream: clients
  connected to it failed with `PRECONDITION_FAILED - stream queue '<queue>'
  ... does not have a running replica on the local node`; the Neutron agents
  of one compute were affected and a new instance got no DHCP. Fixed with
  `rabbitmq-streams add_replica -p / <stream> rabbit@<node>` for each stream
  and `rabbitmq-queues grow rabbit@<node> all` (*state-changing*, replication
  load; undo `rabbitmq-queues shrink` / `rabbitmq-streams delete_replica`);
  the instance needed a hard reboot to get its lease. Check with `rabbitmqctl
  list_queues name type members` after any reset or rejoin.
Not run: `force_reset` or `purge_queue` outside Kolla-Ansible, Mnesia. The
reset was run after the partition had healed, outside the step's
precondition, to test it. Treat the failure as a real risk and the recovery
commands as unverified.

The documented last-resort sequence (Kolla-Ansible) is `kolla-ansible
genconfig`, `kolla-ansible stop --tags <services> --yes-i-really-really-mean-it
-e '{"skip_stop_containers": ["nova_libvirt"]}'`, `kolla-ansible
rabbitmq-reset-state`, `kolla-ansible deploy --tags <services>`.
*Destructive*: every queue, exchange and message is deleted, `reset` also
wipes users, vhosts, permissions and policies; in-flight requests are lost;
the tagged services are down from stop to deploy (no DHCP or metadata while
Neutron agents are stopped). Preconditions: causes 1 to 4 ruled out, a
window, `globals.yml` and overrides unchanged since the last deploy or
reviewed. No undo. [DOCUMENTED-UNVERIFIED: IA-CP-06] Given IA-CP-05, treat it
as unproven with Khepri and reported to fail: rehearse it on a lab of the same RabbitMQ version
first, and have the rejoin and replica repair above ready.

## Controlled degradation and reopening provisioning, as run on a lab

The book's decision — stop accepting requests, recover the shared
components, verify, reopen [Book: Ch. 19] — was run on the lab after a
partition of one RabbitMQ node had left `server create` answering 504 and a
record in `BUILD`. What the run added:

- **Stop the API units, not the containers** (Kolla-Ansible: `systemctl stop
  kolla-nova_api-container.service kolla-neutron_server-container.service
  kolla-cinder_api-container.service kolla-glance_api-container.service`, on
  each controller; units that do not exist only print `Unit ... not loaded`),
  or set the backends to `MAINT` in HAProxy.
- **Keep `placement_api` running**: on 2026.1, `nova-conductor` and
  `nova-scheduler` exit at start-up when Placement answers without a usable
  version (`The placement service for <vip>:RegionOne exists but does not
  have any supported versions.`), so their restart fails with Placement
  stopped. **Keep Keystone running**: the verification needs tokens.
- Stopping the APIs does not stop conductors, schedulers and agents.
- After the bus and database are healthy, restart conductors and schedulers,
  then `nova-compute` and (ML2/OVS) the Neutron agents in batches. With OVN,
  `ovn-controller` does not use RabbitMQ and needs no restart for this.
- **The verification needs some APIs**: the test build needs `nova-api`,
  `neutron-server`, `glance-api` (and `cinder-api` for boot from volume)
  through the internal VIP. On Kolla-Ansible with a single VIP, starting
  them reopens them to users before the gate passes; say so to the decision
  owner. No `mysql` binary in the Kolla `mariadb` image: use `docker exec
  mariadb mariadb ...`.
- Verify: RabbitMQ one cluster, no alarm, every queue with consumers
  (`rabbitmqctl list_queues name messages consumers | awk '$3==0 && $2>0'`
  empty); Galera full and `Primary`; no compute service `down`, every agent
  alive; a test instance created, reached and deleted [Book: Ch. 19].

[DOCUMENTED-UNVERIFIED: IA-CP-07] Reported from the same lab run (stop API
units, bus reset — which failed, see IA-CP-05 — Galera checks read-only
because it was healthy, service restarts, verification, reopening); the test
instance was reachable only after the stream replicas were repaired and a
hard reboot. Not run: HAProxy `MAINT`, a Galera recovery, OVN, Mnesia. The
source page stays a draft without a `confirmed_by` entry or a named executor.

## Galera: one node, quorum lost, every node stopped

**Read-only checks**, on every MariaDB node (Kolla-Ansible):
`sudo docker exec mariadb mariadb -uroot -p -e "SHOW STATUS WHERE Variable_name
IN ('wsrep_cluster_status','wsrep_cluster_size','wsrep_local_state_comment','wsrep_ready','wsrep_last_committed')"`;
`sudo docker ps -a --filter name=mariadb`; `/var/log/kolla/mariadb/mariadb.log`;
`grastate.dat` in the `mariadb` volume.

| Observation | Case |
|---|---|
| Every node `Primary`, `Synced`, same size | healthy: look elsewhere |
| One node `non-Primary` or stopped, the others `Primary` | A: one node |
| Every running node `non-Primary`, `wsrep_ready OFF` | B: quorum lost (split, two of three lost) |
| No node running, or containers restarting in a loop; `grastate.dat` `seqno: -1`, `safe_to_bootstrap: 0` | C: every node stopped |

Clients behind ProxySQL see `9001 ... Max connect timeout reached while
reaching hostgroup 0` rather than `1047 WSREP has not yet prepared node`.

[LAB-VALIDATED: IA-CP-08] Diagnosis above; cases A, B and C reproduced
(MariaDB 11.4.13, Galera 26.4.27, ProxySQL). In case A ProxySQL moved the
writer after 14 s with no API error.

Fixes (save each node's `mariadb` volume first in cases B and C: stop it with
`systemctl stop kolla-mariadb-container.service`, check it stays stopped,
copy; `kolla-ansible mariadb-backup` needs a Primary component and does
nothing unless `enable_mariabackup` is set):
- **A**: fix the node, `sudo systemctl start kolla-mariadb-container.service`
  (*state-changing*, IST/SST from a donor); `Synced` in 18 s on the lab. Do not
  run `mariadb-recovery` for this case: it stops the healthy nodes too.
  [LAB-VALIDATED: IA-CP-09] Lab: the node was stopped with `docker stop` and
  started with `docker start` (`Synced` 18 s later by IST); the `systemctl
  start` form above was not run.
- **B**: repair the network first; the nodes reformed `Primary` within 3 s on
  the lab. If missing nodes cannot return: on the node with the highest
  `wsrep_last_committed` **only**, `SET GLOBAL wsrep_provider_pc_bootstrap=ON`
  then `OFF` once `Primary`. *Destructive*: transactions only the other side
  had are lost; run on two sides, it creates two clusters. On MariaDB
  11.4.13, `SET GLOBAL wsrep_provider_options='pc.bootstrap=YES'` fails
  (`ERROR 1210`). [LAB-VALIDATED: IA-CP-10] Lab: port 4567 dropped on every
  node, then the quorum reset on one node; others rejoined by IST.
- **C**: `kolla-ansible mariadb-recovery -i <inventory>`. *Destructive*: stops
  MariaDB everywhere, bootstraps from the highest `seqno`; all clients cut
  off; if a host's position cannot be read the run can leave MariaDB stopped
  everywhere. Precondition: every controller up with its volume intact.
  Afterwards API containers stayed `unhealthy` and conductor and scheduler
  crash-looped on Placement: check `docker ps --filter health=unhealthy` and
  restart those units. [LAB-VALIDATED: IA-CP-11] Lab: all controllers powered
  off and on; recovery took 4 min 34 s; API containers restarted afterwards.
  Not run: the `-e mariadb_recover_inventory_name=<host>` form, which skips
  the seqno comparison and bootstraps from the host you name, and the generic
  Galera crash-recovery steps for other tools (highest seqno, `safe_to_bootstrap:
  1` on that node only, `galera_new_cluster`).
  [DOCUMENTED-UNVERIFIED: IA-CP-12] The named-host form and the non-Kolla
  procedure.

## HAProxy and keepalived: 503, backend DOWN, VIP flapping

**Recognize.** `503 Service Unavailable: No server is available to handle
this request.` (from HAProxy, `<NOSRV>` in its log); a 503 on Keystone
(5000) breaks every command. VIP flapping cuts API connections and the
services' database connections (through the VIP to ProxySQL), not RabbitMQ.

**Read-only checks**, on each `loadbalancer` node (Kolla-Ansible):
- `ip -brief address show dev <api-interface> | grep -w <internal-vip>` —
  exactly one node in total.
- `sudo docker exec keepalived bash -c 'echo "show stat" | socat
  unix-connect:/var/lib/kolla/haproxy/haproxy.sock stdio'` — backend state
  and check result (`L4CON` refused, `L4TOUT`, `L7TOUT`, `L7STS`).
- `sudo sh -c 'grep -h -e "is DOWN" -e "is UP" -e "no server available"
  /var/log/kolla/haproxy/haproxy_latest*'` (root shell: the glob is not
  expanded otherwise); `sudo docker logs --since 2h keepalived 2>&1 | grep -E
  "Entering|FAULT|VRRP_Script|now returning"`.

| Observation | Cause |
|---|---|
| 503, every server of one backend DOWN `L4CON` | service down on every controller |
| 503, servers DOWN `L7TOUT` / `L7STS` | service runs but its check fails (often a dependency) |
| One server DOWN, others UP | one controller |
| VIP moves, `VRRP_Script(check_alive) failed` | HAProxy **or ProxySQL** unstable on the master (both are in `check_alive`) |
| VIP on two nodes; master logs `Received advert ... with lower priority` | VRRP advertisements lost |
| No 503 but connection refused; VIP on no node | HAProxy down everywhere |

[LAB-VALIDATED: IA-CP-13] Diagnosis above. Lab: Placement stopped on every
controller (DOWN 4 s after the stop), frozen with `docker pause` on one
(`Layer7 timeout`, 59 s), one Placement down, ProxySQL and HAProxy stopped on
the VIP holder (FAULT, VIP moved 1 s later), VRRP dropped on a backup (VIP on
two nodes); HAProxy 2.8.16, keepalived 2.2.8 in unicast mode. Not run: HAProxy
down everywhere, VRID collision, multicast mode, TLS backends.

Fixes: read the service log before restarting ("a container that exits at
start-up will exit again"); fix a failing dependency rather than HAProxy.
*State-changing*: `sudo systemctl restart kolla-<container>-container.service`
for the service on one controller; HAProxy or ProxySQL one node at a time
(restarting it on the VIP holder cuts every connection through it and can
move the VIP; never restart a healthy HAProxy on the master); with the VIP on
two nodes, `systemctl stop kolla-keepalived-container.service` on the wrong
one once the other holds the VIP with its backends UP, fix VRRP transport,
start it again. [LAB-VALIDATED: IA-CP-14] Lab: the service restart, keepalived
stop / fix / start. Not run: `kolla-ansible reconfigure -t loadbalancer`
(new `keepalived_virtual_router_id` or `keepalived_traffic_mode: unicast`),
which restarts keepalived on every node and can briefly put the VIP on two
nodes. [DOCUMENTED-UNVERIFIED: IA-CP-15]

## Database connections exhausted

| Message in service logs | Where the limit is |
|---|---|
| `QueuePool limit of size ... overflow ... reached` in one service | that service's pool (`[database] max_pool_size`, `max_overflow`) |
| `(9001, 'Max connect timeout reached while reaching hostgroup 0 ...')`; writer `SHUNNED`; `1040: Too many connections.` in `proxysql.log` | MariaDB node full (`max_connections` 10000 in Kolla's `galera.cnf`) |
| `9001`; backends `ONLINE`, `ConnUsed` at the ProxySQL backend limit | ProxySQL backend pool full |
| `9001`; hostgroup 0 empty, every node in hostgroup 3 | Galera not synced: see Galera above, do not raise limits |
| `(1040, 'Too many connections')` with a ProxySQL warning | ProxySQL client limit |

oslo.db does not retry `1040` or `9001`. Behind ProxySQL, services never see
`1040` for a full MariaDB node. Read-only checks: the MariaDB
`max_connections`, `Threads_connected`, processlist grouped by user;
ProxySQL `stats_mysql_connection_pool` on the node holding the VIP.

[DOCUMENTED-UNVERIFIED: IA-CP-16] Reported from a lab run recorded in a
draft source page without a named executor (ProxySQL 3.0.11, MariaDB 11.4): MariaDB full
(`max_connections` lowered to 20 on the writer: APIs worked about 2.5 min,
then every service on `9001`, CLI `502`) and no synced writer (hostgroup 0
empty, every service `9001`). Not reproduced: `QueuePool limit` (Kolla's uWSGI
runs one thread per process), the ProxySQL client limit, the ProxySQL backend
pool full.

Fixes: restart the service that holds the connections, one controller at a
time. A full node: `SET GLOBAL max_connections` may be impossible (root was
refused on the lab); restart MariaDB on that node (*state-changing*, only if
the two others are `Synced` and size is 3; it rejoined by IST, `Synced` 33 s
later). Killing idle sessions of the identified service (`KILL <id>` on the
node holding them) is *destructive*: their open transactions roll back.
[DOCUMENTED-UNVERIFIED: IA-CP-17] Reported from the same lab run: the node
restart and killing one idle `neutron` session. Not run: restarting the
service holding the connections, raising `max_connections` on a full node,
raising pool sizes.

## Keystone 401 for valid tokens: Fernet keys or clock

**Recognize.** `openstack token issue` works but later calls fail `401 The
request you have made requires authentication.`; services log only `WARNING
keystonemiddleware.auth_token ... Authorization failed for token` at default
levels. Diverged keys break tokens older than the cache TTL (600 s); a clock
off breaks fresh tokens too.

**Read-only checks.**
- On each controller: `sudo docker exec keystone_fernet bash -c 'cd
  /etc/keystone/fernet-keys && md5sum *'`. Deciding test: is each node's
  primary key (its highest number) present, by checksum, in every other node's
  set? Different lists alone are not a fault.
- `sudo docker ps -a --filter name=keystone` — `keystone_fernet` unhealthy on
  the nodes that cannot **push**; a node whose `keystone_ssh` is down stays
  healthy itself.
- A token older than 600 s against each node's `/v3/auth/tokens`: 200 or 401;
  the 404 reason (`Could not recognize Fernet token` = missing key, `Failed
  to validate token` = expired or revoked per that node's clock). Only the
  first answer for a token is reliable (the cache is shared).
- Clock: `chronyc tracking`, or `timedatectl show -p NTPSynchronized --value`.

[LAB-VALIDATED: IA-CP-18] Diagnosis above. Lab: `keystone_ssh` stopped on one
node and two rotations on another (tokens older than 10 min got 401 on 8 of 8
calls through the VIP); a clock 300 s behind with a revocation event, and two
days ahead. HTTP endpoints, no TLS backend.

Fixes. *State-changing*: start `kolla-keystone_ssh-container.service` where
stopped (use the unit: `docker start` left the unit inactive on the lab).
*Destructive*: back up each node's key directory, then from the source node
chosen by checksum and last rotation (not by highest key number) run `sudo
docker exec keystone_fernet /usr/bin/fernet-push.sh`; it overwrites the
others with `rsync --delete`, so tokens issued by the other nodes fail (up to
two thirds with three nodes) and in-progress operations that forward user
tokens can fail; do it in a quiet window, outside the rotation slots; no real
undo. No Keystone restart is needed. Clock: *state-changing* `sudo timedatectl
set-ntp true` (timesyncd) steps the clock; tokens issued while it was behind
stay rejected until they expire.
[LAB-VALIDATED: IA-CP-19] Lab: `keystone_ssh` repair, backups, push from the
chosen node (identical sets at once, verification 6 of 6), clock fixed with
`timedatectl set-ntp true`. Not run: `chronyc makestep`, `kolla-ansible
reconfigure -t keystone` (which pushes from the first node of the group, a
source you do not choose). [DOCUMENTED-UNVERIFIED: IA-CP-20] Those two.

With the Kolla-Ansible defaults and three Keystone nodes, the rotation cron
gives slots to two nodes only (the third crontab has only a `PATH` line);
check `/etc/kolla/keystone-fernet/crontab`. One missed push is harmless; a
second rotation without a push breaks tokens.

## nova-conductor or nova-scheduler down

| | Conductor down everywhere | Scheduler down everywhere |
|---|---|---|
| New instances | wait in `BUILD`/`scheduling`, finish when it returns | `ERROR` after about `rpc_response_timeout` (60 s), fault `MessagingTimeout`, buried in cell0 with no host |
| Computes | `down` within a minute (`Lost connection to nova-conductor`) | stay `up` |
| Start / stop / reboot | accepted, then time out on the compute and can leave a `task_state` | work |
| Danger | deleting an instance whose compute is `down` is a local delete | failed requests only |

Read-only: `docker ps -a --filter name=nova_conductor --filter
name=nova_scheduler`; `rabbitmqctl list_queues -p <vhost> name messages
consumers | grep -E '^(conductor|scheduler)\s'` (0 consumers, growing).

Fixes: read the log, fix, then *state-changing* `systemctl restart
kolla-nova_conductor-container.service` (or scheduler) per controller. Do not
restart Nova while RabbitMQ is partitioned or blocked. Afterwards: queued
builds finish by themselves; `ERROR` instances from the outage (empty host,
fault `MessagingTimeout` or `No valid host`, created in the window) can be
deleted (*destructive*: the fault is the only trace; `--status ERROR` also
lists real instances). An instance left with a `task_state`: choose the state
from its power state, `openstack server set --auto-approve --state error`
then `openstack server reboot --hard` if the guest is off (a hard reboot is
refused while `task_state` is `powering-on`); `--state` changes the record
only.

[LAB-VALIDATED: IA-CP-21] Lab: conductors stopped on all three controllers
(computes `down` after 51-58 s; queued build `ACTIVE` 32 s after the restart;
a start left `powering-on`, fixed with `--state error` and a hard reboot);
schedulers stopped (build `ERROR` after 61-63 s, fault `MessagingTimeout`);
cell0 clean-up. Not run: resize, migrations, evacuate, a local delete, cell0
database unreachable, `--state active`, a stop or reboot of a running
instance with the conductor down, any start, stop or reboot with the
scheduler down (those table cells come from the code).
