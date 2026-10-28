# Logs and tracing

Where to look, and what a line means, for one instance, port or volume. Everything in this file is
an [Addition] to the book, distilled from the `logs/` pages and
`diagnostics/what-a-vm-creation-traverses-and-tracing-by-request-id.md` of OzarLand
openstack-vm-runbooks at commit `babdd8c07971`.

Lab evidence comes from OpenStack 2026.1 labs deployed with Kolla-Ansible (22.2.0 where recorded),
all-in-one unless stated, ML2/OVS, on 2026-10-26 and 2026-10-27. Different lab runs saw different
lines: a line marked *lab* was captured on at least one run, which does not mean it always appears;
a line marked *src* is message text from upstream source and was never seen on a lab. Paths and
container names are Kolla-Ansible's unless marked "Any:". Every log file under `/var/log/kolla` is
readable by root only.

## Contents

- Where the logs are
- Reading one log line
- Tracing one request, instance, port or volume
- Lines that discriminate causes
- Changing log levels

## Where the logs are

Kolla-Ansible: every container writes into the volume `kolla_logs`, mounted at `/var/log/kolla` (on
disk `/var/lib/docker/volumes/kolla_logs/_data`). `ls /var/log/kolla/<service>/` is the truth on
your platform.

| Service | Kolla-Ansible container | File under `/var/log/kolla/` | Runs on |
|---|---|---|---|
| nova-api | `nova_api` | `nova/nova-api.log`, requests in `nova-api-uwsgi.log` | controllers |
| nova-scheduler, nova-conductor | `nova_scheduler`, `nova_conductor` | `nova/nova-scheduler.log`, `nova/nova-conductor.log` (`nova-super-conductor.log` only with `enable_cells: true`) | controllers |
| nova-compute | `nova_compute` | `nova/nova-compute.log` (also os-brick lines, module `os_brick`) | computes |
| libvirt | `nova_libvirt` | `libvirt/libvirtd.log` (warnings and errors only, `log_level = 3`) | computes |
| placement-api | `placement_api` | `placement/placement-api.log`, `placement-api-uwsgi.log` | controllers |
| neutron-server, RPC server, periodic workers | `neutron_server`, `neutron_rpc_server`, `neutron_periodic_worker` | `neutron/neutron-server.log`, `neutron-rpc-server.log`, `neutron-periodic-workers.log` | controllers |
| Neutron agents | `neutron_openvswitch_agent`, `neutron_l3_agent`, `neutron_dhcp_agent`, `neutron_metadata_agent`, `neutron_ovn_metadata_agent` | `neutron/<agent program>.log` | network nodes, computes |
| Open vSwitch | `openvswitch_vswitchd`, `openvswitch_db` | `openvswitch/ovs-vswitchd.log`, `ovsdb-server.log` | computes, network nodes |
| OVN | `ovn_controller`, `ovn_northd`, `ovn_nb_db`, `ovn_sb_db` | `openvswitch/ovn-controller.log`, `ovn-northd.log`, `ovn-nb-db.log`, `ovn-sb-db.log` | computes, controllers |
| cinder | `cinder_api`, `cinder_scheduler`, `cinder_volume` | `cinder/cinder-api.log`, `cinder-scheduler.log`, `cinder-volume.log` | controllers, storage nodes |
| glance-api, keystone | `glance_api`, `keystone` | `glance/glance-api.log`, `keystone/keystone.log` (+ `-uwsgi.log`) | controllers |
| RabbitMQ, MariaDB | `rabbitmq`, `mariadb` | `rabbitmq/rabbit@<hostname>.log`, `mariadb/mariadb.log` | controllers |

- Each instance's QEMU log is `/var/log/libvirt/qemu/<instance-name>.log` **inside** `nova_libvirt`,
  not on `kolla_logs`, and is lost when the container is recreated (upgrade, redeploy): copy it out
  with `docker cp`. The guest console log is `/var/lib/nova/instances/<server-id>/console.log` in
  the `nova_compute` volume, mode 600.
- `docker logs <container>` is mostly empty (start-up and crashes before the log file opened);
  kernel, container engine, chrony and systemd units are in the host journal, outside
  `/var/log/kolla`.
- **Root-shell glob gotcha.** `sudo grep ... /var/log/kolla/nova/*.log` fails with
  `No such file or directory`: your own shell expands the glob and cannot read the directory. Use
  `sudo sh -c '...'` or `sudo -i`.

```bash
sudo readlink -f /var/log/kolla; sudo ls /var/log/kolla/
sudo grep -nE ' [0-9]+ (ERROR|CRITICAL) ' /var/log/kolla/nova/nova-compute.log | tail -20
sudo docker exec nova_libvirt tail -50 /var/log/libvirt/qemu/<instance-name>.log   # podman exec on Podman
sudo docker logs --tail 50 nova_compute
```

[LAB-VALIDATED: VM-LOG-01] Paths, file names and the commands above. Lab: 2026.1, Kolla-Ansible
all-in-one, ML2/OVS, no HAProxy, host in UTC; not run: package-install commands, journald fields,
HAProxy and OVN log files.

Any: Nova's documentation gives `/var/log/nova/` (units `openstack-nova-compute` on RHEL-family,
`nova-compute` on Ubuntu/Debian); other services follow the same pattern depending on packaging.
oslo.log writes to a file with `log_file` / `log_dir`, to the journal with `use_journal = true`
(with fields such as `REQUEST_ID`, `PRIORITY`, `SYSLOG_IDENTIFIER`), otherwise stdout captured by
systemd: `systemctl cat <unit>`, `journalctl -u <unit> --since "1 hour ago"`,
`grep -E '^\s*(log_file|log_dir|use_journal|use_syslog|use_stderr|debug)\s*=' /etc/nova/nova.conf`.
Out of scope here, but their logs exist: Octavia under `/var/log/kolla/octavia/`, Heat under
`/var/log/kolla/heat/` (read `heat-engine.log` first, then follow the failed resource's physical id
into the service that failed). [DOCUMENTED-UNVERIFIED: VM-LOG-02]

**Container restarts.** Kolla-Ansible runs each container under a systemd unit
`kolla-<container>-container.service`; systemd, not Docker, restarts it.
`journalctl -u kolla-nova_compute-container.service --since "-1h"` shows what the container printed,
including a crash before its log file opened; a loop shows `<unit>: Failed with result 'exit-code'.`
then `<unit>: Scheduled restart job, restart counter is at <n>.` `RestartCount` in `docker inspect`
stays 0 on Kolla-Ansible: read `StartedAt` and
`systemctl show -p NRestarts -p ActiveState -p SubState -p Result kolla-<container>-container.service`.
Exit 137 = SIGKILL (OOM or stop beyond the grace time), 143 = normal stop.

[LAB-VALIDATED: VM-LOG-03] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, systemd 255, Docker 29.9.2,
`docker_client_timeout: 600` (`RestartSec=59`): a `nova_compute` loop for 13 min, counter to 11,
`RestartCount` 0. Not run: Podman, the Kolla default restart values;
`Start request repeated too quickly.` (start limit) never reached.

## Reading one log line

oslo.log default (Kolla-Ansible 2026.1 does not override it):

```text
<date> <time>.<ms> <pid> <LEVEL> <module> [<global-request-id or None> req-<uuid> <user-id> <project-id> <domain> <system-scope> <user-domain> <project-domain>] [instance: <uuid>] <message>
```

- `[-]`: no request (periodic task, start-up); find the line by time and module, not by request id.
- `[None req-A ...]`: the request started in this service. `[req-A req-N ...]`: a called service;
  `req-A` is the caller's id (global request id), `req-N` its own. Grep the id from the first
  service.
- The exception is on the same line after `: `. Traceback lines carry no request id:
  `grep -n "<request-id>" <file> | grep ERROR`, then `sed -n '<line>,+40p' <file>`.
- `ERROR` means an operation failed, not always the cause: find the first one in time. `CRITICAL`:
  the service is stopping or cannot start; read the lines before. `default_log_levels` pins
  `keystonemiddleware=WARN`, `amqp=WARN`, `sqlalchemy=WARN`: `debug = true` does not show those
  libraries.
- uWSGI request lines (`<service>-uwsgi.log`) have no request id and the time is the request start:
  find them by URI or resource id.

| Log | Time stamp |
|---|---|
| oslo.log services | host local time, no zone |
| OVS, OVN | UTC, ends with `Z` |
| libvirtd, instance (QEMU) log | UTC, `+0000` |
| RabbitMQ | offset `+00:00` |
| MariaDB | host local time, 1 s resolution, no offset |
| journal | `journalctl -o short-iso-precise` prints the offset; `--utc` for UTC |

[LAB-VALIDATED: VM-LOG-04] Line format, request-id brackets and time stamps, from real oslo.log,
uWSGI, OVS, RabbitMQ, libvirtd and MariaDB lines. Lab: 2026.1, Kolla-Ansible all-in-one, host in
UTC; not run: a host in a non-UTC zone, journald fields.

**Clocks.** Lines from two hosts can be compared only after correcting each host's offset.
`timedatectl` ("System clock synchronized"), `timedatectl timesync-status` (`Packet count`,
`Offset`), `chronyc tracking`, `chronyc sources -v`. With systemd-timesyncd, NTP blocked for 5.5 min
logged nothing, `Packet count` stayed 0 and "synchronized: yes" stayed. A clock jump shows as
`Time jumped backwards, rotating.` (journald),
`System clock time unset or jumped backwards, restored from recorded timestamp: <date>` and
`Initial clock synchronization to <date>.`: log times jump there. [LAB-VALIDATED: VM-LOG-05] Lab:
2026.1, Kolla-Ansible 22.2.0 all-in-one, systemd-timesyncd (systemd 255); not run: chrony, agents on
another host than neutron-server, a controller clock ahead.

chrony logs `Can't synchronise: no selectable sources`, `System clock wrong by <offset> seconds`,
`System clock was stepped by <offset> seconds` (every log on the host jumps). neutron-server logs,
at agent start only, ERROR
`Message received from the host: <host> during the registration of <agent type> has a timestamp: ... This differs from the current server timestamp: ... by <n> seconds, which is more than the threshold agent down time: <n>.`:
the agent still registers and is not shown down; fix the host clock (never with ML2/OVN). Nova
judges a service up or down with the clock of the controller answering the API: an offset above
about a minute between controllers makes services flap. See *Clock skew* in compute-host-events.md.
[DOCUMENTED-UNVERIFIED: VM-LOG-06]

## Tracing one request, instance, port or volume

Follow the operation through the services it traverses, by the identifier that links each hop
[Book: Ch. 8].

| Hop | Linked by |
|---|---|
| Client → API; nova-api → conductor → scheduler → nova-compute | the request id `req-<uuid>` (returned in `x-openstack-request-id`) |
| Nova → Neutron, Placement, Cinder, Glance | Nova's id as global request id, first in the called service's brackets |
| Neutron → agent or OVN → back to Nova (`network-vif-plugged`) | the port id (the event is a new nova-api request with its own id) |
| Nova → libvirt / QEMU | instance name (`instance-%08x`) and instance UUID |
| Nova → Cinder → backend | the volume id, and Nova's id in Cinder |

1. Identifiers: `openstack server event list <server-id>` (Request ID column, one row per action);
   `openstack server event show <server-id> <request-id>` (admin: per-step events);
   `openstack server show <server-id> -c OS-EXT-SRV-ATTR:instance_name -c OS-EXT-SRV-ATTR:host`;
   `openstack port list --server <server-id> -c ID -c Status`;
   `openstack port show <port-id> -c status -c binding_host_id`.
2. One host: `sudo grep -rh "<request-id>" /var/log/kolla/ | sort | less -S`, or
   `sudo sh -c 'grep -h "<request-id>" /var/log/kolla/nova/*.log /var/log/kolla/neutron/*.log' | sort`.
   `sort` is right only for one host (one clock).
3. Several hosts, from the deployment host (assumes groups `control` and `compute`):
   `ansible -i <inventory> control,compute -b -m shell -a 'grep -rh "<request-id>" /var/log/kolla/nova /var/log/kolla/neutron /var/log/kolla/placement || true'`.
4. Port, on the compute of `binding_host_id`: tap name `port=<port-id>; echo "tap${port:0:11}"`;
   with the hybrid iptables firewall OVS sees `qvo<11 chars>`.
   `sudo grep "<port-id>" /var/log/kolla/neutron/neutron-openvswitch-agent.log`;
   `sudo grep -E "(tap|qvo)<first-11-chars>" /var/log/kolla/openvswitch/ovs-vswitchd.log`; on
   controllers
   `sudo grep "<port-id>" /var/log/kolla/neutron/neutron-server.log /var/log/kolla/nova/nova-api.log`.
5. Hypervisor: `sudo grep "<server-id>" /var/log/kolla/nova/nova-compute.log`; `libvirtd.log` often
   has no line for a healthy domain; read the QEMU log.

On the lab, one successful boot's request id gave 26 lines in `nova-api.log`, `nova-api-uwsgi.log`,
`nova-scheduler.log`, `nova-compute.log`, `placement-api.log` and `neutron-openvswitch-agent.log`,
none in `nova-conductor.log` or `neutron-server.log`; the ansible search returned the same 26. The
port chain captured: ovs-vswitchd `bridge br-int: added interface qvo<11-chars> on port 19`,
nova-api `Creating event network-vif-plugged:<port-id> for instance <server-id> on <host>`, OVS
agent `Port <port-id> updated. Details: {...}` and
`Configuration for devices up ['<port-id>'] and devices down [] completed.`, nova-compute
`Took <n> seconds to spawn the instance on the hypervisor.` [LAB-VALIDATED: VM-LOG-07] Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, ML2/OVS hybrid iptables firewall, host in UTC; not run: several
hosts and their clock offsets, journal searches, DEBUG lines, OVN, a volume.

**Reading.** The last service that logged the request id is where the operation stopped; the first
error after that point is the cause, or the symptom of a dependency (bus, database) failing
underneath. Compare with a request that succeeds.

| Step | What the user sees | Read |
|---|---|---|
| Scheduler / Placement | `ERROR`, fault `No valid host was found`, no host | `nova-scheduler.log`, `placement-api.log` |
| Neutron binding | `binding_failed`; user may only see `Exceeded maximum number of retries` | `neutron-server.log` |
| VIF plug | `BUILD`/`spawning` for `vif_plugging_timeout`, then `ERROR` | agent log or `ovn-controller.log` |
| Glance | `BUILD`/`spawning`, then image download error | `nova-compute.log`, `glance-api.log` |
| Cinder | `block_device_mapping` stuck, volume stays `creating` | `cinder-volume.log` |
| libvirt / QEMU | `ERROR` with a libvirt error in `fault` | `nova-compute.log`, libvirtd and QEMU logs |
| Cell mapping | `Host '<host>' is not mapped to any cell` | `nova-conductor.log`, `nova-manage cell_v2 list_hosts` |

Lab: a no-valid-host boot was found by id in nova-api, placement-api (`GET /allocation_candidates`),
nova-scheduler and nova-conductor within about 2 s; a boot bound to a dead OVS agent showed
neutron-server `Refusing to bind port ... to dead agent` and `Failed to bind port ... on host` with
Nova's id, `PortBindingFailed` in `nova-compute.log`, `ERROR` 15 s after the request with fault
`Exceeded maximum number of retries`, while `server event show` reported the compute event as
`Success`. `server event show` can be that thin; unrelated lines (a later `GET /v2.1`) can carry the
id; Glance at the default level logged nothing for a successful call. [LAB-VALIDATED: VM-LOG-08]
Lab: 2026.1, Kolla-Ansible all-in-one, ML2/OVS, 2026-10-26; not run: the Glance, Cinder, libvirt and
cell-mapping rows.

Not run on a lab [DOCUMENTED-UNVERIFIED: VM-LOG-09]: volume tracing
(`openstack server volume list <server-id>`;
`sudo grep "<volume-id>" /var/log/kolla/nova/nova-compute.log`;
`sudo sh -c 'grep -h "<volume-id>" /var/log/kolla/cinder/cinder-*.log' | sort`; many Cinder lines
carry no volume id: follow Nova's request id); rotated files
(`sudo sh -c 'zgrep -h "<request-id>" /var/log/kolla/nova/nova-compute.log*' | sort`; `.1` is plain,
older `.gz`); journal (`journalctl REQUEST_ID=<request-id> -o short-iso-precise`, only with
`use_journal = true`); central logging strips `req-` (search the bare UUID); the OVN chain
`Claiming lport <port-id> for this chassis.` → `Setting lport <port-id> up in Southbound` →
`OVN reports status up for port: <port-id>` → `Creating event network-vif-plugged:<port-id> ...`
(the step after the last line found is where it stopped).

## Lines that discriminate causes

*Seen* gives the item whose lab run captured the line, or *src*.

### Nova and Placement

| Line | Where | Means → next | Seen |
|---|---|---|---|
| `Claim successful on node <node>` / `Took <n> seconds to spawn the instance on the hypervisor.` | nova-compute | claim and spawn on this host | lab 10 |
| `Failed to build and run instance` + traceback | nova-compute | build failed; the last traceback line is the cause; may be rescheduled | lab 10 |
| `Instance failed to spawn: <exception>` (e.g. `FlavorDiskSmallerThanImage`) | nova-compute | resource setup or hypervisor step → libvirt / QEMU log | lab 10 |
| `Lost connection to nova-conductor for reporting service status.` / `Recovered from being unable to report status.` | nova-compute | heartbeat via conductor timed out; long enough → service `down` | lab 10 (not on the run of item 23) |
| `Starting compute node (version <v>)`; `Connection event '1' reason 'None'` | nova-compute | restart marker; libvirt connection up | lab 10 |
| `Got no allocation candidates from the Placement API. ...` | nova-scheduler | Placement returned nothing; fault `No valid host was found. ` with empty reason → Placement request line | lab 11 |
| `Filtering removed all hosts for the request with instance ID '<uuid>'. Filter results: [...]` | nova-scheduler | the filter whose `end` is 0; fault reason `There are not enough hosts available.` | lab 11 |
| `Failed to schedule instances: ...NoValidHost...` | nova-conductor | instance in cell0, nothing on any compute | lab 11 |
| `Setting instance to ERROR state.: nova.exception.MaxRetriesExceeded: Exceeded maximum number of retries. Exhausted all hosts available ...` | nova-conductor (`nova.scheduler.utils`) | every compute that tried failed; nothing in the scheduler; read each compute's log | lab 11 |
| `Build of instance <uuid> was re-scheduled: <reason>` | nova-compute | one failed attempt; error just before. On Kolla 2026.1 appended to an unrelated WARNING line: `grep 're-scheduled'` | lab 11 |
| `<addr> "PUT /allocations/<server-id>" status: <code> len: <n> microversion: <v>` with `[req-<nova> req-<placement>]` | placement-api | the claim; grep Nova's id | lab 12 |
| `Over capacity for <rc> on resource provider <rp>. Needed: <n>, Used: <n>, Capacity: <n>` | placement-api, 409 | claim does not fit; `Capacity` = (total − reserved) × allocation_ratio | lab 12 |
| `Allocation for <rc> on resource provider <rp> violates min_unit, max_unit, or step_size. ...` | placement-api, 409 | flavor asks more than one provider allows | lab 12 |
| `Resource provider <uuid> is now over-capacity for <rc>` | placement-api | inventory lowered below usage; new claims fail | lab 12 |
| `Failed to allocate network(s)`; fault `Build of instance <uuid> aborted: Failed to allocate the network(s), not rescheduling.` | nova-compute | usually the `network-vif-plugged` wait; not retried → *Stuck in BUILD waiting for vif-plugged* | src |
| `Timeout waiting for ['network-vif-plugged-<port-id>'] for instance with vm_state ...` | nova-compute | waited `vif_plugging_timeout`; `grep "Timeout waiting for"` → port id in agent log | src |
| `Build of instance <uuid> aborted: Failure prepping block device.` | nova-compute | not retried → *Boot from volume fails* | src |
| `Insufficient compute resources: <reason>.` | nova-compute | claim failed, compute disagrees with the scheduler; retried elsewhere | src |
| `Connection event '0' reason 'Connection to libvirt lost: <reason>'` | nova-compute | compute disabled with a reason starting `AUTO: ` until reconnect | src |
| `Error updating resources for node <node>.` | nova-compute | periodic inventory update failed | src |
| `Host '<host>' is not mapped to any cell` | nova-conductor | → `nova-manage cell_v2 list_hosts` | src |
| `Exceeded max scheduling attempts <n> for instance <uuid>. ...` | conductor | `[scheduler] max_attempts` (3; Kolla-Ansible 2026.1 renders 10) | src |
| `Exceeded retry limit of <n> on allocations write`; `Placement API service is not responding.`; `Placement service credentials do not work.`; `[<placement-req-id>] Failed to update inventory ...`; `Unable to delete allocation for <type> <uuid>: ...` | placement / report client in nova-compute | concurrent writes; Placement unreachable; `[placement]` credentials; leftovers become phantom usage. Grep the bracketed id in `placement-api.log` | src |

`sudo grep -nE "Connection event|Connection to libvirt|Lost connection to nova-conductor|Error updating resources" /var/log/kolla/nova/nova-compute.log | tail`;
`sudo grep -n "Got no allocation candidates\|Filtering removed all hosts" /var/log/kolla/nova/nova-scheduler.log | tail`;
`sudo grep "<nova-request-id>" /var/log/kolla/placement/placement-api.log`.

[LAB-VALIDATED: VM-LOG-10] Rows *lab 10*. Lab: 2026.1 (Nova 33.0.3), Kolla-Ansible 22.2.0
all-in-one, captures 2026-10-23 to 27; not seen: network allocation, block device or libvirt
connection failures, max retries on that run. [LAB-VALIDATED: VM-LOG-11] Rows *lab 11*. Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, one compute, ML2/OVS, INFO logs; not seen:
`Exceeded max scheduling attempts`, a reschedule to another compute, DEBUG lines.
[LAB-VALIDATED: VM-LOG-12] Rows *lab 12*. Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, 409s made
with a test consumer; not seen: retry limit, generation conflict, 500, report-client lines.
[DOCUMENTED-UNVERIFIED: VM-LOG-13] Rows *src*.

### Neutron, Open vSwitch and OVN

| Line | Where | Means → next | Seen |
|---|---|---|---|
| `bridge br-int: added interface qvo<prefix> on port <n>` (`tap<prefix>` without hybrid firewall) | ovs-vswitchd | port in the datapath | lab 14 |
| `could not open network device qvo<prefix> (No such device)` | ovs-vswitchd, WARN | interface in OVSDB, device gone (lab: shut-off instance after a host reboot) | lab 14 |
| `br-int<->tcp:127.0.0.1:6633: connection failed (Connection refused)` | ovs-vswitchd, WARN | Neutron OVS agent not listening; expected during an agent restart (`connected` 7.6 s later on lab) | lab 14 |
| `Unreasonably long <n>ms poll interval (<u>ms user, <s>ms system)` | ovs-vswitchd, WARN | main loop over 1 s; lab: at start after host boot | lab 14 |
| `\|00001\|vlog\|INFO\|opened log file` (main thread) | ovs-vswitchd | daemon restarted | lab 14 |
| `Port <port-id> updated. Details: {...}`, `Configuration for devices up [...] ... completed.` | OVS agent | port wired. No line at all in the agent of `binding_host_id` = tap never plugged | lab 07 |
| `Refusing to bind port ... to dead agent`, `Failed to bind port <port-id> on host <host> for vnic_type <vnic> using segments <segments>` | neutron-server | port `binding_failed`: no live agent, or `bridge_mappings` do not cover the physnet → *Port binding failed* | lab 08 |
| `OVS is down, not reporting state to server` | OVS agent, ERROR | agent stops heartbeats on purpose → *ovs-vswitchd down* | src |
| `Agent healthcheck: found <n> dead agents out of <total>:` | periodic workers | heartbeats stopped → agent log, RabbitMQ | src |
| `Failed reporting state!`; `Agent has just been revived. Doing a full sync.` | agent | heartbeat failed; repeating revival = flapping | src |
| `Port <port> was not found on the integration bridge and will therefore not be processed` | OVS agent | port disappeared; **not** "never plugged" | src |
| `Nova event matching ['<nova-request-id>'] response: {...}`; `Failed to notify nova on events: [...]` | neutron-server | Nova accepted the event (grep the id in `nova-api.log`); Nova unreachable or `[nova]` credentials | src |
| `The remote metadata server responded with Forbidden. ...` | metadata agent | `metadata_proxy_shared_secret` differs → *No metadata* | src |
| `Unable to <action> dhcp for <network-id>.` | DHCP agent | dnsmasq failed → *No IP address* | src |
| `<target>: no response to inactivity probe after <n> seconds, disconnecting` | OVS, OVN daemons | peer overloaded or stuck | src |
| `Claiming lport <port-id> for this chassis.` / `Changing chassis for lport <port-id> from <old> to <new>.` | ovn-controller | chassis takes the port; back and forth = two chassis claim it | src |
| `Refusing to bind port <port-id> due to no OVN chassis for host: <host>` | neutron-server (OVN) | no ovn-controller registered for that host | src |
| `<target>: continuing to reconnect in the background but suppressing further logging` | OVN daemons | silence after it is not "reconnected": look for `connected` | src |

Neutron timers: `report_interval` 30 s, `agent_down_time` 75 s. With separate server processes, a
line may be in another of the three server logs. [LAB-VALIDATED: VM-LOG-14] Rows *lab 14*. Lab:
2026.1, Kolla-Ansible 22.2.0 all-in-one, ML2/OVS (VXLAN, hybrid iptables firewall), Open vSwitch
3.7.1; not run: ML2/OVN, DPDK, inactivity probe. [DOCUMENTED-UNVERIFIED: VM-LOG-15] Rows *src*: no
line of the Neutron ML2/OVS agent and OVN pages was captured.

### Cinder, os-brick and host storage

| Line | Where | Means → next | Seen |
|---|---|---|---|
| `Volume volume-<volume-id> (<volume-id>): created successfully` | cinder-volume | normal | lab 16 |
| `volume service is down. (host: <host>@<backend>)` | cinder-scheduler, WARNING | heartbeat older than `service_down_time` (60 s) → that backend's `cinder-volume.log` | lab 16 |
| `Filtering removed all hosts for the request with volume ID '<volume-id>'. Filter results: ...`; `No weighed backend found ...`; `Failed to run task cinder.scheduler.flows.create_volume.ScheduleCreateVolumeTask;volume:create: <error>` | cinder-scheduler | filter with `end` 0 is the cause; the last is the final line of a failed create | lab 16 |
| `Stderr: '  Logical volume cinder-volumes/volume-<volume-id> in use.\n'` after `lvremove` | cinder-volume | LVM delete refused → `error_deleting` | lab 16 |
| `Attaching volume <volume-id> to <mountpoint>`; `Trying to connect to iSCSI portal <portal>` | nova-compute | attach and os-brick login | lab 16 |
| `connection<sid>:<cid>: detected conn error (<code>)` (`1022` = NOP timed out) | kernel | iSCSI connection failed; `replacement_timeout` (120 s) starts | lab 17 |
| `Kernel reported iSCSI connection <sid>:<cid> error (<code> - <name>) state (<n>)` | iscsid | the same, with the code name | lab 17 |
| `session<sid>: session recovery timed out after <n> secs` | kernel | waiting I/O now fails up to the guest (lab: ext4 remounted read-only and stayed so) | lab 17 |
| `connection<sid>:<cid> is operational after recovery (<n> attempts)` | iscsid | session back | lab 17 |
| `Failed to initialize driver.`; `Manager for service cinder-volume <host>@<backend> is reporting problems, not sending heartbeat. ...` | cinder-volume | backend does not serve, shows `down` | src |
| `Volume <volume-id>: create failed`; `Failed to copy image to volume: <reason>` | cinder-volume | traceback before gives the cause; image path → Glance, disk space | src |
| `Insufficient free virtual space (<n>GB) to accommodate thin provisioned <n>GB volume on host ...` | CapacityFilter | usual cause of `CapacityFilter: (start: <n>, end: 0)` | src |
| `Terminate volume connection failed: <error>` | cinder-volume | → *Stuck attaching or detaching* | src |
| `Failed to connect to iSCSI portal <portal>.`; `LUN <lun> on iSCSI portal <portal> not found on sysfs after logging in.`; `Volume device not found at <device>.`; `There were errors removing <devices>, leftovers may remain in the system` | os-brick in nova-compute | network/CHAP; volume not mapped to this host; device never appeared; stale SCSI devices | src |
| `<map>: remaining active paths: 0`; `<map>: Entering recovery mode: max_retries=<n>`; `<map>: Disable queueing` | multipathd | no path; I/O queued (disk frozen); queue given up, guest sees I/O errors | src |
| `<program>: server <server> not responding, still trying` / `timed out` / `OK` | kernel (NFS) | `hard` mount blocks I/O; `soft` fails it | src |

`openstack volume service list`;
`sudo grep -n "os_brick" /var/log/kolla/nova/nova-compute.log | grep -E "WARNING|ERROR" | tail -20`;
`journalctl -k | grep -E "detected conn error|session recovery timed out"` (current boot; `-b -1`
after a reboot); `journalctl -u kolla-iscsid-container.service --since "-1h"`;
`docker exec iscsid iscsiadm -m session -P 1` (lab, during a cut: `TRANSPORT WAIT`, `FAILED`).
Kolla-Ansible runs `iscsid -d 8`: lower-case `login failed ...` and `re-opening session` are debug
noise. On the lab, nova-compute and cinder-volume logged nothing while the iSCSI path was broken.
[LAB-VALIDATED: VM-LOG-16] Rows *lab 16*. Lab: 2026.1 (Cinder 28.0.1), Kolla-Ansible 22.2.0
all-in-one, LVM thin over iSCSI (tgtd), no multipath; not seen: driver init failure, heartbeat stop,
create failure, os-brick failure lines. [LAB-VALIDATED: VM-LOG-17] Rows *lab 17* and the iSCSI
commands. Lab: 2026.1, Kolla-Ansible all-in-one, kernel 6.8, open-iscsi 2.1.9, port 3260 dropped 60
s and 180 s; not run: multipath, NFS, Ceph RBD client logs. [DOCUMENTED-UNVERIFIED: VM-LOG-18] Rows
*src*. With Ceph RBD, librbd inside QEMU logs nowhere useful by default.

### Glance

| Line | Where | Means → next | Seen |
|---|---|---|---|
| `Error contacting glance server '<server>' for '<method>', retrying.` then `done trying.` | nova-compute, nova-api | Nova cannot reach Glance → `GlanceConnectionFailed`, rescheduled; `Exceeded maximum number of retries` when no other compute (lab: four attempts about 1 s apart) | lab 19 |
| `Snapshot extracted, beginning image upload` … `Snapshot image upload complete` | nova-compute | time between = upload; no `complete` = upload failed → *Snapshot never finishes* | lab 19 |
| `trying to snapshot a non-running instance: (state: 4 expected: 1)` | nova-compute | shut-off instance, cold snapshot | lab 19 |
| `Image format matched and virtual size computed: <n>` | glance-api | about all a successful upload leaves at INFO | lab 19 |
| `PUT /v2/images/<image-id>/file` / `GET .../file` | `glance-api-uwsgi.log` | upload / download; no request id, grep the image id | lab 19 |
| `Image storage media is full`; `Image exceeds the storage quota`; `The incoming image is too large` (413); `Insufficient permissions on image storage media` (503) | glance-api | store full; Glance quota; `image_size_cap`; store permissions or Ceph caps | src |
| `Download image error`; `Performing standard snapshot because direct snapshot failed: <error>`; `Failed to snapshot image`; `Image signature verification failed` | nova-compute | RBD download fallback; RBD direct snapshot refused; snapshot failed; signature mismatch | src |

`sudo grep "<nova-request-id>" /var/log/kolla/glance/glance-api.log`;
`sudo grep "<image-id>" /var/log/kolla/glance/glance-api-uwsgi.log | tail`;
`sudo grep -n "<server-id>" /var/log/kolla/nova/nova-compute.log | grep -E "snapshot|Snapshot|glance"`.
[LAB-VALIDATED: VM-LOG-19] Rows *lab 19*. Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Glance file
store, local qcow2 disks, `glance_api` stopped during a boot; not injected: any upload failure, RBD,
signed images. [DOCUMENTED-UNVERIFIED: VM-LOG-20] Rows *src*.

### libvirt, QEMU and kernel

| Line | Where | Means → next | Seen |
|---|---|---|---|
| `<ts>: starting up libvirt version: <v>, ... qemu version: <v>, kernel: <r>, hostname: <host>` + QEMU command line | instance log | each QEMU start; `-incoming` = migration destination | lab 21 |
| `<ts>: shutting down, reason=shutdown` | instance log | guest's own power-off, or QEMU on SIGTERM; with no API action → console log | lab 21 |
| `<ts>: shutting down, reason=destroyed` | instance log | libvirt killed it (hard reboot, delete, stop after the guest ignored ACPI) | lab 21 |
| `<ts>: shutting down, reason=crashed` | instance log | QEMU exited with no shutdown event (OOM killer, abort): no QEMU line → kernel log at the same UTC minute | lab 21 |
| `terminating on signal 15 from pid <pid> (<process>)` | instance log (QEMU) | normal when the sender is the libvirt daemon; another sender is worth investigating; `()` = sender already gone | lab 21 |
| `VM Stopped (Lifecycle Event)`; `Instance shutdown by itself. Calling the stop API.` | nova-compute | power sync stops it in the DB, does not restart it (lab: event 15 s after the stop) | lab 21 |
| `... error : virQEMUCapsCacheLookupDefault:<n> : ... the accel 'kvm' is not supported by '/usr/bin/qemu-system-<arch>' ...` | libvirtd.log | about 60 lines of noise at each libvirtd start | lab 21 |
| `initiating migration`; `shutting down, reason=migrated` / `reason=failed`; `panic <details>` | instance log | migration source; start or incoming migration failed; guest panic | src |
| `KVM internal error. Suberror: <n>`; `error: kvm run failed <errno text>` | instance log, no prefix | KVM could not handle a guest exit; check the host kernel log | src |
| `<command> invoked oom-killer: ...` then `Out of memory: Killed process <pid> (<command>) ...` | kernel | the first names who asked for memory, the second who was killed (`qemu-kvm` or `qemu-system-x86`) → *Shut off by the host OOM killer* | src |
| `Memory cgroup out of memory:` | kernel | a cgroup (container) limit, not the host | src |
| `INFO: task <command>:<pid> blocked for more than <n> seconds.` | kernel | hung `qemu-kvm` almost always waits on storage (NFS, iSCSI, Ceph). Do not follow the hint in the message to disable it | src |
| `<interface>: dropped over-mtu packet: <length> > <mtu>` | kernel (OVS datapath) | → *Tunnel MTU mismatch* | src |
| `nf_conntrack: table full, dropping packet` | kernel | new connections dropped for every instance of the host | src |
| `EXT4-fs (<dev>): Remounting filesystem read-only`; `kvm_intel: VMX not enabled (by BIOS) ...` | kernel | instances directory unwritable; no `kvm` instances possible | src |

"My instance stopped": `openstack server event list <server-id>`, then
`docker exec nova_libvirt grep -E "starting up|shutting down|initiating migration|terminating on signal|KVM internal error|panic" /var/log/libvirt/qemu/<instance-name>.log`,
then for `reason=crashed` `journalctl -k -o short-iso-precise --since "<time>" --until "<time>"`.
Console: `openstack console log show --lines 50 <server-id>`, or
`docker exec -u root nova_compute tail -n 50 /var/lib/nova/instances/<server-id>/console.log`.
[LAB-VALIDATED: VM-LOG-21] Rows *lab 21* and these commands (except `journalctl -k`). Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, libvirt 10.0.0, QEMU 8.2.2, QEMU killed with SIGKILL and SIGTERM,
server stop and hard reboot; not run: live migration, KVM errors, panic, the OOM killer.
[DOCUMENTED-UNVERIFIED: VM-LOG-22] Rows *src* and the kernel commands: `journalctl -k` reads the
current boot only; `journalctl -k -b -1` needs a persistent journal ("boot is not found" otherwise);
`dmesg -T` times can be wrong.

### Messaging and database lines in a service log

If several services or hosts log these lines in the same minutes, the cause is the broker or the
database: hand over to `openstack-incident-analysis`.

| Line | Means → next | Seen |
|---|---|---|
| `[<id>] AMQP server on <host>:<port> is unreachable: <error>. Trying again in <n> seconds.` | that RabbitMQ node down or filtered; the client tries the other `transport_url` hosts (lab: reconnected elsewhere 10 s later with one node down) | lab 23 |
| `[<id>] Reconnected to AMQP server on <host>:<port> via [amqp] client with port <port>.` | end of the client's outage | lab 23 |
| `A recoverable connection/channel error occurred, trying to reconnect: <error>` | one line is normal during a broker restart; many across services is not | lab 23 |
| `Unexpected error while reporting service status: ... DBConnectionError: (pymysql.err.OperationalError) (2003, "Can't connect to MySQL server on '<addr>' (timed out)")` | nova-compute heartbeat could not reach the database (proxy or VIP gone) | lab 23 |
| `SQL connection failed. <n> attempts left.` | service start cannot connect; Kolla-Ansible sets `max_retries = -1`, so the counter goes negative | lab 23 |
| `Timed out waiting for nova-conductor.  Is it running? ...` | nova-compute start, conductor not answering | lab 23 (control-plane start after reboot only) |
| `The broker has blocked the connection: connection blocked, see broker logs` / `The broker has unblocked the connection` | RabbitMQ memory or disk alarm: publishing stops cluster-wide | lab 24 |
| `MessagingTimeout: Timed out waiting for a reply to message ID <msg-id>` | no reply within `rpc_response_timeout` (60 s); the request may still have been processed | lab 10 (RabbitMQ down); lab 23 only at control-plane start, not from the injected broker stop |
| `AMQP server <host>:<port> closed the connection. Check login credentials: <error>` | logged for any `Socket closed`, not only credentials | src |
| `DBConnectionError` with code 2002 / 2003 / 2006 / 2013 / 1047; `OperationalError (9001, …)` | local socket or name / host and port / server gone / lost during query / Galera node not synced; 9001 = ProxySQL has no healthy backend | 2003, 2013, 9001 lab 23; others src |
| `DBDeadlock` (1213) | occasional: usually retried, harmless | src |

[LAB-VALIDATED: VM-LOG-23] Rows *lab 23*. Lab: 2026.1, Kolla-Ansible 22.2.0, three controllers
(RabbitMQ cluster, Galera behind ProxySQL), two computes, RabbitMQ stopped on one then all nodes,
ProxySQL stopped on all controllers; lab run recorded in the page body only. A 90 s stop of every
RabbitMQ node produced no `MessagingTimeout`. Not seen on that run: `Check login credentials`,
`Lost connection to nova-conductor ...` (seen on the item 10 run), `DBDeadlock`.
[LAB-VALIDATED: VM-LOG-24] Rows *lab 24*. Lab: 2026.1, Kolla-Ansible 22.2.0, 3 controllers, RabbitMQ
4.2.9 with Khepri, forced memory alarm; not seen: disk alarm, `Failed to publish message`.
[DOCUMENTED-UNVERIFIED: VM-LOG-25] Rows *src*.

### Keystone and authentication lines

| Line | Where | Means → client gets | Seen |
|---|---|---|---|
| `Authorization failed. <message> from <client address>` | `keystone.log`, WARNING | wrong password, unknown user or refused token → 401 | lab 26 |
| `Authorization failed for token` (`InvalidToken: Token authorization failed`) | each service's log (keystonemiddleware), WARNING | the user's token is invalid: expired, revoked, unknown to this node → 401 | lab 26 |
| `Unable to validate token: <error>` | each service's log (keystonemiddleware), CRITICAL | the service cannot use Keystone (unreachable, its own `[keystone_authtoken]` credentials refused, HTTP error) → 503 (lab: 3.6 s after Keystone stopped) | lab 26 |
| `Starting key rotation with <n> key files: [...]`, `Current primary key is: <n>` | `keystone.log` | Fernet rotation; nodes must end with the same keys | lab 26 |
| `Bad response code while validating token: <status> <message>` | keystonemiddleware, ERROR | unexpected HTTP error → 503 | src |
| `Identity server rejected authorization` | keystonemiddleware, INFO (hidden by default) | service credentials refused | src |
| `Either [<group>] key_repository does not exist or Keystone does not have sufficient permission to access it: <path>` | `keystone.log`, ERROR | this node cannot issue or validate tokens | src |
| `Could not recognize Fernet token`; Keystone's `Unable to validate token: <error>` | `keystone.log`, DEBUG only | Fernet keys differ between nodes; caller gets 404 | src |

401 with WARNING `Authorization failed for token` is a token problem (one user, or every user on
some nodes after a rotation); 503 with CRITICAL `Unable to validate token` is a service that cannot
use Keystone. `sudo sh -c 'grep -l "Unable to validate token" /var/log/kolla/*/*.log'`;
`sudo grep -c "Authorization failed for token" /var/log/kolla/nova/nova-api.log`.
[LAB-VALIDATED: VM-LOG-26] Rows *lab 26*. Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, one
Keystone, no HAProxy; not seen: `Bad response code`, refused service credentials, key repository
errors, a Fernet mismatch between nodes. [DOCUMENTED-UNVERIFIED: VM-LOG-27] Rows *src*, and: token
expiry is checked against the validating node's clock, so a clock ahead gives 401 for valid tokens.
The sources disagree on Keystone's wording for an expired token (one page says
`Failed to validate token`); the line above is the Keystone page's.

## Changing log levels

Every change below is *State-changing*. Note the current value first, change one host and one
service or module, check room for the extra volume
(`sudo df -h "$(sudo readlink -f /var/log/kolla)"`; `/var/log/kolla` is shared by every service of
the host), and undo as soon as you have what you need.

**Debug for one service on one host (Kolla-Ansible).** *State-changing*: edits the configuration and
restarts the container, about a minute (62 s on the lab: the stop waits up to
`docker_graceful_timeout`, 60 s); the service is unavailable meanwhile; for `nova_compute` the
instances keep running. Undo with the reverse commands, or the next `kolla-ansible reconfigure`
rewrites the file.

```bash
sudo grep -n '^debug' /etc/kolla/nova-compute/nova.conf     # expect debug = False; first match is [DEFAULT]
sudo sed -i '0,/^debug = False/s//debug = True/' /etc/kolla/nova-compute/nova.conf
sudo systemctl restart kolla-nova_compute-container.service
sudo grep -c ' DEBUG ' /var/log/kolla/nova/nova-compute.log # the count grows
# undo
sudo sed -i '0,/^debug = True/s//debug = False/' /etc/kolla/nova-compute/nova.conf
sudo systemctl restart kolla-nova_compute-container.service
```

Use `systemctl restart` of the unit, not `docker restart`. A hung service:
`sudo kill -USR2 <pid-of-the-service>` (host pid from `sudo docker top nova_compute`) writes a Guru
Meditation report (over 2000 lines) to `docker logs` and the unit journal; the service kept running.
[LAB-VALIDATED: VM-LOG-28] Lab: 2026.1, Kolla-Ansible all-in-one; debug on and off for
`nova_compute` and the report were run. Not run: a report under uWSGI (SIGUSR2 is intercepted
there), other services.

Not run on a lab [DOCUMENTED-UNVERIFIED: VM-LOG-29]: *State-changing*, whole service on every host:
`nova_logging_debug: "True"` (or `<service>_logging_debug`) in `globals.yml` and
`kolla-ansible reconfigure`, which restarts the service everywhere; undo needs the same reconfigure.
Any: `crudini --set /etc/nova/nova.conf DEFAULT debug true` then `systemctl restart <unit>`, undo
the same way. To see keystonemiddleware's INFO lines, `default_log_levels` must be set for that
service: it replaces the whole default list (copy the defaults, keep the service's additions, change
only `keystonemiddleware=WARN` to `keystonemiddleware=INFO`), then restart; undo by removing the
line and restarting.

**Open vSwitch, one module.** *State-changing*: the log can grow very fast on a busy compute and
costs CPU; instances are not affected; lasts until undone or the daemon restarts. Kolla-Ansible:
prefix with `docker exec openvswitch_vswitchd`.

```bash
ovs-appctl vlog/list | grep -E 'console|bridge|rconn'   # note current levels (console, syslog, file)
ovs-appctl vlog/set bridge:file:dbg
ovs-appctl vlog/set rconn:file:dbg
# undo: the level you noted, info with Kolla-Ansible's -vfile:info
ovs-appctl vlog/set bridge:file:info
ovs-appctl vlog/set rconn:file:info
```

Never run `ovs-appctl vlog/set` without arguments (every module to `dbg`) or `vlog/close` on
production. [LAB-VALIDATED: VM-LOG-30] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, ML2/OVS, Open
vSwitch 3.7.1; 1799 bytes in 30 s on an idle lab. Not run: package installs,
`vlog/disable-rate-limit`.

**libvirt at runtime (Kolla-Ansible).** *State-changing*: writes far more and can fill the disk; no
daemon restart, instances keep running; lost when the daemon restarts. One compute at a time.

```bash
docker exec nova_libvirt virt-admin -c libvirtd:///system daemon-log-filters    # note: Logging filters: ...
docker exec nova_libvirt virt-admin -c libvirtd:///system daemon-log-outputs    # note: Logging outputs: ...
docker exec nova_libvirt virt-admin -c libvirtd:///system daemon-log-outputs "1:file:/var/log/kolla/libvirt/libvirtd-debug.log 3:file:/var/log/kolla/libvirt/libvirtd.log"
docker exec nova_libvirt virt-admin -c libvirtd:///system daemon-log-filters "3:remote 4:event 3:util.json 3:util.object 3:util.dbus 3:util.netlink 3:node_device 3:rpc 3:access 1:*"
```

Undo: set back exactly the noted values with the same two commands; empty filters (the Kolla-Ansible
case) are restored with `daemon-log-filters ""`; never restore outputs with an empty string. Delete
the debug file. Persistent, *State-changing*: `nova_libvirt_logging_debug: true` in
`/etc/kolla/globals.yml` (or the compute's `host_vars`), then
`kolla-ansible reconfigure -i <inventory> --limit <compute> --tags nova`; this restarts
`nova_libvirt`. Precondition: no migration in progress
(`openstack server migration list --host <compute>` shows none whose status is other than
`confirmed`, `reverted`, `error`, `failed`, `completed`, `cancelled` or `done`; `--status running`
alone misses most) and `nova_libvirt` in the host's PID and cgroup namespaces (see *Restarts that
keep instances running* in compute-host-events.md); otherwise every instance can stop or a migration
fail. Undo: remove the variable and rerun, same precondition. The debug lines stay in
`libvirtd.log`: leave them to logrotate, do not truncate. [LAB-VALIDATED: VM-LOG-31] Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, libvirt 10.0.0; runtime debug and undo (780 KB per instance start),
persistent debug and undo (4 min 33 s and 3 min 47 s, instance kept its QEMU pid). Not run: package
installs (modular `virtqemud`), a migration in progress.

Not run on a lab [DOCUMENTED-UNVERIFIED: VM-LOG-32]: `ovs-appctl vlog/disable-rate-limit <module>`
(only briefly; undo `vlog/enable-rate-limit <module>`); modular libvirt
(`virt-admin -c virtqemud:///system daemon-timeout --timeout 0` first, which has no undo until the
next daemon restart, then the same output and filter commands with
`/var/log/libvirt/virtqemud-debug.log 3:journald`). Persistent journal, *State-changing* (uses disk
under `/var/log/journal` up to `SystemMaxUse`; services keep running; precondition: free space on
the file system of `/var/log`; undo: remove the drop-in, restart `systemd-journald`, delete
`/var/log/journal` if not wanted): `mkdir -p /etc/systemd/journald.conf.d`,
`printf '[Journal]\nStorage=persistent\n' > /etc/systemd/journald.conf.d/persistent.conf`,
`systemctl restart systemd-journald`, `journalctl --flush`.
