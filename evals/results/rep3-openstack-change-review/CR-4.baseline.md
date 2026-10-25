The working directory is empty, so I can't find the script. Please paste it or drop it into `/tmp/osk-eval-cvwqinob`. Until then, here is what I'd check, because the plan has structural problems whatever the SQL says.

**Problems with the approach**

1. **One transaction per database doesn't give you atomicity across the three.** Nova, Neutron and Cinder are separate databases. If the Nova commit succeeds and the Neutron one fails, you are left in a new inconsistent state. Make each step idempotent and re-runnable, and keep the order explicit.
2. **Marking instances deleted in the DB is not the same as deleting them.** Setting `deleted=id`, `vm_state='deleted'` or `deleted_at` on `instances` leaves the following behind:
   - Resources on the hypervisor: libvirt domains, disks, and the files in `/var/lib/nova/instances`. Instances stuck in BUILD may have partial ones.
   - Placement allocations, which are the biggest hidden problem. The resource providers keep counting the usage, so capacity stays consumed and scheduling gets worse.
   - Related rows: `instance_info_caches`, `block_device_mapping`, `instance_system_metadata`, `instance_faults`, `instance_extra`, `instance_actions`, `security_group_instance_association`, `instance_id_mappings` and `instance_mappings` in the API DB. Soft-deleting only `instances` leaves these orphaned.
   - Quota usage. Stale `quota_usages` or `reservations` rows can keep counting against projects. Newer releases count usage from the instances themselves, so check your release.
   - The API DB. `nova_api.instance_mappings` and `request_specs` need to be consistent with the cell DB.
3. **Deleting Neutron ports directly in SQL is dangerous.** Removing rows from `ports` skips:
   - `ml2_port_bindings`, `ipallocations`, `portsecuritybindings`, `standardattributes`, `ml2_port_binding_levels`, `ipamallocations`, `floatingips` and `allowedaddresspairs`. Depending on the FK cascades, you get orphans or constraint errors.
   - The backend. OVN/OVS state, DHCP agent leases and L3/router ports are not cleaned up. Make sure the script cannot match `device_owner` values such as `network:router_interface`, `network:dhcp` or `network:floatingip`.
   - How "orphan" is decided. A cross-DB join isn't possible, so the instance ID list has to come from Nova. If that list is stale or built wrong, you delete live ports. Check that the match is on `device_id` plus `device_owner LIKE 'compute:%'`, and that the ports' hosts are checked.
4. **Detaching volumes in the Cinder DB is the riskiest part.** Setting `volumes.status='available'` and `attach_status='detached'`, and deleting `volume_attachment` rows, does not terminate the connection on the storage backend. The volume can still be exported or mapped to the hypervisor's initiator (iSCSI/RBD lock/multipath). If a volume is then attached elsewhere, you can get two writers and data corruption. Use `cinder reset-state --attach-status detached` or `cinder attachment-delete` where possible. Also make sure the volume isn't attached to a **live** instance, which a wrong join would hide.
5. **Large instance sets must not be handled by guessing from the state.** Months in BUILD or ERROR is a good filter, but some of those instances may have running guests or hold volumes with data. Verify per instance.

**What I'd ask for before tonight**

- **Backups.** Take a fresh dump of all three DBs, plus `nova_api`, and confirm you can restore it.
- **A dry run.** Run the script's `SELECT` equivalents and review the exact lists: 300 instance IDs, the ports and the volumes. Have a second person sign off on them.
- **A canary.** Do 3 to 5 instances first, through the APIs if possible, then verify Placement, the hypervisor, Neutron and Cinder.
- **Prefer the supported tools.** For instances:
  - `nova reset-state --active` followed by `openstack server delete` (or `--force`).
  - `nova-manage` for orphaned allocations (`nova-manage placement audit --verbose [--delete]`).
  - `openstack port delete` and `openstack volume delete`/`attachment delete`.

  Use SQL only for what the APIs can't clear.
- **A quiet window**, nova-conductor/scheduler awareness, and a rollback plan.
- **Row-count assertions.** Have each `UPDATE` and `DELETE` check `ROW_COUNT()` and abort the transaction on a mismatch with the expected count.
- **A `WHERE` clause on every statement** that is tied to an explicit ID list, not only to state and age.
- **Avoid long locks.** Don't hold a big transaction open on busy tables like `instances` or `ports`.

Send me the script and I'll go line by line. I'll check the join logic, the FK and cascade effects, which rows each statement touches, and whether anything can match live resources.