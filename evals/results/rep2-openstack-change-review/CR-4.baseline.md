The working directory (`/tmp/osk-eval-36lrb50r`) is empty, so I can't see the script yet. Please paste it or drop it into that directory. I can still flag the structural problems with the plan as you described it.

**Design problems**

1. **"One transaction per database" gives you no cross-database atomicity.** Nova, neutron and cinder are three separate commits. If cinder fails after nova has committed, you have a half-cleaned state and no way to roll back. Run each database as a separate, individually verified step, and decide the order on purpose.

2. **Marking instances `deleted` in SQL leaves the real resources behind.** For BUILD and ERROR instances this matters most:
   - Hypervisor side: libvirt domains, disks, and `instances/<uuid>` directories stay on compute nodes.
   - Placement: allocations stay, so capacity is consumed forever. You need `openstack resource provider allocation delete` or `nova-manage placement heal_allocations` / `audit`.
   - Ceph/LVM or other backend volumes and Glance-backed ephemeral disks are not touched.
   - Prefer `openstack server delete` or `nova reset-state --active` followed by a delete. If that fails, use `nova-manage` first. SQL should be the last resort for rows that really have nothing left behind.

3. **Nova's soft-delete is multi-table.** Setting `instances.deleted = id` alone is not enough. A correct script also needs the following (also check the nova version's schema):
   - `deleted`, `deleted_at`, `vm_state='deleted'`, `task_state=NULL`, and `terminated_at`.
   - The matching rows in `instance_info_caches`, `instance_system_metadata`, `instance_metadata`, `block_device_mapping`, `instance_extra`, `instance_faults`, `security_group_instance_association`, `instance_actions`, and `virtual_interfaces`.
   - The `deleted` column holds the row `id`, not `1`. It must be set that way, or unique constraints will break.
   - Quota usage / `quota_usages` and `reservations` need reconciling afterwards.
   - Instances that live in cell databases but are also referenced in `nova_api` (`instance_mappings`, `request_specs`, `build_requests`) need those updated too.

4. **Deleting "orphan" ports by SQL is dangerous.** The definition of orphan matters:
   - Check `device_id` against live Nova instances, not just deleted ones. A port whose `device_id` is a router, DHCP agent, load balancer, Octavia amphora, or Manila share is not an orphan.
   - Direct deletes skip `ml2_port_bindings`, IP allocations (`ipallocations`), floating IP associations, security group bindings, and DHCP/OVN/OVS state. OVN's northbound DB will keep the logical port. Use the API (`openstack port delete`) or at least `neutron-ovn-db-sync-util`.
   - If any ports are still attached on the hypervisor, deleting the row can break a running VM.

5. **Cinder "detach in the DB" is the riskiest part.** Updating `volumes.status/attach_status` and deleting `volume_attachment` rows does not touch the backend. The connection (iSCSI/RBD/FC export, multipath on the compute node) can stay live, and a later attach elsewhere risks data corruption. Use `cinder reset-state --attach-status detached` and `cinder attachment-delete`, which run `terminate_connection`. Then confirm no host is still using the volume (`rbd status`, `iscsiadm -m session`, `multipath -ll`). Also check `block_device_mapping.volume_id` in nova for consistency.

**Process before tonight**

- **Take backups and verify they restore.** `mysqldump --single-transaction` of `nova`, `nova_api`, `nova_cell0`, `neutron` and `cinder`, or a snapshot of the DB.
- **Build the list from a SELECT.** Review the exact 300 UUIDs and run the same query with `COUNT(*)` so it can be compared. A script should assert `ROW_COUNT() = 300` and `ROLLBACK` otherwise.
- **No `WHERE` that matches more than the intended set.** An `UPDATE` with a missing or loose `WHERE` (for example matching just `vm_state IN ('building','error')` across all projects) will hit instances that are legitimately in ERROR, such as those a customer is debugging. Use an explicit UUID list, plus a `created_at` / `updated_at` age cutoff.
- **Watch lock size and replication.** 300 instances is small, but cascading updates on `block_device_mapping` and `instance_actions_events` can hold locks. Galera deployments suffer from large write-sets (`wsrep_max_ws_rows`), and a Galera cluster will certify the whole transaction at commit, so deadlocks show up at the end.
- **Do a dry run on a restored copy** and compare results with `nova-manage db`, `openstack server list --all-projects`, `openstack volume list`, and `openstack port list`.
- **Stop or pause the services** (or at least the `nova-compute` / `nova-conductor` periodic tasks) that could race with your edits. The `_cleanup_running_deleted_instances` and `_sync_power_states` tasks will act on what they see in the DB.
- **Avoid running it at night with nobody around.** If it goes wrong, you want people awake who can restore.
- **Write the rollback.** If it is "restore the dump," then say how long that takes.

**A safer alternative**

1. Per instance, try `openstack server delete`. Fall back to `nova reset-state --active` and delete again.
2. For what remains, `nova-manage` / manual cleanup of hypervisor and placement leftovers.
3. Detach volumes with `cinder attachment-delete` and `cinder reset-state`.
4. Delete the ports via API once no live device references them.
5. Use SQL only for the stragglers, per database, with a UUID list, a count assertion, and a backup.

Send me the script and I'll go through it statement by statement, checking the `WHERE` clauses, the table coverage, and the count assertions.