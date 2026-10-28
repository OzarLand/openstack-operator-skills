**Not as your first move.** Don't run `reset-state` yet. For a volume left `in-use` after its server was deleted, the lower-risk fix is to delete the stale attachment. The reset only edits Cinder's record, and the leftover attachment and iSCSI export would stay in place.

## Why not reset first

- `cinder reset-state --state available --attach-status detached` is the same as `openstack volume set --state available --detached`. It changes the database row and nothing else. It doesn't remove the attachment record, the iSCSI target export on the LVM host, or any iSCSI session or libvirt domain still on the compute.
- If the old guest is still running with the disk open, for example because the compute was down when the delete ran, a reset lets you attach the volume to a new instance while the old guest can still write to it. That means two writers and a risk of corruption. In the lab, a delete with the compute down left the guest running with the volume open until nova-compute returned.

## Read-only checks first (Observed evidence needed from you)

1. `openstack volume show <vol> -c status -c attachments`
2. `cinder --os-volume-api-version 3.27 attachment-list --all-tenants 1 --volume-id <vol>`. Check the Volume ID column, because the `openstack` filter is ignored on client 9.0.0.
3. `openstack --os-volume-api-version 3.27 volume attachment show <att-id>` to get the connector and host. Redact the CHAP `auth_username` and `auth_password` before pasting.
4. `openstack server show <deleted-id>` should return not found. On the old host, run `virsh list --all` and `virsh domblklist <instance-name>`. On Kolla-Ansible, run these inside `nova_libvirt`. Nothing should reference the volume.
5. On the compute, `iscsiadm -m session` should show no session for the volume's IQN.

## Fix options (not yet authorized)

| Option | Use when | Risk | Status |
|---|---|---|---|
| **A. `openstack --os-volume-api-version 3.27 volume attachment delete <att-id>`** (preferred) | The attachment exists, the instance is gone, and no domain uses the volume | State-changing. It releases the reservation and the backend export, and data is untouched. No undo is needed. | `[LAB-VALIDATED: VM-VOL-16]` on 2026.1, Kolla-Ansible 22.2.0 all-in-one, Cinder LVM over iSCSI. The volume went `available` in about 2s. Not run on RBD or multinode. |
| **B. `openstack volume set --state available --detached <vol>`** (the reset) | Last resort. The volume is `in-use` and no attachment record is left, and no domain on any past host uses it | Destructive. It changes the record only. | `[LAB-VALIDATED: VM-VOL-20]`, same lab scope. Not run: the RBD watcher check. |

If you do B, the undo is to set the status back. Data written by two writers can't be recovered without a backup.

## Verification

- The volume is `available` with no attachments.
- `lvs` and `tgtadm` or `targetcli` on the cinder-volume host show no leftover export.
- After the user attaches it to the new instance, there is exactly one attachment. Its ID matches `server volume list --os-compute-api-version 2.89`, and `virsh domblklist` on the new host shows the disk.

## Gaps

- I haven't seen your outputs, so the cause is an assumption.
- I don't know your release. The lab was 2026.1, and other releases need their own verification.
- I don't know whether the compute was healthy when the instance was deleted.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you paste the output of checks 1–4, with the CHAP credentials redacted, I can tell you whether A applies or whether B is justified.