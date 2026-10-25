## Summary

**Verdict: Not ready.** This is a review of the plan as you described it. I haven't seen the script (no `.sql` file is in this session), so everything about its contents is `unknown`.

**Depth:** full. This is a direct edit of three production databases that can't be cleanly undone, and its effects reach hypervisors and storage backends that SQL can't see.

**Top 3 risks:**
1. **The DB state and reality will diverge.** Nova, Neutron and Cinder will say "deleted", "gone" and "detached" while guests, attachments and allocations still exist on hypervisors, in Placement and on the storage backend.
2. **"One transaction per database" gives no safety across the three.** The transactions only help if the script crashes midway. A wrong `WHERE` clause commits cleanly. After `COMMIT` the only rollback is a DB restore, which isn't credible on a live platform.
3. **"Orphan" is probably defined by a query that can misfire.** Neutron ports with a `device_id` that Nova doesn't know can be DHCP ports, router interfaces, Octavia, Manila or Ironic ports. These are not orphans.

## Starting state

Several things look true from your description, but I haven't seen output for any of them:
- **Reported:** ~300 instances are stuck for months, with orphan ports and volumes attached to deleted instances.
- **Unknown:** the root cause of the stuck state. If it's a bus, scheduler or compute problem, it will recreate stuck instances after the cleanup.
- **Unknown:** whether other changes are scheduled tonight, and whether the platform is stable now.
- **Unknown:** how many cells you have. Failed-scheduling instances live in `cell0`, and instance mappings live in `nova_api`.

## Blast radius: what a DB-only cleanup misses

These are the standard gaps. I can't confirm which apply until I see the script.

**Nova**
- **Running guests:** an instance in ERROR or "deleting" can still have a live libvirt domain, disks and OVS/tap devices on a host. Marking the row deleted orphans them.
- **Reaping risk:** `running_deleted_instance_action` defaults to `reap` on many releases (verify for yours). Once rows are deleted, the compute periodic task can destroy a still-running guest that someone is actually using.
- **Placement allocations:** these are not released, so capacity leaks. That's the same class of problem `nova-manage placement audit` exists to find.
- **Other tables:** a correct soft delete also touches `block_device_mapping`, `instance_info_caches`, `instance_extra`, metadata tables, faults and security-group associations. In `nova_api` it touches `instance_mappings`, `request_specs` and `build_requests`. A partial update leaves API list and show calls inconsistent.
- **Cells:** a script that only touches one cell DB misses the others.

**Neutron**
- **Port ownership:** check `device_owner`, not just `device_id`. Anything other than `compute:*` needs separate justification.
- **Port bindings:** bound ports may have stale OVN or OVS state on a host. Floating IP associations and IPAM allocations are also affected.
- **Quotas:** quota counts and fixed IP allocations can go stale.

**Cinder**
- **Backend export:** flipping `attach_status` in the DB does not remove the iSCSI/NVMe/RBD export or the host-side connection. If a volume is reported "available" but is still attached to a zombie guest, the next attach can mean two writers, which is a data-corruption risk. This matters most for multi-attach and for RBD locks.
- **Attachment rows:** `volume_attachment` rows and nova's `block_device_mapping` must agree. Cinder's `quota_usages` can drift.

**People**
- **Tenant data:** owners of ERROR or BUILD instances may not know they exist or may still want the data. Billing or usage events are not emitted either.

## Decision gates

| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | There's no impact statement, and no tenant or owner notification is mentioned. |
| Recovery | **fail** | Post-commit recovery is "restore the DB", which is not credible on a live platform. Restoring one DB to a different point in time than the others leaves them inconsistent. |
| Evidence | **fail** | There's no test in a representative environment. There's no dry run showing exactly which 300 rows, ports and volumes would be touched. |
| Owner | unknown | |
| Authority | unknown | Direct DB edits need a named human with authority to accept the consequence. |
| Blast radius | **fail** | It's all 300 at once, with no batches and no pilot. |
| Mandatory requirements | unknown | Check whether audit, billing or retention rules apply to deleting tenant resources. |

## Why tonight isn't the constraint

These instances have been stuck for months, so waiting a week costs little. A rushed run of a script that hasn't been tested costs a lot. The schedule pressure doesn't change the verdict.

## What I'd propose instead

1. **Triage read-only first:**
   - Run the SELECTs to produce the exact lists: instance UUIDs with host and state, ports with `device_owner`, and volumes with attachments.
   - Cross-check every instance against its hypervisor (`virsh list --all`, disks, tap devices) and against Placement (`nova-manage placement audit`).
   - Check whether the compute service and host for each instance even exist.
2. **Use the APIs wherever they work.** These go through the services, so they clean up Placement, hypervisors and backends:
   - **Instances:** `openstack server set --state error`, then `openstack server delete`. Nova does a local delete when the compute service is down.
   - **Ports:** `openstack port delete` for ports confirmed orphaned.
   - **Volumes:** use `cinder attachment-delete` or `cinder reset-state --attach-status detached` after confirming the backend is not exported or attached.
3. **Pilot 5–10 instances**, covering each state (BUILD, ERROR, deleting), and verify the capability end to end. Only the residue the APIs can't clear goes to SQL.
4. **Run any remaining SQL per batch, one row at a time with verification**, as the database-intervention notes require. Each batch needs:
   - A pre-image export of the affected rows and a generated reverse script. This is a row-level undo and is far more realistic than a restore.
   - An expected row count asserted inside the script, with `ROLLBACK` if it differs.
   - Small transactions, because large writesets on Galera can hit certification conflicts and flow control.
5. **Notify project owners** with the list and a cutoff date.
6. **Fix or understand the root cause**, or you'll be back here.
7. **Afterwards:** reconcile Placement, `nova-manage db archive_deleted_rows`, and re-run the audits.

## Prerequisites

| Prerequisite | Status | Owner |
|---|---|---|
| Backups of nova, nova_api, cell DBs, placement, neutron and cinder at one point in time, with a restore test | unknown | |
| Dry-run output reviewed by someone other than the author | missing | |
| Hypervisor and backend cross-check | missing | |
| Monitoring and verification queries defined | missing | |
| Galera health and write path confirmed | unknown | |
| Named approver | unknown | |

## Stop conditions to define before any run

- The row count differs from the reviewed list.
- Any instance turns out to be running or reachable.
- Any port has a non-`compute:*` owner.
- A volume is still exported on the backend.
- Galera shows flow control, or API errors or latency rise.
- The approver is unavailable.

## Verification

- `openstack server list --all-projects` shows none of the 300.
- `nova-manage placement audit` is clean.
- `nova-manage cell_v2 verify_instance` is clean (verify the command for your release).
- No `device_id` points at a non-existent instance, and no volume is `in-use` against a missing server.
- Hypervisors show no orphan domains or disks.
- A new instance boots, attaches a volume and gets a port end to end.

## Decision rights

- **Technical assessor:** unknown
- **Capability owners:** nova, neutron, cinder and storage backend owners (unknown)
- **Accountable:** unknown
- **Decision maker:** unknown
- **Consumer communication:** unknown

## What I need from you

1. The script, with any credentials, `transport_url` or `connection` strings redacted.
2. Your OpenStack release and Cinder backend, and the number of cells.
3. Output of the SELECT-only versions of its `WHERE` clauses.
4. The backup and restore status.
5. Who the approver is.

With the script I can review it statement by statement and say which of the gaps above actually apply.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.