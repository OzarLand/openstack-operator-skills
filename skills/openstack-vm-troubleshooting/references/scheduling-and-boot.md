# Scheduling and boot failures

Builds that fail before or while an instance is placed and its root disk is
prepared, and the compute and Placement records the scheduler depends on.
Distilled from the OzarLand `openstack-vm-runbooks` repository
(`scheduling/` pages) at commit `babdd8c`. Everything in this file is an
`[Addition]` to the book unless it carries a book chapter tag. Each procedure carries
its validation tag (rule 12 of the safety rules); untagged technical text is
unverified.

Labs referred to below, all OpenStack 2026.1 with Kolla-Ansible 22.2.0:
*multinode lab* = 3 controllers, 2 computes, Ubuntu 24.04, ML2/OVS, local
instance disks, no Cinder; *all-in-one lab* = one node, ML2/OVS, local disks
or Cinder LVM (thin) over iSCSI where stated. Commands are `openstack` CLI
unless prefixed "Kolla-Ansible:". On Kolla-Ansible `nova-manage` runs as
`sudo docker exec nova_api nova-manage ...`, without `-it` (it fails outside
an interactive terminal); elsewhere, run it where `nova.conf` has
`[api_database]` and `[placement]`. `resource provider` and
`allocation candidate` commands need the `osc-placement` plugin.

## Contents

- Exceeded maximum number of retries
- No valid host with free capacity
- Image larger than the flavor disk
- Boot from volume fails
- Compute disabled, forced down, renamed
- Placement allocations out of sync

## Exceeded maximum number of retries

**Recognize.** New instance `ERROR`, often after a longer wait, fault
`Exceeded maximum number of retries. Exhausted all hosts available for
retrying build failures for instance <server-id>.` (code 500). Every compute
the scheduler offered tried and failed; the fault is a summary, the cause is
the error each compute hit, usually the same on all. Not the scheduler's
`No valid host was found`, which comes before any compute tries. Running
instances are not affected.

**Read-only checks.**
- `openstack server show <server-id> -c status -c fault -c created`.
- `openstack server event list <server-id>`, then
  `openstack --os-compute-api-version 2.84 server event show <server-id> <request-id>`
  for the `compute_...` events and their hosts. On the lab the events carried
  no error, details or traceback (the compute that failed showed `Success`):
  use them for the hosts only.
- `openstack compute service list --service nova-compute`; `openstack network agent list`.
- On each compute named: Kolla-Ansible: `sudo grep <server-id> /var/log/kolla/nova/nova-compute.log`;
  Any: the nova-compute log. Lab example: `Instance failed to spawn:
  nova.exception.InvalidMachineType: 'pc-i440fx-1.0' is not valid/supported machine type`;
  conductor: `Failed to compute_task_build_instances: Exceeded maximum number of retries`.

[LAB-VALIDATED: VM-SCH-01] Recognition, checks and causes 1 and 3. Lab:
2026.1, Kolla-Ansible 22.2.0, multinode lab, ML2/OVS, local disks; image with an unsupported
`hw_machine_type`: tried compute-1 then compute-2, `ERROR` after 34 s (two
attempts: two computes give one alternate, whatever `max_attempts` says).
One compute broken the same way: first build failed there and succeeded on
compute-2 (37 s), the next three went straight to compute-2. Not run: cause 2,
the "Any:" lines.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| One compute fails, a later attempt or other builds succeed elsewhere | 1: one broken compute |
| Same error on different computes, every new instance fails | 2: dependency shared by every compute (storage unreachable, libvirt misconfigured everywhere) |
| Same error everywhere, only for this flavor or image | 3: request no compute can satisfy at spawn (image property, device) |
| `ComputeResourcesUnavailable` (claim failed) | see *No valid host with free capacity* |
| `os_brick` volume connection error | see *Boot from volume fails*, cause 4 |
| `binding_failed`, fault after about 20 s | dead agent at request time: see *Stuck in BUILD waiting for vif-plugged* in instance-lifecycle.md |

[DOCUMENTED-UNVERIFIED: VM-SCH-02] Mechanism: the scheduler returns a host
plus alternates, `[scheduler] max_attempts` in all (Nova default 3;
Kolla-Ansible 2026.1 writes `max_attempts = 10`, seen in the lab's
`nova.conf`). Retried: resource claim failures and spawn errors. Not retried
(`Build of instance <server-id> aborted: ...` on the first compute): network
allocation failure, block device step of boot from volume, image or flavor
mismatch. A compute that fails every build is weighed last
(`build_failure_weight_multiplier`, default 1000000.0, counted when
`[compute] consecutive_build_service_disable_threshold` is non-zero, default
10) but, on 2026.1, not disabled despite the option's name.

**Fix options.**
1. Fix the error each compute reported (the rows above, compute disk full,
   `nova_libvirt` logs), then build again: an instance in `ERROR` from a
   failed build is not retried by Nova. Do not retry before finding it.
2. *State-changing*: keep the broken compute out while repairing:
   `openstack compute service set --disable --disable-reason "<why>" <host> nova-compute`
   (no new instance lands on it; running instances unaffected). Undo:
   `openstack compute service set --enable <host> nova-compute`. A successful
   build resets the failure count.
   [LAB-VALIDATED: VM-SCH-03] Lab: 2026.1, Kolla-Ansible 22.2.0, multinode
   lab, ML2/OVS, local disks; disable, repair (restart of `nova_compute`), enable and the test build
   on the repaired compute were run. Not run: repairs for cause 2.

**Verify.** *State-changing* (test instance, needs quota):
`openstack server create --image <image> --flavor <flavor> --network <network> --wait <test-name>`;
`openstack server show <test-name> -c status -c OS-EXT-SRV-ATTR:host` is
`ACTIVE`, on the formerly failing compute if repaired and enabled;
`openstack server delete --wait <test-name>`. Covered by VM-SCH-03.

## No valid host with free capacity

Capacity exists but nothing lands on it [Book: Ch. 5].

**Recognize.** `ERROR`, `OS-EXT-SRV-ATTR:host` empty (no host was ever
selected), Placement shows room. The message tells where scheduling stopped
(observed on the lab):
| Fault | Stopped at |
|---|---|
| `No valid host was found. There are not enough hosts available.` | a filter rejected every host |
| `No valid host was found. ` | Placement returned no candidate |
| `Host '<host>' is not mapped to any cell` | the chosen host is not mapped to a cell |

**Read-only checks.**
1. `openstack compute service list --service nova-compute -c Host -c Zone -c Status -c State`.
2. `nova-manage cell_v2 list_hosts`: a host in 1 but not here is unmapped.
3. `openstack --os-placement-api-version 1.22 allocation candidate list --resource VCPU=<vcpus> --resource MEMORY_MB=<ram> --resource DISK_GB=<disk> --forbidden COMPUTE_STATUS_DISABLED`
   (as Nova asks; without `--forbidden` a disabled compute still appears).
4. `nova-scheduler.log` for the request ID (`openstack server event list <server-id>`).
5. `openstack resource provider inventory list <rp-uuid>` (total, reserved,
   allocation_ratio) and `openstack resource provider usage show <rp-uuid>`.
   `openstack hypervisor list` no longer shows capacity with recent microversions.

[LAB-VALIDATED: VM-SCH-04] Recognition and checks for four causes. Lab:
2026.1, Kolla-Ansible 22.2.0, all-in-one lab (one compute), ML2/OVS, osc-placement
4.8.0. Unmapped host: `list_hosts` empty, one candidate, `HostMappingNotFound`
in the conductor log. `reserved_host_memory_mb = 15000` on a 16 GB compute:
check 3 empty, scheduler `Got no allocation candidates from the Placement API`
(one such build ended in `MessagingTimeout` instead, cause not established).
Disabled service: one candidate without `--forbidden`, none with it.
Second anti-affinity member: `Filter ServerGroupAntiAffinityFilter returned 0 hosts`.
Not run: stale allocations, missing trait or resource class, a `down`
service, anything needing several computes.

**Tell the causes apart.**
| Observation | Cause |
|---|---|
| `is not mapped to any cell`; host missing from `list_hosts` | host not mapped |
| Candidate list empty; low `allocation_ratio` or high `reserved` | inventory or ratios |
| `usage show` above the instances on the host; `placement audit` reports orphans | stale allocations: see *Placement allocations out of sync* |
| Scheduler log `Filter <Name> returned 0 hosts` | that filter (aggregate extra specs, anti-affinity, AZ, NUMA, ComputeFilter, image properties) |
| Check 1 `disabled` or `down` | see *Compute disabled, forced down, renamed* |
| Candidates empty for one flavor only | resource class or trait no host has (`resource provider trait list`) |

**Fix options.**
1. Unmapped host. *State-changing*: writes the host mapping to the Nova API
   database, no impact on running instances, undo `delete_host`:
   `nova-manage cell_v2 discover_hosts --verbose` (lab: `Creating host mapping
   for compute host '<host>'`), then `nova-manage cell_v2 list_hosts`.
   Kolla-Ansible 22.2.0 writes `discover_hosts_in_cells_interval = -1` and maps
   computes it deploys; a host added or re-created outside it needs this.
2. Wrong reserved value or ratio. *State-changing*: set `reserved_host_*` or
   `*_allocation_ratio` in `[DEFAULT]` of the compute's `nova.conf`, restart
   nova-compute; Kolla-Ansible: in `/etc/kolla/config/nova/nova-compute.conf`,
   then `kolla-ansible reconfigure -i <inventory> --tags nova` (recreates
   changed `nova_compute` containers, running instances unaffected). Recheck
   `inventory list` about a minute later. Prefer Nova configuration to editing
   ratios in Placement, which the compute overrides.
3. Disabled compute. *State-changing*: instances will be scheduled there
   again; first make sure the reason no longer applies:
   `openstack compute service set --enable <compute-host> nova-compute`.

[LAB-VALIDATED: VM-SCH-05] Fixes 1, 2 (removing the `reserved_host_memory_mb`
override with `reconfigure`: reserved back to 512) and 3, and deleting the
anti-affinity members, each followed by a test instance. Lab: 2026.1,
Kolla-Ansible 22.2.0, all-in-one lab, ML2/OVS. Not run: changing allocation ratios.

[DOCUMENTED-UNVERIFIED: VM-SCH-06] Diagnosis and repair of stale allocations
(`placement audit`, `heal_allocations`), a missing resource class or trait,
a `down` service, ratio changes, setting
`[scheduler] discover_hosts_in_cells_interval = 300` (check how your
deployment tool handles it first), and every multi-compute case.

**Verify.** Check 3 lists the host; a test instance (`--flavor <flavor>
--image <image> --network <network> sched-test`) is `ACTIVE` with a host;
delete it. Covered by VM-SCH-05.

## Image larger than the flavor disk

**Recognize.** `server create` refused at once (HTTP 400 or 403), or
`ERROR` later with `Build of instance <server-id> aborted: ...` (no retry
elsewhere), one of:
- `Flavor's disk is too small for requested image. Flavor disk is <n> bytes, image is <n> bytes.`
- `Flavor's disk is smaller than the minimum size specified in image metadata. ...`
- `Volume is smaller than the minimum size specified in image metadata. ...`
- `Flavor's memory is too small for requested image.`
- `Only volume-backed servers are allowed for flavors with zero disk.`
- nova-compute log: `<base> virtual size <n> larger than flavor root disk size <n>`.
Every boot of that image with that flavor fails; running instances unaffected.

**Read-only checks.** `openstack image show <image> -c size -c virtual_size -c min_disk -c min_ram -c disk_format`;
`openstack flavor show <flavor> -c disk -c ram`. Compare flavor `disk` (GB)
with image `size` and `virtual_size` (bytes) and `min_disk` (GB).

**Why it passes first and fails later.** The API check (before scheduling)
compares the image **file** size and `min_disk` with the flavor disk, RAM
with `min_ram`, a Nova-created volume with `min_disk`, and refuses a zero-disk
flavor for image-backed boot except for admins (default policy). The compute
check (after download, every image backend) compares the **virtual** size. A
compressed qcow2 with `min_disk` unset passes the first and aborts on the
second.

| Observation | Cause |
|---|---|
| `virtual_size` or `min_disk` above flavor `disk` | 1: flavor too small |
| Accepted, aborted on the compute; `min_disk` 0 or too low | 2: `min_disk` not set |
| `Only volume-backed servers ... zero disk` (403 for a member) | 3: zero-disk flavor |
| `Flavor's memory is too small` | 4: flavor RAM below `min_ram` |

[LAB-VALIDATED: VM-SCH-07] Recognition, checks and causes 2, 3, 4. Lab:
2026.1, Kolla-Ansible 22.2.0, all-in-one lab, local qcow2, OSC 9.0.0; CirrOS
grown to 2 GB virtual (21 MB file), 1 GB flavor: accepted, compute log 12 s
later, `ERROR` 17 s after the request, no retry. Not run: the API refusal on
the image file size, a Ceph RBD image backend.

**Fix options.**
1. Causes 1 and 3: a flavor whose `disk` covers `virtual_size` (rounded up
   to GB) and `min_disk`, or boot from volume:
   `openstack server create --image <image> --boot-from-volume <GB> ...`.
   With OSC 9.0.0 that volume is not deleted with the instance (stays `available`).
2. Cause 2. *State-changing*: changes image metadata, every later boot with
   a smaller flavor is refused at the API; running instances unaffected;
   undo: set the previous value back:
   `openstack image set --min-disk <GB> <image>`.
3. Cause 4: a flavor with enough RAM, or, if the image value is wrong,
   *State-changing* (same warning): `openstack image set --min-ram <MB> <image>`.

[LAB-VALIDATED: VM-SCH-08] Fixes 1 to 3 as written (`--min-disk 2` then
refused at once with HTTP 400; `--min-ram 1024` refused; a member booted the
zero-disk flavor with `--boot-from-volume 1`; `--boot-from-volume 3` and a
larger flavor reached `ACTIVE`). Lab: 2026.1, Kolla-Ansible 22.2.0,
all-in-one lab, local disks. Not run: Ceph RBD.

[DOCUMENTED-UNVERIFIED: VM-SCH-09] The API refusal when the image file
itself exceeds the flavor disk, and the compute-side virtual size check on a
Ceph RBD image backend. Not covered: resizes to a smaller disk, rebuilds,
drivers other than libvirt.

**Verify.** *State-changing*: test instance with that image and flavor
reaches `ACTIVE`, then `openstack server delete --wait <test-name>`.

## Boot from volume fails

Root disk is a Cinder volume (`--boot-from-volume <GB>`, a volume snapshot,
or `--volume <volume-id>`); local-root instances still build. The failure
itself risks no data, but each blind retry creates another volume (quota,
backend space).

**Read-only checks.**
1. `openstack server show <server-id> -c status -c fault -c OS-EXT-SRV-ATTR:host -c created`.
2. `openstack server volume list <server-id>`; `openstack volume show <volume-id> -c status -c size -c bootable -c availability_zone -c volume_image_metadata`.
3. `openstack --os-volume-api-version 3.3 volume message list | grep <volume-id>`.
4. `openstack volume service list`; `openstack image show <image-id> -c disk_format -c min_disk -c size`.
5. Logs: Kolla-Ansible: `/var/log/kolla/nova/nova-compute.log` (host field is
   empty on an `ERROR` instance: search every compute for the server ID);
   `/var/log/kolla/cinder/cinder-scheduler.log`, `cinder-volume.log`.

**Tell the causes apart.** Nova polls Cinder every 3 s, 61 times by default
(`block_device_allocate_retries` + 1): about 3 minutes, then aborts without
trying another compute.
| Observation | Cause |
|---|---|
| Refused at once: `Volume is smaller than the minimum size ...`, `Block Device <volume-id> is not bootable.`, AZ mismatch, `Block Device Mapping is Invalid` | 1: request refused by Nova |
| Fault `... waited 0 seconds or 1 attempts. And its status is error.` within seconds; volume `error` | 2: Cinder could not create (backend, space, quota, driver; check 3 gives the reason, e.g. `Could not find any available weighted backend.`) |
| Fault `... waited 185 seconds or 61 attempts. And its status is creating.` after ~3 min; volume `creating`/`downloading` | 3: not ready in time, including a stopped `cinder-volume` |
| `Exceeded maximum number of retries.`; volume `available`; `os_brick` error in nova-compute log | 4: compute cannot connect (iSCSI, multipath, RBD) |
| `ACTIVE`, console log empty or "No bootable device" | 5: no bootable system (blank volume, firmware or disk bus) |

[LAB-VALIDATED: VM-SCH-10] Recognition, checks and causes 1 to 5. Lab:
2026.1 (Nova 33.0.3), Kolla-Ansible 22.2.0, all-in-one lab, Cinder LVM
(thin) over iSCSI, OSC 9.0.0. Cause 2: 500 GB on a 380 GB pool, `ERROR` in
13 s, `CapacityFilter` in cinder-scheduler. Cause 3: `cinder-volume` stopped,
`ERROR` after 3 min 16 s, volume `creating`; started again, it created the
volume (`available` 27 s later). Cause 4: `iscsid` stopped, `ERROR` in ~40 s,
`Failed to login iSCSI target ... (exit code 20)` then
`os_brick.exception.VolumeDeviceNotFound`. Cause 5: blank `--bootable`
volume, `ACTIVE`, empty console; a qcow2 declared `raw` was refused by Cinder
(`ImageUnacceptable`, volume `error`: cause 2). Not run: `cross_az_attach`,
Ceph. On older releases the fault can read `Failure prepping block device.`

**Fix options.** Read-only checks first, then the smallest change.
1. Cause 1: fix the request (volume ≥ `min_disk`, boot index 0, same AZ when
   `[cinder] cross_az_attach = False`).
2. Cause 3 or 4, volume ended `available`: fix the host (Kolla-Ansible:
   `sudo docker ps -a --filter name=iscsid`, `-a` shows a stopped container;
   *State-changing*, no undo given: `sudo systemctl start kolla-iscsid-container.service`),
   then boot from it:
   `openstack server create --volume <volume-id> --flavor <flavor> --network <network> <name>`.
3. Cause 5, reuse the volume. *Destructive*: deletes the failed instance;
   with "Delete On Termination" `True` **the volume and its data are deleted
   too**; check first with
   `openstack --os-compute-api-version 2.79 server volume list <server-id>`
   and, if `True`, build from a new volume instead. No undo.
   `openstack server delete --wait <server-id>`, then `server create --volume`.
   [LAB-VALIDATED: VM-SCH-11] Fixes 1 to 3 as observed: refusals, `iscsid`
   started, boot with `--volume` from the left-over volume (causes 3 and 4),
   delete with Delete On Termination `False` leaving the volume `available`.
   Lab: 2026.1, Kolla-Ansible 22.2.0, all-in-one, Cinder LVM over iSCSI. Not run: the `True` case, Ceph;
   the command used to start `iscsid` on the lab was not recorded.
4. [DOCUMENTED-UNVERIFIED: VM-SCH-12] Not run on the lab:
   - Cause 2: fix what Cinder reported (`openstack quota show <project-id>`;
     LVM space `sudo vgs cinder-volumes`), retry once. A stopped
     `cinder-volume`, *State-changing* (volumes being created or attached
     through it can fail; read why it stopped first): Kolla-Ansible:
     `sudo systemctl restart kolla-cinder_volume-container.service`.
     The page also lists "cinder-volume down" under volume `error`; the lab
     showed `creating` (cause 3): follow the lab.
   - Cause 3 always over 3 min: Cinder image-volume cache, `raw` images on
     Ceph; or *State-changing* `block_device_allocate_retries = 180` (about
     9 min) in `[DEFAULT]`; Kolla-Ansible:
     `/etc/kolla/config/nova/nova-compute.conf`, then
     `kolla-ansible reconfigure -i <inventory> --tags nova`; undo: remove and
     reconfigure. Delays the `ERROR` of hopeless builds too.
   - Cause 4, no `iscsid` container: Kolla-Ansible:
     `enable_cinder_backend_iscsi: true` in `globals.yml`, then
     *State-changing* `kolla-ansible deploy -i <inventory> --tags iscsi` in a
     maintenance window. Ceph: the nova-compute log names the RBD error.
   - Cause 5, missing property. *State-changing* (metadata only; undo
     `openstack volume unset --image-property <key> <volume-id>`):
     `openstack volume set --image-property hw_firmware_type=uefi <volume-id>`
     or `openstack image set --property hw_firmware_type=uefi <image-id>`,
     then a **new** build (rebooting does not help: Nova copied the properties
     at build time). Wrong `disk_format`: re-upload, new volume.
5. [DOCUMENTED-UNVERIFIED: VM-SCH-13] *Destructive*: rebuild rewrites the
   boot volume from the image, everything on it is replaced; only for an
   instance that never booted:
   `openstack --os-compute-api-version 2.93 server rebuild --image <image-id> <server-id>`
   (compute API 2.93, block storage 3.68). The source page itself lists
   rebuild of volume-backed instances as not covered.

**Verify.** `ACTIVE`; boot volume `in-use`, `bootable`;
`openstack console log show <server-id> | tail -20` shows the OS starting;
`openstack volume list --project <project-id> --status available --long`
for leftovers (reuse, or the owner decides).

## Compute disabled, forced down, renamed

Two independent fields: **Status** `enabled`/`disabled` (may the scheduler
place here?) and **State** `up`/`down` (heartbeat, or *forced* down).
Mixing them up is how instances get lost.

**Read-only checks.**
1. `openstack compute service list --service nova-compute --host <host> --long`
   (`Forced Down` column with compute API 2.11 or later).
2. Kolla-Ansible: `sudo docker ps --filter name=nova_compute --filter name=nova_libvirt --format '{{.Names}} {{.Status}}'`;
   `sudo grep -e "Connection event" -e "Connection to libvirt lost" /var/log/kolla/nova/nova-compute.log | tail -5`.
3. `openstack resource provider trait list <node-uuid> | grep COMPUTE_STATUS_DISABLED`.
4. `openstack server list --all-projects --host <host> -c ID -c Status`;
   `openstack server migration list --host <host> --type evacuation`.

| Status / State / reason | Cause |
|---|---|
| `disabled`, `up`, reason `AUTO: Connection to libvirt lost...` | 1: libvirt connection lost; re-enables itself on reconnect |
| `disabled`, `up`, other or no reason | 2: disabled by an operator or tool |
| `down`, Forced Down `False` | 3: no heartbeat for `service_down_time` (60 s) |
| `down`, Forced Down `True` | 4: forced down (`set --down`), never set back up |

**What `down` allows.** Resize, cold migration, volume detach: refused
`Service is unavailable at this time.` (409); other actions accepted and
never done. Delete becomes a **local delete**: the record, ports and
allocations go, the guest keeps running unseen; when nova-compute returns
it destroys it (`running_deleted_instance_action = reap`). Evacuate is
allowed (refused with 400 `Compute service of <host> is still in use.` while
`up`). Do not delete instances of a `down` compute.

[LAB-VALIDATED: VM-SCH-14] The four causes, checks and the behaviours above.
Lab: 2026.1, Kolla-Ansible 22.2.0, multinode lab, ML2/OVS, local disks, no Cinder, nested KVM. Cause 1:
`AUTO: Connection to libvirt lost: 0` within 3 s, trait set, builds `No valid
host`, guests kept running; re-enabled 15 s after libvirt started. Cause 3:
`down` 63 s after the last heartbeat; reboot accepted then dropped on return;
deleted instance's guest destroyed 34 s after nova-compute started. Not run:
volume detach (no Cinder), `AUTO:` over an operator reason, trait update error.

**Fix options.**
1. Cause 1: repair `nova_libvirt`; it re-enables. Do not `--enable` while
   libvirt is down (every build would fail there).
2. Cause 2. *State-changing*: ask who set the reason; once resolved and the
   service is `up`: `openstack compute service set --enable <host> nova-compute`.
   Undo: `--disable --disable-reason "<why>"`.
3. Cause 3: start or repair nova-compute (see *nova-compute down, host alive*
   in compute-host-events.md).
   [LAB-VALIDATED: VM-SCH-15] Fixes 1 to 3. Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS, local disks, no Cinder. Not run:
   `--enable` while libvirt down.
4. Cause 4. Nova refuses `--up` while evacuations are `done` (the client
   prints only `failed to set`; see why with `openstack --debug compute
   service set --up <host> nova-compute`). A nova-compute that kept running
   must be restarted. *Destructive*: at start it destroys the local guest
   and, without shared storage, the disks of every instance evacuated from
   this host; precondition: each is `ACTIVE` on its destination and nothing
   is needed from the source copies; no undo. Kolla-Ansible:
   `sudo systemctl restart kolla-nova_compute-container.service`. Then
   *State-changing*, once it has reported and no `done` evacuation remains:
   `openstack compute service set --up <host> nova-compute`, later `--enable`.
   [LAB-VALIDATED: VM-SCH-16] Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS, local disks; `--down` with nova-compute
   running, evacuation, `--up` refused, restart destroyed the source copy,
   record `completed`, `--up` worked. Not run: `--enable` after `--up`,
   forcing down a fenced host.

[DOCUMENTED-UNVERIFIED: VM-SCH-17] `--down` (needs compute API 2.11 or
later) is only for a host that is fenced; never force down a compute whose
instances still run and that is not fenced: Nova then allows local deletes
and evacuations of live instances. Hand over to `openstack-incident-analysis`.

**Renamed, reinstalled or re-added compute.** Service (by host name),
compute node (UUID in `compute_id`) and Placement provider (same UUID,
hypervisor host name) must agree. Checks:
`openstack --os-compute-api-version 2.53 hypervisor list --long -c ID -c "Hypervisor Hostname" -c State`
(ID = node UUID); `openstack resource provider list --name <hypervisor-hostname>`;
`hostname; hostname -f`; Kolla-Ansible:
`sudo docker exec nova_compute cat /var/lib/nova/compute_id` and
`sudo cat /etc/kolla/nova-compute/compute_id`. Healthy: one service, one
hypervisor whose ID is `compute_id`, one provider with that UUID.
| Log (nova-compute) | Cause |
|---|---|
| `Possible rename detected, refusing to start!`; `My hypervisor has existing instances, but I appear to be a new service` | A: host name changed |
| `No local node identity found`; Kolla-Ansible: container loops on `MissingRequiredSource: /var/lib/kolla/config_files/compute_id` | B: `compute_id` lost |
| `Got 409 ... Conflicting resource provider name`; provider UUID not in `hypervisor list` | C: old provider left |
| Kolla-Ansible deploy: `Found multiple compute services with same host name` | two services (short name and FQDN) |

[LAB-VALIDATED: VM-SCH-18] Checks and causes A (simulated with `[DEFAULT]
host`) and B. Lab: 2026.1, Kolla-Ansible 22.2.0, multinode lab, ML2/OVS, compute
without instances. Cause A: the process stayed up, container `healthy`,
service went `down`: read the log, not the container status; `hostnamectl
set-hostname` plus a container restart did not change the container's name.
Not run: a real rename or reinstall, cause C (the attempt gave `Duplicate
compute node record` instead).
- Cause B fix. *State-changing*: rewrites the compute's configuration and
  `compute_id` and restarts its containers; running instances keep running;
  precondition: one hypervisor with this node name. Kolla-Ansible:
  `kolla-ansible reconfigure -i <inventory> -t nova --limit <host>`.
  [LAB-VALIDATED: VM-SCH-19] Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS, local disks; 2 minutes, both files got
  the old ID, service `up`. Not run: the hand-written `compute_id` of other
  deployments, a compute with running instances (the lab compute had none, so
  "running instances keep running" is from documentation).
- [DOCUMENTED-UNVERIFIED: VM-SCH-20] Cause A: give the old name back,
  *State-changing* (`sudo hostnamectl set-hostname <old-host>`; undo: set the
  new name), then Kolla-Ansible `reconfigure ... --limit <old-host>`; renaming
  a registered compute is not supported upstream. Other deployments, cause B:
  write the hypervisor's own UUID (`echo -n <node-uuid> | sudo tee /var/lib/nova/compute_id`,
  `chown nova:nova`); a wrong UUID takes over another compute's records.
- [DOCUMENTED-UNVERIFIED: VM-SCH-21] *Destructive*: delete the second (`down`)
  service, its compute node, host mapping, aggregates and provider:
  `openstack compute service delete <service-id>`; precondition: it is `down`
  and `openstack server list --all-projects --host <that-service-host>` is
  empty; a wrong ID loses the real compute's record; no undo.
- [DOCUMENTED-UNVERIFIED: VM-SCH-22] *Destructive*, cause C: prove the
  provider is a leftover, save `openstack resource provider show --allocations <old-node-uuid> -f json`,
  `placement audit --verbose --delete --resource_provider <old-node-uuid>`,
  `openstack resource provider delete <old-node-uuid>`, then
  `heal_allocations --instance` for instances still on this compute (they have
  no allocation until healed: overcommit). Preconditions and the procedure in
  *Placement allocations out of sync*. No undo for the provider.

**Verify.** One service `up`, `enabled`, Forced Down `False`, recent
`Updated At`; hypervisor ID = `compute_id`; no `COMPUTE_STATUS_DISABLED`;
`openstack allocation candidate list --resource VCPU=1 --resource MEMORY_MB=512 --forbidden COMPUTE_STATUS_DISABLED | grep <node-uuid>`.

## Placement allocations out of sync

**Recognize.** Usually after an evacuation, a failed move, a rebuilt or
renamed compute, or a Placement database restore.
`openstack resource provider usage show <rp-uuid>` above or below the
flavors running there; `No valid host` with room (scheduler `Got no
allocation candidates from the Placement API`); nova-compute repeating at
each resource update `Instance <consumer-uuid> has allocations against this
compute host but is not found in the database.` or `Instance <server-id> has
been moved to another host ... allocations remaining against the source
host`; `resource provider delete` refused `Resource provider has
allocations. (HTTP 409)`. Missing allocations let the scheduler overcommit.
Quota is not affected unless `[quota] count_usage_from_placement = True`.

**Read-only checks.**
1. `openstack resource provider show --allocations <rp-uuid>` (consumers)
   against `openstack server list --all-projects --host <host> -c ID -c Name -c Status -c Flavor`.
2. `openstack --os-placement-api-version 1.12 resource provider allocation show <server-id>` (expect one provider).
3. `nova-manage placement audit --verbose` (no `--delete`: changes nothing;
   rc 3 = orphans found) and `nova-manage placement heal_allocations --dry-run --verbose`
   (rc always 4, proves nothing; read the `[dry-run] Create` lines).

| Observation | Cause |
|---|---|
| Consumer is no server; `audit` lists it; log `not found in the database` | 1: orphaned allocation |
| Instance on another host, allocation on two providers, no move running | 2: leftover source allocation |
| Instance with no allocation; dry-run proposes `Create` | 3: missing allocation |
| Instance with a `task_state`, two providers | normal during a move: `audit` lists the destination as orphaned; **do not touch** |

[LAB-VALIDATED: VM-SCH-23] Recognition (log lines within 20 s, nothing
logged for a missing allocation), checks and discrimination. Lab: 2026.1,
Kolla-Ansible 22.2.0, multinode lab, ML2/OVS, osc-placement 4.9.1, the three causes
injected by hand. Not run: the `No valid host` symptom, the 409 on provider
delete, causes produced by a real evacuation, failed move or restore.

**Before any change.** Save `openstack resource provider show --allocations <rp-uuid> -f json`
and, per consumer, `openstack --os-placement-api-version 1.12 resource provider allocation show <consumer-uuid> -f json`;
every `openstack server migration list` entry final; no instance with a
`task_state`.

**Fix options.**
1. Cause 1. *Destructive*: for each consumer `audit` reports on that
   provider, removes its allocation there; can lose the destination
   allocation of an instance being moved and a migration's allocation that
   `heal_allocations` cannot restore. Always pass `--resource_provider`.
   Undo: `openstack resource provider allocation set` from the saved JSON.
   `nova-manage placement audit --verbose --delete --resource_provider <rp-uuid>` (rc 4).
   [LAB-VALIDATED: VM-SCH-24] Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS, local disks. Not run: the undo. A
   consumer created by another service with a Nova resource class is also
   reported as orphaned: check it first.
2. Cause 2. *State-changing*: removes the allocation on the old provider
   only; undo from the saved JSON:
   `openstack --os-placement-api-version 1.12 resource provider allocation unset --provider <old-rp-uuid> <server-id>`
   (osc-placement 1.8.0+). Do not use `allocation delete` here: it removes
   the allocation on every provider, including the current one.
   [LAB-VALIDATED: VM-SCH-25] Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS, local disks. Not run: the undo.
3. Cause 3. *State-changing*: creates flavor-based allocations, the
   scheduler sees less room at once; dry-run first:
   `nova-manage placement heal_allocations --verbose --instance <server-id>`
   (`Successfully created allocations`, rc 0). Wrong allocation:
   *State-changing* `... --instance <server-id> --force` (replaces it; undo
   from the saved JSON).
   [LAB-VALIDATED: VM-SCH-26] Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS, local disks; one instance and `--force`.
   Not run: healing every instance (no `--instance`), the undo.
4. *Destructive*, last resort: `openstack resource provider allocation delete <server-id>`
   then `heal_allocations --instance <server-id>`; deletes every allocation of
   the consumer, loses migration and nested (vGPU, Cyborg) allocations;
   precondition: `ACTIVE`, `SHUTOFF` or `PAUSED`, no `task_state`, JSON
   saved; undo `allocation set` from it.
   [LAB-VALIDATED: VM-SCH-27] Lab: 2026.1, Kolla-Ansible 22.2.0, multinode, ML2/OVS, local disks; rc 0. Not run: nested
   allocations, the undo.

[DOCUMENTED-UNVERIFIED: VM-SCH-28] The undo with `openstack resource provider allocation set`
from the saved JSON, `heal_allocations` over every instance, and
`openstack resource provider delete <old-rp-uuid>` for a decommissioned
compute once it holds no allocation.

**Verify.** `audit --verbose` rc 0, no output; the dry-run grep for
`[dry-run] Create`/`Update` prints nothing; usage matches the flavors; one
allocation per instance on its compute's provider; the log lines stop at the
next resource update (about 60 s).
