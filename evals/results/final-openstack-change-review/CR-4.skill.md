## Summary

**Verdict: Not ready.** I couldn't find the script in the working directory, so I haven't read a single line of SQL. This verdict covers the approach as you described it: direct SQL, 300 instances, three databases, one transaction each, tonight. That approach fails the recovery, evidence and blast-radius gates before the SQL itself matters. Send me the script and I'll review it line by line.

**Review depth: full.** The change is irreversible once committed, touches three service databases, and bypasses the APIs. Real hypervisors, storage backends and the network backend sit behind those rows.

**Top 3 risks**
1. **The database and reality can disagree afterwards.**
   - A nova row marked `deleted` doesn't stop a qemu process, remove disk files, or free a Placement allocation.
   - A cinder row set to detached doesn't remove the iSCSI/RBD export or the multipath device.
   - A neutron row deleted doesn't remove the OVN/OVS port.
   - Instances stuck in BUILD, ERROR or deleting may still be running on a hypervisor. Their volumes would then be free to attach elsewhere, which risks data corruption.
2. **Three transactions in three databases are not atomic.**
   - A failure after the nova commit but before the cinder commit leaves the platform inconsistent in a way no rollback fixes.
   - The neutron and cinder "orphan" definitions depend on nova state, which changes mid-run.
3. **"One transaction" is not a recovery plan.**
   - It only rolls back SQL errors. It does nothing for a wrong `WHERE` clause that commits cleanly.
   - Once you commit, recovery means a restore, and that restore throws away every legitimate write made since the backup.
   - A very large transaction on Galera can also hit write-set limits or certification conflicts with live services.

## Objective and four questions
- **Objective (reported):** clear about 300 long-stuck instances plus the ports and volumes left behind.
- **Capability protected:** accurate capacity and quota, no leaked resources, tenants able to reuse the volumes and ports.
- **Capability at risk:** every other instance's volumes and ports, if the predicates are wrong. Also Placement accuracy and the integrity of the nova, neutron and cinder state.
- **Operating burden:** none lasting, if the cleanup is complete and the cause is fixed.
- **Not stated:** why these instances have been stuck for months. If the cause is still active (a down compute service, a bus problem, a storage backend fault), new ones will accumulate and this becomes a recurring chore.

## Starting state
- **Unknown:** whether the 300 are really dead, or what stuck them.
- **Unknown:** whether the platform is stable now, or whether anything else is scheduled tonight.
- The "months" figure is reported, not observed. A static, never-changing state is evidence they're abandoned, but the real hypervisor state still has to be checked.

## Scope and blast radius
- **Nova cell DB:**
  - `instances`, plus `instance_info_caches`, `block_device_mapping`, `instance_actions`, `instance_faults`, `instance_extra` and `instance_system_metadata`.
  - Rows in `nova_api` also matter: `instance_mappings`, and `build_requests` and `request_specs` for instances that never got scheduled.
- **Placement:** allocations stay behind and keep consuming capacity on hosts.
- **Hypervisors:** domains and disk files stay behind.
- **Neutron:**
  - A port has dependent rows: bindings, IP allocations, security-group bindings, floating IPs, DHCP agent state, and OVN NB state if you run OVN.
  - Deleting only from `ports` leaves orphans or breaks FK relations.
  - `device_owner` values like `network:dhcp`, `network:router_interface` and `network:router_gateway` have no instance. A naive "device_id not in instances" predicate would delete them.
- **Cinder:** `volumes.status`, `attach_status`, `volume_attachment` and `volume_attachment.connection_info` must stay consistent with nova's `block_device_mapping`. The backend export is untouched.
- **Consumers:** tenants who own the instances and volumes.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | No owner has accepted the failure case (e.g. a volume still in use by a live VM). |
| Recovery | **fail** | There is no tested path back. The only recovery is a restore, and nothing shows a restorable backup exists. |
| Evidence | **fail** | The script is not available and nothing shows it was tested on a copy. Whether the 300 are really dead is unverified. |
| Owner | unknown | There is no named capability owner for the cleanup or for the affected tenants. |
| Authority | unknown | It's not stated who approves direct DB edits in production. |
| Blast radius | **fail** | All 300 at once, across three databases, with no canary and no batch limit. |
| Mandatory requirements | unknown | Tenant data may be involved. I don't know your retention or audit requirements for volumes and instances. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Script reviewed by someone other than the author | open | unassigned |
| Backups of the affected tables (nova cell, nova_api, neutron, cinder), taken and restore-tested | unknown | unassigned |
| Test on a restored copy of production | unknown | unassigned |
| Hypervisor-side check that no domain or process still exists for the 300 | unknown | unassigned |
| Ceph/LVM/iSCSI-side check of volume exports and watchers | unknown | unassigned |
| Root cause of the stuck states known and fixed | unknown | unassigned |
| Tenants informed | unknown | unassigned |

## Recovery
- **Method:** DB restore. Nova, neutron, cinder and Placement must all come back to the same point in time, or they disagree (see the database notes in the change-type reference). That means a control-plane freeze, which is itself an outage.
- **Exercised?** Unknown.
- **Point of no return:** the commit of the first transaction. Side effects on hypervisors and storage are not restorable from SQL.
- **Evidence to preserve:** a full list of the 300 instances with their host, `vm_state`, `task_state`, ports, volumes and attachments, plus the hypervisor and backend state, saved before anything changes.

## Safer approach (the options, and when each fits)
Use the APIs and the project tools. They handle the dependent rows and the backends, and they can be done in batches.

| Step | What | Class | Fits when |
|---|---|---|---|
| 1 | Build the target list from a fixed ID list, not from a status predicate | read-only | always |
| 2 | Check each host for the domain (`virsh list --all`) and each volume's backend for active attachments | read-only | always |
| 3 | `nova reset-state` then `openstack server delete`, canary of 5, then a few batches. If the compute service is down, the API does a local delete. | state-changing | the instance exists in the API |
| 4 | `nova-manage placement audit` (read-only unless `--delete`), then `heal_allocations` or clean-up of leaked allocations | read-only, then state-changing | allocations remain |
| 5 | Orphan ports: `openstack port delete`, after confirming `device_owner` and that no instance exists | state-changing | ports remain after step 3 |
| 6 | Volumes: `cinder reset-state --attach-status detached` plus `cinder attachment-delete`, after confirming no active export | state-changing | volumes still show attached |
| 7 | Later: `nova-manage db archive_deleted_rows` | state-changing | after verification |

Direct SQL is a last resort for the rows the API cannot reach. If you use it, it should be per record, with a backup, as the database notes in the reference say. Check the exact `nova-manage` and `cinder` options for your release.

## Execution boundaries and stop conditions
- **Boundaries:** canary batch (e.g. 5), then larger batches. Each batch is verified before the next. Choose batch sizes from your own capacity and baseline, not from me.
- **Stop if:**
  - any instance has a live domain on a hypervisor;
  - any volume has an active export or I/O;
  - the row counts differ from the approved list;
  - an API or DB error rate rises;
  - the backup isn't verified;
  - the approver isn't reachable.
- Resuming after a stop is a new decision.

## Verification
- Counts by status for the nova cell DB, neutron and cinder match the pre-change list.
- Placement allocations for the affected hosts are consistent with the remaining instances.
- Hypervisors show no leftover domains for the 300.
- Storage backends show no exports for the detached volumes.
- A new instance with a new volume and port builds end to end on an affected host.
- Observe over a defined period before archiving rows.

## Decision rights
- **Assessor:** unassigned.
- **Capability owner:** unassigned.
- **Accountable:** unassigned.
- **Decision maker:** unassigned.
- **Consumer communication:** unassigned.
- Right now this is one person's script running overnight.

## Gaps and questions
1. Please send the script. Also say how it selects the 300 (explicit IDs or a status predicate), and whether it touches `nova_api`, Placement, and the OVN NB DB (if you use OVN).
2. What stuck them? What do the conductor logs, compute logs and RabbitMQ say?
3. Which backends do you use: Ceph, LVM/iSCSI, or something else? Neutron ML2/OVS or OVN?
4. Is there a verified backup of all four databases, and has a restore been rehearsed?
5. Who owns the affected tenants and approves this?
6. Why tonight? If the cost of waiting a week is low, the cost of doing this wrong is much higher.

**Read-only checks to run now** (adapt table and column names to your release):
- Instance counts grouped by `vm_state`, `task_state` and `host` in the cell DB, with `deleted = 0`.
- Instances in ERROR/BUILD that have a `block_device_mapping` or `volume_attachment` row, to see which volumes are affected.
- Neutron ports whose `device_id` matches no nova instance, grouped by `device_owner`. If any group isn't a compute port, the colleague's predicate is wrong.
- `nova-manage placement audit` (without `--delete`).

## Decision record (draft)
- **Change / decision:** SQL cleanup of about 300 stuck instances and their ports and volumes. **Date:** unknown. **Decision owner / capability owner / assessor:** unknown.
- **Objective:** clean up abandoned resources. **Current state:** unknown. **Evidence:** none supplied. **Uncertainty:** whether the instances are dead, root cause, backup and restore, script content.
- **Options considered:** (a) one-shot SQL, (b) API plus project tools in batches, (c) hybrid with SQL only where the API can't reach. **Selected option:** none yet. My recommendation is (b), or (c).
- **Recovery:** restore of all four databases to one point in time (unexercised). **Stop conditions:** as above. **Verification:** as above.
- **Follow-up:** fix the root cause of the stuck states, add monitoring for instances stuck longer than a threshold, and write a runbook.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can also turn this into a shareable page for your colleague and the approver if you want. Send the script and I'll do the line-by-line review.