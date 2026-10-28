# Volumes

Cinder volumes that do not reach or leave a state: creation, attach and
detach, attachments left behind, deletion, and extending an attached volume.
Everything in this file is an [Addition] to the book, distilled from the
`volumes/` pages of OzarLand openstack-vm-runbooks at commit `babdd8c07971`.
Lab evidence comes from one OpenStack 2026.1 all-in-one lab deployed with
Kolla-Ansible 22.2.0, with Cinder LVM (thin) over iSCSI and
python-openstackclient 9.0.0. Nothing here was run on Ceph RBD, NFS, Fibre
Channel, multipath or a multinode platform.

Commands need admin credentials and the microversions shown.
`openstack volume attachment list --volume-id` ignores the filter with
python-openstackclient 9.0.0 and lists every attachment of the cloud: use
`cinder --os-volume-api-version 3.27 attachment-list --all-tenants 1 --volume-id <volume-id>`
and check the Volume ID column before acting on any attachment.

## Contents

- Stuck in creating
- Stuck attaching or detaching
- Stale attachment
- Stuck in deleting
- Extend while attached

## Stuck in creating

**Recognize.** After `openstack volume create`, the volume is `error` within
seconds, or stays `creating` / `downloading` far longer than the image size
explains. A request refused at once (quota, invalid type, size too small for the
image) creates no volume and is not this section. Existing volumes and
attachments are unaffected; an `error` or `creating` volume holds no user data
but counts against quota.

[LAB-VALIDATED: VM-VOL-01] Recognition, read-only checks and the cause table
below. Lab: 2026.1 (Cinder 28.0.1), Kolla-Ansible 22.2.0 all-in-one, Cinder LVM
(thin, 19 GB pool, `max_over_subscription_ratio` 20) over iSCSI, RabbitMQ 4.2
quorum queues; not run: cause 5 as a separate case, Ceph, NFS, a real RabbitMQ
outage.

**Read-only checks.**
- `openstack volume show <volume-id> -c status -c os-vol-host-attr:host -c type -c size -c created_at`
  (the column is `type`; client 9.0.0 silently ignores `-c volume_type`; host `None` = no backend chosen).
- `openstack --os-volume-api-version 3.3 volume message list | grep <volume-id>`.
- `openstack volume service list` (`cinder-volume` listed as `<host>@<backend>`);
  `openstack volume backend pool list --long` (`free_capacity_gb`);
  `openstack volume type show <type> -c properties` (`volume_backend_name` must match a backend).
- Logs, Kolla-Ansible: `/var/log/kolla/cinder/cinder-scheduler.log` and
  `/var/log/kolla/cinder/cinder-volume.log`; Any: the same services' logs. Scheduler:
  `Filtering removed all hosts for the request with volume ID '<volume-id>'. Filter results: ...`
  (e.g. `CapacityFilter: (start: 1, end: 0)`); `No valid backend was found` does not carry the ID.

Path: `cinder-api` records `creating`, casts to `cinder-scheduler`, which filters
(`AvailabilityZoneFilter`, `CapacityFilter`, `CapabilitiesFilter`), sets the host
and casts to that `cinder-volume`; from an image the status goes `downloading`.
A `cinder-volume` or scheduler that starts again sets volumes it left in
`creating`/`downloading` to `error` (`Cleaning Volume with id <volume-id> and status creating`);
a request still queued in RabbitMQ is carried out when the service is back.

| Observation | Points to |
|---|---|
| `error`, host empty, message `Could not find any available weighted backend.` | 1: no backend passes (capacity, `volume_backend_name`, zone, backend down; on the lab a volume created 8 s after `cinder-volume` was `up` again failed with `AvailabilityZoneFilter: (start: 0, end: 0)`) |
| `error`, host set, `Driver failed to create the volume.` / `Image used for creating volume exceeds available space.`, or no message and an error in `cinder-volume.log` | 2: backend failed (VG/thin pool full: `vgs`, `lvs cinder-volumes` `Data%`; image data not matching `disk_format`: `ImageUnacceptable`, error in 4 s, no user message) |
| `creating`/`downloading`, host set, that `cinder-volume` `down` | 3: the service that had the request stopped |
| `creating`, host empty, every service `up`, volume ID in no Cinder log | 4: request lost before reaching a service |
| `creating` during download or `downloading`, service `up`, no error | 5: image still being written (`Image download <n> MB at <n> MB/s`, `Converted <n> MB image ...`) |

[LAB-VALIDATED: VM-VOL-02] Cause 3 behaviour: after `docker kill cinder_volume`
37 s into a 2 GB image download the volume stayed `creating` with its host set,
the service was `down` after about 55 s, systemd restarted the container after
60 s (Kolla-Ansible `Restart=always`, `RestartSec` 11 s by default, 59 s on this
lab with `docker_client_timeout: 600`) and the start-up clean-up set `error`; a
`systemctl stop` during a creation waited 21 s for it to finish (`available`).
Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder LVM (thin) over iSCSI; not
run: a manual `systemctl restart`, a RabbitMQ loss.

**Fix options.** A volume in `error` is not retried: fix the cause, create a new volume.
1. Wrong `volume_backend_name`. *State-changing*, for every future volume of the
   type (existing ones keep their backend); undo: set the previous value:
   `openstack volume type set --property volume_backend_name=<backend-name> <type>`.
   Refused with `Volume Type is currently in use. (HTTP 400)` while any volume of the
   type exists, `error` ones included: delete those first, or create a new type.
   [LAB-VALIDATED: VM-VOL-03] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder
   LVM (thin) over iSCSI; refusal, then success after deleting the error volume,
   then an `available` volume. Not run: zone or backend-down variants.
2. Capacity (free space or add a backend; raising `max_over_subscription_ratio` is
   a capacity decision, not a fix), backend or `image_conversion_dir` repair
   (cause 2), and cause 5 (wait; image-volume cache; with Ceph RBD for Glance and
   Cinder keep images `raw` so Cinder clones). [DOCUMENTED-UNVERIFIED: VM-VOL-04]
3. Cause 3. *State-changing*: restart `cinder-volume` after fixing what stopped it;
   operations in progress through it can fail, attached volumes stay attached.
   Kolla-Ansible: `sudo systemctl restart kolla-cinder_volume-container.service`;
   Any: `sudo systemctl restart <cinder-volume-unit>`. [DOCUMENTED-UNVERIFIED: VM-VOL-05]
4. Cause 4. Check RabbitMQ first (Kolla-Ansible: `docker exec rabbitmq rabbitmqctl cluster_status`).
   *Destructive*: `openstack volume set --state error <volume-id>`, then delete.
   Precondition: host empty, or that host's `cinder-volume` log shows no activity
   for the ID, and the volume was never `available`; otherwise the record lies and
   the delete can fail or orphan storage. [LAB-VALIDATED: VM-VOL-06] Lab: 2026.1,
   Kolla-Ansible 22.2.0 all-in-one, Cinder LVM (thin) over iSCSI, lost request made
   by purging the `cinder-scheduler` queue; not run: a real RabbitMQ outage.
5. Clean up. *Destructive*, no undo: `openstack volume delete <volume-id>`, only if
   never `available` (`created_at`, logs) and `attachments` empty. Verify with a
   test volume (*State-changing*, 1 GB, needs quota): `openstack volume create --size 1 runbook-check`,
   expect `available` on the expected backend, then delete it.
   [LAB-VALIDATED: VM-VOL-07] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder
   LVM (thin) over iSCSI; the delete removed the logical volume the backend had
   created; not run: Ceph, NFS.

## Stuck attaching or detaching

**Recognize.** Volume `attaching`, `reserved` or `detaching` minutes after the
request; a retry is refused because Cinder attaches only from `available` and
detaches only from `in-use` (non multi-attach). `openstack server event list <server-id>`
shows an `attach_volume` / `detach_volume` that failed or has no result. Data is
safe while nothing forces a state; forcing a status without checking the
hypervisor can give the volume two writers.

[LAB-VALIDATED: VM-VOL-08] Four views and causes 1, 2 and 4 below. Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, Cinder LVM over iSCSI, CirrOS; not run: cause 3,
RBD, multipath, multinode.

**Read-only checks** (compare all four; trust the hypervisor over both databases):
- Cinder: `openstack volume show <volume-id> -c status -c attachments` and the `attachment-list` above.
- Nova: `openstack --os-compute-api-version 2.89 server volume list <server-id>` (attachment ID needs 2.89);
  `openstack server event show <server-id> <request-id>`; `openstack volume service list`;
  `openstack compute service list --service nova-compute`.
- Hypervisor, on the host from `server show -c OS-EXT-SRV-ATTR:host -c OS-EXT-SRV-ATTR:instance_name`:
  Kolla-Ansible `sudo docker exec nova_libvirt virsh domblklist <instance-name>`; Any `virsh domblklist <instance-name>`.
- Logs: Kolla-Ansible `/var/log/kolla/cinder/cinder-volume.log`, `/var/log/kolla/nova/nova-compute.log`; Any: those services' logs.

| Observation | Points to |
|---|---|
| `reserved`/`attaching`, last event without result, Nova already lists it | attach still in progress: wait. With `cinder-volume` down Nova retried every 60 s; service back in time: `in-use`, event `Success`; after about 6 min Nova gave up (`CinderConnectionFailed`), volume `available`, event `Error` |
| Volume service `down` now or at the time | 1: `cinder-volume` down (a second attach refused with `400 Invalid volume`) |
| `detaching`, compute service `down` (it shows `up` for about a minute after stopping) | 2: `nova-compute` down; the request waits on the bus and ran within 20 s of the restart |
| `os_brick` exception (iSCSI login, multipath, RBD map), volume not in `domblklist` | 3: compute could not reach the storage |
| `detaching` then `in-use` again, still in `domblklist`, `DeviceDetachFailed: Device detach failed for vdb: Run out of retry while detaching device` | 4: guest did not release the device (8 tries of about 25 s; about 3.5 min on the lab with a paused guest). Nova already removed it from the persistent config, the running domain still has it |
| No trace of the request in `nova-compute.log` | request never reached the compute |

Cause 3 recognition and its fix: *State-changing*: when the volume is not in
`domblklist`, Nova does not list it and the last attach event has a result,
`openstack --os-volume-api-version 3.27 volume attachment delete <attachment-id>`
releases the reservation and the backend export (data untouched); then fix the
`os_brick` error before the user retries. [DOCUMENTED-UNVERIFIED: VM-VOL-09]
The same command on an attachment Nova still uses was refused with
`409 ... ConflictNovaUsingAttachment` (bug 2004555; releases without that fix
accept it, so check Nova's list yourself). [LAB-VALIDATED: VM-VOL-10] Lab: 2026.1,
Kolla-Ansible 22.2.0 all-in-one, Cinder LVM over iSCSI; not run: a release without the fix.

**Fix options.** Fix the service first, then make records match the hypervisor.
1. Causes 1 and 2. *State-changing*: interrupts other operations on that service;
   running instances unaffected. Kolla-Ansible:
   `sudo systemctl restart kolla-cinder_volume-container.service` (host running
   `cinder_volume`) or `sudo systemctl restart kolla-nova_compute-container.service`
   (compute); Any: restart the service. Then re-check `domblklist`; on the lab
   both completed by themselves (`in-use` / `available`), nothing to force.
   [LAB-VALIDATED: VM-VOL-11] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one,
   Cinder LVM over iSCSI; not run: the Any variant, multinode.
2. Cause 4, step 1: owner stops using the disk in the guest (unmount, stop the
   application) or stops the instance. Step 2, only if Cinder still shows
   `detaching`: *Destructive*: `openstack volume set --state in-use <volume-id>`
   changes the record with no check; only while `domblklist` (checked a minute
   ago) shows it attached to this instance and nothing else runs on the volume;
   `available` on an attached volume lets a second instance write to it. Undo:
   set the status matching the hypervisor. Cinder refuses it with no attachment
   record (`Cannot reset-state to in-use because volume does not have any attachments`).
   [DOCUMENTED-UNVERIFIED: VM-VOL-12]
3. Cause 4, step 3. *State-changing*: `openstack server remove volume <server-id> <volume-id>`;
   anything in the guest still using the disk loses it. Still stuck: stop the
   instance and detach while stopped. [LAB-VALIDATED: VM-VOL-13] Lab: 2026.1,
   Kolla-Ansible 22.2.0 all-in-one, Cinder LVM over iSCSI, paused guest resumed,
   Nova had set `in-use` itself; not run: step 2, the detach while stopped.
4. Hypervisor detached it, records did not follow (not in `domblklist`).
   *State-changing*: `openstack server reboot --hard <server-id>` (guest loses
   unwritten data; agree a time). Nova lists it, Cinder no longer: Nova removes it
   (`Removing stale volume attachment '<id>' from instance for volume '<volume-id>'`).
   Both still have it: the reboot **attaches it again**; then `server remove volume`.
   Nova's record without connection info: reboot leaves it out, `server remove volume`
   refused while `reserved`, `VolumeDriverNotFound: Could not find a handler for None volume`
   once `in-use`; what worked with the volume in no domain: the last resort in
   *Stale attachment*, then the hard reboot, then a normal attach.
   [LAB-VALIDATED: VM-VOL-14] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder
   LVM over iSCSI (hypervisor-only detach with `virsh detach-disk --live`); not run:
   other releases (the clean-up is documented in the 2026.1 Nova guide).

**Verify.** `in-use` with one attachment to the right server or `available` with
none; the attachment ID Nova lists equals Cinder's; `domblklist` agrees.

## Stale attachment

**Recognize.** Instance deleted but the volume `in-use` for it (`No Server found for <server-id>`),
so it can be neither deleted nor attached elsewhere; or after an evacuation,
more than one attachment, or one whose connector names the old host. Data intact;
the risk is giving the volume two writers.

**Read-only checks.** The Cinder checks above, plus
`openstack --os-volume-api-version 3.27 volume attachment show <attachment-id>`
(connector and host; on iSCSI/LVM its Properties hold CHAP `auth_username` and
`auth_password` in clear text: redact before pasting). Nova:
`server show -c status -c OS-EXT-SRV-ATTR:host -c OS-EXT-SRV-ATTR:instance_name`,
`server volume list` (2.89), `server event list`. `virsh list --all` and
`virsh domblklist <instance-name>` on the connector's host and the current host
(Kolla-Ansible inside `nova_libvirt`). `nova-manage volume_attachment show <server-id> <volume-id> --json`
(Kolla-Ansible: `sudo docker exec nova_api ...` on a controller) gives Nova's
attachment ID; for a deleted instance: `No volume Block Device Mapping with id <volume-id>`.

| Observation | Meaning |
|---|---|
| Instance absent from Nova, no domain on its last host uses the volume | stale, left by the deletion (cause 1) |
| Instance exists, attachment ID = the one `server volume list` shows | in use: keep |
| Instance on host B, this connector names host A, ID differs from Nova's | stale, left by the evacuation (cause 2) |

[LAB-VALIDATED: VM-VOL-15] Deletion case and Nova 2026.1 behaviour: `cinder-api`
down during a delete: instance gone in about 15 s, attachment left, three
`keystoneauth.session` warnings `Unable to establish connection to http://<cinder-api>:8776/v3/attachments/<attachment-id>`,
then `Ignoring unknown exception for volume <volume-id>: Connection to cinder host failed`;
no iSCSI session left, target still exported. `cinder-volume` down: instance
`deleting` (up to 7 min), finished when back, nothing stale. Compute down:
instance deleted from the database, Cinder showed `available`, but **the guest
kept running with the volume open** until `nova-compute` returned (`Destroying instance ... marked as DELETED but still present on host`),
leaving the domain defined and an iSCSI session: check `virsh list --all` before
trusting `available`. Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder LVM
over iSCSI; not run: the evacuation case and its classification row, RBD.

**Fix options.** Precondition for every step: no domain on the connector's host
uses the volume; for an evacuation the source host is fenced or its domain
destroyed (`openstack-incident-analysis`).
1. Cause 1. *State-changing*: `openstack --os-volume-api-version 3.27 volume attachment delete <attachment-id>`;
   releases the volume and the export, data untouched, undo not needed.
   Expect `available` once no attachment remains (about 2 s on the lab, target removed).
   [LAB-VALIDATED: VM-VOL-16] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder
   LVM over iSCSI; not run: RBD, multinode.
2. Cause 2. Preferred *State-changing*: `openstack server reboot --hard <server-id>`
   (documented to remove dangling attachments from both databases; guest loses
   unwritten data). Else delete only the attachment whose ID differs from Nova's
   and whose connector names the fenced old host; without the 409 protection that
   ID check is all that prevents detaching a running disk. [DOCUMENTED-UNVERIFIED: VM-VOL-17]
3. Nova's own attachment carries the old connection info. `nova-manage volume_attachment get_connector`
   then `refresh` (Nova 24.0.0 Xena and later; instance stopped and unlocked;
   disconnects, deletes and recreates the attachment). On Kolla-Ansible 22.2.0 it
   failed as written: `get_connector` as the default user gave `FailedToDropPrivileges`
   (works with `sudo docker exec -u root nova_compute ...`); `refresh` in `nova_api`
   as root gave `[Errno 13] Permission denied: '/dev/shm/<host>_nova-api_qmanager'`;
   as `nova` it timed out (`use_queue_manager = true`) **after** removing the
   connection and the attachment: volume `reserved`, instance started without it,
   repaired with the last resort, a hard reboot and a new attach. With
   `use_queue_manager = false` in a second `--config-file` the reply arrived.
   [LAB-VALIDATED: VM-VOL-18] Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder
   LVM over iSCSI; these are observed failures, not a working procedure; not run: a completed refresh.
   *Destructive on Kolla-Ansible 22.2.0*: the refresh itself (Any:
   `nova-manage volume_attachment get_connector --json > connector.json` on the compute,
   `nova-manage volume_attachment refresh <server-id> <volume-id> connector.json`;
   Kolla-Ansible: copy the file into `nova_api`, run as `-u nova` with the second
   config file); the owner may lose the volume until the repair. [DOCUMENTED-UNVERIFIED: VM-VOL-19]
4. Last resort, volume `in-use` with no attachment left. *Destructive*:
   `openstack volume set --state available --detached <volume-id>` changes the
   record only. Precondition: no attachment record, and on every host named by past
   attachments no domain uses it (`virsh domblklist`; RBD: `rbd status <pool>/volume-<volume-id>`
   shows no watcher). Undo: set the status back; data from two writers is lost
   without a backup. [LAB-VALIDATED: VM-VOL-20] Lab: 2026.1, Kolla-Ansible 22.2.0
   all-in-one, Cinder LVM over iSCSI; not run: the RBD watcher check.

**Verify.** Deleted instance: `available`, no attachment. Evacuated: `in-use`,
one attachment to the instance on its current host, listed by `domblklist` there.

## Stuck in deleting

**Recognize.** After `openstack volume delete`: `deleting` longer than the
backend needs, `error_deleting`, or back to `available`; or refused at once with
`Invalid volume: Volume status must be available or error or error_restoring or error_extending or error_managing and must not be migrating, attached, belong to a group, have snapshots, ...`.
The volume keeps its space and quota; no instance is affected unless it is still in use.

[LAB-VALIDATED: VM-VOL-21] Checks, delete path and causes 1, 2, 5 below. Lab:
2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder LVM (thin, iSCSI), 1 GB volumes;
not run: every Ceph RBD step, encrypted volumes, a lost RabbitMQ message.

**Read-only checks.** `openstack volume show <volume-id> -c status -c attachments -c os-vol-host-attr:host -c migration_status`;
`openstack volume snapshot list --all-projects --volume <volume-id>`;
`openstack volume service list --service cinder-volume`; Kolla-Ansible:
`sudo grep <volume-id> /var/log/kolla/cinder/cinder-volume.log | tail -n 30` (Any: same grep).

Path (Cinder 2026.1): the API accepts only `available`, `error`, `error_restoring`,
`error_extending`, `error_managing`, not attached/migrating/in a group, no
snapshots (unless `--cascade`); `--force` drops only the status condition. It
sets `deleting` and casts to `cinder-volume`, which logs `Deleted volume successfully.`;
`VolumeIsBusy` -> `Unable to delete busy volume.` and back to `available`; any
other error -> `error_deleting`. A queued delete runs when `cinder-volume` comes
back; one taken and not finished is rerun at start-up (`Initiating service <id> cleanup`).

| Observation | Points to |
|---|---|
| `deleting`, nothing in the log after the delete, service `down` (within 53 s on the lab) | 1: `cinder-volume` down or request lost |
| `error_deleting` with a traceback; on LVM `Logical volume cinder-volumes/volume-<volume-id> in use.` from `lvremove` (37 s on the lab) | 2: backend failed (an LV open on the host is this, not cause 4) |
| Log shows the operation in progress (Ceph flatten, large array delete) | 3: backend slow |
| `Unable to delete busy volume.`, back to `available` | 4: still in use (RBD watcher, exported LUN with a session) |
| `Invalid volume ...` at once | 5: refused by the API |
| Encrypted, `error_deleting`, `Unable to delete encryption key for volume`, nothing in `cinder-volume` | 6: key manager |

Ceph RBD and encryption (Cinder source, not lab-run): a watcher raises `ImageBusy`
(`ImageBusy error raised while deleting RBD volume`) and the volume returns to
`available`; a volume with clones (`<volume-name>.clone_snap`) is renamed
`<volume-name>.deleted` and kept until they go; dependent snapshots are flattened
first. The RBD trash is a fallback; without `enable_deferred_deletion` (default)
Cinder never purges it (`deferred_deletion_purge_interval` 60 s when enabled).
Read-only: `rbd status <pool>/volume-<volume-id>` (watchers), `rbd children`,
`rbd ls <pool> | grep <volume-id>`, `rbd trash ls <pool>`. For an encrypted
volume the API deletes the key **before** the delete: unrecoverable from then on,
whatever the status says later. [DOCUMENTED-UNVERIFIED: VM-VOL-22]

**Fix options.**
1. Cause 1. *State-changing*: start `cinder-volume` (or fix RabbitMQ), then **wait**
   for `Initiating service ... cleanup` and `Deleted volume successfully.` (15 s
   after the start on the lab; no reset needed). [LAB-VALIDATED: VM-VOL-23] Lab:
   2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder LVM over iSCSI,
   `systemctl stop` then `systemctl start kolla-cinder_volume-container.service`;
   not run: a lost message, the reset for a volume still `deleting`.
2. Cause 2. Fix what the traceback names, then *State-changing*:
   `openstack volume set --state error <volume-id>` (record only; precondition: no
   delete of it in progress in the log, or it races; undo
   `openstack volume set --state <previous-state> <volume-id>`), then *Destructive*,
   no undo: `openstack volume delete <volume-id>`; preconditions: owner confirms
   the data is not needed or backed up, attached nowhere. [LAB-VALIDATED: VM-VOL-24]
   Lab: 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder LVM over iSCSI, LV held
   open; gone in 6 s, quota back to 0; not run: Ceph, the undo of the reset.
3. Cause 1 still `deleting` with the service up and no delete in its log: the same
   reset and delete; `openstack volume delete --force <volume-id>` equals both, with
   both preconditions. Cause 6: fix the key manager (Barbican or the configured one),
   then reset and delete. *Destructive*. [DOCUMENTED-UNVERIFIED: VM-VOL-25]
4. Cause 3: wait; do not reset or delete again while a flatten runs. Cause 4: never
   force; find the client (watcher address, `virsh domblklist` on that compute),
   detach through Nova (see *Stale attachment*), delete when no watcher remains;
   removing the backend image by hand leaves a guest writing to freed storage.
   Covered by VM-VOL-22.
5. Cause 5: detach, delete snapshots, wait for the migration or leave the group.
   *Destructive*: `openstack volume delete --cascade <volume-id>` also deletes its
   snapshots. [LAB-VALIDATED: VM-VOL-26] Lab: 2026.1, Kolla-Ansible 22.2.0
   all-in-one, Cinder LVM over iSCSI; refusals for a snapshot and an attachment,
   `--force` on the attached one still refused, `--cascade` done in 6 s; not run: groups, migrations, transfers.

**Verify.** `openstack volume show <volume-id>` gives `No Volume found for <volume-id>`;
`openstack quota show --usage <project>` shows volumes and gigabytes down. LVM
leftovers: `sudo lvs <vg> | grep volume-<volume-id>`. Ceph: no image left except a
`.deleted` one kept for clones; check the trash.

## Extend while attached

**Recognize.** After `openstack volume set --size <new-GB> <volume-id>` on an attached volume:
- refused by the client: `Failed to set volume size: --os-volume-api-version 3.42 or greater is required to extend in-use volumes.`
  and `One or more of the set operations failed` (exit 1);
- accepted (exit 0) but size and status unchanged, message `extend volume:Could not find any available weighted backend.`
  (`Failed to schedule_extend_volume` in `cinder-scheduler.log`);
- `error_extending`, with `Extend volume failed.`, `Failed to extend volume.` and
  message `extend volume:Volume Driver failed to extend volume.` (no message if the driver is not initialised);
- Cinder shows the new size, the guest (`lsblk`) the old one.

Read-only: `openstack volume show <volume-id> -c size -c status -c attachments -c os-vol-host-attr:host`;
`openstack --os-volume-api-version 3.3 volume message list | grep <volume-id>`;
`openstack server event list <server-id>`. Kolla-Ansible:
`sudo grep -E 'Extend volume|Failed to extend|volume-extended' /var/log/kolla/cinder/cinder-volume.log`
(those lines carry no volume ID: match by time or request ID) and
`sudo grep <volume-id> /var/log/kolla/nova/nova-compute.log | grep -iE 'extend'` on the compute; Any: same greps.

Path: Cinder sets `extending`, the scheduler checks capacity, the driver grows
the volume, Cinder sends Nova `volume-extended`; `nova-compute` logs
`Cinder extended volume <id>; extending it to detect new size`, rescans (iSCSI,
FC via os-brick; RBD has no host device) and tells QEMU. If that refresh fails
(`Extend volume failed, volume_id=<id>, reason: ...`) **Cinder is not told**.
Partition and file system in the guest never grow by themselves.

[DOCUMENTED-UNVERIFIED: VM-VOL-27] Recognition and checks, reported from a lab run recorded only in a draft source page, executor not recorded (so not counted as validated). Normal path: `Extend volume completed successfully.`
2 s after the command, `Nova event response` 1 s later, the Nova line 1 s after,
guest `lsblk` at the new size. Shut-off guest: saw the new size at start (no
`Skipping block device resize` at INFO). Lab (recorded in the page body; the page
is a draft with no confirmed_by entry): 2026.1, Kolla-Ansible 22.2.0 all-in-one,
Cinder LVM (thin) over iSCSI, CirrOS with a 1 GB data volume, 2026-10-27; not
run: a refresh failure on the compute, Ceph RBD, Fibre Channel.

| Observation | Points to |
|---|---|
| Client or API refusal | 1: no 3.42, size not larger, quota or type limit, status not `available`/`in-use`, policy `volume:extend_attached_volume` |
| `error_extending` | 2: backend could not grow it |
| Old size and status, `Could not find any available weighted backend.` | pool too small: scheduler refused before the driver |
| New size in Cinder, old in guest | 3: event lost, `nova-compute` down, or refresh failed |
| `lsblk` new size, `df` old | 4: file system not grown |

Refusals other than the missing microversion (size, quota, type limits, status,
policy, API message `Volume <volume-id> status must be '...' to extend`) come
from the source code, not the lab. [DOCUMENTED-UNVERIFIED: VM-VOL-28]

**Fix options.**
1. Cause 1. *State-changing*, no undo (cannot shrink; quota charged):
   `openstack --os-volume-api-version 3.42 volume set --size <new-GB> <volume-id>`.
   [DOCUMENTED-UNVERIFIED: VM-VOL-29] Lab: as VM-VOL-27, normal path 1 GB to 2 GB; not run: Ceph RBD, FC.
2. Cause 2. Fix what `cinder-volume` names; size in Cinder is still the old one.
   *State-changing*: `openstack volume set --state in-use <volume-id>` (or `available`
   if detached), record only; precondition: backend volume healthy at its old size,
   attached as Cinder says; undo `cinder reset-state --state error_extending <volume-id>`
   (`volume set --state` does not accept it). Then extend again.
   [DOCUMENTED-UNVERIFIED: VM-VOL-30] Lab: as VM-VOL-27, failure injected by renaming the
   backend LV (`error_extending` within 8 s); not run: the undo, other backend errors.
3. Cause 3. Bring `nova-compute` back first: the queued event was processed 18 s
   after `systemctl start` and the guest saw the new size without reboot; check
   `Cinder extended volume <volume-id>` and `lsblk` before anything else. Cinder
   does not resend the event; if it was lost: *State-changing*:
   `openstack server reboot --hard <server-id>` (guest loses unwritten data; agree
   with the owner); 22 s with `--wait` on the lab. [DOCUMENTED-UNVERIFIED: VM-VOL-31]
   Lab: as VM-VOL-27, `nova-compute` stopped with `systemctl stop kolla-nova_compute-container.service`,
   lost event simulated by removing it from the queue; not run: a refresh failure, Ceph RBD.
4. Cause 3 alternative for a data volume: *State-changing*: `openstack server remove volume`
   then `openstack server add volume` (unmount in the guest first). Cause 4: the
   owner grows partition and file system in the guest (e.g. `growpart`, `resize2fs`
   or `xfs_growfs`). [DOCUMENTED-UNVERIFIED: VM-VOL-32]

**Verify.** `openstack volume show <volume-id> -c size -c status` shows the new
size and `in-use`; in the guest `lsblk` shows the new size, `df -h` the grown file system.
