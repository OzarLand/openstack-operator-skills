# Instance lifecycle

Stuck or failed instance operations: build, delete, resize and cold migration,
snapshot, unexpected shutdown, disk full, rescue, console, and the stale
records they leave. Everything here is an `[Addition]` to the book, distilled
from the OzarLand `openstack-vm-runbooks` repository (`lifecycle/` pages, commit
`babdd8c07971`), except statements carrying a Book citation (Ch. 5, Ch. 10), which those pages
take from the book. Validation tags say what a lab executed; untagged
technical text is unverified. Container names and paths after "Kolla-Ansible:"
are Kolla-Ansible ones; "Any:" gives the equivalent elsewhere.

## Contents

- Stuck in BUILD waiting for vif-plugged
- Stuck in deleting
- Resize or cold migration not finished
- Snapshot never finishes
- Shut off by the host OOM killer
- Compute disk full
- Rescue mode
- Console not available
- Stale records

---

## Stuck in BUILD waiting for vif-plugged

A networking problem wearing a compute symptom [Book: Ch. 5]: Nova bound the
port, then waited for Neutron's `network-vif-plugged` event that never came.

**Recognize.** `status BUILD`, `task_state spawning` for about
`vif_plugging_timeout` (default 300 s), then `ERROR` with fault `Build of
instance <id> aborted: Failed to allocate the network(s), not rescheduling.`
The details and `nova-compute.log` carry `Timeout waiting for ...
network-vif-plugged ...`, `InstanceEventTimeout`, `VirtualInterfaceCreateException`.
Once aborted, the host field is empty and the Placement allocation is gone;
the build is not retried elsewhere. Running instances are not affected.

[LAB-VALIDATED: VM-LC-01] Recognition and read-only checks below. Lab:
2026.1, Kolla-Ansible 22.2.0, ML2/OVS (multinode and all-in-one), OVS agent
paused; fault after 317-324 s. Not run: every OVN check.

**Read-only checks.**
- `openstack port show <port-id> -c binding_vif_type -c binding_host_id -c status`
  (`port list` silently drops a binding-host column).
- `openstack network agent list --host <compute>`; Kolla-Ansible:
  `docker ps -a --filter name=neutron_openvswitch_agent` (`Up ... (Paused)` is frozen).
- OVN: `ovn-sbctl --columns=logical_port,chassis find Port_Binding logical_port=<port-id>`
  (empty `chassis`: the controller never claimed the port).

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| Port bound (`binding_vif_type ovs`), `DOWN`; agent not alive now | agent or OVN controller stopped after binding |
| `binding_vif_type binding_failed`; ERROR within seconds with "Exceeded maximum number of retries" | agent already dead at request time, or bridge mapping / physnet mismatch: see *Exceeded maximum number of retries* in scheduling-and-boot.md |
| Agent alive but processes nothing; recovers on restart | stale RPC connection |
| Port `ACTIVE`, `Failed to notify nova on events` in neutron-server | Neutron cannot reach the Nova API |

**Fix options.**
1. Frozen or dead agent. *State-changing*: Kolla-Ansible:
   `docker unpause neutron_openvswitch_agent` if paused (find out what paused
   it), else `systemctl restart kolla-neutron_openvswitch_agent-container.service`
   (on a paused agent it took about 60 s: the container is killed, `Exited (137)`,
   then restarted). Restarting the OVS agent can briefly disrupt data-plane
   changes on the host; do one host first.
   [LAB-VALIDATED: VM-LC-02] Lab: 2026.1, Kolla-Ansible 22.2.0, ML2/OVS;
   `docker unpause`, the unit restart, deleting the ERROR instances and the
   test boot were run. Not run: `docker restart`, `ovn-controller` restart.
2. Bridge mapping mismatch, stale RPC, Neutron-to-Nova notification, slow
   host: fix the cause named in the table, restart the agent or
   `neutron-server`; raising `vif_plugging_timeout` is a workaround, not a fix.
   [DOCUMENTED-UNVERIFIED: VM-LC-03]
3. Clean up. *State-changing*: `openstack server delete <id>` frees quota and
   allocations; ask the owner first if a volume may hold data (it is deleted
   only if created with `delete_on_termination`). Covered by VM-LC-02.

**Verify.** A test boot pinned to the host
(`--availability-zone nova:<compute>`) reaches `ACTIVE`, its port `ACTIVE`;
`openstack network agent list` shows every agent alive.

---

## Stuck in deleting

**Recognize.** After `openstack server delete <server-id>`: `task_state
deleting`, host still set, `status` unchanged (`ACTIVE`, `SHUTOFF`, `ERROR`),
or `ERROR` with a fault from the delete. Deleting again returns no error and
changes nothing; while the compute is up, nova-api logs `Instance is already
in deleting state, ignoring this request`. Until the delete completes the
instance keeps its quota, allocation, ports and addresses and volume
attachments; the guest may still run. Out of scope: soft delete
(`reclaim_instance_interval` set, instances in `SOFT_DELETED`).

How a delete runs: **compute up**: the compute logs `Terminating instance`,
destroys the guest (`Instance destroyed successfully.`), frees the network,
detaches volumes, deletes the allocation. **Compute down** (or no host):
*local delete* in the API (`instance's host <compute> is down, deleting from
database`): ports freed, attachments deleted, `delete_on_termination` volumes
**deleted**, allocation removed; nothing is done on the compute, so the guest
may still be defined, and running, there.

[LAB-VALIDATED: VM-LC-04] Recognition, read-only checks and the behaviours
of causes 1, 4 and 5 below. Lab: 2026.1 (Nova 33.0.3), Kolla-Ansible 22.2.0,
all-in-one; nova-compute paused or its unit stopped; local delete after the
service went `down` (51 s) left the guest running until nova-compute
returned. Not run: causes 2 and 3, `disable_terminate`.

**Read-only checks.**
- `openstack server show <server-id> -c status -c OS-EXT-STS:task_state -c OS-EXT-STS:power_state -c OS-EXT-SRV-ATTR:host -c OS-EXT-SRV-ATTR:instance_name -c locked -c fault`;
  `openstack server event list <server-id>`.
- `openstack compute service list --service nova-compute --host <compute>`.
- On the compute, Kolla-Ansible: `sudo docker exec nova_libvirt virsh list --all --uuid | grep <server-id>`
  and `sudo grep <server-id> /var/log/kolla/nova/nova-compute.log | tail -n 30`;
  Any: `sudo virsh list --all --uuid | grep <server-id>` and the nova-compute log.

**Tell the causes apart** (nova-compute log of the instance's host).
| Observation | Points to |
|---|---|
| No `Terminating instance` for the server ID | 1: request never reached the compute (message bus) or nova-compute blocked |
| `Terminating instance`, no `Instance destroyed successfully.` after it | 2: guest cannot be destroyed, usually I/O hung on lost storage (NFS, iSCSI, Ceph); the compute is still on it, do not reset state |
| `Cannot destroy instance, operation time out`; `Error from libvirt during destroy. Code=<n> Error=<message>`; `Setting instance vm_state to ERROR` + traceback | 3: delete failed part way, instance `ERROR`; traceback names the step |
| `Ignoring unknown cinder exception for volume <id>` | Cinder failed to detach; Nova continued; volume may stay `in-use` |
| `Service started deleting the instance during the previous run, but did not finish. Restarting the deletion now.` | nova-compute restarted and resumed the delete |
| Host gone but service still `up` | 4: died less than `service_down_time` (60 s) ago, or something still reports for it |
| `Instance <id> is locked` (HTTP 409) for a non-admin; or API logs `instance termination disabled` | 5: locked (admins bypass the lock), or `disable_terminate` set (nobody can delete) |

**Fix options.**
1. Cause 1. Fix the message bus first if it is the cause
   (`openstack-incident-analysis`). *State-changing*: restart nova-compute;
   at start-up it resumes every delete left in `deleting` on its host.
   Kolla-Ansible: `sudo systemctl restart kolla-nova_compute-container.service`
   (stop can take up to 60 s); Any: restart `nova-compute`. Running instances
   are not affected; operations in progress on that compute fail. Undo: none
   needed. Not `docker restart nova_compute`: it bypasses the systemd unit,
   which re-attaches after `RestartSec` (11 s with Kolla defaults, 59 s on the
   lab); on a **paused** `nova_compute` it only unpaused it.
   [LAB-VALIDATED: VM-LC-05] Lab: 2026.1, Kolla-Ansible 22.2.0, all-in-one;
   unit stopped then started: `Restarting the deletion now` 9 s after start,
   instance gone 24 s later; cause 4 with the host really gone: once the
   service showed `down`, a new delete was a local delete, and the guest was
   reaped 54 s after nova-compute came back. Not run: the forced-down path.
2. Causes 2, 3 and 5. [DOCUMENTED-UNVERIFIED: VM-LC-06]
   - Cause 2: repair the storage path (QEMU then dies and the delete
     completes). A process waiting on storage gone for good often cannot be
     killed: *State-changing* host reboot after moving the other instances
     (it stops every instance on the host; nova-compute resumes the delete).
     Do not shortcut with `virsh undefine`, removing disks by hand or editing
     the database.
   - Cause 3: an `ERROR` instance with no task state accepts a new delete.
     *Destructive*: `openstack server delete <server-id>` deletes the guest,
     local disks, ports and addresses, allocations and the
     `delete_on_termination` volumes (others are detached and kept).
     Precondition: the owner confirms the data is not needed or is backed up.
     No undo. If it stays `deleting` with the compute up and the guest gone,
     restart nova-compute first (resetting while the compute may still work
     runs two deletes at once); still stuck: *State-changing*
     `openstack server set --state error <server-id>` (database only; undo
     `--state active`), then the destructive delete.
   - Cause 5: `openstack server unlock <server-id>`, then the delete above.
     No API or CLI clears `disable_terminate`; a database edit is its own
     destructive change, not covered.
3. Cause 4, host may come back: fence it first (`openstack-incident-analysis`).
   *Destructive*: `openstack --os-compute-api-version 2.11 compute service set
   --disable --disable-reason "<why>" --down <compute> nova-compute`, then
   `openstack server delete <server-id>`. Forcing down affects **every
   instance on that compute** (their deletes become local deletes; they can be
   evacuated, also by automation). Unfenced, the guest keeps running while its
   addresses and volumes are reused: duplicate IPs, two writers on one volume.
   Lost: the instance record, `delete_on_termination` volumes, local disks.
   Precondition: host powered off or cut off from network and storage, checked
   out of band (BMC, switch port); owner agrees; snapshot of each
   `delete_on_termination` volume whose data matters. Undo:
   `... compute service set --up --enable <compute> nova-compute` restores the
   service, not the instance. On return, `running_deleted_instance_action =
   reap` (default) logs `Destroying instance with name label '<name>' which is
   marked as DELETED but still present on host.` and destroys it (every
   `running_deleted_instance_poll_interval`, 1800 s, and once shortly after
   start). [DOCUMENTED-UNVERIFIED: VM-LC-07]

**Verify.** `openstack server show <server-id>`: not found;
`openstack port list --device-id <server-id>`: empty;
`openstack volume show <volume-id> -c status -c attachments`: no attachment
to it; on the compute no guest in `virsh list --all --uuid` (after a local
delete, check when the compute returns). Leftovers: see *Stale records*
below and *Stale attachment* in volumes.md.

---

## Resize or cold migration not finished

**Recognize** (`openstack server show <server-id> -c status -c OS-EXT-STS:task_state -c OS-EXT-SRV-ATTR:host -c flavor`):
| status / task_state | Meaning |
|---|---|
| `VERIFY_RESIZE` / `None` | The resize **worked** and waits for confirm or revert; can stay so for days, with resources held on both computes |
| `RESIZE` / `resize_prep`, `resize_migrating`, `resize_migrated`, `resize_finish` | Stopped part way (service died, message lost) |
| `ERROR` / `None` | A step failed; the fault says which |

Flow: destination `prep_resize` claims; source `resize_instance` powers the
guest off, renames the directory to `<uuid>_resize`, copies local disks over
SSH, then sets `host` to the **destination**; destination `finish_resize`
starts the guest (`VERIFY_RESIZE`). `resize_confirm_window` (default 0, off;
Kolla-Ansible 2026.1 does not set it) makes the destination auto-confirm.

**Read-only checks.** The `server show` above with `-c OS-EXT-STS:power_state -c fault`;
`openstack server migration list --server <server-id>`;
`openstack server event list <server-id>`, `openstack server event show <server-id> <request-id>`;
`openstack compute service list --service nova-compute`; nova-compute log of
source and destination (Kolla-Ansible: `sudo grep <server-id> /var/log/kolla/nova/nova-compute.log`);
guest existence with `virsh list --all --uuid | grep <server-id>` (Kolla-Ansible:
in `nova_libvirt`).

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| `VERIFY_RESIZE` | 1: nobody confirmed |
| `RESIZE` with a task state; migration `pre-migrating`/`migrating`/`post-migrating`; source log `Instance found in migrating state during startup. Resetting task_state` or `Failed to revert crashed migration` | 2: service died or message lost |
| Rollback or `ERROR` at copy: `not able to execute ssh command`, `ssh: connect to host <dest> port 8022: Connection refused` | 3: SSH between computes (Kolla-Ansible: `nova_ssh` containers and keys) |
| `ERROR`, `host` = destination, flavor back to old; dest log `Deleting allocations for old flavor on source node <source> after finish_resize failure...` | 4: destination cannot run the guest |
| HTTP 400 `Flavor's disk is smaller than the minimum size specified in image metadata...`, or rollback with `Unable to resize disk down.` | 5: smaller disk; Nova does not shrink disks (except a volume-backed root) |
| `ERROR`, `host` still source (copy interrupted, destination disk full) | copy failed; disks on the source |

[LAB-VALIDATED: VM-LC-08] Recognition, checks and the observations of
causes 1, 2, 3 and 5. Lab: 2026.1, Kolla-Ansible 22.2.0, 3 controllers + 2
computes, ML2/OVS, local qcow2 disks: `VERIFY_RESIZE` in 34 s; ephemeral
shrink rolled back in 13 s; `nova_ssh` stopped: rollback in 16 s; nova_compute
stopped during the copy: systemd restarted it 60 s later, the revert failed
(`AttributeError ... _finish_revert_migration_vtpm`), instance stopped on the
source, migration left `migrating`, allocations swapped. Not run: cause 4.

**Fix options.**
1. Cause 1, owner's choice, neither can be undone. *Destructive*:
   `openstack server resize confirm <server-id>` deletes the old copy on the
   source for good. *Destructive*: `openstack server resize revert <server-id>`
   destroys the resized guest and restarts the old copy: everything written
   to local disks since the resize is lost (volumes kept); a snapshot is
   refused (409) in `VERIFY_RESIZE`, so copy data out from the guest first.
   [LAB-VALIDATED: VM-LC-09] Lab: as VM-LC-08; confirm in 12 s, revert in
   19 s, `server image create` refused with 409. Not run: `resize_confirm_window`.
2. Other recovery. [DOCUMENTED-UNVERIFIED: VM-LC-10]
   - Cause 2: bring back the service or bus (Kolla-Ansible 2026.1: systemd
     restarts a stopped container after `RestartSec`). Revert failed: check
     the disks are on the source and `virsh list --all` shows the domain on
     the source and none on the destination, then *State-changing*
     `openstack server start <server-id>` (undo: `server stop`); check
     allocations (instance's on destination, migration's on source).
   - Causes 2 (still `RESIZE`, services up), 3, 4: fix the cause, then recover
     where `host` says. *State-changing*: `openstack server reboot --hard
     <server-id>` recreates the guest from the disks on that compute;
     precondition: the disks are there (or shared storage, volumes); if they
     are only on the other compute, stop (not covered). If the reboot is
     refused for a `RESIZE` task state: *State-changing*
     `openstack server set --state active <server-id>` (database only; undo
     `--state error`), then the hard reboot. The client help warns that
     setting the state after a failed move "can result in instances that are
     no longer usable": prefer the hard reboot.
   - Keep `<instances-path>/<server-id>_resize` on the source until the owner
     has checked the instance: it is the only copy. A partial `<server-id>`
     directory can remain on the destination after an SSH failure; the page
     says to remove it once the instance runs on the source, with no risk note.
   - Auto-confirm: Kolla-Ansible `/etc/kolla/config/nova/nova-compute.conf`
     `[DEFAULT] resize_confirm_window = <seconds>`, `kolla-ansible reconfigure
     -i <inventory> --tags nova` (*State-changing*: restarts `nova_compute`;
     every older resize is then confirmed without the owner).
   - Cause 5: nothing to recover; resize to a flavor with disks at least the
     current sizes.

**Verify.** `server show`: `ACTIVE` (or `SHUTOFF`), no task state, expected
flavor and host; `server migration list`: none in progress (after cause 2 it
stays `migrating`). Allocations: `openstack resource provider allocation show
<server-id>` and `... show <migration-uuid>` (UUID column of `openstack
--os-compute-api-version 2.59 server migration list`, osc-placement). Deleting
the instance does not remove a stuck migration's allocation.

---

## Snapshot never finishes

**Recognize.** After `openstack server image create --name <name> <server-id>`:
`task_state image_uploading` (or `image_snapshot_pending`, `image_snapshot`,
`image_pending_upload`), `status ACTIVE`, image `saving` or `queued`. No
other action is accepted while the task state is set. Or the snapshot fails:
task state clears and the image disappears. `server event list` shows
`createImage` as `Success` even when the upload fails later.

**Read-only checks.** `openstack server show <server-id> -c OS-EXT-STS:task_state -c OS-EXT-STS:power_state -c OS-EXT-SRV-ATTR:host`;
`openstack image show <image-id> -c status -c size -c created_at -c updated_at`
(size only once `active`); `openstack compute service list --service nova-compute --host <compute>`.
On the compute, Kolla-Ansible:
`sudo grep <server-id> /var/log/kolla/nova/nova-compute.log | grep -iE 'snapshot|upload' | tail -n 20`,
`sudo docker exec nova_compute df -h /var/lib/nova/instances`,
`sudo docker exec nova_compute ls -la /var/lib/nova/instances/snapshots/`;
Any: the nova-compute log and `[libvirt] snapshots_directory` (default
`$instances_path/snapshots`).

**Where it stops.**
| Task state, image / last log line | Points to |
|---|---|
| `image_snapshot_pending` / none | request did not reach the compute (nova-compute down or busy, bus) |
| `image_snapshot` / none yet | waiting for a slot (`max_concurrent_snapshots`, default 5) |
| `image_pending_upload` / `Beginning live snapshot process` (or cold) | writing the disk under `snapshots_directory`: space, disk speed, large disk |
| `image_uploading`, `saving` / `Snapshot extracted, beginning image upload` | upload to Glance (network, Glance API, store); no progress indicator, no size |
| `image_uploading`, `queued` / no `Snapshot extracted`, Ceph RBD | direct snapshot stuck in Ceph |
| cleared, image gone / `Error contacting glance server '<url>' for 'upload', retrying.` ... `done trying.`, `Successfully reverted task state from ... on failure for instance.` | standard path failed; nova-compute deleted the image (no `Failed to snapshot image` line) |
| cleared, image gone / `Failed to snapshot image` (ERROR) | direct (Ceph) snapshot failed |
| cleared, image left `queued`/`saving`, `tmp*` dir left under `snapshots/` | 4: nova-compute stopped or restarted mid-snapshot (start-up clears task states, not the image) |

Other causes: 2 no space on the compute (whole disk written there first;
can also pause writing instances, see *Compute disk full*); 3 Glance store
full or unreachable (Kolla-Ansible default file store on the first
`glance-api` host). Kolla-Ansible HAProxy cuts Glance uploads after 6 h.

[LAB-VALIDATED: VM-LC-11] Standard-path recognition and the cause 1, cause
4 and upload-failure signatures. Lab: 2026.1, Kolla-Ansible 22.2.0,
all-in-one, local qcow2, Glance file store, upload slowed with `tc`: at
4 Mbit/s `Snapshot extracted` to `upload complete` 108 s, image `saving`
without size; upload failure as in the table, image deleted. Not run: causes
2 and 3, cold snapshot, Ceph direct snapshot and `rbd` checks, slot wait.

**Fix options.**
1. Cause 1: if the temp file grows or the upload runs with no error, let it
   finish. Causes 2, 3: free space on the compute or the Glance store; the
   failed snapshot cleaned itself; snapshot again. Covered by VM-LC-13.
2. Cause 4. Start nova-compute if down (clears the task state). Identify the
   image: `openstack image show <image-id> -c status -c size -c owner -c created_at -c properties`
   (owner = instance's project, `created_at` = snapshot time, `instance_uuid`
   = `<server-id>`, size not growing). *Destructive*: `openstack image delete
   <image-id>`; another `queued`/`saving` image of the project may be an
   upload still running; precondition: no snapshot of this instance running
   and all checks match; no undo. Then *Destructive*: Kolla-Ansible
   `sudo docker exec -u root nova_compute rm -rf /var/lib/nova/instances/snapshots/<tmp-dir>`;
   precondition: no snapshot running on this compute, only `tmp*` dirs older
   than the last start of `nova_compute`
   (`sudo docker inspect -f '{{.State.StartedAt}}' nova_compute`); no undo.
   [LAB-VALIDATED: VM-LC-12] Lab: as VM-LC-11; unit restart 20 s into the
   upload (61 s), task state cleared, image left `queued` and deleted, 52 MB
   `tmp` dir removed, new snapshot `active` and bootable.
3. [DOCUMENTED-UNVERIFIED: VM-LC-13] Causes 2 and 3 as above. Task state
   stuck while nova-compute is up and nothing runs: check the host's other
   instances first, then *State-changing* restart nova-compute (Kolla-Ansible:
   `sudo systemctl restart kolla-nova_compute-container.service`; operations
   in progress on that compute fail; no undo needed). Interrupted cold
   snapshot most likely leaves the instance `SHUTOFF`: `openstack server start
   <server-id>` once the task state is clear (`server resume` is refused
   unless Nova shows `SUSPENDED`). Ceph direct path: deleting the image may
   leave the Ceph snapshot or clone; look read-only (`rbd snap ls
   <pool>/<server-id>_disk`, `rbd ls -l <images-pool>`) and escalate to the
   Ceph owner rather than deleting there.

**Verify.** No task state; new snapshot `active` with a size;
`openstack image list --status queued ; openstack image list --status saving`
shows no leftovers; a test instance boots from the snapshot.

---

## Shut off by the host OOM killer

**Recognize.** Instance went `SHUTOFF`, nobody stopped it; `openstack server
event list <server-id>` shows a `stop` made by Nova itself. Guest logs end
abruptly. nova-compute: `VM Stopped (Lifecycle Event)`, then `Instance shutdown
by itself. Calling the stop API. Current vm_state: active, ...`. libvirt guest
log: `shutting down, reason=crashed`. Nova aligns its record with the
hypervisor; it does not restart the guest. Any guest death (QEMU crash,
`kill`, OOM) looks the same in Nova: the kernel log tells which. Unwritten
data is lost; it can recur on any instance of the host, and host services
(OVS, nova-compute) can be killed too.

**Read-only checks** (on the instance's compute, from `openstack server show
<server-id> -c OS-EXT-SRV-ATTR:host -c OS-EXT-SRV-ATTR:instance_name`).
- `sudo dmesg -T | grep -E 'invoked oom-killer|Killed process'`;
  `sudo journalctl -k --since "-2 days" | grep -E 'invoked oom-killer|Killed process'`
  (add `-b -1` for the previous boot; needs a persistent journal). `free -m`.
- libvirt log, Kolla-Ansible: `sudo docker exec nova_libvirt tail -n 5 /var/log/libvirt/qemu/<instance-name>.log`
  (lost when `nova_libvirt` is recreated: read it before a redeploy); Any:
  `sudo tail -n 5 /var/log/libvirt/qemu/<instance-name>.log`.
- `sudo grep <server-id> /var/log/kolla/nova/nova-compute.log | grep -E 'Lifecycle Event|shutdown by itself'` (Kolla-Ansible path).
- Compare with Placement: `openstack resource provider inventory show <rp-uuid> MEMORY_MB`
  (total, reserved, allocation_ratio), `openstack resource provider usage show <rp-uuid>`.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| `Out of memory: Killed process <pid> (qemu-system-x86) ...` | host-wide OOM: 1 host processes exceed `reserved_host_memory_mb` (default 512 MB), 2 `ram_allocation_ratio` > 1.0, or 3 something else grew |
| `Memory cgroup out of memory: Killed process ...`, preceded by `oom-kill:constraint=CONSTRAINT_MEMCG,...,oom_memcg=<cgroup>` | a cgroup limit, not host memory (Kolla-Ansible guest cgroup `/machine/qemu-<n>-<instance-name>.libvirt-qemu`) |
| No `Killed process` line at that time | 4: not the OOM killer; read the libvirt guest and `nova_libvirt` logs |
| Process killed inside the guest, instance still `ACTIVE` | guest OOM, a different problem |

The `<task> invoked oom-killer` line names the task that triggered the kill,
not necessarily the one killed. The scheduler offers host memory minus
`reserved_host_memory_mb`, times `ram_allocation_ratio`; Kolla-Ansible 2026.1
does not change these for libvirt computes.

[LAB-VALIDATED: VM-LC-14] Nova, libvirt and kernel signatures and the
read-only checks, for a **cgroup-level** OOM only. Lab: 2026.1, Kolla-Ansible
22.2.0 all-in-one, Ubuntu 24.04, no swap; `memory.max` of one guest's libvirt
cgroup set to 50M: `Memory cgroup out of memory: Killed process` at once,
`reason=crashed` 0.3 s later, `VM Stopped` 15 s after QEMU died; the
`SHUTOFF` instance kept its `MEMORY_MB` allocation. Not run: a host-wide OOM
and its `Out of memory: Killed process` line, causes 2 and 3.

**Fix options.**
1. Bring it back once the compute has free memory (`free -m`).
   *State-changing*: `openstack server start <server-id>`; the guest boots as
   after a power loss (file system or database recovery). Undo:
   `openstack server stop <server-id>`. Still short of memory: move instances
   away first, or the next one killed may be another.
2. Causes 1 and 2: first write down `reserved` and `allocation_ratio` from
   the inventory. Set `reserved_host_memory_mb` to what host processes really
   use, with margin. Kolla-Ansible: `/etc/kolla/config/nova/nova-compute.conf`,
   `[DEFAULT] reserved_host_memory_mb = <MB>`, then `kolla-ansible reconfigure
   -i <inventory> --tags nova --limit <computes>`; Any: `nova.conf` on the
   computes, restart `nova-compute`. *State-changing*: restarts nova-compute
   (running instances not affected); the inventory shrinks, instances already
   there stay. Undo: set back the values written down, explicitly, and
   reconfigure again.
   [LAB-VALIDATED: VM-LC-15] Lab: as VM-LC-14; `server start`: `ACTIVE` in
   18 s; `reserved_host_memory_mb = 4096` and reconfigure: 4 min 42 s,
   `nova_compute` recreated, `nova_libvirt` and the guest's QEMU not,
   inventory `reserved 4096`. Undo was run by removing the override, not by
   writing the old values back.
3. [DOCUMENTED-UNVERIFIED: VM-LC-16] `ram_allocation_ratio` (e.g. `1.0`)
   only to change the ratio: once set it overwrites any ratio set through
   Placement, and removing it later does not restore the old one. The
   per-host file `/etc/kolla/config/nova/<inventory-hostname>/nova.conf`.
   Cause 3: `ps aux --sort=-rss | head` and the tasks listed in the kernel's
   OOM report; fix or limit that process. Hugepages: a persistent pool stays
   in `MEMORY_MB`; reserve enough non-huge-page memory.

**Verify.** Instance `ACTIVE`; inventory shows the values set; over the
following days no new `Killed process` in `dmesg` or `journalctl -k`, and
`free -m` keeps a margin with every instance running.

---

## Compute disk full

**Recognize.** An instance that writes "hangs"; Nova still says `ACTIVE`
with `OS-EXT-STS:power_state Paused` (the only signal in Nova);
`virsh domstate <domain> --reason` gives `paused (I/O error)` (QEMU's default
`werror=enospc`). Guest console: last output before the write, then nothing.
`nova-compute.log` has no `No space`/`ENOSPC`: that absence is part of the
signature. Placement counts flavor disk, not used space: the scheduler keeps
placing new instances on the full compute. A paused instance loses nothing,
it waits; instances that do not write keep running. If the store shares `/`,
the whole host suffers.

**Read-only checks.**
- `openstack server list --all-projects --long -c ID -c Name -c Status -c "Power State" -c Host | grep -i paused`.
- Kolla-Ansible (compute, needs sudo): `df -h /var/lib/docker/volumes/nova_compute/_data /`;
  `findmnt -T /var/lib/docker/volumes/nova_compute/_data` (own file system or `/`);
  `for d in $(docker exec nova_libvirt virsh list --all --name); do echo "$d: $(docker exec nova_libvirt virsh domstate "$d" --reason)"; done`.
  Any: `df -h /var/lib/nova/instances /` and the same loop with `virsh`.
- What filled it (in the store): `du -xsh * 2>/dev/null | sort -h | tail`;
  `du -xsh instances/* 2>/dev/null | sort -h | tail`; `ls -la instances/_base | head`.
  A directory under `instances/` is named by instance ID.

**Tell the causes apart.**
| Observation | Points to |
|---|---|
| Store 100 % and a domain `paused (I/O error)` | this section |
| Paused on I/O error, store not full | another storage path or I/O cause |
| Store full, nothing paused yet | act now |
| `du`: space in instance directories, flavors' disks exceed the store | 1: overcommitted local disk; deleting files is not the fix: move instances or extend the file system |
| `instances/_base` holds a large share | 2: base image cache |
| Space at the top of the store or of `/` (logs, images, stray file) | 3: something else on the same file system |

[LAB-VALIDATED: VM-LC-17] Recognition and read-only checks. Lab: 2026.1,
Kolla-Ansible 22.2.0, ML2/OVS, local qcow2, CirrOS, no Cinder, store on `/`
and on its own ext4: `paused (I/O error)` with Nova `ACTIVE`/Paused, nothing
in the log, and a new instance on the full compute became `ACTIVE`. Not run:
finding the cause on a real store, OVN, Ceph, volume-backed instances.

**Fix options.**
1. *Destructive*: free space by removing a file known not to be used
   (`du`, `ls -la`, `qemu-img info <file>`; `fuser <file>` or `lsof <file>`),
   then `sudo rm <file>`; back it up elsewhere if in doubt; no undo. Never
   delete or truncate an instance disk, never remove from `instances/_base` a
   backing file a running instance uses.
   Then *State-changing*: freeing space does not resume instances, and
   `openstack server unpause` does not apply (Nova sees `ACTIVE`).
   Kolla-Ansible: `docker exec nova_libvirt virsh resume <domain>`, or all:
   `for d in $(docker exec nova_libvirt virsh list --state-paused --name); do docker exec nova_libvirt virsh resume "$d"; done`;
   Any: `virsh resume <domain>`. The guest retries the write; precondition:
   space is free, else it pauses again. Undo: `virsh suspend <domain>`.
   [LAB-VALIDATED: VM-LC-18] Lab: as VM-LC-17; removing the fill file, then
   `virsh resume`, resumed the domain; freeing space alone did not. Not
   observed: whether Nova's power state returns to `Running` after the
   resume, disabling the service, removing base images.
2. [DOCUMENTED-UNVERIFIED: VM-LC-19] Stop placement first. *State-changing*:
   `openstack compute service set --disable --disable-reason "instance store full <date>" <compute-host> nova-compute`
   (running instances not affected; undo `--enable`). Instances themselves
   use the space: move them off or extend the file system; a paused instance
   needs space back on this compute before it can move. Prevent: monitor
   real store usage and `Paused` while `ACTIVE`; `reserved_host_disk_mb`,
   lower `disk_allocation_ratio` if overcommitted (they change what Placement
   offers, not what guests write); store on its own file system. Then
   *State-changing* re-enable (`--enable`): new instances land there again.
   A domain paused on I/O error still holds its QEMU process and disk locks:
   never evacuate it without fencing.

**Verify.** Store below 100 % with margin; `virsh list --state-paused --name`
empty; `openstack server list --all-projects --host <compute-host> --long -c ID -c Status -c "Power State"`
shows `ACTIVE` and `Running` (not lab-confirmed, see VM-LC-18); inside each
resumed instance, the interrupted work finished or failed cleanly.

---

## Rescue mode

For a guest that does not boot (kernel panic, emergency shell after a bad
`/etc/fstab`, full root) or boots unreachable (network, firewall, lost key):
Nova says `ACTIVE`, a reboot does not help, data is intact on the disk.

**Read-only checks.** `openstack server show <server-id> -c status -c image -c volumes_attached -c OS-EXT-SRV-ATTR:host`
(empty image or `volumes_attached`: volume-backed);
`openstack console log show --lines 100 <server-id>`; console URL if the log is empty.

**How rescue works.** The guest is stopped (clean shutdown first) and started
from a rescue disk with its own disks attached; state `RESCUE`. Accepted only
from `ACTIVE`, `SHUTOFF` or `ERROR` (else 409). **Legacy** (default): rescue
disk first, original root second (`vdb`); rescue image is `--image`, else
`[libvirt] rescue_image_id`, else the instance's own image (must still exist);
refused for volume-backed (`Cannot rescue a volume-backed instance`).
**Stable device rescue**: used as soon as the rescue image has
`hw_rescue_device` or `hw_rescue_bus`; original root stays first, rescue disk
last; the only way for volume-backed: API 2.87+, both properties, compute
trait `COMPUTE_RESCUE_BFV`.

[LAB-VALIDATED: VM-LC-20] Rescue, repair and unrescue as below. Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, local qcow2, Cinder LVM, CirrOS 0.6 made
unreachable: legacy rescue with its own image reached `RESCUE` in 16 s but
booted the **broken original disk** (both disks labelled `cirros-rootfs`;
console `info: initramfs loading root from /dev/vdb1`); a relabelled rescue
image still did; one with `root=/dev/vda1` worked; unrescue `ACTIVE` in 7 s.
Volume-backed: 400 without the properties or with 2.86; both and 2.87:
`RESCUE` in 21 s. Not run: `--password`, `rescue_timeout`, other guest OSes.

**Steps.**
1. Check `[DEFAULT] rescue_timeout` on the compute (default 0, off): if set,
   Nova unrescues without warning, possibly with the disk mounted.
   *State-changing*: `openstack server rescue <server-id>` (own image),
   `openstack server rescue --image <rescue-image> <server-id>`, or
   volume-backed `openstack --os-compute-api-version 2.87 server rescue --image <image-with-hw_rescue-properties> <server-id>`.
   The guest is stopped; disks are not changed by the rescue. Undo:
   `openstack server unrescue <server-id>`. A dedicated rescue image helps
   only if its root is found otherwise than by the guest's label.
2. Check the rescue runs from the rescue disk (`mount | grep ' / '`, `lsblk`,
   or the console log); if `/` is the original disk, unrescue and use another
   image. Find the original root with `lsblk`, `blkid` (legacy: second disk;
   stable device: usually first). *State-changing*: fix the files, with the
   owner's agreement, keeping a copy of each changed file; unmount.
3. *State-changing*: `openstack server unrescue <server-id>` (undo: rescue again).

[DOCUMENTED-UNVERIFIED: VM-LC-21] Not lab-run: `openstack server rescue
--password <password> <server-id>`; `rescue_timeout` behaviour; messages
`Host unable to rescue a volume-backed instance` (no `COMPUTE_RESCUE_BFV`),
`Requested rescue image '<image>' is not supported` (missing image or volume
snapshot image), `Driver Error: <error>` (nova-compute logs `Error trying to
Rescue Instance`). Do not pause, suspend or stop an instance in `RESCUE`: it
loses the original state and makes unrescue impossible (upstream guide).

**Verify.** `ACTIVE`; `openstack console log show --lines 50 <server-id>`
ends at a login prompt; users reach it as usual (SSH, service port).

---

## Console not available

[DOCUMENTED-UNVERIFIED: VM-LC-22] Whole section: written from Nova 2026.1
and Kolla-Ansible 2026.1 code and documentation; never reproduced on a lab.

Only the console is affected, not the instance. The compute builds the
console token itself and stores it with expiry `[consoleauth] token_ttl`
(default 600 s, read on the **compute**): a URL must be opened within 10
minutes. An open session lasts until the browser closes it, unless
`[consoleauth] enforce_session_timeout` is true or a load balancer cuts it
(Kolla-Ansible HAProxy `timeout tunnel 1h`). Kolla-Ansible defaults:
`nova_console: novnc`, proxies on port 6080 of each controller, URL from
`nova_novncproxy_fqdn` (default `kolla_external_fqdn`). SPICE: read
`nova_spicehtml5proxy`, port 6082, `--spice` instead.

**Read-only checks.** `openstack console url show <server-id>`;
`openstack server show <server-id> -c status -c OS-EXT-SRV-ATTR:host -c OS-EXT-SRV-ATTR:instance_name`;
`openstack compute service list --service nova-compute --host <compute>`;
proxy log, Kolla-Ansible on controllers: `sudo tail -n 50 /var/log/kolla/nova/nova-novncproxy.log`
(Any: the `nova-novncproxy` log); on the compute `sudo docker exec nova_libvirt virsh vncdisplay <instance-name>`
(Any: `sudo virsh vncdisplay <instance-name>`).

| Message (where) | Points to |
|---|---|
| `Unavailable console type novnc.` (API) | VNC disabled on the compute (`[vnc] enabled = false`), or guest definition without VNC device |
| `Instance <id> is not ready` (API) | no host yet, or guest missing while building |
| HTTP 404, instance not found (API) | compute does not find the guest in libvirt |
| `The token '***' is invalid or has expired` (proxy) | token older than `token_ttl`, or console port changed (moved, rebooted) |
| `Origin header does not match this host.` / `Origin header protocol does not match this host.` (proxy) | wrong URL host or `http`/`https` mismatch: `novncproxy_base_url`, `[console] allowed_origins` |
| `connecting to: <address>:<port>`, then an error (proxy) | proxy cannot reach the compute's VNC ports (5900 and up): firewall, routing, `server_proxyclient_address` |
| Every console fails | proxy containers down, or no healthy HAProxy backend |
| Drops after an hour | HAProxy tunnel timeout (or token expiry with `enforce_session_timeout`) |

[DOCUMENTED-UNVERIFIED: VM-LC-23] **Fix options**, all *State-changing*:
- Expired token: rerun `console url show` and open at once. Longer lifetime:
  Kolla-Ansible `/etc/kolla/config/nova/nova-compute.conf` `[consoleauth]
  token_ttl = <seconds>`, `kolla-ansible reconfigure -i <inventory> --tags
  nova --limit <computes>` (`--limit` must name only computes: the `nova` tag
  also runs on conductor and proxy hosts). Restarts `nova_compute`; a leaked
  URL stays usable longer. Undo: remove the override, reconfigure.
- Wrong URL: Kolla-Ansible `nova_novncproxy_fqdn`, `nova_novncproxy_public_port`
  in `globals.yml`, `kolla-ansible reconfigure -i <inventory> --tags nova`.
  Platform-wide settings (`kolla_external_fqdn`, external TLS, certificates)
  must not be changed with `--tags nova` only. Any: `[vnc] novncproxy_base_url`
  on computes, `[console] allowed_origins` where the proxy runs.
- VNC unreachable: check the port answers (5900 + display number), open the
  range between controllers and the compute's API network.
- VNC disabled: Kolla-Ansible remove `[vnc] enabled = false` from whichever
  override holds it (`global.conf`, `nova.conf`, `nova/nova-compute.conf`,
  per-host files), reconfigure `--limit <compute>`; Any: `[vnc] enabled =
  true`, restart `nova-compute`. A guest with no VNC device needs
  `openstack server reboot --hard <server-id>` (stops it abruptly; agree with
  the owner).
- Proxy down: Kolla-Ansible `sudo docker restart nova_novncproxy` on each
  controller (open consoles disconnect); Any: restart `nova-novncproxy`.

**Verify.** A fresh URL opened within the token lifetime shows the guest;
the proxy log has `connect info:` and `connecting to:` without error.

---

## Stale records

Records that no longer match reality: instances in `BUILD`, `ERROR` or
`deleting` for days, ports of deleted instances, volumes `in-use` for missing
instances, allocations without a consumer. "The state that lies"
[Book: Ch. 10]: no direct impact, but inflated usage causes scheduling
failures, quota blocks and wrong capacity figures. Establish what is real
before touching any record.

**Read-only checks.**
- `openstack server list --all-projects --long -c ID -c Status -c "Task State" -c Host | awk '$4=="BUILD" || $4=="ERROR" || $6!="None"'`
  (no Updated column: `openstack server show <server-id> -c updated`).
- `nova-manage placement audit --verbose`: read-only without `--delete`;
  exit code 3 when it finds some.
- Orphan ports: `for p in $(openstack port list --device-owner compute:nova -f value -c ID); do d=$(openstack port show "$p" -f value -c device_id); openstack server show "$d" -f value -c id >/dev/null 2>&1 || echo "port $p: device $d not found"; done`.
- `openstack volume list --all-projects --status in-use -c ID -c "Attached to" -f value`;
  `cinder --os-volume-api-version 3.27 attachment-list --all-tenants 1 --volume-id <volume-id>`
  (not `openstack volume attachment list --volume-id`: client 9.0.0 ignores
  the filter and lists every attachment).
- Kolla-Ansible: `nova-manage` runs in `nova_api` (`sudo docker exec nova_api nova-manage ...`),
  whose database is **cell0**: archive and purge need `--all-cells` there;
  `cinder-manage` in `cinder_api`. `resource provider` commands need osc-placement.

**What is real.**
| Record | Check before acting |
|---|---|
| `BUILD`/`spawning` | domain on the host? build timed out? Usually safe to delete via the API |
| `deleting` | host died or storage hung? see *Stuck in deleting*; a local delete leaves the domain running on a stopped host |
| `ERROR` | read `fault`: failed builds (delete) vs real instances after a failed resize or migration (reset state, do not delete) |
| Orphan port | server not found (or archived) before deleting the port |
| Volume `in-use` | compare attachment-list with `server show` |
| Phantom allocation | audit also lists a `BUILD` instance without host as deletable: clear stuck builds first, check each consumer UUID with `server show` |

**Which tools change which records.**
| Tool | Changes | Risk, tag |
|---|---|---|
| `server list/show`, `placement audit` without `--delete`, `port show`, `attachment-list`, `virsh list` | nothing | read-only, VM-LC-24 |
| `openstack server set --state error --auto-approve <server-id>`, or `--state active` (reset-state) | Nova's record only, not the hypervisor; `active` on a dead domain lies to users | state-changing, VM-LC-24 |
| `openstack server delete <server-id>` | the instance in every service; local delete when the host is down | destructive, VM-LC-24 |
| `nova-manage placement audit --verbose --delete` | removes allocations whose consumer does not exist | state-changing, VM-LC-24 |
| `nova-manage placement heal_allocations --verbose` | creates or corrects allocations of existing instances | state-changing, VM-LC-24 |
| `openstack port delete <port-id>` | frees the port and its IP | state-changing, VM-LC-24 |
| `nova-manage db archive_deleted_rows --until-complete --all-cells` | moves soft-deleted rows to shadow tables; live resources untouched | destructive (history), VM-LC-24 |
| `openstack --os-volume-api-version 3.27 volume attachment delete <attachment-id>` | the attachment; the volume's status | state-changing, VM-LC-25 |
| `openstack volume set --state available --detached <volume-id>` | Cinder's record only | destructive, VM-LC-25 |
| `nova-manage db purge --all --all-cells` (or `--before <date>`), `cinder-manage db purge <days>` | deletes archived rows for good | destructive, VM-LC-25 |
| Direct SQL | anything, bypassing every check | destructive, VM-LC-25 |

[LAB-VALIDATED: VM-LC-24] Read-only checks and the Nova, Placement and port
tools above. Lab: 2026.1, Kolla-Ansible all-in-one, no Cinder; nova-compute unit
stopped to leave a stuck delete and a stuck build, an orphan port and phantom
and missing allocations made by hand; the checks found all; `audit --delete`,
`heal_allocations`, `port delete`, reset to `error` then `active` of a
running instance and the delete of the stuck build worked; archive in
`nova_api` without `--all-cells` touched only cell0. Not run: every Cinder
step, purge, force volume state, SQL.

[DOCUMENTED-UNVERIFIED: VM-LC-25] The Cinder steps, purge and direct
database edits: never run on a lab.

**Order and preconditions.**
1. Instances: `--state error` then delete for a truly dead instance; `--state
   active` only for a domain that really runs; a `BUILD` instance can usually
   be deleted without the reset. python-openstackclient 10.x asks for
   confirmation without `--auto-approve` and, without a terminal, does
   nothing. If the host is gone, the delete becomes local once the service is
   `down`; if it still reports `up` after losing its storage, fix or fence it.
2. Placement: always `audit` without `--delete` first and read the list; both
   `--delete` and `heal_allocations` change what the scheduler sees.
3. Ports and attachments: confirm the owning instance is gone first. Forcing
   a volume's state (*Destructive*): if a hypervisor still has it attached,
   a second attachment can write concurrently and corrupt data; precondition:
   no domain uses it (`virsh domblklist <instance-name>` on the last host; RBD:
   `rbd status <pool>/volume-<volume-id>` shows no watcher); no undo once two
   writers touched it.
4. Archive and purge (*Destructive*): loses the history of deleted resources
   that audits, billing and incident reviews may need; precondition: a
   database backup and retention checked (`--before <date>`); no undo without
   the backup. The page reports a 2026.1 failure when `--all-cells` is
   combined with `--verbose`, without making clear which command it hits:
   do not add `--verbose`, and check `nova-manage --help` on the platform
   (flags change between releases).
5. Direct database edits: last resort, only when no API or `*-manage`
   command covers the case; full backup, one row by UUID at a time, verified
   after each, recorded in the change record.

**Verify.** The server-list filter above is empty or explainable;
`placement audit --verbose` reports no orphans; `openstack quota show --usage
<project>` and `openstack resource provider usage show <rp-uuid>` match what
runs.
