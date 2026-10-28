# Host and database operations

`[Addition]` — everything in this file is distilled from the OzarLand
repository `kolla-ansible-deployment-patterns` at commit `dee2c60`
(Kolla-Ansible for OpenStack 2026.1); the book does not describe these
procedures. Commands starting with `kolla-ansible`, `docker`, Kolla container
names and paths under `/etc/kolla`, `/var/log/kolla` or
`/var/lib/docker/volumes` are Kolla-Ansible specifics (Docker engine);
`openstack ...` commands apply to any deployment. Every section is a
production change with real blast radius: present each step with its label
(*Read-only*, *State-changing*, *Destructive*), its validation status, and a
named owner for anything destructive.

Most of this file is `DOCUMENTED-UNVERIFIED`: the compute and controller
procedures were written from the Kolla-Ansible 2026.1 guide and code and were
not run on a lab. Only parts of the MariaDB and secret-rotation sections were.

## Contents

- Adding a compute node
- Removing or replacing a compute node
- Replacing a failed controller
- MariaDB backup and restore
- Recovering a stopped Galera cluster (mariadb-recovery)
- Rotating secrets in passwords.yml

---

## Adding a compute node

Usually the least risky change to a running deployment (a compute runs no
clustered service); the risk is in the commands around it. Covers
libvirt/KVM computes; not Ironic, cells, SR-IOV/PCI/GPU hosts, new
controllers or network nodes. [DOCUMENTED-UNVERIFIED: KA-OPS-01]

**Before.** Run with the Kolla-Ansible version that deployed the platform:
`pip show kolla-ansible` in its virtualenv must match the series of the
running images (`openstack_release` in `globals.yml`, or the image tags of
`docker ps`); a newer Kolla-Ansible deploys newer images to the new host.
The host needs the same interface names as the other computes (or its own
`host_vars`: `network_interface`, `tunnel_interface`,
`neutron_external_interface`, storage network), the same MTU, SSH from the
deploy host, and reach to the internal VIP, the registry and, with Ceph, the
monitors. Add it to `[compute]` only (plus other groups only if computes
carry them). Keep the name stable and unique; reusing a removed compute's
name needs the old records cleaned first (next section).

**Steps** (Kolla-Ansible, from the deploy host; type the host name, not a
group, so a typo fails instead of widening the run):
1. *Read-only*: `openstack compute service list --service nova-compute`,
   `openstack network agent list`, `ansible -i <inventory> compute-03 -m ping`.
2. *State-changing*: `kolla-ansible bootstrap-servers -i <inventory> --limit compute-03`
   (installs packages, configures Docker on the limited host only).
3. Read-only for the platform: `kolla-ansible pull -i <inventory> --limit compute-03`;
   `kolla-ansible prechecks -i <inventory> --limit compute-03`.
4. *State-changing*: `kolla-ansible deploy -i <inventory> --limit compute-03`.
   Creates the compute containers and registers the host; it is schedulable
   as soon as it registers. Undo: the removal procedure.
5. *Read-only* verify: `openstack compute service list --service nova-compute --host compute-03`
   (up, enabled), `openstack hypervisor list`, `openstack network agent list --host compute-03`,
   `openstack resource provider list --name compute-03` (osc-placement).
6. *State-changing* test (admin, test project, small flavor):
   `openstack server create --flavor <flavor> --image <image> --network <network>
   --availability-zone nova:compute-03 test-compute-03`, then `openstack server show
   test-compute-03 -c status -c addresses -c OS-EXT-SRV-ATTR:host`;
   it must reach `ACTIVE`, get its address, answer and reach metadata; then
   delete it. Test before disabling: a disabled service gets the
   `COMPUTE_STATUS_DISABLED` trait and cannot take a test boot.
7. On failure, *State-changing*: `openstack compute service set --disable
   --disable-reason "new host, failed test" compute-03 nova-compute` (running
   instances unaffected; undo `--enable`).
8. Rebalance only by live-migrating instances one at a time (*State-changing*,
   short pause at the end): `openstack server migrate --live-migration --host
   compute-03 --os-compute-api-version 2.30 <server-id>`.

**What `--limit` and `bootstrap-servers` really touch.**
[DOCUMENTED-UNVERIFIED: KA-OPS-02] (read from the 2026.1 roles, not run)
- `bootstrap-servers` without `--limit` runs on every host and can upgrade or
  restart Docker and every container with it: never run it unlimited on
  production.
- With `--limit`, the `gather-facts` play still gathers facts for every
  inventory host (delegated through the limited ones); an unreachable host
  can make templates that need its address fail: fix or remove it first.
  Fact gathering allows failures (`max_fail_percentage` 100): the run goes
  on, reports the host unreachable at the end and exits non-zero.
- `customize_etc_hosts` (default true) writes `/etc/hosts` entries on the
  limited hosts only: existing hosts do not learn the new name that way.
- `--limit` leaves configuration drift on other hosts unapplied; the
  operating guide warns `--limit` has known bugs in general.

**Registration wait.** [DOCUMENTED-UNVERIFIED: KA-OPS-03] Near the end of the
Nova part, Kolla-Ansible waits for the new `nova-compute` service (20 tries,
10 s apart, about 200 s), then runs `nova-manage cell_v2 discover_hosts
--by-service` itself (do not run it by hand). On timeout the deploy fails
that host only (unless `nova_compute_registration_fatal` is true) with
`The following Nova compute services failed to register themselves: <host>`.
Read `nova-compute.log` on the new host (Kolla-Ansible:
`/var/log/kolla/nova/nova-compute.log`).
**Open point, not resolved:** this page says the cause is most often
RabbitMQ or the Placement API unreachable, or libvirt not started; the
deployment-error page for that message says Placement and Keystone errors do
**not** cause it in Nova 2026.1 (the service record is created after
`init_host`, whose Placement call only logs; such a compute registers but has
no resource provider and gets no instances), and points to
`Connection to libvirt failed`, `AMQP server on <address>:5672 is unreachable`
or a host name mismatch. Let the log decide; say which page you follow.

---

## Removing or replacing a compute node

What matters is the instances on the host and the records Nova, Placement and
Neutron keep: a host removed from the inventory but not cleaned up stays
`down` in the lists; a reinstalled host reusing the name of uncleaned records
can fail to start `nova-compute`. Where instance disks live decides how
instances leave: shared storage (Ceph RBD, boot from volume) live-migrates or
evacuates with the disk intact; local disks live-migrate by block migration
(automatic from microversion 2.25) but **are lost on evacuation** (rebuilt
from the image). If the host also carried provider networks, distributed
floating IPs or an OVN gateway, check `openstack network agent list --host <host>` first.

**Host still running.** [DOCUMENTED-UNVERIFIED: KA-OPS-04]
1. *Read-only*: `openstack server list --all-projects --host <host> --long`,
   `openstack hypervisor list --long` (room elsewhere?),
   `openstack network agent list --host <host>`.
2. *State-changing*: `openstack compute service set --disable --disable-reason
   "decommissioning" <host> nova-compute`. Undo: `--enable`.
3. *State-changing*: live-migrate one by one, then check the host is empty:
   `openstack server list --all-projects --host <host> -f value -c ID | while read server; do openstack server migrate --live-migration --wait "$server"; done`.
   PCI, SR-IOV or GPU instances usually cannot live-migrate: plan a cold
   migration or an agreed restart with owners. Undo: migrate back.
4. *State-changing*, precondition host empty: Kolla-Ansible:
   `kolla-ansible stop -i <inventory> --yes-i-really-really-mean-it --limit <host>`
   (stops every Kolla container on that host only). Undo:
   `kolla-ansible deploy -i <inventory> --limit <host>`.
5. Remove the host from every inventory group and its `host_vars` (own
   commit); check a boot and a migration between the remaining hosts. Until
   removed, a later full `deploy` starts its `nova_compute` again.

**Clean up the records.** [DOCUMENTED-UNVERIFIED: KA-OPS-05] *Destructive*,
no undo (records come back only by deploying the host again). Precondition:
no instance on the host and its services stopped, otherwise agents
re-register. Deleting the compute service also deletes its compute node and
its Placement resource provider; Nova refuses while instances or migrations
reference the host (documented behaviour, not checked on 2026.1).
```bash
openstack network agent list --host <host> -f value -c ID | while read id; do openstack network agent delete $id; done
openstack compute service list --os-compute-api-version 2.53 --host <host> -f value -c ID | while read id; do
  openstack compute service delete --os-compute-api-version 2.53 $id; done
```
Replacing: with a new name, remove then add. With the same name, finish the
removal including this cleanup first (no service, compute node or resource
provider left under that name), then add it as a new host.

**Host dead.** [DOCUMENTED-UNVERIFIED: KA-OPS-06] *Destructive*: evacuation
rebuilds each instance elsewhere; local-disk data is lost, no undo.
Precondition: the host is **fenced** (powered off or cut from storage and
network), otherwise one instance can run twice and corrupt a shared disk.
Nova must see the service `down` (disabling is not enough):
`openstack compute service set --down <host> nova-compute` after fencing,
then `openstack server evacuate <server-id>` one at a time, checking each.
Read Nova's *Evacuate instances* and *Recover from a failed compute node*
first. Then stop what remains (step 4, if reachable), remove from inventory,
clean records. If the dead machine is powered on with its old disks, keep
`nova-compute` from starting: at start-up it deletes local copies of
evacuated instances (`_destroy_evacuated_instances`).

---

## Replacing a failed controller

One of three controllers lost; Galera and RabbitMQ keep quorum with two, the
cloud is degraded and one more failure loses quorum. Not for two lost
controllers (see the Galera recovery below), controllers with Ceph monitors,
cells or Podman. Decide first: **same name** (inventory unchanged; clean the
failed host's records before it registers) or **new name** (replace it in
every group; memberships change). Nothing to move for data: Galera and Fernet
keys are copied to the replacement when it joins; RabbitMQ quorum queues and
streams are not.

**Steps 1-3.** [DOCUMENTED-UNVERIFIED: KA-OPS-07]
1. *Read-only*, do not start unless both survivors are healthy: Kolla-Ansible:
   `sudo docker exec -it mariadb mariadb -uroot -p -e "SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment');"`
   (size 2, `Primary`, `Synced`; `-p` prompts for `database_password`);
   `sudo docker exec rabbitmq rabbitmqctl cluster_status` (two running, the
   failed one stopped); `openstack network agent list --host <failed-host>`.
2. ML2/OVS without L3 HA (`enable_neutron_agent_ha`), *State-changing* (short
   routing/DHCP interruption for moved networks; undo: move back): the guide's
   loop moves routers from the dead L3 agent to a healthy one
   (`openstack router list --agent $l3_id`, `network agent remove router ... --l3`,
   `network agent add router ... --l3`), then `openstack network agent set
   $l3_id --disable`; same loop for DHCP (`network list --agent`, `--dhcp`),
   and disable the dead DHCP agent. ML2/OVN reschedules gateways itself.
3. If reachable, *State-changing*: `kolla-ansible stop -i <inventory>
   --yes-i-really-really-mean-it --limit <failed-host>`.

**Step 4, remove the RabbitMQ member.** [DOCUMENTED-UNVERIFIED: KA-OPS-08]
*Destructive*, no undo: `sudo docker exec rabbitmq rabbitmqctl
forget_cluster_node rabbit@<failed-short-name>` on one healthy controller;
a queue whose only replica was on it is lost. Precondition: failed host down
or stopped and listed as a stopped member. Galera needs no command. With
`etcd`, set `etcd_remove_deleted_members: "yes"` before step 6 or remove the
member with `etcdctl`. **Open point, not resolved:** this page runs
`forget_cluster_node` even when the replacement keeps the same name; the
RabbitMQ clustering error page says not to forget a name that is reused, but
to reset the replacement node instead (`rabbitmqctl stop_app`, `force_reset`
or `reset`, `start_app`, after exporting definitions). Raise it with the
owner before choosing; neither variant was run on a lab.

**Steps 5-6, deploy with all controllers in the limit.**
[DOCUMENTED-UNVERIFIED: KA-OPS-09] Update the inventory (new name only).
*State-changing*: `kolla-ansible bootstrap-servers -i <inventory> --limit control`
can upgrade or restart Docker on the healthy controllers and every container
with them (maintenance window; consider Docker `live-restore` or an exact
package pin; no undo); the guide requires all controllers because RabbitMQ
needs `/etc/hosts` entries for all of them. Then
`kolla-ansible pull -i <inventory> --limit <replacement-host>` and
`kolla-ansible deploy -i <inventory> --limit control`. With a new name, the
healthy controllers' `wsrep_cluster_address` and RabbitMQ peer list change:
MariaDB and RabbitMQ restart one by one, briefly interrupting API calls
through the restarted host; with the same name only the new node joins. The
replacement's MariaDB joins by full state transfer (slow, loads the donor).
Fernet keys are pushed from a healthy controller.

**Step 7, grow quorum queues and streams.** [DOCUMENTED-UNVERIFIED: KA-OPS-10]
A joining node is not added to existing quorum queues (default in 2026.1)
or streams (`om_enable_rabbitmq_stream_fanout`, default true); the 2026.1
role does not reconcile. *State-changing* (replication load), precondition
`cluster_status` shows three running:
`sudo docker exec rabbitmq rabbitmq-queues grow rabbit@<replacement-short-name> all`;
for each stream from `rabbitmqctl list_queues name type` (type `stream`):
`rabbitmq-streams add_replica <stream-queue> rabbit@<replacement-short-name>`.
Default vhost `/` assumed (else `-p <vhost>` / `--vhost <vhost>`). Undo:
`rabbitmq-queues shrink rabbit@<replacement-short-name>`,
`rabbitmq-streams delete_replica <stream-queue> rabbit@<replacement-short-name>`.

**Step 8, records, and verify.** [DOCUMENTED-UNVERIFIED: KA-OPS-11]
*Destructive*, no undo: delete the failed host's network agents and compute
services with the same loops as for a compute (previous section). Order: new
name, after step 6; **same name, before step 6**, so the replacement
registers fresh. Verify: Galera size 3, RabbitMQ three running nodes,
`rabbitmq-queues check_if_node_is_quorum_critical` on each node,
`rabbitmqctl list_queues name type members` (three members), every agent
alive, a test instance; move routers/DHCP back if step 2 moved them.

---

## MariaDB backup and restore

Galera protects against losing a node, not a bad `DELETE`, a failed schema
migration or losing every controller. `kolla-ansible mariadb-backup` takes hot
Mariabackup backups; it does not schedule, copy off-host or restore them.

**Enable and back up.** [LAB-VALIDATED: KA-OPS-12] Lab: 2026.1, Kolla-Ansible
22.2.0, 3 controllers (MariaDB 11.4.13 Galera behind ProxySQL) + 2 computes,
Docker, about 100 MB of data; enabling, one full and one incremental backup
were run. Not run: several incrementals, a large database, Podman.
- *State-changing*: `enable_mariabackup: "yes"` in `globals.yml`, then
  `kolla-ansible reconfigure -i <inventory> --tags mariadb` (creates the
  backup user; MariaDB containers restart one by one if their configuration
  changed). Without this, `mariadb-backup` does nothing.
- `kolla-ansible mariadb-backup -i <inventory>` (full) and `... --incremental`
  (on the last full). No downtime; read load on the backup host. It runs a
  short-lived `mariabackup` container with the running `mariadb` image.
- Files land only on `mariadb_backup_host` (first host of the shard group),
  Docker volume `mariadb_backup`: `/var/lib/docker/volumes/mariadb_backup/_data/`
  holds `full-<date>-<n>/`, `incr-<time>-<date>-since-<date>-<n>/` and
  `last_full_file`. List files with `sudo bash -c 'ls -lh .../_data/*/'`
  (with `sudo ls .../_data/*/` your shell expands the glob and fails). Lab:
  full 37 s, incremental 58 s, full backup 1.8 MB compressed. Only the
  default shard is backed up.

**Copy off the host.** [DOCUMENTED-UNVERIFIED: KA-OPS-13] A backup left on the
controller is lost with it. The guide suggests daily full kept two weeks and
hourly incrementals kept one day, scheduled outside Kolla-Ansible; copy
e.g. `sudo rsync -a /var/lib/docker/volumes/mariadb_backup/_data/ <backup-user>@<backup-server>:<backup-path>/`
and check the copy. Not run on the lab.

**Restore a Galera cluster.** [LAB-VALIDATED: KA-OPS-14] Lab: 2026.1,
Kolla-Ansible 22.2.0, 3 MariaDB nodes behind ProxySQL, Docker, full backup
plus one incremental; steps 1-4 as written (the interactive `docker run -it
... bash` given to `bash -c`): both emptied nodes took a full SST one after
the other, the recovery took 3 min 9 s, all `Synced`, data at the
incremental's point, test instance `ACTIVE` in 26 s. Not run: single-node
restore, several incrementals, a large database (SST and role time-outs).
*Destructive*: every OpenStack database returns to the backup; everything
written after it is unknown to OpenStack while hypervisors, Ceph and network
may still hold it; every API is down from step 2 to the end. Only when the
data is lost or corrupt beyond repair (if intact but stopped, use
`mariadb-recovery` below), with the owner's recorded decision, after copying
each node's `mariadb` volume aside. Run on the first MariaDB host;
`<mariadb-image>` from `sudo docker inspect mariadb --format '{{.Config.Image}}'`
(not the guide's `-rocky-10` example).
1. Prepare (database not touched): `sudo docker run --rm -it --volumes-from
   mariadb --name dbrestore --volume mariadb_backup:/backup <mariadb-image> /bin/bash`;
   inside: `rm -rf /backup/restore && mkdir -p /backup/restore/full`, `gunzip`
   the full file, `mbstream -x -C /backup/restore/full/ < <file>.qp.xbc.xbs`,
   `mariabackup --prepare --target-dir /backup/restore/full`. Per incremental,
   oldest first: extract to `/backup/restore/inc`, then
   `mariabackup --prepare --incremental-dir=/backup/restore/inc --target-dir /backup/restore/full`.
   Do not use the guide's `--tmpfs /backup/restore` (step 3 needs it). Go on
   only after `completed OK!`.
2. *Destructive*: `kolla-ansible stop -i <inventory> --tags mariadb --yes-i-really-really-mean-it`.
3. *Destructive*, precondition every node's volume copied aside (e.g.
   `sudo cp -a /var/lib/docker/volumes/mariadb/_data <safe place>`): same
   `docker run`, inside `rm -rf /var/lib/mysql/*`, `rm -rf /var/lib/mysql/\.[^\.]*`,
   `mariabackup --copy-back --target-dir /backup/restore/full`.
4. On every **other** node: *Read-only* `sudo docker ps -a --filter name=mariadb
   --format '{{.Names}}\t{{.Status}}'` must show `Exited` (emptying a running
   node corrupts it); then *Destructive* (undo: copy saved data back)
   `sudo find /var/lib/docker/volumes/mariadb/_data -mindepth 1 -delete`. Then
   *Destructive* `kolla-ansible mariadb-recovery -i <inventory> -e
   mariadb_recover_inventory_name=<first-mariadb-host>`. Without the named
   host it picks the highest `seqno`, which is not the restored node.
   Expected: a joiner may log `No donor candidates temporarily available`
   while the other one transfers. A node that still refuses (`Local state
   seqno ... is greater than group seqno`, states diverged) was not cleared.
   On a large database the role's waits may run out; see *Recovering a
   stopped Galera cluster* and its open point on the wait time.
Podman: `podman` and `/var/lib/containers/storage/volumes/`.

**Variants not run.** [DOCUMENTED-UNVERIFIED: KA-OPS-15] Single node: after
step 3, `sudo docker start mariadb` and read `sudo docker logs mariadb`.
Several incrementals: one `--prepare --incremental-dir` each, in order.
[DOCUMENTED-UNVERIFIED: KA-OPS-16] Why other nodes are emptied: the role
starts them as they are, and a node ahead of the new cluster normally refuses
to join instead of taking an SST (from Galera behaviour and the role's code;
the refusal was not observed). The lighter variant (moving only
`grastate.dat` aside) is unverified and may still refuse (`--wsrep-recover`
restores the node's own newer `seqno`): use the full emptying.

---

## Recovering a stopped Galera cluster (mariadb-recovery)

**Recognize.** After every controller was down together (power loss, all
rebooted, containers stopped together), MariaDB does not return, APIs answer
`Bad Gateway (HTTP 502)`, and any `deploy`/`reconfigure`/`upgrade` fails in
`TASK [mariadb : Fail on existing but stopped cluster]` with `MariaDB cluster
exists but is stopped. Please start it using kolla-ansible mariadb-recovery`
(more than one MariaDB host, every host has a `mariadb` volume, none answers
on the port), after one ignored `Timeout when waiting for search string
MariaDB in <address>:3306` per host. Running instances keep running; data is
not lost yet: the risk is recovering the wrong way.

[LAB-VALIDATED: KA-OPS-17] Recognition and read-only checks. Lab: 2026.1,
Kolla-Ansible 22.2.0, 3 controllers (Galera behind ProxySQL) + 2 computes,
Docker; three containers stopped cleanly within seconds with `systemctl`.
Not run: a crash (`seqno: -1`), cause 2.

**Read-only checks** (Kolla-Ansible, each MariaDB host):
`sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -w mariadb`;
`sudo cat /var/lib/docker/volumes/mariadb/_data/grastate.dat` (`seqno`,
`safe_to_bootstrap`); `sudo tail -n 50 /var/log/kolla/mariadb/mariadb.log`;
from the deploy host `nc -zv -w 3 <controller-api-address> 3306`. Lab:
`Exited (0)` everywhere, a `seqno` on each node, `safe_to_bootstrap: 1` only
on the highest (last stopped), `Connection refused`.

| Observation | Points to |
|---|---|
| All nodes down, this message | cause 1: no primary component; `mariadb-recovery` is made for it |
| One node answers but not `Synced`; roles fail earlier with `MariaDB cluster is not synced. Please wait for WSREP sync before proceeding.` | cause 2: inspect that node (`SHOW STATUS LIKE 'wsrep_%'`) |

**Cause 1, recover.** [LAB-VALIDATED: KA-OPS-18] Lab: 2026.1, Kolla-Ansible
22.2.0, 3 controllers (Galera behind ProxySQL) + 2 computes, Docker, 2.3 GB of
data, clean stop: step 1, the recovery without a named host (2 min 32 s, highest `seqno`
chosen, `failed=0`, APIs answered without restarting them), step 3 and the
verification were run. Not run: crash with `seqno: -1`, forced bootstrap
outside a restore, a time-out on a joiner.
1. *State-changing*, on every node: if the container shows `Restarting` or
   `Up`, `sudo systemctl stop kolla-mariadb-container.service` (in 2026.1
   systemd restarts a container stopped any other way); then
   `sudo cp -a /var/lib/docker/volumes/mariadb/_data /var/lib/mariadb-before-recovery-$(date +%F)`
   (free space = data size; about 30 s per node for 2.3 GB). Undo:
   `sudo systemctl start kolla-mariadb-container.service`.
2. *Destructive*: `kolla-ansible mariadb-recovery -i <inventory>`. Stops MariaDB
   everywhere, runs `--wsrep-recover` on each node, bootstraps the highest
   `seqno` (`safe_to_bootstrap: 1`, `--wsrep-new-cluster`), starts the others
   (they replace their data by state transfer), then restarts the bootstrap
   node normally. Transactions only a lower node had are lost. Precondition:
   step 1 on every node, every MariaDB host reachable by Ansible. Undo: only
   by restoring the step 1 copies.
3. *Read-only*: the chosen host is in `/tmp/kolla_mariadb_recover_inventory_name_<shard>`
   on the deploy host; on each node `sudo grep 'Recovered position:'
   /var/log/kolla/mariadb/mariadb.log | tail -n 1`. Keep the colon: without it
   the pattern matches `Recovered position from storage:`, written later by
   state transfer (seen on the lab). Run it before step 2 too.

**Verify.** `sudo docker exec -it mariadb mariadb -uroot -p -e "SHOW STATUS
WHERE Variable_name IN ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment');"`
(size = MariaDB hosts, `Primary`, `Synced`; `-p<password>` in a script puts
it in the process list and history), `openstack token issue`,
`openstack server list --all-projects --limit 5`; a later `deploy` passes the
task.

**After a power loss, check the other containers too.** On a lab, after every
controller lost power and `mariadb-recovery` ran, `nova_api`,
`nova_metadata`, `placement_api` and `neutron_server` stayed `unhealthy`
(uWSGI `no python application found`, HAProxy 503) and `nova_conductor` and
`nova_scheduler` crash-looped on `The placement service for <vip>:RegionOne
exists but does not have any supported versions.` Check
`sudo docker ps --filter health=unhealthy` on every controller and restart
those units (*state-changing*, requests in flight on that controller fail):
`sudo systemctl restart kolla-<container>-container.service` (conductor and
scheduler need Placement answering to start). [LAB-VALIDATED: IA-CP-11] Lab: 2026.1, Kolla-Ansible 22.2.0, three
controllers with ProxySQL; one power-loss run.

**Blind spots.** [DOCUMENTED-UNVERIFIED: KA-OPS-19] After a crash `grastate.dat`
reads `seqno: -1` and the role recovers the position from data files
(`Recovered position: <uuid>:<seqno>`). A node whose recovery wrote no such
line gets an empty `seqno`, is skipped by every comparison and can be chosen
itself; the role reads the whole log, so the last line can be from an
earlier run (on the lab, the pre-run line was about 50 minutes old). If the
chosen host's line is missing or older than this run, stop before services
write again.

**Forcing the host.** [DOCUMENTED-UNVERIFIED: KA-OPS-20] *Destructive*:
`kolla-ansible mariadb-recovery -i <inventory> -e mariadb_recover_inventory_name=<mariadb-host>`
skips the `seqno` comparison, writes no `/tmp` file, starts the others with
their own data; everything newer than the named host is lost and nodes ahead
of it normally refuse to join. Use it only when the named host is known to be
the right source (after a restore, with the other nodes emptied: that path is
KA-OPS-14). Not run on its own.

**Cause 2 and time-outs.** [DOCUMENTED-UNVERIFIED: KA-OPS-21] Do not run
`mariadb-recovery` while a node serves data: it restarts every node. Wait for
the state transfer, or find why the node cannot join (network between
controllers, disk space, log). The role waits for the bootstrap node to be
`OPERATIONAL`, then for each joiner; a full transfer of a large database can
take longer. If it times out on a joiner, read `docker logs mariadb` there
for progress before running anything again. **Open point, not resolved:**
this page gives the joiner-port wait as about 10 x 6 s (and 30 x 10 s for
`Synced`); the backup-and-restore page gives about 11 minutes for a joiner's
port (and about 5 minutes for `Synced`). Neither time-out was hit on a lab.

---

## Rotating secrets in passwords.yml

Three cost groups (Kolla-Ansible 2026.1 password rotation guide, which
covers the most common secrets only). Never ask for or quote values.

**Regenerate and apply a first-group secret.** [LAB-VALIDATED: KA-OPS-22]
Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, no HAProxy, Docker;
`glance_keystone_password` and `cinder_database_password` rotated, plus the
`heat_domain_admin_password` manual step, then `kolla-ansible reconfigure -i
<inventory> --tags glance,cinder,heat` (5 min, `failed=0`; Glance listed
images, a volume and a Heat stack were created and deleted). Not run: a full
`reconfigure` without `--tags`, any other secret, multinode, the Ansible Vault
working copy. The source page is a draft.
1. Back up first: `cp /etc/kolla/passwords.yml ./passwords.yml.bak` (keep it
   out of any repository until the rotation is checked).
2. Empty each value to rotate (`foo: "old"` -> `foo:`); *State-changing*:
   `kolla-genpwd -p /etc/kolla/passwords.yml` fills only empty values (lab:
   exactly those, 40 characters). Nothing reaches the platform before a
   `reconfigure`/`deploy`; undo: copy the backup back. With Ansible Vault,
   run it on a plain working copy and re-encrypt.
3. Heat: `openstack user set --domain heat_user_domain --password <new> heat_domain_admin`.
4. *State-changing*: `reconfigure`; containers whose configuration changed restart.

[LAB-VALIDATED: KA-OPS-23] (source page still `draft`) `kolla-ansible stop` without
`--yes-i-really-really-mean-it` exits with `the following arguments are
required: --yes-i-really-really-mean-it` and stops nothing (the guide omits
the flag). Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Docker; not run:
other Kolla-Ansible versions.

**Groups.** [DOCUMENTED-UNVERIFIED: KA-OPS-24]

| Group | Secrets | Applied by | Cost |
|---|---|---|---|
| Reconfigure | `*_keystone_password`, `*_database_password` except `nova_database_password`, `*_ssh_key` except `kolla_ssh_key`, `keystone_admin_password`, `designate_rndc_key`, `keepalived_password`, `libvirt_sasl_password`, `metadata_secret`, `opensearch_dashboards_password`, `osprofiler_secret`, `prometheus_alertmanager_password`, `qdrouterd_password`, `valkey_master_password` | `reconfigure` | changed containers restart |
| Manual step, then reconfigure | `horizon_secret_key`, `grafana_admin_password`, `database_password`, `nova_database_password`, `heat_domain_admin_password` | guide's step each, in order | API may be disrupted from Nova's DB password on |
| Outage | `rabbitmq_cluster_cookie`, `rabbitmq_password` | stop all, rebuild RabbitMQ, `deploy` | all APIs down |
| Not handled | `kolla_ssh_key`, `docker_registry_password` | outside Kolla-Ansible | depends |

Not covered: Fernet and credential keys, TLS certificates, Ceph keyrings,
HashiCorp Vault.

**Manual steps not run.** [DOCUMENTED-UNVERIFIED: KA-OPS-25] *State-changing*,
in the guide's order (it has the exact commands): `horizon_secret_key` as
`newsecret' 'oldsecret`, remove the old one after one to two weeks and
reconfigure again; `grafana_admin_password` with `grafana-cli admin
reset-admin-password` in a Grafana container; `database_password` (MariaDB
`root`) with `SET PASSWORD FOR 'root'@'%' = ...` for every `root` entry;
`nova_database_password` ("From this point onward, API service may be
disrupted"), updating the `cell0` connection with `nova-manage cell_v2
update_cell` from `nova_conductor`. Take a MariaDB backup before rotating
database passwords.

**RabbitMQ secrets.** [DOCUMENTED-UNVERIFIED: KA-OPS-26] *Destructive*, a
planned outage: every API down until `deploy` completes, in-flight messages
lost, running instances keep running. Precondition: window, new values in
`passwords.yml`, backup kept. `kolla-ansible stop -i <inventory>
--yes-i-really-really-mean-it`; on each RabbitMQ node `sudo docker stop
rabbitmq`, `sudo docker rm rabbitmq`, `sudo docker volume rm rabbitmq`; then
`kolla-ansible deploy -i <inventory>` (not `reconfigure`: the containers no
longer exist). Then flush Memcached (*State-changing*, cached tokens
refetched, nothing persistent lost): find address and port with
`sudo grep command /etc/kolla/memcached/config.json` (after `-l` and `-p`),
then `telnet <address> <port>`, `flush_all`, `quit`, on every Memcached host.
