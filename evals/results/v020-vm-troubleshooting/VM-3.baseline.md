Yes, it usually works, but it should be your last step, not your first. `reset-state` only edits the Cinder database. It doesn't touch the backend, so it can leave things behind on the LVM/iSCSI side.

**Check first**

1. **Make sure nothing is still using the volume.** If the instance delete only half-completed, the VM or its iSCSI session could still exist on the old compute node. Check with `virsh list --all` and `iscsiadm -m session` (and `multipath -ll`) on that host. Writing to the volume from two places can corrupt it.
2. **Look at the stale attachment records.**
   ```
   openstack volume show <vol>        # attachments, status, attach_status
   cinder attachment-list --volume-id <vol>
   ```
3. **Try the clean path first.** Delete the stale attachment, which calls `terminate_connection` and removes the iSCSI export and ACL for the old initiator:
   ```
   cinder attachment-delete <attachment-id>
   ```
   Nova also keeps its own `block_device_mapping` row. If it still points at the deleted instance UUID, that row can cause trouble later. Nova's `nova-manage volume_attachment` commands handle that case.

**If the attachment delete fails or there's no attachment record**

```
cinder reset-state --state available --attach-status detached <vol>
```
Afterwards, check these:
- `volume_attachment` rows for that volume are gone or marked deleted. If they linger, the next attach can fail.
- The backend export is gone. On the cinder-volume node, run `tgtadm --lld iscsi --op show --mode target` for tgt, or `targetcli ls` for LIO. Look for a target for that volume and remove any stale one. Otherwise the new attach may hit a duplicate-target or ACL error, or leave the old host's initiator with access.
- The volume's `status` and `attach_status` both read `available` and `detached`.

Then attach it to the new instance as normal. For a bootable or data volume, it's worth a quick `fsck` or a read-only mount first if the old instance died uncleanly.

Check the volume's `multiattach` flag as well. It isn't the cause here, but it's a common reason for a volume to look stuck.