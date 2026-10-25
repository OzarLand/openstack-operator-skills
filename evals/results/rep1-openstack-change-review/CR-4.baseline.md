The working directory (`/tmp/osk-eval-_itqu4m6`) is empty, so I can't see your colleague's script. Paste it here or put it in that directory and I'll review the actual SQL.

Until then, here is what I'd flag from the plan as you describe it. Treat it as a checklist to hold the script against, not a review of the script.

**Biggest concern: direct SQL across three services**
- Direct DB edits skip the services' own logic. Nova's API delete does more than set `deleted`: it cleans up allocations in Placement, BDMs, port bindings, instance mappings in the API DB, and the hypervisor-side resources. Marking rows deleted in the cell DB leaves these behind and breaks the **Placement allocations**, which will keep consuming capacity on compute hosts.
- Three separate databases cannot share one transaction. "One transaction per database" means a failure in the third can leave nova, neutron and cinder inconsistent with each other.

**Nova**
- Soft delete in nova sets `deleted = id` (not `1`), plus `deleted_at` and `vm_state='deleted'`, `task_state=NULL`. Check the script does all of these, and the same for related tables (`instance_info_caches`, `instance_system_metadata`, `instance_extra`, `block_device_mapping`, `instance_faults`, `instance_actions`, `security_group_instance_association`, and others).
- `nova_api.instance_mappings` and `request_specs` need attention too, or `nova list` and the scheduler will behave strangely.
- Check the `WHERE` clause. It should match explicit UUIDs from a reviewed list, not just `vm_state IN ('building','error')` or "older than N months". Otherwise tonight's run may hit instances that are legitimately in ERROR. Confirm the row count is exactly ~300 before commit.
- Check for instances that still exist on a hypervisor. Run `virsh list --all` or equivalent on the computes. Otherwise you'll leak running VMs and their disks, and could leave duplicate MACs/IPs.
- Check for instances in the middle of a live operation, for example `task_state` not NULL on a compute that is currently alive.

**Neutron**
- "Orphan ports" needs a precise definition. The script should only delete ports whose `device_id` points to an instance that's confirmed gone in nova, and should skip router, DHCP and other `device_owner` ports.
- Deleting from `ports` alone leaves rows in `ml2_port_bindings`, `ipallocations`, `securitygroupportbindings`, `portsecuritybindings`, `standardattributes`, etc. Foreign-key cascades may cover some of these, but verify.
- Backend state remains: OVN/OVS entries, DHCP leases, and floating IPs attached to those ports. With OVN, deleting from SQL does not remove the NB DB logical switch ports, so you get a permanent mismatch.
- Floating IPs and allocated fixed IPs: check the script doesn't leave dangling references.

**Cinder**
- Detaching in SQL only changes `volumes.status/attach_status` and `volume_attachment`. The backend export (iSCSI target, RBD lock, multipath) is not touched. A volume marked `available` while still exported to a dead host risks double attach and data corruption.
- Check `volume_attachment` is marked deleted rather than the row being removed, and that `attached_host`/`instance_uuid` are cleared. Also check `connection_info` and BDM consistency with nova.
- Volumes with `multiattach` or in `in-use` status that are really attached to a live instance must be excluded.

**Process**
- Take backups or dumps of all three DBs (and the nova_api DB) immediately before running, and test a restore.
- Run it on a restored copy first and compare row counts.
- Print affected-row counts per statement and `ROLLBACK` by default. Require a manual `COMMIT` after you check the numbers.
- Run it in batches (for example 20 instances) rather than all 300 at once. Long transactions on nova's `instances` table can lock out live traffic.
- Run it in a maintenance window, not just "tonight," and make sure nova-conductor and the API aren't acting on these instances concurrently.
- Prefer the supported tools where possible:
  - `nova-manage` and `nova-manage db archive_deleted_rows` for cleanup.
  - `nova reset-state --active` followed by `nova delete`, or `nova force-delete`.
  - `openstack volume set --state available` / `cinder reset-state --attach-status detached`, and `cinder-manage volume update_host` where relevant.
  - `neutron-db-manage`, or `openstack port delete`.
  - `nova-manage placement heal_allocations` / `audit --delete` for orphaned allocations.
  
  A small loop around the APIs for 300 items is slow-ish but safe, and it's the better default.

Send me the script and I'll go through it line by line against this list.