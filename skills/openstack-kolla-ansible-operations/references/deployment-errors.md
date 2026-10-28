# Kolla-Ansible deployment errors

Errors met during `kolla-ansible prechecks`, `pull`, `deploy`, `reconfigure`
or `upgrade`, each with how to recognise it, read-only checks, how to tell its
causes apart, the fixes with their risk, and verification. Everything in this
file is an [Addition] to the book, distilled from the OzarLand
`kolla-ansible-deployment-patterns` repository at commit `dee2c60`
(`deployment-errors/`). Everything here is Kolla-Ansible for OpenStack 2026.1
(lab runs on Kolla-Ansible 22.2.0, Docker, Ubuntu 24.04): container names,
`kolla-*-container.service` units, `/var/lib/docker/volumes/...` and
`/var/log/kolla/...` paths and `kolla-ansible` commands are Kolla-Ansible
specifics, not universal. Podman paths differ and were not covered.

Untagged technical text is unverified. Never paste `passwords.yml` values,
Fernet keys or the Erlang cookie; compare hashes instead.

## Contents

- Reading a failed run
- Index: error text -> section
- "Ansible version should be between ..." (prechecks)
- "Timeout when waiting for <VIP>:61313" (Wait for haproxy to listen on VIP)
- "Some hosts need Fernet key bootstrapping" / Keystone SSH port / "Fernet keys have not been populated"
- "MariaDB cluster exists but is stopped"
- Deploy hangs on MariaDB port liveness: "Got error: 98: Address already in use"
- "The following Nova compute services failed to register themselves"
- "http: server gave HTTP response to HTTPS client" (pull)
- RabbitMQ nodes do not form a cluster
- Deploy fails part-way after Ubuntu upgraded packages during the deploy

## Reading a failed run

[PROPOSED-UNVERIFIED: KA-ERR-01] A reading guide put together from the
output captured on the labs of the pages below; each form was seen on one
page's run, the guide as a whole was not exercised.

- **Failure lines (ansible-core 2.20 output).** `[ERROR]: Task failed: ...`,
  then `Origin: <path to the role file>:<line>`, then
  `fatal: [<host>]: FAILED! => {... "msg": "..."}`. The `msg` is what the
  index below matches; `Origin` names the role and task file.
- **Retries before the failure.** `FAILED - RETRYING: [<host>]: <task> (N
  retries left).` means a wait loop; the failure comes only at the end: about
  200 s for the Nova registration wait (20 × 10 s), three retries in 41 s for
  an image pull, and up to about 55 minutes for the Keystone SSH port wait
  (10 tries of up to 300 s). A delegated task shows both hosts:
  `[compute-03 -> controller-1]`.
- **A handler can be the failing step.** `RUNNING HANDLER [loadbalancer : Wait
  for haproxy to listen on VIP]` runs only when keepalived was restarted.
- **Not every failure stops the run.** When one task fails on some hosts only,
  the run goes on with the other plays and ends with `failed=1` on those hosts
  in `PLAY RECAP` (exit code 2 on the lab). Some failures are expected and
  ignored: in the `mariadb` role, one `Timeout when waiting for search string
  MariaDB in <address>:3306` per host before *Fail on existing but stopped
  cluster*.
- **A hang is not a failure.** A task can sit for many minutes
  (`Wait for first MariaDB service port liveness`, `Wait for MariaDB service
  to be ready through VIP`, the Keystone SSH wait). Look at the containers
  meanwhile; the labs stopped a stuck run with Ctrl-C or
  `pkill -f ansible-playbook` from another session.
- **The cause is often in a container log, not in the Ansible output.**
  `sudo docker ps -a` (exited, restarting, `unhealthy`), then
  `sudo docker logs <container>` and `/var/log/kolla/<service>/`. A container
  shown `Up ... (healthy)` can still be failing and being restarted: read its
  log.
- **The cause can be outside Kolla-Ansible:** the deploy host's Ansible, the
  Docker daemon configuration, the hosting cloud's ports, the host's package
  upgrades. The sections below say which.

## Index: error text -> section

| Error text or symptom (as the operator sees it) | Section |
|---|---|
| `Ansible version should be between 2.19 and 2.20. Current version is ... which is not supported.` | "Ansible version should be between ..." |
| `[Errno 2] No such file or directory: 'ansible-playbook'` | "Ansible version should be between ..." (cause 1) |
| `Timeout when waiting for <internal-vip>:61313` at *Wait for haproxy to listen on VIP* | "Timeout when waiting for <VIP>:61313" |
| `Some hosts (...) need Fernet key bootstrapping, but not all Keystone hosts are in the target list` | Keystone Fernet |
| `FAILED - RETRYING` at *Waiting for Keystone SSH port to be UP*; `fernet-push.sh` failing | Keystone Fernet |
| `keystone` log: `Fernet keys have not been populated`, `Waited for 3 minutes - failing` | Keystone Fernet |
| `MariaDB cluster exists but is stopped. Please start it using kolla-ansible mariadb-recovery` | "MariaDB cluster exists but is stopped" |
| `MariaDB cluster is not synced. Please wait for WSREP sync before proceeding.` | "MariaDB cluster exists but is stopped" (cause 2) |
| Stuck at *Wait for first MariaDB service port liveness*; `mariadb` `Exited (1)`; `Got error: 98: Address already in use` | MariaDB port liveness |
| `The following Nova compute services failed to register themselves: <host>` | Nova compute registration |
| `Possible rename detected, refusing to start!` in `nova-compute.log` | Nova compute registration (cause 3) |
| `http: server gave HTTP response to HTTPS client` (inside `docker.errors.APIError: 500`) | Pull |
| `Hostname has to resolve uniquely to the IP address of api_interface`; timeout at *Waiting for rabbitmq to start*; `cluster_status` lists only some nodes | RabbitMQ |
| Deploy that worked before fails part-way, a container never starts, Galera never forms; `apt` activity in the window | Unattended upgrades |

## "Ansible version should be between ..." (prechecks)

The run stops on the deploy host's own tools; nothing on the OpenStack hosts
changed. The risk is in the fix: installing into the wrong environment.

**Recognize.** `kolla-ansible prechecks` stops at *Checking Ansible version*
(task of `ansible/roles/prechecks/tasks/package_checks.yml`), after the
earlier checks, with `fatal: [localhost]: FAILED!` and `"msg": "Ansible
version should be between 2.19 and 2.20. Current version is 2.18.10 which is
not supported."` (bounds from `ansible_version_min: '2.19'` and
`ansible_version_max: '2.20'`; on the lab the run stopped after 8 s,
`failed=1`). With no `ansible-playbook` in the `PATH` and `kolla-ansible`
called by its full path, it stops at once with `[Errno 2] No such file or
directory: 'ansible-playbook'`. With prechecks skipped, the same problem shows
on any command as a missing module, filter or plugin
(`couldn't resolve module/action`) or unknown syntax; that wording varies by
`ansible-core` version.

[LAB-VALIDATED: KA-ERR-02] (source page still `draft`) Recognition, quick checks and causes 1-2 below.
Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, deploy host on the node,
backend not relevant; not run: cause 3, the missing-module and syntax forms.

**Read-only checks** (deploy host):
- `command -v kolla-ansible ansible-playbook ansible-galaxy`;
  `ansible-playbook --version | head -1`
- `/path/to/venv/bin/pip show kolla-ansible ansible-core | grep -E '^(Name|Version)'`
- `ansible-galaxy collection list 2>/dev/null | grep -E '^#|openstack.kolla|community.docker|ansible.utils|community.general'`

**Tell the causes apart.** Kolla-Ansible runs the bare name
`ansible-playbook` from the `PATH`; 2026.1 requires
`ansible-core>=2.19,!=2.19.0,<2.21`; `kolla-ansible install-deps` installs the
Galaxy collections at user level, shared by every virtual environment of that
user (the last `install-deps` wins).

| Observation | Points to |
|---|---|
| `command -v ansible-playbook` is not in `/path/to/venv/bin/` | 1: virtual environment not active |
| `pip show ansible-core` in the venv gives a version outside 2.19-2.20 | 2: wrong `ansible-core` in the venv |
| Collection versions outside `/path/to/venv/share/kolla-ansible/requirements-core.yml`, or `openstack.kolla` missing / from another release | 3: collections from another release, or none |

`openstack.kolla` is installed from Git (`stable/2026.1` branch); the list
showed it as `openstack.kolla 1.0.0`, which does not name the branch.

**Fix options.**
1. Cause 1: `source /path/to/venv/bin/activate` before any `kolla-ansible`
   command, in every shell, script and scheduled job.
2. Cause 2. *State-changing* (the deploy host's venv only; do it outside a
   running `kolla-ansible` command; undo: install the previous version back):
   `pip install 'ansible-core>=2.19,!=2.19.0,<2.21'` in the activated venv
   (read your release's `requirements.txt`). Without PyPI access it fails with
   `ERROR: No matching distribution found for ansible-core!=2.19.0,<2.21,>=2.19`;
   the lab copied the wheel of 2.20.10 and ran `pip install --no-deps <wheel file>`.
   [LAB-VALIDATED: KA-ERR-03] (source page still `draft`) Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one;
   venv activation and the offline wheel install were run, then `prechecks`
   passed (`failed=0`). Not run: the `pip install` from PyPI.
3. Cause 3. *State-changing* (reinstalls the user's collections with
   `--force`; another release used by the same user sees them too; undo: run
   `install-deps` from the other release's venv): activate the venv, then
   `kolla-ansible install-deps`. To keep two releases apart, use a system user
   per release, or a collections path per environment
   (`ANSIBLE_COLLECTIONS_PATH` or `collections_path`, then
   `ansible-galaxy collection install -r <requirements file> -p <path>`);
   Ansible's mechanism, test it on a lab first.
   [DOCUMENTED-UNVERIFIED: KA-ERR-04]

**Verify.** `command -v ansible-playbook` is the venv's;
`ansible-playbook --version` within range; `kolla-ansible prechecks -i
<inventory>` passes *Checking Ansible version*.

## "Timeout when waiting for <VIP>:61313" (Wait for haproxy to listen on VIP)

**Recognize.** In the `loadbalancer` role, after keepalived and HAProxy were
(re)started: `RUNNING HANDLER [loadbalancer : Wait for haproxy to listen on
VIP]`, then `fatal: [controller-2]: FAILED! => {"changed": false, "elapsed":
301, "msg": "Timeout when waiting for 192.0.2.10:61313"}` (the address is
`kolla_internal_vip_address`, `61313` is `haproxy_monitor_port`). Each host of
the `loadbalancer` group waits 300 s for a TCP connection to it. On the lab
the VIP holder passed (`ok: [controller-3]`), the two others failed; the run
went on and ended `failed=1` on those two. The handler runs only when
keepalived restarts: on the lab a change to HAProxy's configuration alone
restarted HAProxy and ProxySQL, not keepalived, and did not wait on the VIP.
Impact on a running platform: the VIP down or held by several hosts, every
API and service call through it failing or flapping; instances keep running,
but metadata requests (cloud-init) of instances booting meanwhile fail.

[LAB-VALIDATED: KA-ERR-05] (source page still `draft`) Recognition, quick checks and identification of
cause 4. Lab: 2026.1, Kolla-Ansible 22.2.0, 3 controllers (loadbalancer
group, keepalived unicast, ProxySQL) + 2 computes nested in an OpenStack
cloud, failure triggered by `reconfigure --tags loadbalancer` changing
`keepalived_virtual_router_id` with the VIP missing from the allowed address
pairs; not run: causes 1-3, the multicast mode, `tcpdump`.

**Read-only checks** (each `loadbalancer` host):
- `ip -o addr show | grep -w '<internal-vip>'` (exactly one host should list it)
- `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E '^(keepalived|haproxy)\b'`
- `sudo docker logs --tail 50 keepalived` (MASTER, BACKUP or FAULT)
- `sudo ss -ltnp | grep ':61313'` (lists the VIP wherever HAProxy runs,
  holder or not: it says whether HAProxy listens, not who holds the VIP)
- From a non-holder: `ping -c 3 <internal-vip>`;
  `curl -s -o /dev/null -w '%{http_code}\n' http://<internal-vip>:61313/`
  (any HTTP code means HAProxy answered); `ip neigh show <internal-vip>`.
- To see VRRP: `sudo tcpdump -ni <api_interface> vrrp` (expected: one source,
  the MASTER, with the vrid of `keepalived_virtual_router_id`).

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| One host holds the VIP, HAProxy listens, others cannot reach it; lab: `100% packet loss` with `+2 errors`, curl `000`, `ip neigh` `FAILED`, holder answers `200`, one `Entering MASTER STATE` | 4: the network does not deliver traffic to the VIP (hosting cloud port security; or VIP not in the `api_interface` subnet) |
| No host holds the VIP; keepalived `FAULT` / check script failing; `haproxy` restarting | 1: HAProxy not running (invalid config, missing TLS certificate; or `net.ipv4.ip_nonlocal_bind` = `0` with `set_sysctl: false`) |
| VIP on several hosts, each keepalived entered `MASTER` | 2: VRRP advertisements (IP protocol 112, multicast by default) do not pass |
| Advertisements from unexpected sources, VRID/password mismatch, `vrid 51` from foreign addresses | 3: another VRRP cluster uses the same `keepalived_virtual_router_id` (default `51`) |

[DOCUMENTED-UNVERIFIED: KA-ERR-06] Rows 1-3 of the table, the
`ip_nonlocal_bind` variant and the `tcpdump` reading.

**Fix options.**
1. Cause 4, hosting cloud. *State-changing* (the hosting cloud's port, not
   the Kolla deployment; by whoever administers those ports): add the VIP
   (internal, and external if separate) to the allowed address pairs of every
   load balancer host's port:
   `openstack port set --allowed-address ip-address=<internal-vip> <port-id>`.
   On the lab the VIP answered from every host within seconds, without
   restarting anything, and the next `reconfigure` passed. Undo:
   `openstack port unset --allowed-address ip-address=<internal-vip>,mac-address=<port-mac> <port-id>`
   (without `mac-address`, `Port does not contain allowed-address-pair`).
   [LAB-VALIDATED: KA-ERR-07] (source page still `draft`) Lab: 2026.1, Kolla-Ansible 22.2.0, 3
   controllers nested in an OpenStack cloud, unicast; `port set`, the undo
   form and the verification were run. Not run: the wrong-subnet variant.
2. Causes 1-3 and the wrong subnet. [DOCUMENTED-UNVERIFIED: KA-ERR-08]
   - Cause 1: read why HAProxy stops, fix the config or the missing file
     (`kolla-ansible certificates` makes test certificates for a lab only),
     run `kolla-ansible prechecks -i <inventory>`, then
     `kolla-ansible deploy -i <inventory> --tags loadbalancer`.
     *State-changing*: restarts the load balancer containers where config
     changed; on a running platform the VIP moves, API calls fail for a few
     seconds.
   - Cause 2: allow IP protocol 112 between the load balancer hosts on
     `api_interface` (host firewall, hosting cloud's security groups), or set
     `keepalived_traffic_mode: "unicast"` in `globals.yml` (writes a
     `unicast_peer` list; protocol 112 still must pass).
   - Cause 3: set a `keepalived_virtual_router_id` from 1 to 255 that no other
     VRRP cluster uses on that network; coordinate with the other cluster's
     owner.
   - For causes 2 and 3: `kolla-ansible reconfigure -i <inventory> --tags
     loadbalancer`. *State-changing*: keepalived and HAProxy restart, the VIP
     moves once, API calls fail for a few seconds. Undo: the previous value
     and the same command.
   - Wrong subnet: on a first deployment, pick a free address in the
     `api_interface` subnet and deploy again (prechecks catch it only while no
     keepalived container exists); changing the VIP of a running platform
     changes every internal endpoint and is out of scope.
   - `--tags loadbalancer` follows the play tags of 2026.1 `site.yml`; check
     yours.

**Verify.** Exactly one host lists the VIP; `curl ... :61313/` answers from
every host; keepalived: one MASTER, others BACKUP; the run goes past the
handler and ends `failed=0`.

## "Some hosts need Fernet key bootstrapping" / Keystone SSH port / "Fernet keys have not been populated"

Three failures of the `keystone` role. Impact: a Keystone host without keys
fails its API; keys that differ between hosts give random `401` behind the
load balancer. Running instances are not affected.

**Recognize.**
- `TASK [keystone : Fail if any hosts need bootstrapping and not all hosts
  targeted]`: `Some hosts (controller-1) need Fernet key bootstrapping, but not
  all Keystone hosts are in the target list. Stopping as it may be unsafe to
  proceed. Please run without --limit or --serial to bootstrap these hosts.`
  (names only hosts in the run; lab: failed in 49 s, no key touched).
- `FAILED - RETRYING: [controller-3]: Waiting for Keystone SSH port to be UP
  (10 retries left).`, or `Run fernet key distribution` failing on
  `docker exec -t keystone_fernet /usr/bin/fernet-push.sh`. Lab: three
  `RETRYING` lines in about 18 minutes (300 s per try; all 10 would take about
  55 minutes).
- The `keystone` container restarts; its log: `ERROR: Fernet keys have not
  been populated, rechecking in 5 seconds`, then `CRITICAL: Waited for 3
  minutes - failing`. Lab: tokens kept working through the other two hosts.

[LAB-VALIDATED: KA-ERR-09] Recognition, quick checks and the mechanics below.
Lab: 2026.1, Kolla-Ansible 22.2.0, 3 controllers + 2 computes; not run: a
first deployment with `--limit`, `kolla_serial`, `keystone_ssh` stopped, a
different `keystone_ssh_key`.

**Read-only checks** (each Keystone host):
- `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E '^keystone'`
  (`unhealthy` `keystone_fernet` points to cause 2 or 3)
- `sudo docker exec keystone_fernet ls -l /etc/keystone/fernet-keys/` (key `0`
  present, owned by `keystone:keystone`)
- `sudo docker exec keystone_fernet sh -c 'sha256sum /etc/keystone/fernet-keys/*'`
  (compare between hosts; never print the keys)
- `sudo docker exec keystone_fernet /usr/bin/fernet-healthcheck.sh; echo "exit=$?"`
- `nc -zv -w 3 <other-controller-api-address> 8023` (`keystone_ssh_port`)
- Container stopped: `sudo ls -l /var/lib/docker/volumes/keystone_fernet_tokens/_data/`
  (lab: `0` and `1` owned by `42425`)

**Mechanics that matter.** Bootstrap (`fernet_setup`) runs only if no host
runs `keystone_fernet`; under `--limit` or `kolla_serial` it refuses. The push
(`rsync --delete` over SSH, user `keystone`, port 8023) runs once, from **the
first Keystone host in inventory order whose `keystone_fernet` was running**:
the source is chosen by its running container, not by whether it has keys.

| Observation | Points to |
|---|---|
| The bootstrap message | 1: `--limit`/`kolla_serial` while no `keystone_fernet` runs (stopped containers count as not bootstrapped) |
| SSH port wait retrying, `fernet-push.sh` SSH/rsync error, healthcheck exit 1, `nc` timeout | 2: `keystone_ssh` path broken (port blocked, container down, key pair differs) |
| Empty key directory or wrong owner on one host; `keystone` logs the waiting lines | 3: key 0 missing (volume removed or emptied) |

**Fix options.**
1. Cause 1. Check each host's volume first. *State-changing*: start
   `keystone_fernet` **only on hosts whose key directory is not empty**:
   `sudo systemctl start kolla-keystone_fernet-container.service` (2026.1:
   systemd units, not `docker start`; undo: `systemctl stop` of the same unit).
   Then `kolla-ansible deploy -i <inventory> --tags keystone` on every
   Keystone host, without `--limit` or `kolla_serial`.
   [LAB-VALIDATED: KA-ERR-10] Lab: 2026.1, Kolla-Ansible 22.2.0, 3
   controllers; `systemctl start` on the three hosts (then `healthy`) and the
   deploy were run. Not run: a first deployment with `--limit`, `kolla_serial`.
2. Cause 2, blocked port: open `keystone_ssh_port` between the controllers on
   the API network; the waiting deploy continues. Lab: an `iptables` DROP of
   8023 removed during the wait; the next try passed, distribution ran, no
   failure. [LAB-VALIDATED: KA-ERR-11] Lab: 2026.1, Kolla-Ansible 22.2.0, 3
   controllers. Not run: `keystone_ssh` stopped, a differing key pair.
3. Cause 2, `keystone_ssh` down or differing SSH key pair: start
   `keystone_ssh`, use the one `passwords.yml` of the deployment, then run the
   keystone role again (same warning as item 5). [DOCUMENTED-UNVERIFIED: KA-ERR-12]
4. Cause 3. (a) On the host with no keys, if its `keystone_fernet` runs,
   *State-changing*: `sudo systemctl stop kolla-keystone_fernet-container.service`
   so it cannot be the push source (deploy or next cron rotation); undo:
   `systemctl start`. (b) Check another host has a running `keystone_fernet`
   and a full key directory (hashes). (c) `kolla-ansible deploy -i <inventory>
   --tags keystone` (the role picks the source before restarting containers).
   (d) Compare hashes on every host.
   [LAB-VALIDATED: KA-ERR-13] Lab: 2026.1, Kolla-Ansible 22.2.0, 3
   controllers; steps (a)-(d) run, deploy 1.5 minutes, push from
   controller-1, same two hashes on three hosts, healthcheck exit 0, token
   issue 6/6. Not run: a push from an empty host.
5. The deploy of items 1-4 is *State-changing* with no undo if it goes wrong:
   with no `keystone_fernet` running anywhere it runs `fernet_setup`, which on
   an empty repository creates new keys and invalidates every token (whether it
   replaces present keys was not checked); if the push source has an empty key
   directory, every other host's keys are deleted and every Keystone API
   fails. `fernet-rotate.sh` (cron in `keystone_fernet`) ends with the same
   push. Do not copy keys by hand; never run `fernet_setup` on one host of a
   running cluster. [DOCUMENTED-UNVERIFIED: KA-ERR-14]

**Verify.** Same key hashes on every host; `fernet-healthcheck.sh` exit 0;
`openstack token issue` and `openstack project list` several times in a row.

## "MariaDB cluster exists but is stopped"

**Recognize.** After every controller was down at the same time (power loss,
all rebooted, every `mariadb` container stopped), any `deploy`, `reconfigure`
or `upgrade` stops in the `mariadb` role, on every MariaDB host:
`TASK [mariadb : Fail on existing but stopped cluster]`, `MariaDB cluster
exists but is stopped. Please start it using kolla-ansible mariadb-recovery`
(`Origin: .../roles/mariadb/tasks/lookup_cluster.yml`). Earlier in the run,
one ignored `Timeout when waiting for search string MariaDB in <address>:3306`
per host is expected. The APIs answer `Bad Gateway (HTTP 502)`. The task fires
when the inventory has more than one MariaDB host, every host has a `mariadb`
volume, and none answers on the MariaDB port. Running instances keep running;
no data is lost yet, the risk is in recovering the wrong way.

[LAB-VALIDATED: KA-ERR-15] Recognition and read-only checks. Lab: 2026.1,
Kolla-Ansible 22.2.0, 3 controllers (Galera behind ProxySQL) + 2 computes,
Docker, the three `mariadb` containers stopped cleanly together with
`systemctl`, then `reconfigure --tags mariadb`; not run: a crash
(`seqno: -1`), cause 2.

**Read-only checks.**
- Each MariaDB host: `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -w mariadb`;
  `sudo cat /var/lib/docker/volumes/mariadb/_data/grastate.dat` (`seqno`,
  `safe_to_bootstrap`); `sudo tail -n 50 /var/log/kolla/mariadb/mariadb.log`.
- From the deploy host: `nc -zv -w 3 <controller-api-address> 3306`.
- Lab (clean stop): `Exited (0)` everywhere, a `seqno` on every node,
  `safe_to_bootstrap: 1` only on the highest `seqno` (the last to stop),
  `Connection refused`. After a crash, `grastate.dat` reads `seqno: -1`.

**Tell it apart.**
| Observation | Points to |
|---|---|
| No node answers on 3306; this message | Cause 1: the whole cluster stopped; one node must be bootstrapped from the highest `seqno` |
| One node answers but is not `Synced`; the roles fail earlier with `MariaDB cluster is not synced. Please wait for WSREP sync before proceeding.` | Cause 2: look at that node first (`SHOW STATUS LIKE 'wsrep_%'`, state transfer, network, disk) |

[DOCUMENTED-UNVERIFIED: KA-ERR-16] Cause 2: its message and the rule *do not
run `mariadb-recovery` while a node is serving data* (it restarts every node).

**Procedure.** For cause 1 the procedure (save every node's data first, then
`kolla-ansible mariadb-recovery`, *Destructive*, then check which host was
chosen) is in host-and-database-operations.md, section *Recovering a stopped
Galera cluster (mariadb-recovery)*. It needs a named owner.

## Deploy hangs on MariaDB port liveness: "Got error: 98: Address already in use"

Single node with `enable_haproxy: "no"` and `kolla_internal_vip_address` equal
to the node's own address: ProxySQL (on by default, `enable_proxysql: "{{
enable_mariadb }}"`, already on in 2025.1) listens on the VIP port 3306,
MariaDB on `api_interface_address` port 3306, the same socket. The
`loadbalancer` role (enabled if any of HAProxy, keepalived, ProxySQL is) runs
first, so ProxySQL takes the port.

**Recognize.**
- First deploy: stuck at `RUNNING HANDLER [mariadb : Wait for first MariaDB
  service port liveness]` until timeout; `mariadb` `Exited (1)`; log:
  `Can't start server: Bind on TCP/IP port. Got error: 98: Address already in
  use`. `prechecks` passed (nothing listened on 3306 yet).
- Already-deployed node with ProxySQL turned on again: `proxysql.log` shows
  `bind() error for <node-address>:3306: Address already in use` while
  `proxysql` is reported `healthy`; the deploy sat on `Wait for MariaDB service
  to be ready through VIP` for 11 minutes (not traced why); MariaDB keeps
  running until its next restart, then exits with error 98, and ProxySQL
  answers the services with `Access denied for user 'nova'@'<node-address>'`.
- A `haproxy` container running although `enable_haproxy` is `"no"` is part
  of the signature (observed, not traced in the source).

[LAB-VALIDATED: KA-ERR-17] Recognition and read-only checks. Lab: 2026.1,
Kolla-Ansible all-in-one, Ubuntu 24.04, Docker, already deployed, ProxySQL
re-enabled; not run: multinode, Podman. The first-deploy form comes from an
earlier build whose date the page records inconsistently (2026-10-21 in the
body, captures of 2026-10-26 in its lab record).

**Read-only checks** (on the node):
- `sudo ss -ltnp | grep ':3306'` (this problem: `proxysql` on the node's
  address; anything else, e.g. a host MariaDB or MySQL, is cause 2, out of
  scope: stop or remove that service)
- `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E 'mariadb|proxysql|haproxy|keepalived'`
- `sudo tail -n 20 /var/lib/docker/volumes/kolla_logs/_data/mariadb/mariadb.log`
- `grep -E '^(enable_haproxy|enable_keepalived|enable_proxysql|kolla_internal_vip_address)' /etc/kolla/globals.yml`

**Fix options.**
1. Stop the deploy (Ctrl-C or `pkill -f ansible-playbook`), set
   `enable_proxysql: "no"` in `/etc/kolla/globals.yml` (with
   `enable_haproxy: "no"` and the node address as VIP). *State-changing*:
   `sudo docker rm -f proxysql haproxy mariadb` removes the containers, not
   the volumes; on a deployment that already ran it is a database outage for
   every service on the node until the next deploy. Precondition: the setting
   above, and the right node. Undo: the next deploy recreates them. Then
   `kolla-ansible prechecks -i <inventory>` and `kolla-ansible deploy -i
   <inventory>`. **On a deployment that already ran, keep the `mariadb`
   volume**: the deploy found the existing cluster (`Establish whether the
   cluster has already existed`, `Restart MariaDB container`) and kept the
   data.
   [LAB-VALIDATED: KA-ERR-18] Lab: 2026.1, Kolla-Ansible all-in-one,
   already deployed; the setting, `docker rm -f`, prechecks, deploy
   (`failed=0` in 11.5 minutes) and verification run. Not run: the volume
   removal of item 2.
2. **Only on a fresh deployment that never completed.** *Destructive*:
   `sudo docker volume rm mariadb` deletes the MariaDB data volume; on any
   other deployment it deletes every OpenStack database. Check first that
   `sudo docker ps -a` lists only what the failed deploy created and that this
   is the right node. Cannot be undone. [DOCUMENTED-UNVERIFIED: KA-ERR-19]
3. Leftovers. *State-changing* (precondition: `enable_proxysql: "no"` set and
   the containers removed; undo: a deploy with them enabled recreates them):
   `sudo systemctl disable --now kolla-proxysql-container.service kolla-haproxy-container.service`;
   `sudo rm /etc/systemd/system/kolla-proxysql-container.service /etc/systemd/system/kolla-haproxy-container.service`;
   `sudo systemctl daemon-reload`; `sudo systemctl reset-failed`;
   `sudo docker volume rm proxysql proxysql_socket haproxy_socket`. The
   alternative to all this: keep ProxySQL with HAProxy and keepalived on and a
   separate unused address as VIP (the multinode layout).
   [DOCUMENTED-UNVERIFIED: KA-ERR-20]

**Verify.** `sudo ss -ltnp | grep ':3306'`: `mariadbd` only;
no `proxysql` or `haproxy` container, `mariadb` `Up (healthy)`;
`sudo docker exec -it mariadb mariadb -uroot -p -e "SHOW STATUS LIKE
'wsrep_local_state_comment';"` gives `Synced` (prompts for
`database_password`); the deploy ends `failed=0`.

## "The following Nova compute services failed to register themselves"

**Recognize.** `kolla-ansible deploy` (often `--limit` on a new compute)
retries `TASK [nova-cell : Waiting for nova-compute services to register
themselves]` 20 times, 10 s apart (about 200 s), then `TASK [nova-cell : Fail
if nova-compute service failed to register]`: `The following Nova compute
services failed to register themselves: compute-1`. The name is the host's
`ansible_facts.nodename` (may be a full name); on multinode the retry lines
read `[compute-03 -> controller-1]`. The host is not added to Nova; other
hosts are not failed unless `nova_compute_registration_fatal` is true. The wait
and `discover_hosts` run once per batch on its first compute: if that one
failed, discovery is skipped for every new compute of the run. A compute that
registered earlier and is now `down` does not produce this error.

[LAB-VALIDATED: KA-ERR-21] (source page still `draft`) Recognition, quick checks and the cause 3 rename
variant. Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, ML2/OVS (`host =`
injected in `/etc/kolla/config/nova/nova-compute.conf` after deleting the
host's instance and compute service; run failed after 20 retries, 9 min);
not run: causes 1 and 2; the multinode delegation output and the batch-wide
discovery skip described above come from the code, not from this run.

**Read-only checks.**
- `openstack compute service list --service nova-compute` (under which names?)
- `ansible -i <inventory> compute-03 -m setup -a 'filter=ansible_nodename'`
- On the compute: `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E 'nova_compute|nova_libvirt|nova_ssh'`;
  `sudo tail -n 100 /var/log/kolla/nova/nova-compute.log`;
  `sudo docker logs --tail 50 nova_compute`

**Tell the causes apart** (in `nova-compute.log`).
| Observation | Points to |
|---|---|
| `Possible rename detected, refusing to start!` (`My node <uuid> has host 'compute-1' but my host is '...'`), while `docker ps` shows `nova_compute` `Up ... (healthy)` (restarted after each exit) | 3: rename; the node UUID in `/var/lib/nova/compute_id` still points to the old name, even after the old service was deleted |
| Service up under another name in `compute service list` | 3: `host =` override, or a fact cache from before a rename |
| `Connection to libvirt failed` | 1: `nova_libvirt` down, or a host libvirt holds `/run/libvirt/libvirt-sock` |
| `AMQP server on <address>:5672 is unreachable`, `Trying again in N seconds`, TLS errors | 2: compute cannot reach RabbitMQ (firewall, `network_interface`, MTU, CA) |

Placement or Keystone errors do **not** cause this failure: such a compute
registers and passes the wait, but gets no resource provider (another
problem). [DOCUMENTED-UNVERIFIED: KA-ERR-22] Rows for causes 1 and 2 and the
Placement statement (from the order of `Service.start()`; not run).

**Fix options.** Then re-run the same deploy (idempotent; waits again and runs
discovery).
1. Cause 3: remove the `host =` override and deploy again. *State-changing*
   (restarts the compute containers and registers the host).
   [LAB-VALIDATED: KA-ERR-23] (source page still `draft`) Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one,
   ML2/OVS; override removed, `deploy --tags nova` (no `--limit` on an
   all-in-one): `Discover nova hosts` ran, `failed=0`, 5 min. Not run: a
   fact-cache clear, deleting a wrongly named record, `--limit <compute>`.
2. Other fixes. [DOCUMENTED-UNVERIFIED: KA-ERR-24]
   - Cause 1, with the containerised libvirt (default): `systemctl list-units
     --all 'libvirtd*' 'virtqemud*'` (read-only), then *State-changing* (stops
     any VM the host libvirt runs; none expected on a new compute; undo:
     `systemctl enable --now` on the same units):
     `sudo systemctl disable --now libvirtd.service libvirtd.socket libvirtd-ro.socket libvirtd-admin.socket`,
     then `kolla-ansible prechecks -i <inventory> --limit <compute>`. The
     precheck tests the socket only while no `nova_libvirt` container exists;
     otherwise check `ls -l /run/libvirt/libvirt-sock`. With
     `enable_nova_libvirt_container: false` the host libvirt is intended:
     look at it instead.
   - Cause 2: open the path from the compute to every controller's RabbitMQ
     port on the `api_interface` network; check the MTU end to end.
   - Cause 3: clear a stale fact cache after a rename. A wrong service record:
     *State-changing*, cannot be undone, deletes its compute node record:
     check `openstack server list --all-projects --host <wrong-name>` is
     empty, then `openstack compute service delete <service-id>`. Nova refuses
     while the host has instances (`409 ... Unable to delete compute service
     that is hosting instances`); on the lab the refusal also came right after
     the last instance was deleted and the same command passed about 20 s
     later.
   - Then `kolla-ansible deploy -i <inventory> --limit <compute>`.

**Verify.** `openstack compute service list --service nova-compute --host
<node-name>` `up`, `enabled`; `openstack hypervisor list` lists it; the run
passes the wait with `failed=0`.

## "http: server gave HTTP response to HTTPS client" (pull)

**Recognize.** `kolla-ansible pull` (or `deploy`, `upgrade`) fails on the
first image, on every host; `globals.yml` has a plain-HTTP `docker_registry`
and `docker_registry_insecure: true`. Lab form: `FAILED - RETRYING:
[localhost]: Pull images for kolla_toolbox (3 retries left).`, then after 41 s
`docker.errors.APIError: 500 Server Error for http+docker://localhost/...`
... `Head "https://<registry-host>:4000/v2/...": http: server gave HTTP
response to HTTPS client`, `failed=1`. Nothing running is affected.

`docker_registry_insecure` reaches the Docker daemon only through
`kolla-ansible bootstrap-servers`; `pull`, `deploy` and `upgrade` do not apply
it. So it appears when the registry or the setting changed after the last
`bootstrap-servers` (e.g. a new local registry for an upgrade). An HTTPS
registry with an untrusted CA gives a certificate error instead (out of scope).

[LAB-VALIDATED: KA-ERR-25] Recognition, quick checks, diagnosis. Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, Ubuntu 24.04, Docker (met during a 2025.1 to
2026.1 upgrade, reproduced by emptying `insecure-registries`); not run: the
other triggers (setting added later, host added without `bootstrap-servers`).

**Read-only checks.** `sudo docker info | grep -A5 'Insecure Registries'`;
`sudo cat /etc/docker/daemon.json`;
`grep -E '^(docker_registry|docker_registry_insecure)' /etc/kolla/globals.yml`.
Confirmed when `globals.yml` names the registry as insecure but neither
`docker info` nor `daemon.json` lists it.

**Fix options** (every host that pulls).
1. By hand. *State-changing* (Docker daemon configuration): add
   `"insecure-registries": ["<registry-host>:<port>"]` to
   `/etc/docker/daemon.json`, keeping the other keys, then
   `sudo systemctl reload docker` and check `docker info`. A reload applied it
   with no container restarted (31, then 40 containers kept running);
   `systemctl restart docker` restarts every container. Undo: remove the
   entry from the list and reload; deleting the whole key does not work (the
   reload keeps the previous list). Then `kolla-ansible pull -i <inventory>`.
   [LAB-VALIDATED: KA-ERR-26] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one,
   Docker; edit, reload, `pull --tags common` (`failed=0` in 25 s) and the
   key-deletion behaviour run. Not run: a full `pull`.
2. With Kolla-Ansible: `kolla-ansible bootstrap-servers -i <inventory>`.
   *State-changing*: can restart Docker and every container on the host; limit
   with `--limit`, `-e kolla_serial=...` or Docker's `live-restore`; on a
   running platform use a maintenance window or the manual way.
   [DOCUMENTED-UNVERIFIED: KA-ERR-27]

**Verify.** `docker info` lists the registry on every host;
`kolla-ansible pull -i <inventory>` ends `failed=0`.

## RabbitMQ nodes do not form a cluster

[DOCUMENTED-UNVERIFIED: KA-ERR-28] This whole section was written from the
Kolla-Ansible 2026.1 code and RabbitMQ's documentation and not reproduced on a
lab. RabbitMQ and Erlang log lines are described, not quoted.

**Recognize** (first deployment, controller added or reinstalled, or
`passwords.yml` changed):
- `prechecks`: `Hostname has to resolve uniquely to the IP address of
  api_interface` (task *Check if each rabbit hostname resolves uniquely to the
  proper IP address*);
- `deploy` fails or times out at *Waiting for rabbitmq to start*
  (`rabbitmqctl wait --timeout 60`), or `rabbitmq` restarts in a loop;
- the deploy passes but `rabbitmqctl cluster_status` lists only itself or not
  all controllers; services log AMQP errors. Impact: RPC timeouts, instances
  stuck in `BUILD`, agents down; with `pause_minority` (Kolla default) a
  minority pauses itself.

**Read-only checks** (each RabbitMQ host):
- `sudo docker exec rabbitmq rabbitmqctl cluster_status`
- `hostname -s`; `getent ahostsv4 "$(hostname -s)"` (`ahostsv6` with IPv6)
- `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -w rabbitmq`;
  `sudo ls /var/log/kolla/rabbitmq/`; the `rabbit@<short-name>.log` there or
  `sudo docker logs --tail 50 rabbitmq`
- `nc -zv -w 3 <other-controller-api-address> 4369` and `... 25672`
- `sudo docker exec rabbitmq env | grep RABBITMQ_CLUSTER_COOKIE | sha256sum`
  (compare hashes between hosts; never paste the cookie)

Nodes are `rabbit@<short host name>`, listed statically in `rabbitmq.conf`,
authenticated with `rabbitmq_cluster_cookie`, talking on 4369 and 25672 on the
`api_interface` address.

| Observation | Points to |
|---|---|
| `getent` on a host does not return exactly its `api_interface` address (e.g. an extra loopback line in `/etc/hosts`); `nxdomain` in the log | 1: name resolution |
| `nc` fails; log shows timeouts or refusals to other nodes | 2: Erlang ports closed |
| Cookie hashes differ; log shows authentication refusals | 3: different cookie (another `passwords.yml`, cookie changed outside the rotation procedure) |
| `cluster_status` lists members that no longer exist, or others list this node as stopped; "inconsistent cluster" | 4: old cluster state (reinstalled/renamed controller, old volume) |

**Fix options.** [DOCUMENTED-UNVERIFIED: KA-ERR-29]
1. Cause 1. *State-changing* (host name resolution; undo: restore the copy):
   `sudo cp /etc/hosts /etc/hosts.before-rabbitmq-fix`, `sudoedit /etc/hosts`,
   then `getent ahostsv4 "$(hostname -s)"` shows only the API address
   (`bootstrap-servers` writes entries when `customize_etc_hosts`). Check
   inside the container (`sudo docker exec rabbitmq getent ahostsv4
   <short-name>`): it may keep its old copy. If so, *State-changing*, one
   host at a time, only while the other nodes form a healthy cluster: `sudo
   docker rm -f rabbitmq` on the host, then `kolla-ansible deploy -i
   <inventory> --tags rabbitmq --limit <host>` (data stays in the volume;
   services reconnect to the other nodes). Then `prechecks` and the failed
   run again without `--limit`.
2. Cause 2: open TCP 4369, 25672 and the AMQP port (5672, or 5671 with TLS)
   between the RabbitMQ hosts on the API network; deploy again.
3. Cause 3: use the one `passwords.yml` for every run; a deliberate cookie
   change means finishing the password rotation procedure (an outage).

**Cause 4: reset the stale node.** [DOCUMENTED-UNVERIFIED: KA-ERR-30]
*Destructive*: removes this node's queues, messages and view of the cluster;
messages queued only there are lost. Precondition: the other nodes form a
healthy cluster, and you are on the stale node. Cannot be undone; save the
definitions first (messages in flight cannot be saved):
```
sudo docker exec rabbitmq rabbitmqctl export_definitions /tmp/definitions-before-reset.json
sudo docker cp rabbitmq:/tmp/definitions-before-reset.json .
sudo docker exec rabbitmq rabbitmqctl stop_app
sudo docker exec rabbitmq bash -c 'rabbitmqctl force_reset || rabbitmqctl reset'
sudo docker exec rabbitmq rabbitmqctl start_app
sudo docker exec rabbitmq rabbitmqctl await_online_nodes <number of rabbitmq hosts>
```
(`force_reset` first as Kolla's `reset-state.yml` does; with Khepri, the
default from RabbitMQ 4.2, it is refused (`Forced reset is unsupported with
Khepri`) and `reset` runs.) A controller renamed or replaced
**under a new name**, still listed as stopped: *Destructive* (queues whose only
replica was on it are lost; the old node must be gone for good and not
running; no undo), from one healthy node:
`sudo docker exec rabbitmq rabbitmqctl forget_cluster_node rabbit@<old-short-name>`.
**If the replacement reuses the old name, do not forget it: reset that node
as above instead.** `kolla-ansible rabbitmq-reset-state` resets every node at
once: a full messaging outage, not for one bad node.

**Verify.** `cluster_status` on each host lists every `rabbit@<controller>`
running, no partitions, no alarms; the run passes *Waiting for rabbitmq to
start* with `failed=0`; `openstack network agent list` and
`openstack compute service list` show agents alive.

## Deploy fails part-way after Ubuntu upgraded packages during the deploy

**Recognize.** A deploy that worked before fails part-way on some hosts with
no configuration change: containers created but never started or
restarting, MariaDB never forming its Galera cluster (the deploy times out on
the MariaDB tasks), systemd re-executed and units restarted during the run.
Met once on a 3-controller + 2-compute lab build (two hosts of five, 178
packages upgraded during the deploy). The stock Ubuntu cloud images enable
unattended upgrades; `apt-daily-upgrade.timer` fires daily with a random
delay; a `libc6`/`systemd` upgrade re-executes systemd, and `needrestart`
restarts services using upgraded libraries, Kolla's container units included.
`bootstrap-servers` (2026.1) does not change these settings.

[LAB-VALIDATED: KA-ERR-31] Quick checks and the restart behaviour. Lab:
2026.1, Kolla-Ansible 22.2.0 all-in-one, Ubuntu 24.04 cloud image with 195
pending updates: a manual `unattended-upgrade` during `deploy --tags mariadb`
showed `Reexecuting` twice, `Stopping kolla-mariadb-container.service`,
`containerd` restarted, 39 of 40 containers restarted within three minutes
and all came back (the deploy had ended 53 s earlier). Not run: the Galera
failure across several controllers.

**Read-only checks** (each failed host):
- `grep -E "^Start-Date|^Commandline|^Upgrade" /var/log/apt/history.log | tail -30`
- `systemctl list-timers apt-daily.timer apt-daily-upgrade.timer`
- `cat /etc/apt/apt.conf.d/20auto-upgrades`
- `journalctl --since "<deploy start>" | grep -iE "reexecut|Reloading|unattended-upgrade" | head`

| Observation | Points to |
|---|---|
| `Upgrade:` lines (`libc6`, `systemd`, base packages) in the window under `Commandline: /usr/bin/unattended-upgrade` | unattended upgrade during the deploy |
| Same, with `Commandline: apt upgrade` and a user | a manual upgrade by someone else |
| `apt-get install` lines from `bootstrap-servers` (it upgraded `dpkg`, `libbz2-1.0` on a lab) | expected; not the cause |
| No apt activity in the window | Galera failed for another reason (disk, network, clock) |

**Prevent it before deploying.** *State-changing*: disables automatic security
updates; fine for a short-lived lab, on a long-lived platform schedule
upgrades in maintenance windows instead (a policy decision).
```
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer
while systemctl is-active --quiet apt-daily.service apt-daily-upgrade.service; do sleep 10; done
systemctl list-jobs | grep -E "apt-daily" || echo "no apt run queued"
```
Never kill a `dpkg` run half-way; wait for it.
[LAB-VALIDATED: KA-ERR-32] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one,
Ubuntu 24.04; run as written, `no apt run queued`. Not run: Debian or Rocky
hosts.

**Recover a failed deploy** (not tried on the multinode lab; it was rebuilt).
[DOCUMENTED-UNVERIFIED: KA-ERR-33]
1. Let any running upgrade finish.
2. If the platform holds data and the cluster really lost quorum (no node
   `Primary`, or every `mariadb` down) and no deploy, upgrade or apt run is in
   progress: recover Galera with `kolla-ansible mariadb-recovery`,
   *Destructive* (transactions only on the nodes not chosen are lost; APIs
   down while it runs; copy each node's stopped data volume aside and note
   each `seqno` first; undo only by restoring the copies). Procedure:
   host-and-database-operations.md, *Recovering a stopped Galera cluster
   (mariadb-recovery)*.
3. Re-run the failed deploy, reconfigure or upgrade. *State-changing*:
   restarts containers on every host it touches.

**Verify.** Timers inactive or scheduled in a chosen window;
`sudo docker ps --filter "status=restarting" --format '{{.Names}}'` empty on
every host; `wsrep_cluster_size` equals the number of controllers and
`wsrep_cluster_status` is `Primary` (use the `mariadb` client with `sudo`:
`mysql` is not in the 2026.1 MariaDB 11.4 image).
