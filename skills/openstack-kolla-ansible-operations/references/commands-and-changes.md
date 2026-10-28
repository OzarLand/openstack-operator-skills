# Commands and changes

`[Addition]` — everything in this file is added by this repository, distilled
from the OzarLand `kolla-ansible-deployment-patterns` repository at commit
`dee2c60` (pages `operations/deploy-reconfigure-upgrade-and-limiting-runs.md`,
`operations/checking-a-deployment-after-a-change.md`,
`operations/bootstrap-servers-what-it-changes-and-its-pitfalls.md`). The book
does not name Kolla-Ansible. Everything here is Kolla-Ansible 2026.1
(`kolla-ansible` CLI, `openstack.kolla` collection `stable/2026.1`); other
versions change commands, variables and defaults. Lab runs were on Docker:
with Podman, replace `docker` (not tested). Untagged technical text is
unverified.

## Contents

- Which command after which change
- A safe sequence for a configuration change
- What a run restarts
- Narrowing a run with --limit and --tags
- bootstrap-servers on a live platform
- Checking a deployment after a change

---

## Which command after which change

Kolla-Ansible: one playbook, `site.yml`; most commands run it with a
different `kolla_action`. Commands read the inventory (`-i`, several
allowed), `/etc/kolla/globals.yml`, `/etc/kolla/passwords.yml` and
`/etc/kolla/config/`. Keep `/etc/kolla` in version control and commit before
each run, so "what changed" has an answer.

| Command | What it does to running containers | Risk |
|---|---|---|
| `prechecks` | Nothing; checks ports, files, variables before a deploy | read-only |
| `genconfig` | Writes config files under `/etc/kolla/<container-config-dir>/` on the hosts; no restart, so not applied yet | state-changing (files) |
| `validate-config` | Validates the generated files; reports under `/var/log/kolla/config-validate` | read-only |
| `check` | Checks container status | read-only |
| `pull` | Downloads images; no container change | read-only for services |
| `deploy` | Writes config, bootstraps what is new (databases, users, endpoints), creates missing containers, restarts containers whose config or definition changed | state-changing |
| `reconfigure` | In most roles the same tasks as `deploy` (`reconfigure.yml` imports `deploy.yml`; checked for Glance, MariaDB, Nova cell only) | state-changing |
| `deploy-containers` | Checks and updates containers without generating config | state-changing |
| `upgrade` | Each role's upgrade tasks: new images, database migrations, rolling restarts where the role supports them | state-changing |
| `post-deploy` | Writes `admin-openrc.sh` on the deploy host | state-changing (local file) |
| `stop` | Stops containers; needs `--yes-i-really-really-mean-it` | state-changing, outage |
| `destroy` | Removes containers and volumes; needs `--yes-i-really-really-mean-it`; `--include-images`, `--include-dev` remove more | *Destructive* |

[DOCUMENTED-UNVERIFIED: KA-CMD-01] Table from `kolla_ansible/cli/commands.py`
and the 2026.1 operating guide. `deploy`, `deploy-containers`, `upgrade`,
`pull`, `check`, `post-deploy`, `stop`, `destroy` were not run on the lab for
this page (`check` was run for *Checking a deployment after a change*). The
rows `prechecks`, `genconfig`, `validate-config`, `reconfigure` were run: see
KA-CMD-03.

Choosing:
- One service's override changed: `reconfigure --tags <service>` (shorter,
  does not apply unrelated pending changes; those stay unapplied until the
  next full run, so know what is pending).
- A full `reconfigure` from time to time, in a maintenance window: proves the
  whole configuration still applies; long; restarts whatever drifted.
- `genconfig` + `validate-config` before applying, to see the files before any
  restart.

Traps the page is written against (none observed):
- a `deploy` "to fix one thing" that also applied every pending change in
  `globals.yml`;
- a newer Kolla-Ansible on the deploy host than the platform's release:
  `deploy` then deploys the new images, an upgrade without the upgrade tasks.
  Keep the deploy host's Kolla-Ansible pinned to the platform's release.

[DOCUMENTED-UNVERIFIED: KA-CMD-02] Choice rules and traps.

## A safe sequence for a configuration change

1. Change `globals.yml` or the override; commit it.
2. Read-only. Kolla-Ansible: `kolla-ansible prechecks -i <inventory>` (or
   `--tags <service>`).
3. *State-changing* (files). Generate and inspect without applying.
   Rewrites the files under `/etc/kolla/<container-config-dir>/` on the
   hosts; running containers keep their configuration until they restart, but
   a container restarted for another reason (host reboot, crash) picks up the
   new files. Undo: revert the change and run `genconfig` again.
   ```bash
   kolla-ansible genconfig -i <inventory> --tags <service>
   kolla-ansible validate-config -i <inventory> --tags <service>
   # on a host, compare with what the container runs:
   sudo docker exec -u root <container> diff /etc/<service>/<file> /var/lib/kolla/config_files/<file>
   ```
   `/var/lib/kolla/config_files/` is the bind mount of the host's
   `/etc/kolla/<container-config-dir>/` (named after the container, e.g.
   `/etc/kolla/glance-api/`); `/etc/<service>/` is what the service runs with.
   The directory is `drwxrwx--- root root` and `docker exec` runs as the
   service user, hence `-u root`; without it `diff` fails with
   `Permission denied`. Most Kolla images have `diff`; not checked for each.
   `validate-config` exits 0 even when it finds errors: read the reports on
   the deploy host, `/var/log/kolla/config-validate/<host>/<project>/<service-name>/*.err`.
   On 2026.1 the Glance report holds two `ERROR` lines for options
   Kolla-Ansible itself sets (`os_glance_tasks_store/filesystem_store_datadir
   is not part of the sample config`, same for `os_glance_staging_store`):
   compare with a report taken before the change.
4. *State-changing*. Apply: `kolla-ansible reconfigure -i <inventory> --tags <service>`.
   Restart scope: see *What a run restarts*. Undo: revert the change and run
   the same command.
5. Verify: the run ends with `failed=0`, the service's containers are
   `healthy` (`docker ps`), a real API call works; then the checks of
   *Checking a deployment after a change*.

[LAB-VALIDATED: KA-CMD-03] (source page still `draft`) Steps 1-5 and the undo, on Glance (`debug = True`
in `/etc/kolla/config/glance.conf`). Lab: 2026.1, Kolla-Ansible 22.2.0,
all-in-one, Docker, ML2/OVS, no HAProxy; `prechecks --tags glance` 15 s,
`genconfig` 10 s (no restart), `validate-config` 23 s, `diff -u root` showed
the change, `reconfigure --tags glance` 76 s restarted `glance_api` only
(healthy 11 s later); undo (override removed, full `reconfigure` without
`--tags`) 647 s, restarted `glance_api` only. Not run: other services,
several hosts, HAProxy enabled, data-plane agents.

## What a run restarts

- `deploy` and `reconfigure` restart a container only when something changed:
  Kolla-Ansible compares each running container with what it should be
  (image, volumes, environment) and runs `kolla_set_configs --check` inside it
  against the new files (`compare_container` in
  `ansible/module_utils/kolla_docker_worker.py`). A `reconfigure` after a
  change in one service's override restarts that service only, even without
  `--tags`; `--tags` saves time and exposure to changes you did not mean to
  apply.
- The run's `changed` count does not count restarts. A full `reconfigure`
  after a Glance override change ended `changed=22` (bootstrap containers of
  5 services, Keystone user registration, Fernet key distribution …) and
  restarted `glance_api` only. Restarts show as `Notify handlers to restart
  containers for <service>` among changed tasks; confirm with
  `docker inspect -f '{{.Name}} {{.State.StartedAt}}'` before and after.

[LAB-VALIDATED: KA-CMD-04] (source page still `draft`) Change-only restarts and how to see them. Lab:
2026.1, Kolla-Ansible 22.2.0, all-in-one, Docker, ML2/OVS, no HAProxy,
`reconfigure` on Glance only. Not run: `deploy`, other roles, several hosts.

Restart scope of `reconfigure --tags <service>`, as the page states it:
- the containers of that service whose configuration changed, **on every
  host where it runs, all at once** (no rolling: see `kolla_serial` below).
  API calls to that service fail briefly;
- data-plane agents (Neutron agents, `nova_compute`, `openvswitch`): say what
  a restart interrupts before running it;
- if the change touches the service's HAProxy frontends (TLS, ports, external
  endpoints), `--tags <service>` also restarts the `haproxy` containers,
  backups first, then the host holding the VIP: every API behind the VIPs is
  briefly interrupted;
- `upgrade`: rolling restarts only where the role supports them.

[DOCUMENTED-UNVERIFIED: KA-CMD-05] Multi-host and HAProxy restart scope (HAProxy
was disabled on the lab; no multi-host run).

## Narrowing a run with --limit and --tags

**`--tags <service>`** selects plays and tasks by tag. Each service's play in
`site.yml` is tagged with its name (`nova`, `neutron`, `keystone`, `mariadb`,
`loadbalancer` …); a service's HAProxy configuration is tagged with the
service name too, so `--tags nova` also updates Nova's frontends in HAProxy.
Fact gathering is tagged `always` and always runs.
[DOCUMENTED-UNVERIFIED: KA-CMD-06]

**`--limit <hosts>`** restricts the hosts, but Kolla-Ansible still gathers
facts for every host (the `gather-facts` play delegates it to the limited
hosts): an unreachable host still fails the run, in task
`Gather facts for all hosts (if using --limit)` (`UNREACHABLE`, rc 4).

[LAB-VALIDATED: KA-CMD-07] (source page still `draft`) Lab: 2026.1, Kolla-Ansible 22.2.0, all-in-one,
Docker, ML2/OVS; `--limit localhost` with an unreachable host in the
inventory. Not run: `--limit` across real hosts.

- The 2026.1 operating guide warns: "using the ansible `--limit` option is not
  recommended", because of known bugs in how `register:` interacts with it
  (bug 2054348; upgrading parts of Nova is the guide's example). Use it where
  upstream does (adding computes, removing hosts, batching
  `bootstrap-servers`); test other uses on a lab. Trap: `--limit` excluding
  the hosts a task delegates to or registers results on.
- **Never** use `--limit` with clustered services so that the cluster's other
  members are out of the play when membership changes (MariaDB, RabbitMQ):
  upstream asks to include all controllers (`--limit control`) when
  controllers are added or removed.

[DOCUMENTED-UNVERIFIED: KA-CMD-08] `--limit` cautions; bug 2054348 not
reproduced.

**`-e kolla_serial=<n or %>`** runs each play in batches of hosts (rolling).
With `reconfigure` and `upgrade`, the 2026.1 CLI appends `-e kolla_serial=0`
after the operator's own `-e` options; Ansible keeps the last value, so a
`kolla_serial` given to these two commands is overridden and the run is
**not** rolling. Observed: `kolla-ansible reconfigure … -e kolla_serial=1`
ran `ansible-playbook` with `-e kolla_serial=1 -e kolla_action=reconfigure -e kolla_serial=0`.

[LAB-VALIDATED: KA-CMD-09] (source page still `draft`) Override seen on the command line. Lab: 2026.1,
Kolla-Ansible 22.2.0, all-in-one, Docker; `reconfigure` only. Not run: the
same with `upgrade` (from the code), any multi-host run.

`kolla_serial` works with `deploy` and `bootstrap-servers` (the bootstrap
servers guide uses it). [DOCUMENTED-UNVERIFIED: KA-CMD-10] No rolling run was
done on a lab.

## bootstrap-servers on a live platform

Kolla-Ansible: `kolla-ansible bootstrap-servers` prepares hosts (roles
`baremetal`, `docker`, `etc_hosts`, `kolla_user`, `packages`,
`apparmor_libvirt`, `journal` of the `openstack.kolla` collection, installed
by `kolla-ansible install-deps`). It is re-run on live platforms for a new
host, a registry or proxy change, before an upgrade, and each rerun can change
hosts and restart Docker. Nothing in this section was run on a lab.

What a run changes (collection 2026.1 defaults):

| What | Variables (default) | Effect |
|---|---|---|
| Host firewall | `disable_firewall` (**true**) | Every run: `ufw` disabled, policy `allow` (Debian/Ubuntu); `firewalld` stopped and disabled (Red Hat family). `false` + `enable_external_api_firewalld: true` to have Kolla-Ansible manage firewalld |
| `/etc/hosts` | `customize_etc_hosts` (true) | One entry per `baremetal` host's API address, on the hosts of the run only; loopback line mapping the host name (other than `localhost`) removed; cloud-init `manage_etc_hosts` false (`/etc/cloud/cloud.cfg.d/99-kolla.cfg`) |
| User | `create_kolla_user` (false), `create_kolla_user_sudoers` (true) | When enabled: `kolla` user with `kolla_ssh_key`, in `sudo` and `docker` (root-equivalent), passwordless sudo |
| Packages | `*_pkg_install`, `*_pkg_removals` | Installs a few tools; **removes** `lxd`, `lxc`, `open-iscsi` (Ubuntu); `libvirt`, `libvirt-daemon`, `iscsi-initiator-utils` (Red Hat), `libvirt-bin` (Ubuntu), the libvirt ones when `enable_nova_libvirt_container` is true |
| Docker packages | `enable_docker_repo`, `docker_apt_package_pin`, `docker_yum_package_pin` (empty) | Docker CE, `state: present`: upgraded on rerun only if pin or repository changes |
| Docker daemon | `docker_registry`, `docker_registry_insecure` (false), `docker_log_max_file` (5), `docker_log_max_size` (`50m`), `docker_custom_config`, `docker_disable_default_iptables_rules` (yes) | `/etc/docker/daemon.json`; proxy drop-in `docker.service.d/kolla.conf`; registry CA under `/etc/docker/certs.d/` |
| systemd | — | `kolla.target` written |
| AppArmor (Ubuntu) | `apparmor_remove_libvirt_profile` | `libvirtd` profile removed |
| Red Hat family | `change_selinux` (true), `selinux_state` (`permissive`) | SELinux permissive; `net.ipv4.ping_group_range`; persistent journal when Fluentd reads it |

[DOCUMENTED-UNVERIFIED: KA-CMD-11] From the guide and collection code; NTP is
not configured by the 2026.1 roles.

**Docker restart = every container of the host.** The `Restart docker`
handler is a full `systemctl restart` (reload only if
`docker_systemd_reload` is true; default false). Triggered by any change to
`daemon.json` (registry, insecure registry, mirrors, log options, storage
driver), to the proxy drop-in, to the registry CA, or a Docker package
upgrade. Registry, mirror and proxy settings reach Docker **only** through
`bootstrap-servers` (not `pull`, `deploy`, `upgrade`), so changing them
always means this restart; a plain-HTTP registry also loses registry
authentication.

*State-changing, outage per batch.* Each run can restart Docker and every
container on the batch's hosts. Keep a quorum of controllers outside each
batch (MariaDB, RabbitMQ). Undo: none for a restart that happened.
```bash
kolla-ansible bootstrap-servers -i <inventory> --limit controller-1,compute-01
kolla-ansible bootstrap-servers -i <inventory> --limit controller-2,compute-02
kolla-ansible bootstrap-servers -i <inventory> --limit controller-3,compute-03
# or plays in batches
kolla-ansible bootstrap-servers -i <inventory> -e kolla_serial=30%
```
Docker `live-restore` keeps containers across a daemon restart; the guide
says issues were reported, use at your own risk. Pin Docker's version; the
guide asks to test any operation that updates Docker.
[DOCUMENTED-UNVERIFIED: KA-CMD-12]

Other pitfalls of a rerun:
- **Firewall off, every run** while `disable_firewall: true`: rules enabled
  since are dropped. Set `false` before any run on managed firewalls.
- **`/etc/hosts` only on the hosts of the run.** A host added with
  `--limit <new-host>` is unknown to the others; for controllers include every
  controller (RabbitMQ needs every controller in every controller's
  `/etc/hosts`).
- **Packages removed**; check your release's lists on hosts with other
  software.
- **Security settings** (AppArmor, SELinux, `kolla` sudo and `docker` group).
- **Facts gathered for every host** even with `--limit`; an unreachable host
  makes the run exit non-zero.

[DOCUMENTED-UNVERIFIED: KA-CMD-13]

*State-changing.* First bootstrap of new hosts (the `kolla` user and the
hosts' virtualenv may not exist yet). Run only on hosts with no workload yet.
Undo: none simple; reinstall the host.
```bash
kolla-ansible bootstrap-servers -i <inventory> -e ansible_user=<bootstrap-user> -e ansible_python_interpreter=/usr/bin/python3
```
[DOCUMENTED-UNVERIFIED: KA-CMD-14] A repository upgrade report avoided
`bootstrap-servers` during an upgrade for its Docker restart and applied a
registry setting by hand with `systemctl reload docker`.

## Checking a deployment after a change

`failed=0` says every task passed, not that the cloud works. Run these,
cheapest first, and keep the output with the change record; compare with the
same checks taken before the change (keep a baseline). All read-only except
step 6.

1. Kolla-Ansible: `kolla-ansible check -i <inventory>` — fails if a container
   that should run is missing, stopped or unhealthy (`service-check` role;
   some roles add probes, e.g. MariaDB through the VIP). Messages:
   `The following <service> containers are missing or not running: <containers>`,
   `The following <service> containers are unhealthy: <containers>`. A failed
   host skips the checks of later roles (lab: `ok=28` vs `ok=36`): read the
   recap, fix, run again. Healthy run 41 s on the lab.
2. Per host: `sudo docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -v 'Up .* (healthy)'`
   — read what remains (no health check, restarting, exited, unhealthy).
3. On one controller:
   `sudo docker exec -it mariadb mariadb -uroot -p -e "SHOW STATUS WHERE Variable_name IN ('wsrep_cluster_size','wsrep_cluster_status','wsrep_local_state_comment');"`
   (`-p` prompts for `database_password`; never paste it; drop `-it` in a
   script) and `sudo docker exec rabbitmq rabbitmqctl cluster_status` (every
   node running, no partitions, no alarms).
4. Any (OpenStack client, admin): `openstack token issue`;
   `openstack endpoint list --interface internal`; `openstack compute service list`;
   `openstack network agent list` (agents alive for ML2/OVS, OVN controllers
   up for ML2/OVN); `openstack volume service list` if Cinder;
   `openstack resource provider list` (one per hypervisor); on a controller
   `sudo docker exec nova_api nova-status upgrade check` (0 passed,
   1 warnings, 2+ failure).
5. Per host: `sudo find /var/log/kolla/ -name '*.log' -newermt '<time of the change>' -exec grep -l -E ' (ERROR|CRITICAL) ' {} +`.
   Keep the trailing slash: `/var/log/kolla` is a symlink to the `kolla_logs`
   volume and without the slash `find` lists nothing (lab: nothing vs 12
   files). It lists files containing any `ERROR`, older lines included: check
   timestamps. One `ERROR` right after a restart can be normal; repeats are not.

[LAB-VALIDATED: KA-CMD-15] Steps 1-5, including `check` failing with
`nova_metadata` stopped (`The following nova containers are missing or not
running: nova_metadata` on `controller-3`). Lab: 2026.1, Kolla-Ansible
22.2.0, 3 controllers + 2 computes, Docker, ML2/OVS, no Cinder; Galera query
run without `-it`. Not run: `volume service list` with Cinder (fails without
it), ML2/OVN, Podman.

6. *State-changing.* One real instance, the only test crossing scheduler,
   placement, network, storage and metadata. Uses quota and a little capacity
   for a few minutes; creates a floating IP only if you test external access.
   Undo: the delete commands.
   ```bash
   openstack server create --flavor <small-flavor> --image <image> --network <network> --wait check-after-change
   openstack server show check-after-change -c status -c addresses -c OS-EXT-SRV-ATTR:host
   openstack console log show check-after-change | tail -20
   openstack floating ip create <external-network>        # only to test external access
   openstack server add floating ip check-after-change <floating-ip>
   openstack floating ip delete <floating-ip>
   openstack server delete --wait check-after-change
   ```
   Console log: cloud-init images end with a `finished` line after reading
   metadata; CirrOS prints `=== datasource: ec2 net ===`, `instance-id: …`.
   Delete the instance even when it failed; keep its fault for the record.

[LAB-VALIDATED: KA-CMD-16] Lab: same as KA-CMD-15; instance `ACTIVE`, CirrOS
0.6.3 console lines seen, floating IP created, attached and deleted. Not run:
access through the floating IP, ML2/OVN.

Targeting what the change touched (administrator action by default policy):
a host with `--availability-zone nova:<host>` (bypasses scheduler filters)
or `openstack --os-compute-api-version 2.74 server create --host <host> …`
(keeps filters, refuses a host that does not fit); a volume back-end with a
boot-from-volume instance; the external network with a floating IP.
[DOCUMENTED-UNVERIFIED: KA-CMD-17]

Typical findings (not observed on the lab): a network agent down after a
network change; `nova-compute` down where `nova_compute` restarted but cannot
reach RabbitMQ; a Galera node not `Synced` after a reboot; `401` from
Keystone on some calls only (Fernet keys differ between Keystone hosts).
