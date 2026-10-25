The working directory is empty, so I can't find your colleague's script. Please paste it here or drop it into `/tmp/osk-eval-znm22t2o`, and I'll review the actual SQL.

Until then, these are the problems I'd expect in a plan like this. I'll check each one against the script.

**Blocking issues**

1. **Back up first.** Take a `mysqldump` or `pg_dump` of `nova`, `nova_api`, `neutron` and `cinder`, or at least of the affected tables. One transaction per database only gives atomicity inside each database. The three databases can't be rolled back together. If the nova commit succeeds and the neutron one fails, you have a half-cleaned state.
2. **Don't set `deleted` by hand.** Setting `instances.deleted = id` and `vm_state='deleted'` leaves other tables inconsistent:
   - `instance_info_caches`, `instance_system_metadata`, `instance_metadata`, `block_device_mapping`, `security_group_instance_association`, `instance_actions` and `instance_faults` don't get their rows soft-deleted.
   - `nova_api.instance_mappings` and `request_specs` are not updated. In cells v2, `nova list` and the scheduler still see them.
   - Placement allocations for these instances are not released. Compute nodes show phantom usage, which is probably why BUILD and ERROR instances matter at all. Clean them up with `openstack resource provider allocation delete <consumer>`.
3. **Real resources may still exist.** For instances stuck in BUILD for months, the hypervisor may still have libvirt domains, disks and `instances/<uuid>` directories. Also check for Cinder volumes that nova attached and Neutron ports bound to a host. The DB-only approach leaks these silently. Compare against `virsh list --all` on the computes.
4. **Prefer supported tooling.** For each instance, try `nova reset-state --active <uuid>` and then `nova delete`. If compute is unreachable, `nova force-delete` or `nova-manage` will work. At 300 instances this is a short loop with logging, and it handles ports, volumes and allocations through the APIs. For ports, use `openstack port delete`.
5. **Detaching volumes in the Cinder DB is the riskiest step.**
   - Setting `status='available'` and `attach_status='detached'` by hand can leave `volume_attachment` rows, connection info and backend exports (iSCSI/RBD/NFS locks) stale.
   - If a volume is still mapped or in use on a host, you risk data corruption when it is reattached elsewhere.
   - Use `cinder reset-state --state available --attach-status detached` plus `cinder attachment-delete`. Also confirm that no hypervisor still has the device open.
6. **Deleting neutron ports from the DB** leaves stale entries elsewhere. OVS or OVN flows, DHCP and the L3 agent, `ml2_port_bindings`, `ipallocations`, floating IP associations and OVN NB `Logical_Switch_Port` all go out of sync. Use `openstack port delete`, and for OVN run `neutron-ovn-db-sync-util`.

**Script-level checks I'll apply once I see it**

- Are the `WHERE` clauses keyed on explicit UUID lists or on a status and age filter? A status-only filter can catch live instances that are legitimately building. Also look for `deleted = 0` and `project_id` or `cell_id` scoping.
- Is the `UPDATE` row count asserted to be ≤ 300 before `COMMIT`? Look for `ROW_COUNT()` checks or a `SELECT count(*)` dry run.
- Does "orphan ports" mean `device_id` pointing at a nonexistent instance? That's a cross-database join, so the instance list has to be copied in. Does it exclude `device_owner` values such as `network:dhcp`, `network:router_interface` and `network:floatingip`? Those aren't instances and must never be deleted.
- Is the transaction isolation and lock scope acceptable? A large `UPDATE` on `instances` holds locks that can stall API requests. If tables are InnoDB, it should be batched.
- Is there a Galera/MariaDB cluster? Large transactions can fail certification, so batch them.
- Is the script idempotent, and does it log which UUIDs it touched so you can reverse it?

**Suggested plan for tonight**

1. Run a read-only version of the script (`SELECT` instead of `UPDATE`/`DELETE`) and diff the UUID list against `openstack server list --all-projects` and `virsh`.
2. Back up the databases.
3. Try the API route on 5 instances. Check allocations, ports and volumes.
4. Fall back to DB edits only for instances the API can't handle (for example, an unreachable compute). Use an explicit UUID list, batches of about 25, and a verification query after each batch.

Send the script and I'll go through it line by line.