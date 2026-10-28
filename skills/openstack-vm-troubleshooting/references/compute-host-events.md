# Compute host events

What instances see when something happens to their compute host: the Nova
agent stops, the host reboots, a host service is restarted, a live migration
does not converge, pinned CPUs show steal, the host clock drifts.
Everything in this file is an [Addition] to the book, distilled from the
`recovery/`, `lifecycle/`, `migration/` and `diagnostics/` pages of OzarLand
openstack-vm-runbooks at commit `babdd8c07971`. Lab evidence comes from
OpenStack 2026.1 deployed with Kolla-Ansible 22.2.0 (Docker, Ubuntu 24.04,
ML2/OVS, local instance disks); each tag says which lab and which steps were
not run. Nothing here was run on OVN, Ceph, Podman, another release or
another deployment tool.

## Contents

- nova-compute down, host alive
- After a compute reboot
- Restarts that keep instances running
- Live migration never completes
- CPU steal on pinned instances
- Clock skew
- Host failure and planned maintenance

## nova-compute down, host alive

**The safety point.** "Compute down" in Nova means Nova has heard nothing
from the host's `nova-compute` agent for `service_down_time` seconds (default
60). It does not mean the host is dead. A host that answers (ping, TCP 22, a
login as another user, the console) while its agent is down is alive, and its
instances run on. Evacuating it, by hand or by automation reacting to a lost
heartbeat, would rebuild each instance elsewhere while the original still
runs, both writing to the same volumes or ports: that corrupts data. An SSH
authentication failure says nothing about liveness; only a failure at the TCP
level does. **Never evacuate a host that answers**; evacuation needs the host
fenced first (see the last section).
[DOCUMENTED-UNVERIFIED: VM-HOST-01]

**Recognize.** `openstack compute service list --service nova-compute` shows
the host `down`; its instances still answer on the network and stay `ACTIVE`,
power state Running, in Nova; the host answers ping and SSH. Nova cannot act
on those instances (start, stop, reboot, resize, migration, console) and does
not schedule new ones there while the service is down. A variant: the SSH
user of your monitoring or automation is also refused on that host
(`Permission denied (publickey)`), so your tools cannot read it either; that
is a second, independent fault (below).

**Read-only checks.**
- Controller: `openstack compute service list --service nova-compute --long`
  (since when; `Forced Down` `True` means someone marked it down on purpose,
  the step that precedes an evacuation: find out who and why first);
  `openstack server list --all-projects --host <compute-host> --long -c ID -c Status -c "Power State"`.
- Compute, Kolla-Ansible:
  `docker ps -a --filter name='^nova_compute$' --filter name='^nova_libvirt$' --format '{{.Names}}\t{{.Status}}'`,
  `systemctl is-active kolla-nova_compute-container.service` (`inactive` or
  `failed`: both mean stopped), `docker exec nova_libvirt virsh list --all`.
  Any: `systemctl is-active nova-compute libvirtd`, `virsh list --all`.
- This section applies when the host answers, `nova_compute` is not running,
  `nova_libvirt` runs and `virsh list` shows at least one domain `running` or
  `paused`. A domain paused on an I/O error counts as running: it keeps its
  QEMU process and disk locks (see *Compute disk full* in
  instance-lifecycle.md).

[LAB-VALIDATED: VM-HOST-02] Recognition and the checks above, with the
signature service `down` about a minute after the agent stopped, container
`Exited (137)`, unit `failed`, domains `running` in `virsh`, instance
`ACTIVE`/Running in Nova. Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS (VXLAN),
local instance disks, agent container stopped on purpose (page body: 3
controllers + 2 computes; its lab record: all-in-one). Not run: the real
causes below, the Any commands, a paused domain at the same time.

**Why the agent stopped** (on the compute, before or right after starting it):
Kolla-Ansible:
`docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} finished={{.State.FinishedAt}}' nova_compute`,
`journalctl -u kolla-nova_compute-container.service --since -2h --no-pager | tail -n 50`,
`grep -E 'ERROR|CRITICAL|AMQP|MessagingTimeout' /var/log/kolla/nova/nova-compute.log | tail -n 20`.
Any: `journalctl -u nova-compute`, `/var/log/nova/nova-compute.log`. Both:
`journalctl -k --since -2h --no-pager | grep -i -E 'out of memory|oom-kill|killed process'`.
Exit code 137 is SIGKILL: the OOM killer (`oom=true`) or the container engine
after a stop that did not finish in time.

| Observation | Points to |
|---|---|
| Exited with an error code, traceback at the end of `nova-compute.log` | crash |
| `OOMKilled` `true`, `oom-kill` in the kernel log | killed for lack of memory |
| Exited cleanly or 137 at the time of a change; unit `inactive` or `failed` | stopped and not started again (maintenance, failed restart after an upgrade) |
| Container `Up`, AMQP or `MessagingTimeout` errors, no state report | agent cut off from RabbitMQ |

In every case the fix is the agent, never an evacuation.
[DOCUMENTED-UNVERIFIED: VM-HOST-03]

**Fix.**
1. Prove the instances run first (`virsh list --all`, or the console of a few).
2. *State-changing*: start the agent. Kolla-Ansible:
   `sudo systemctl start kolla-nova_compute-container.service`; Any:
   `sudo systemctl start nova-compute`. Running instances are not touched; on
   start the agent reconciles power states and cleans up the domains of
   instances deleted or evacuated while it was down. Undo: stop the unit (not
   useful). Then fix what stopped it.
   [LAB-VALIDATED: VM-HOST-04] Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS,
   local disks; start through the unit brought the service `up`, whole undo
   (including a test-instance delete) 34 s. Not run: the Any command, cleanup
   of instances deleted or evacuated meanwhile.
3. Agent `Up` but cut off from RabbitMQ: *State-changing*: restart it instead
   (`sudo systemctl restart kolla-nova_compute-container.service`; Any:
   `sudo systemctl restart nova-compute`). Running instances are not touched;
   a build or migration in progress on the host can fail and need a retry.
   [DOCUMENTED-UNVERIFIED: VM-HOST-05]

Deleting an instance while its compute service is down removes it from the
database only ("local delete"); the domain keeps running until `nova-compute`
returns and cleans it up (see *Stale records* in instance-lifecycle.md).
[DOCUMENTED-UNVERIFIED: VM-HOST-06]

**SSH refused as well.** From the monitoring host:
`ssh -v -o BatchMode=yes -o ConnectTimeout=5 <monitoring-user>@<compute-host> true 2>&1 | tail -n 5`.

| Last lines | Meaning |
|---|---|
| `Connection timed out`, `No route to host` | not reached at TCP level: the host may be down or cut off; see the last section |
| `Connection refused` | host up, nothing listening on 22 (sshd stopped) |
| `Permission denied (publickey)` after the key exchange | host up, sshd up, this user refused |

Then, logged in as an accepted administrator (or on the console):
`sudo sshd -T | grep -i -e '^denyusers' -e '^allowusers' -e '^denygroups' -e '^allowgroups'`,
`ls -la /etc/ssh/sshd_config.d/`,
`sudo journalctl --no-pager --since -15min -t sshd -t sshd-session | grep -i '<monitoring-user>' | tail -n 10`.
A `DenyUsers` rule shows in `sshd -T` and in the journal as
`User <monitoring-user> from <address> not allowed because listed in DenyUsers`.
Your own attempts land in that journal too, and a 15-minute window still
shows refusals from before a fix.
[LAB-VALIDATED: VM-HOST-07] The `Permission denied (publickey)` reading, and
the `DenyUsers` diagnosis. Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS, Ubuntu
24.04 OpenSSH as shipped, one run (page body: 3 controllers + 2 computes; its
lab record: all-in-one). Not run: ping, `nc -zv -w 5 <compute-host> 22`, the
timed-out and refused readings, the other causes below.

Other refusals, all seen by the client as `Permission denied (publickey)`:
an `AllowUsers`/`AllowGroups` list without the user (journal says it is not
listed); account missing (`getent passwd <monitoring-user>` empty, journal
`Invalid user <monitoring-user>`); key missing or changed in
`authorized_keys`, or account expired or locked (`sudo chage -l <monitoring-user>`).
Journal tags and messages may differ on other OpenSSH versions.
[DOCUMENTED-UNVERIFIED: VM-HOST-08]

**Fix the SSH side** (keep the admin session open, test from a second one):
*State-changing*: remove or correct the refusing line in the drop-in or
`/etc/ssh/sshd_config`, then `sudo sshd -t && sudo systemctl reload ssh.service`;
changes who may log in, a reload keeps open sessions, `sshd -t` first guards
against a lockout; undo: put the line back and reload. Then start
`nova-compute` as above, and read the host again with the monitoring user
before deciding anything about it.
[LAB-VALIDATED: VM-HOST-09] Lab: as VM-HOST-07; drop-in removed, `sshd -t`,
reload, `nova_compute` started through its unit; user accepted on all hosts,
service `up`. Not run: a fix inside `/etc/ssh/sshd_config` itself.

*State-changing*: a missing or changed key: put the monitoring user's public
key back in its `authorized_keys`; precondition: the key is the one your
monitoring uses, from a trusted source; undo: remove the line.
[DOCUMENTED-UNVERIFIED: VM-HOST-10]

**Verify.** `ssh -o BatchMode=yes -o ConnectTimeout=5 <monitoring-user>@<compute-host> id -un`
prints the user, exit 0; the service is `up`; on the compute libvirt runs as
many domains as Nova shows instances running there (each instance once;
`virsh domuuid <domain>` gives the instance ID).

## After a compute reboot

**Recognize.** A compute came back from a reboot (kernel update, hardware,
crash) and answers SSH, then either its instances stay `SHUTOFF`
(`Power State` `Shutdown`) although they ran before, or they run and Nova
shows them `ACTIVE` but they have no network. Nothing is lost on disk.
Until `nova-compute` is back and has synchronised, Nova still shows them
`ACTIVE`/`Running` from before the reboot: read their state only once the
compute service is `up` again.

**Read-only checks.**
- `openstack server list --all-projects --host <compute> --long -c Name -c Status -c "Power State"`,
  `openstack compute service list --host <compute>`,
  `openstack network agent list --host <compute>`.
- Kolla-Ansible, on the compute:
  `systemctl list-units 'kolla-*' --all --no-pager --state=failed,inactive,activating`;
  `sudo docker ps -a --filter name=openvswitch --format '{{.Names}}\t{{.Status}}'`;
  `sudo docker exec nova_compute grep -rn resume_guests_state_on_host_boot /etc/nova/`
  (empty: the default, `False`);
  `sudo docker exec openvswitch_db ovs-vsctl list-ports br-ex`.
- Any: `ip -br link`; `ip link show <tunnel-interface> | grep -o 'mtu [0-9]*'`;
  `ip link show <neutron-external-interface>`.

| Observation | Cause |
|---|---|
| Instances `SHUTOFF`; the option check is empty or `False` | 1. Nova does not resume guests after a reboot (the default) |
| A `kolla-*` unit not running; `openvswitch_vswitchd` among them cuts every instance | 2. a container did not come back |
| External interface, bond or VLAN `DOWN`; floating IPs and provider networks of this host do not answer | 3. host interface not up |
| Smaller MTU than the other computes; ping works, large transfers stall | 4. an MTU set by hand was not persistent |
| The host lost an address after the reboot | 5. an address was on `br-ex` or on the plugged interface |

Cause 1: `resume_guests_state_on_host_boot` defaults to `False` and
Kolla-Ansible 2026.1 does not set it, so guests that ran before the reboot
are not started and turn `SHUTOFF` once Nova synchronises (about a minute
after `nova-compute` came back, on the lab). With it `true`, `nova-compute`
starts them and logs `Rebooting instance after nova-compute restart.` for
each. Kolla-Ansible does not remove the unit of a service disabled after
deployment (for example `enable_haproxy: "no"` set later): it shows `failed`
or `activating auto-restart` at every boot; compare with `globals.yml` before
blaming it.
[LAB-VALIDATED: VM-HOST-11] Cause 1 with and without the option, the stale
units of disabled services, and the read-only checks. Lab: 2026.1,
Kolla-Ansible 22.2.0, all-in-one, ML2/OVS, CirrOS instances; not run: a
reboot of a compute in a multinode platform (controllers staying up; the
all-in-one control plane took 8 to 10 min to answer).

**Fix, cause 1.** *State-changing*: `openstack server start <server-id>`;
check with the owner first, an instance stopped on purpose before the reboot
is also `SHUTOFF`. To have Nova start them after the next reboot,
*State-changing*: Kolla-Ansible override
`/etc/kolla/config/nova/nova-compute.conf` with `[DEFAULT]`
`resume_guests_state_on_host_boot = true` (computes only; the global
`/etc/kolla/config/nova.conf` works too), then
`kolla-ansible reconfigure -i <inventory> --tags nova`, which restarts the
Nova containers whose configuration changed; running instances not affected.
Undo: remove the override and reconfigure again.
[LAB-VALIDATED: VM-HOST-12] Lab: as VM-HOST-11; start brought both instances
and their floating IPs back; reconfigure recreated only `nova_compute`,
instances unaffected; removal and reconfigure undid it. Not run: multinode.

**Fix, cause 3.** Persist the interface, bond, VLAN and MTU in the host's
network configuration (netplan, NetworkManager, systemd-networkd);
Kolla-Ansible does not configure them, and anything set by hand is lost at
reboot. To restore now, *State-changing*:
`sudo ip link set dev <interface> up`; a wrong interface can cut the host's
own connectivity: have console access, one interface at a time.
[LAB-VALIDATED: VM-HOST-13] Lab: as VM-HOST-11, without a reboot: the
external interface set `DOWN` showed `DOWN`, floating IPs stopped answering,
`ip link set ... up` restored them. Not run: a bond or VLAN, after a reboot.

**Fix, causes 2, 4, 5.** Cause 2, *State-changing*:
Kolla-Ansible: `sudo systemctl start kolla-<container>-container.service`,
then `journalctl -u kolla-<container>-container.service -b --no-pager | tail -n 50`
for why it did not start (for `openvswitch_vswitchd`, see *ovs-vswitchd down*
in instance-networking.md). Cause 4, *State-changing*:
`sudo ip link set dev <tunnel-interface> mtu <mtu-used-by-the-other-computes>`
(same console precaution), then persist it (see *Tunnel MTU mismatch* in
instance-networking.md). Cause 5: restore the host address from the console,
in the host's network configuration, on an interface not plugged into
`br-ex`; Kolla-Ansible's Neutron guide recommends leaving
`neutron_external_interface` without an address and calls a shared external
interface out of scope. [DOCUMENTED-UNVERIFIED: VM-HOST-14] Not covered:
ML2/OVN, DPDK, Ceph-backed disks.

**Verify.** Instances `ACTIVE`/`Running`, agents alive, floating IP pings;
every unit running, interfaces up with the expected MTU, the external
interface in `br-ex`.

## Restarts that keep instances running

**Question.** "I must restart `nova_libvirt` on a compute (configuration
change, stuck libvirtd, a Nova reconfigure or upgrade, which restarts it on
every compute). Will the instances stop?" With Kolla-Ansible defaults,
`nova_libvirt` runs with `pid_mode: host` and `cgroupns_mode: host`: QEMU
processes are host processes, outlive the container, and the new libvirtd
re-attaches to the running domains without restarting them. Libvirt
operations on that compute (start, stop, reboot, new instances, migrations)
wait until libvirtd is back.

**Read-only checks, before.**
- `openstack server list --all-projects --host <compute> --long -c ID -c Name -c Status -c "Task State" -c "Power State"`.
- `openstack server migration list --host <compute> --status running`: no
  migration may run (a migration during the restart was not tested).
- Kolla-Ansible: `docker inspect -f '{{.HostConfig.PidMode}} {{.HostConfig.CgroupnsMode}}' nova_libvirt`
  must print `host host`. If not, **do not restart**: the QEMU processes would
  end with the container and every instance of the compute stop; move them
  off first (`openstack-maintenance-planning`).
- Record Kolla-Ansible: `docker exec nova_libvirt virsh list --all`, and
  `pgrep -a -f qemu-system`.

[DOCUMENTED-UNVERIFIED: VM-HOST-15] The precondition checks (migration list,
`host host`), the claim that a non-host PID namespace stops the instances,
the stuck-libvirtd case (`virsh list` hangs, libvirt timeouts in
nova-compute), and Any: `systemctl restart libvirtd` (or modular
`virtqemud`), whose effect on instances was not tested.

**Restart.** *State-changing*: Kolla-Ansible:
`systemctl restart kolla-nova_libvirt-container.service`. Precondition:
`host host` and no migration running; otherwise every instance of the compute
can stop or a migration can fail. Undo: none needed; if the container does
not come back, `systemctl start kolla-nova_libvirt-container.service`.
Kolla-Ansible: follow it with `docker logs --tail 50 -f nova_libvirt`; nova-compute reconnects by
itself (read `/var/log/kolla/nova/nova-compute.log` if its connection errors
persist).
[LAB-VALIDATED: VM-HOST-16] Lab: 2026.1, Kolla-Ansible 22.2.0 default
`nova_libvirt` settings, Docker, ML2/OVS, local disks, one instance on the
compute, requests every 0.5 s: 174 then 339 requests, 0 lost; domain kept
ID 1; instance `ACTIVE`/running. Not run: the precondition checks, the qemu
PID comparison after the restart, a stuck libvirtd, a libvirt operation or
live migration during the restart, Podman, Cinder volumes, PCI passthrough
or vGPU; a gap under 0.5 s could have been missed.

**Verify.** Same domain IDs and qemu PIDs as recorded, instances
`ACTIVE`/`Running`, `nova-compute` `up`, pings answered. To measure the gap,
run `ping -i 0.5 -D <instance-address>` across the restart.

For the Open vSwitch agent, see *Restarting the OVS agent* in
instance-networking.md.

## Live migration never completes

**Recognize.** `openstack server migrate --live-migration <server-id>` was
accepted; the instance stays `MIGRATING` far longer than its peers, then is
`ACTIVE` again **on the source host** with the migration record `error`. The
instance runs on the source throughout; the host cannot be drained, and the
copy loads the network (and both hosts' disks for a block migration). A
migration refused at once (pre-check, shared storage, CPU, versions) is a
planned-maintenance question (`openstack-maintenance-planning`).

**Read-only checks.**
- `openstack server migration list --server <server-id>`.
- `openstack --os-compute-api-version 2.24 server migration show <server-id> <migration-id>`,
  repeated: is `memory_remaining_bytes` going down?
- `openstack server show <server-id> -c flavor` (memory; ephemeral disk for a
  block migration).
- Source compute, Kolla-Ansible:
  `sudo grep -E 'WARNING.*<server-id>' /var/log/kolla/nova/nova-compute.log | grep -i 'live migration not completed'`
  (Any: the same on your `nova-compute` log); upstream shows
  `live migration not completed after <n> sec`.

| Observation | Meaning |
|---|---|
| `memory_remaining_bytes` falls steadily, slowly | copy progresses, link slow or busy (large instance, 1 Gbit/s or shared network, several migrations) |
| Falls, then hovers at the same order of magnitude | guest dirties memory as fast as it is copied: will not converge without help |
| `disk_*` fields stay 0 during a block migration | expected: not reported |
| `live migration not completed after <n> sec` | Nova's completion timeout fired |

The timeout is `[libvirt] live_migration_completion_timeout` (default 800) s
per GiB of memory, plus the ephemeral disk for a block migration (8 GiB on
shared storage: 6400 s). Then `[libvirt] live_migration_timeout_action`:
`abort` (default, instance stays on source) or `force_complete`.
Kolla-Ansible 2026.1 sets none of these, nor auto-converge or post-copy
(both off), and `migration_interface` defaults to `api_interface`, so
migrations share the API and database network.
[DOCUMENTED-UNVERIFIED: VM-HOST-17] Not reproduced on a lab (small idle
instances block-migrated in 32 to 34 s there).

**Fix options**, least intrusive first; none deletes anything.
1. *State-changing*: abort:
   `openstack --os-compute-api-version 2.24 server migration abort <server-id> <migration-id>`;
   instance stays on the source unchanged; nothing to undo.
2. *State-changing*: finish now (memory-bound case):
   `openstack --os-compute-api-version 2.22 server migration force complete <server-id> <migration-id>`
   pauses the instance until the rest is copied (or switches to post-copy if
   allowed); the pause affects timekeeping and not every application
   tolerates it: agree with the owner first.
   [DOCUMENTED-UNVERIFIED: VM-HOST-18]
3. *State-changing*: let future migrations converge, on **all** computes:
   Kolla-Ansible override `/etc/kolla/config/nova/nova-compute.conf`,
   `[libvirt]` `live_migration_permit_auto_converge = true` (throttles the
   guest CPU, no guarantee) or `live_migration_permit_post_copy = true`
   (certain to complete, but the instance is rebooted if the inter-host
   network breaks during that phase), then
   `kolla-ansible reconfigure -i <inventory> --tags nova` (restarts changed
   `nova_compute` containers; instances unaffected; undo: remove and
   reconfigure). Any: same options in `nova.conf`, restart `nova-compute`.
   Slow network: a dedicated `migration_interface` in `globals.yml`, then
   reconfigure in a window. Large local disk: plan the time or cold-migrate.
   [DOCUMENTED-UNVERIFIED: VM-HOST-19] Not covered: PCI, vGPU, NUMA-pinned
   instances, failures after switch-over.

**Verify.** The new migration `completed`; instance `ACTIVE` on the
destination; the owner checks the application (especially after a pause).

## CPU steal on pinned instances

**Recognize.** A `hw:cpu_policy=dedicated` instance shows non-zero steal
(`st` in `top` or `/proc/stat`); latency-sensitive workloads report jitter.
After a live migration steal drops to zero, then returns days or weeks later
on the new host: migration moves the symptom, not the cause, which lives in
the host configuration [Book: Ch. 15]. Nova pins the guest's vCPUs, nothing
else.

**Read-only checks** (on the compute; `<instance-name>` is
`OS-EXT-SRV-ATTR:instance_name`):
- `virsh vcpupin <instance-name>`, `virsh emulatorpin <instance-name>`,
  `virsh dumpxml <instance-name> | sed -n '/<cputune>/,/<\/cputune>/p'`.
- Per pinned host CPU: `ps -eLo pid,tid,psr,comm | awk '$3==<host-cpu>'`;
  `cat /proc/interrupts | awk '{print $1, $<host-cpu+2>}' | sort -k2 -n | tail`.
- `grep -E 'cpu_dedicated_set|cpu_shared_set|vcpu_pin_set' /etc/nova/nova.conf`
  (Kolla-Ansible: `/etc/kolla/nova-compute/nova.conf`);
  `cat /sys/devices/system/cpu/isolated`; `/proc/cmdline`.

| Observation | Cause (check in this order) |
|---|---|
| `isolated` empty; kernel threads or daemons on pinned CPUs; interrupts counted on them | host threads and IRQs not isolated from the dedicated set |
| `virsh emulatorpin` equals the vCPU set; flavor lacks `hw:emulator_threads_policy` | emulator threads share the pinned CPUs |
| Two domains' `vcpupin` share a host CPU | overlapping pinning |
| `cpu_dedicated_set` differs from what domains use; migrations on pre-Train releases | Nova/host mismatch |

[LAB-VALIDATED: VM-HOST-20] Read-only checks and the host-process cause:
steal 0.8 % idle, 26.7 % with host processes on the pinned CPU. Lab: 2026.1,
Kolla-Ansible multinode (1 controller, 2 computes), nested KVM; network and
storage not recorded. Not run: host isolation, any migration.

[LAB-VALIDATED: VM-HOST-21] With `hw:emulator_threads_policy=share`, the
emulator threads moved off the pinned CPUs. Lab: as VM-HOST-20; how the
policy reached the instance (new instance, resize or rebuild) and the steal
afterwards were not recorded.

**Fix options.** Stop migrating first; the book's team accepted a bounded
steal while investigating [Book: Ch. 15].
1. *State-changing*: emulator threads:
   `openstack flavor set --property hw:emulator_threads_policy=share <flavor>`
   with a `[compute] cpu_shared_set` on every host (`isolate` instead gives an
   extra dedicated CPU). Affects new and resized instances only; existing
   ones need a resize to a new flavor (same flavor is not enough) or a
   rebuild. [DOCUMENTED-UNVERIFIED: VM-HOST-22]
2. *State-changing*: isolate host CPUs (`isolcpus=`, `nohz_full=`,
   `rcu_nocbs=` matching `cpu_dedicated_set`, or a tuned profile
   `cpu-partitioning` / `realtime-virtual-host`), pin IRQs away, keep
   housekeeping CPUs in `cpu_shared_set`, per the OS and hardware vendor.
   Needs a host reboot, hence moving or stopping its instances; one host
   first, measure, then roll out. Overlap or mismatch: move one instance per
   overlap to a host with free dedicated CPUs and check `virsh vcpupin`
   there. Release facts: NUMA-aware live migration of pinned instances from
   Train (Nova 20.0); on Stein with `enable_numa_live_migration` and earlier,
   a migration could itself create overlapping pinning;
   `hw:emulator_threads_policy=share` with `cpu_shared_set` from Rocky
   (Nova 18.0). [DOCUMENTED-UNVERIFIED: VM-HOST-23]

**Verify**, over days: `vmstat 5 12` in the guest, `st` at 0; on the host
`ps -eLo psr,comm | awk '$1==<pinned-cpu>' | sort | uniq -c` shows only the
vCPU threads (`CPU n/KVM`) and per-CPU kernel threads (`ksoftirqd/N`,
`migration/N`, `cpuhp/N`, `kworker/N`).

## Clock skew

**Recognize.** While building a timeline across hosts, one compute's log
lines appear minutes before (or after) the controller events that caused
them. Everything else is healthy: `nova-compute` `up`, agents alive, new
instances boot. The drift is silent because service liveness is recorded by
`nova-conductor` and `neutron-server` with the controllers' clocks; what the
compute stamps itself is its logs.

**Read-only checks.**
- On each host: `timedatectl` (`System clock synchronized: no`,
  `NTP service: inactive`, or active with an unreachable source);
  `timedatectl show -p NTPSynchronized --value`;
  `systemctl status systemd-timesyncd`; `journalctl -u systemd-timesyncd --since "-1d"`.
- All clocks at once, Kolla-Ansible deployment host:
  `ansible -i <inventory> all -m command -a 'date -u +%s'`.
- Offset in the logs: the same `<request-id>` with `sudo grep` in
  Kolla-Ansible: `/var/log/kolla/nova/nova-conductor.log` (controller) and
  `/var/log/kolla/nova/nova-compute.log` (compute); without `sudo`,
  `Permission denied`.

| Observation | Cause |
|---|---|
| `NTP service: inactive` | 1. time service stopped |
| `NTP service: active`, `Packet count: 0`, journal `Timed out waiting for reply from <server>:123` | 2. time source unreachable |
| clock set by hand (`date -s`) or hardware clock wrong after reboot, sync off | 3. clock set by hand |

[LAB-VALIDATED: VM-HOST-24] Checks, causes 1 to 3 and the silence: compute
300 s back for 180 s, services up, an instance `ACTIVE` there in 13 s and
27 s, 0 requests lost, no time-related WARNING/ERROR, request id 299 s apart.
Lab: 2026.1, Kolla-Ansible 22.2.0, multinode (3 controllers, 2 computes),
ML2/OVS, Ubuntu 24.04 systemd-timesyncd, database service group driver. Not
run: a controller drift, a forward drift, more than 300 s, TLS checks.

**`timedatectl timesync-status` is not read-only** when systemd-timesyncd is
only stopped (`systemctl stop`): D-Bus starts it, the clock steps back to the
right time at once and the offset can no longer be measured. Measure the
offset first and skip it when `NTP service: inactive`; undo
(`sudo systemctl stop systemd-timesyncd`) does not undo the step. After
`timedatectl set-ntp false` it only prints `Failed to query server: Unit
dbus-org.freedesktop.timesync1.service not found.`
[LAB-VALIDATED: VM-HOST-25] Lab: as VM-HOST-24, both stopped and disabled
cases.

**Fix.** *State-changing*, causes 1 and 3: `sudo systemctl start systemd-timesyncd`
and `sudo systemctl enable systemd-timesyncd` (without `sudo`:
`Interactive authentication required`); the clock jumps by the offset, this
host only (log timestamps and service timers see the jump); precondition: a
reachable source; undo: `sudo systemctl disable --now systemd-timesyncd`.
Cause 2: make the source reachable (firewall, routing,
`/etc/systemd/timesyncd.conf`), then *State-changing*:
`sudo systemctl restart systemd-timesyncd`. Wait for
`timedatectl show -p NTPSynchronized --value` to print `yes`; correct the
drift-period log timestamps by the measured offset.
[LAB-VALIDATED: VM-HOST-26] Lab: as VM-HOST-24; synchronised within 1 s,
within 5 s of the first controller. Not run: chrony.

With chrony: `chronyc tracking`, `chronyc sources`, `sudo systemctl start chrony`.
Any (no Ansible):
`for h in controller-1 compute-1 compute-2; do echo "$h $(ssh $h date -u +%s)"; done`
(needs SSH and known host keys to each host).
[DOCUMENTED-UNVERIFIED: VM-HOST-27] A drift on a controller (Keystone tokens,
Galera, RabbitMQ, TLS) is not covered by this section.

**Verify.** `timedatectl`: synchronized `yes`, NTP service `active`; the
Ansible comparison within a few seconds; compute service and agents still
healthy. Monitor `NTPSynchronized` (or chrony's offset) on every host.

## Host failure and planned maintenance

Two neighbouring situations belong to other skills; do not run their
procedures from this one.

- **The host does not answer at all** (no ping, TCP 22 times out, no route)
  and someone proposes `openstack server evacuate`: hand over to
  `openstack-incident-analysis`, which covers fencing through an out-of-band
  channel before any evacuation. If the host answers, it is the first section
  of this file, not a host failure.
- **Planned work on a host** (patching, reboot, hardware) and moving its
  instances off with live or cold migration, including instances that cannot
  be live-migrated and capacity per failure domain: hand over to
  `openstack-maintenance-planning`. Its migrations that run long are covered
  above in *Live migration never completes*.
