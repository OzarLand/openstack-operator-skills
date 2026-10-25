## Summary

**Verdict: Not ready** (full-depth review: direct SQL on three production databases, with deletions that can't be undone). I couldn't find the script in the working directory, so this review covers the plan as you described it. Everything below is **Reported**, not Observed. Please send the script with credentials redacted, plus the output of the read-only checks listed under Gaps.

**Top three risks**
1. **The database state will disagree with the real world.** Marking an instance deleted in the cell DB doesn't remove its libvirt guest, volume connections, port bindings or Placement allocations. The script can only make the database say those things are gone.
2. **nova-compute may destroy guests that are still running.** Its periodic "running deleted instance" cleanup acts on instances that are deleted in the DB but still running on the hypervisor. The default action is, I believe, `reap`. Verify this for your release. Some of your ERROR or stuck instances may be live guests holding user data.
3. **One transaction per database is not atomic across the change.** Nova, Neutron and Cinder can each commit or roll back alone, and cross-DB "orphan" lists go stale between the time they're generated and the time the script runs. There is no recovery path for Neutron's hard deletes.

## Objective and starting state
- **Objective (Reported):** remove about 300 long-stuck instances, the orphan ports and the phantom volume attachments.
- **Four questions:**
  - It protects quota, capacity accounting and operator clarity.
  - It could affect running guests, tenant volumes and data, and the Neutron backend (OVN/OVS).
  - It adds no ongoing burden if done cleanly.
  - It leaves the root cause of the stuck states unaddressed, and that is unknown.
- **Starting state: unknown.** I have no evidence on:
  - why the instances got stuck, and whether that cause still exists;
  - whether the platform is stable tonight;
  - whether other changes are scheduled in the same window.

## Blast radius
- **Nova (cell DB):** the cell DB is only one of the places Nova keeps state for these instances. Also affected:
  - the matching `instance_mappings` and `request_specs` in the API DB;
  - Placement allocations, which stay behind and keep consuming capacity;
  - the hypervisors, where libvirt domains, disks and volume connections remain.
- **Cinder:** a volume flipped to `available` while its backend export, iSCSI session, RBD lock or multipath device is still live can be attached elsewhere and corrupt data.
  - Check whether any "attached to a deleted instance" volume is actually in use by a live instance.
  - A normal API delete would honour `delete_on_termination`, which may delete boot volumes. Decide that per volume, because the SQL shortcut silently skips it.
  - Quota usage counters drift.
- **Neutron:** direct deletes bypass ML2 and the backend.
  - OVN NB/SB entries, DHCP and port bindings are left behind.
  - Floating IPs, IPAM allocations and DNS records can be left dangling.
  - "Orphan" must exclude `network:*` ports (DHCP, router interfaces) and ports used by Octavia, Manila or Ironic.
- **Galera:** large multi-table transactions can trigger certification conflicts and flow control. Confirm the write path and cluster health before and after.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | The tenants and data behind the 300 instances haven't been identified. |
| Recovery | **fail** | Neutron deletes can't be reversed. A single-DB restore gives mixed points in time. No pre-image export or rehearsal has been mentioned. |
| Evidence | **fail** | There is no test on a copy, and no proof the SQL matches what the API does. |
| Owner | unknown | There's no named owner for the instances, volumes and ports. |
| Authority | unknown | No named person has accepted the data-loss consequence. |
| Blast radius | **fail** | All 300 plus ports and volumes go in one shot, with no canary or batches. |
| Mandatory requirements | unknown | Check retention and audit rules. Deleting tenant data may need approval. |

## Prerequisites
| Prerequisite | Status |
|---|---|
| Restorable backup, or a pre-image export of every affected row | unknown |
| Rehearsal on a restored copy of each DB | unknown |
| Frozen target list, each entry verified against the API and hypervisor | unknown |
| `running_deleted_instance_action` known, and set to `log` or `noop` during the change | unknown |
| Placement audit and quota resync plan | unknown |
| Tenants informed | unknown |
| Neutron backend (ML2/OVS or OVN) known | unknown |

## Recovery
- **Nova:** soft-delete flags are reversible only if you export the pre-image of every affected row. Before the change, compute could recreate or reap state.
- **Cinder:** reversible with a pre-image of the `volume_attachment` and `volumes` rows. It can't undo backend damage.
- **Neutron:** hard-deleted rows can't be recovered without a pre-image of ports, bindings, IP allocations and so on.
- **Point of no return:** the commit, and then any compute-side reap or later archive/purge job.
- **Exercised?** Unknown.

## Recommended path to "ready"
1. **Run the read-only inventory first.**
   - For each of the 300 instances, collect `task_state`, `updated_at`, host, volumes, ports and Placement allocations.
   - Use `openstack server show` and `nova-manage placement audit` (read-only).
   - Check hypervisors for live guests that match.
   - Freeze the result as a static UUID list, not a `WHERE vm_state IN (...)` predicate.
2. **Prefer supported mechanisms, with SQL only for what's left.**
   - Instances: `openstack server set --state error`, then `openstack server delete`. This does a local delete if the compute is down.
   - Ports: `openstack port delete`.
   - Volumes: `cinder attachment-delete` or `cinder reset-state --attach-status detached`.
   - Placement: `nova-manage placement audit` and `heal_allocations`.
   - Direct SQL belongs only where the API genuinely fails, one record at a time, with backup first and verification after.
3. **Canary.** Start with 5 to 10 instances of mixed types. Verify end to end (hypervisor, Placement, Cinder backend, Neutron backend, quota), then continue in batches.
4. **Fix the script itself if SQL stays.**
   - It should default to `ROLLBACK`, with `COMMIT` as a manual step.
   - It should assert `ROW_COUNT()` equals the expected number per statement, and abort otherwise.
   - It should run with errors fatal.
   - It should write a pre-image export.
   - It should do no autocommit or DDL.
5. **Keep evidence** for a few stuck instances so you can find the root cause. If that cause still exists, the problem will come back.

## Stop conditions (to define before running)
- Any row count differs from the frozen list.
- A target turns out to have a live guest or a volume in use elsewhere.
- Galera shows flow control or a cluster warning.
- The Neutron or Cinder backend shows state the DB doesn't match.
- Nobody with decision authority is reachable.

## Verification (to define before running)
- Create and delete a test VM with a volume and a port.
- Run the Placement audit and check no new orphan allocations.
- Confirm no unexpected guest reaping in nova-compute logs.
- Confirm the Cinder backend shows no stale exports.
- Confirm Neutron/OVN has no dangling entries.
- Check quotas, then observe for an agreed period.

## Decision rights
Technical assessor, capability owner, accountable person and decision maker are all **unknown**. Name them, and name who tells tenants what's happening.

## Gaps and questions
- Please send the script (redacted) and the instance, volume and port selection criteria.
- Which release, Neutron backend and volume backend do you run, and how many cells?
- Why were the instances stuck, and is that cause fixed?
- What is `running_deleted_instance_action`?
- Which backup or restore evidence exists?
- Why tonight, and what is the cost of waiting a week for a staged run?

## Decision record (draft)
- **Change:** direct DB cleanup of ~300 stuck instances, orphan ports and phantom volume attachments.
- **Options considered:** (a) one-shot SQL, (b) API-first staged cleanup with SQL for residue. Option (a) was rejected pending the evidence above.
- **Recovery, stop conditions and verification:** see above.
- **Owners, date and dependencies:** unknown.

I haven't seen or run anything, so none of this confirms the script is wrong. These are the questions that must be answered before it runs.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can write this up as a shareable page for your colleague and the change board if you'd like.