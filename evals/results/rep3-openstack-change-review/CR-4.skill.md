## Summary

**Verdict: Not ready.** I haven't seen the script. No SQL file is in this session and none was pasted, so this review covers the plan as you described it. I looked at the approach, not the statements.

**Depth:** Full review. This is direct database editing across three services, with no tested way back and effects on running workloads.

**Top 3 risks:**
1. **Live guests and attached disks.** Instances stuck in BUILD, ERROR or deleting for months may still exist on hypervisors, with real disks, ports and volume attachments. Marking them deleted in the DB doesn't remove any of that. It hides it from Nova.
   - Nova may later reap guests that are running but marked deleted. I recall the default `running_deleted_instance_action` being `reap`, but verify that for your release.
   - Setting a volume to detached in Cinder while a guest still has it attached lets another VM attach it. That risks data corruption.
2. **The DB is not the only source of truth.**
   - Placement allocations keep consuming capacity on the compute hosts.
   - Nova's `nova_api` DB still holds `instance_mappings` and `request_specs`, and the block device mappings also need handling.
   - With OVN, the Neutron DB is not the data-plane truth, so deleting port rows leaves stale logical ports in the OVN NB DB.
   - Cinder backend exports and locks (iSCSI targets, RBD) are untouched.
3. **One transaction per DB gives no cross-DB atomicity and no rollback after commit.**
   - If Nova commits and Neutron or Cinder fails, the three services disagree.
   - A bulk transaction on Galera can cause writeset-size limits or flow control. The cause of the original stuck state also isn't known (see below).

## Objective and four questions
- **Objective:** Clear about 300 dead instances and the leaked ports and volumes. The business reason is not stated. Is it reclaimed capacity, quota, billing accuracy or tidiness? That decides how much risk is worth taking.
- **What does it protect?** Capacity and quota accuracy, plus a clean inventory. *(Reported)*
- **What could it affect?**
  - Running guests that are mislabelled as dead.
  - Customer data on volumes and boot disks.
  - Capacity accounting.
- **Operational burden:** The DBs would then disagree with the hypervisors and backends. That is hidden debt.
- **Who operates it afterwards?** Unknown.

## Starting state
- **Unknown:** Why they have been stuck for months. *(Gap)*
  - If the cause is still active (a dead compute service, a broken bus, a Cinder or Neutron error on delete), the pile will regrow after cleanup.
  - The cause may also explain why API deletes failed, which affects the method.
- **Unknown:** Platform health tonight, other changes in the window, and the release, Neutron backend, Cinder backend and Galera topology.

## Scope and blast radius
- **Touched:** Nova cell DB, Neutron DB and Cinder DB, written directly.
- **Reaches:**
  - Placement and `nova_api`.
  - OVN NB or agents.
  - Cinder backends.
  - Hypervisors (libvirt guests, disks, multipath).
  - Tenants' data, quotas and billing.
- **Selection logic is the main exposure:**
  - **Orphan ports:** A cross-DB join isn't possible, so "orphan" relies on a pasted ID list or a naive `device_id` test. That is dangerous because DHCP, router, floating IP and load balancer ports have non-instance `device_id`s. Ports of instances being created right now can also look orphaned.
  - **Instance selection:** Selecting by status and age can match instances that are legitimately slow or rebuilding.
- **Cell scope:** One cell, or all cells? Unknown.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | Nobody has accepted the failure case: a running customer VM reaped, or a volume corrupted. |
| Recovery | **fail** (as described) | Commit is irreversible. A whole-DB restore would discard other changes and leave the three DBs at mixed points in time. Row-level backups aren't mentioned. |
| Evidence | **fail/unknown** | No inventory showing these 300 are dead on the hypervisors. No rehearsal on a copy. |
| Owner | unknown | Owner for Nova, Neutron, Cinder and the tenants' data? |
| Authority | unknown | Who approves direct DB edits and accepts data-loss risk? |
| Blast radius | **fail** | All 300 in one go, no pilot, no batches. |
| Mandatory requirements | unknown | Data retention, audit trail and tenant notification rules. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Script reviewed line by line (redact credentials) | not met | Colleague |
| Per-resource inventory (read-only, below) | not met | Operator |
| Row-level backup of every row to be changed, plus a full dump of each DB, verified restorable | unknown | DBA |
| Rehearsal on a restored copy | unknown | Operator |
| Root cause of the stuck state identified | unknown | Operator |
| Galera health, write path and writeset limits checked | unknown | DBA |
| Tenants and billing informed | unknown | Service owner |
| Monitoring that sees the effect (Placement drift, orphan counts, VM and volume health) | unknown | Operator |

## Recovery
- **Method:** None credible today. A rollback would mean re-inserting saved rows, and that has never been exercised.
- **Point of no return:** Commit, plus any nova-compute reap or periodic task that acts on the new state.
  - Reaped guests and disks cannot be restored from the DB.
  - Data destroyed at the backend isn't recoverable from a DB backup.
- **Preserve first:** Full dumps; per-row exports of the affected tables, including dependent tables; hypervisor `virsh list --all` output; Placement allocations; Cinder backend listings.

## Recommended approach
Do the work through service APIs and the project tools, in batches. Use direct SQL only for the residue the APIs cannot clear, one record at a time, with a backup and a verification after each. That follows the usual guidance for database surgery.

1. **Inventory (read-only).** Per instance, record:
   - host and compute service state;
   - whether the hypervisor has the guest (`virsh`) and its disks (RBD or LVM);
   - Placement allocations (`nova-manage placement audit`, which is read-only unless `--delete`);
   - ports, including OVN logical ports;
   - volume attachments, BDMs and Cinder backend exports.

   Then classify:
   - **A:** nothing exists anywhere, so it is safe.
   - **B:** only DB residue.
   - **C:** a real guest or disk exists, so it needs the owner's decision.
2. **Fix the cause first,** or the pile regrows.
3. **Clean through the APIs where possible** *(state-changing)*:
   - Reset state, then delete.
   - Let Nova handle local delete where it supports that.
   - `openstack port delete`.
   - `cinder reset-state` plus attachment delete.
   - `nova-manage placement heal_allocations` and `nova-manage db archive_deleted_rows` afterwards.
4. **Pilot** with 3–5 category-A instances. Observe through a full periodic-task cycle, then move to batches.
5. **Direct SQL** only for what remains, per record.
6. **Never treat a volume as detached** before the backend and hypervisor confirm it.

## Execution boundaries and stop conditions
Batch size and observation period should come from your own baselines. Stop if:
- any inventory result contradicts "dead", such as a running guest, a watcher on an RBD image or an active port binding;
- affected row counts differ from the approved list;
- a service logs errors after a batch;
- the Galera cluster shows flow-control or lag;
- Placement or capacity numbers move unexpectedly;
- the approver is unreachable.

Resuming after a stop is a new decision.

## Verification (design before running)
- Counts of stuck instances, orphan ports and stale attachments reach zero, and the list of survivors is explained.
- Placement allocations match actual instances (`placement audit`).
- Quota usage matches reality.
- OVN NB has no stale logical ports for the deleted ones.
- Volumes still attached to real guests are untouched.
- A canary VM can be created, with a port and a volume attached, end to end.
- Observe for at least one full periodic-task cycle after each batch.

## Decision rights
- **Assessor:** Colleague plus a second engineer.
- **Capability owners:** Unknown for compute, network and block storage.
- **Accountable and decision maker:** Unknown. Someone with authority over tenant data.
- **Consumer communication:** Unknown. Tenants with ERROR instances may still want their volumes.

## Gaps and questions
Please send these, with credentials redacted:
1. The script itself, plus how it selects instances, ports and volumes.
2. Release, Neutron backend (OVN or OVS), Cinder backend, Galera topology and whether there is one cell or several.
3. Whether API deletes were tried, and what errors came back.
4. The reason for "tonight". Is it a deadline or just convenience?
5. What backups exist, and whether a restore has been tested.

## Decision record (draft)
- **Change:** Bulk cleanup of about 300 stuck instances, orphan ports and stale volume attachments. **Date:** unknown. **Decision owner, capability owner, assessor:** unknown (see Decision rights).
- **Objective:** Reclaim capacity and accurate inventory. The business driver is unknown.
- **Current state:** Unknown beyond "about 300 stuck for months".
- **Evidence:** None shown.
- **Uncertainty:** Root cause, hypervisor state, backend state, cross-DB consistency.
- **Options considered:**
  - (a) One SQL script per DB, tonight. **Rejected for now:** no recovery, no pilot, DB-only fix.
  - (b) Inventory, then API and tool-driven batches, with residue SQL per record. **Recommended.**
  - (c) Do nothing. This is cheap, but allocations and quota stay wrong.
- **Recovery:** Not credible yet. Needs row-level backups and a rehearsal.
- **Stop conditions and verification:** As above.
- **Follow-up:** Alert on instances in transitional states beyond a threshold, and record the root cause.
- **Risk acceptance:** None recorded. Any acceptance should be time-limited.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.