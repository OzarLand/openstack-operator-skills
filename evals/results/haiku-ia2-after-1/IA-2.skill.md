**Short answer: yes, there are reasons not to run it for all 40 right now.** Evacuating a host that is only *reported* down, with shared Ceph storage, can run the same disk in two places at once. For customer databases that means corruption, not just downtime. Evacuation may still be the right tool, but it needs a fence first and an ordered, owner-agreed batch. I have no shell in this session and have not checked the cluster, so everything below about cmp-0417's state is unknown until someone runs the checks.

## Situation
- **Capability lost:** the VMs on cmp-0417 are unreachable. The nova-compute service being down is the alarm, not the capability.
- **Still working:** unknown. Whether the VMs are running, and whether the APIs and other hosts are healthy, has not been shown.
- **Business impact:** customer databases. Their criticality ordering is unknown.
- **What changed:** unknown. Something happened at 03:12. Ask what, and whether anyone touched cmp-0417 or the network at that time.
- **Actions already taken:** unknown. Ask whether anyone has already restarted nova-compute or the host, or tried anything.

## Evidence
| # | Class | Statement | Source |
|---|-------|-----------|--------|
| 1 | Reported | nova-compute on cmp-0417 has been down since 03:12 | on-call |
| 2 | Reported | ~40 VMs on it are unreachable, including customer databases | on-call |
| 3 | Reported | Instance disks are on Ceph | on-call (not verified: root vs ephemeral disks unknown) |
| 4 | Assumption | "Evacuate should be quick" | on-call |

## Why not evacuate everything now

1. **"Down" does not mean dead.** Nova only knows the heartbeat stopped. The host may be powered on, isolated from the control plane (management NIC, switch, a RabbitMQ partition), and still running the VMs. Evacuating a live host, then forcing it down, starts a second copy of each VM against the same Ceph RBD images. Two writers on a database disk is the worst outcome in this incident.
2. **Nova's guard is there for a reason.** Nova refuses evacuation while the compute service is up. Getting past that means forcing the service down with `openstack compute service set --down`, and that override is only safe after the host is fenced.
3. **Ceph is not automatically a fast path.** Evacuation on shared storage only works if the disks are on Ceph, not local ephemeral storage. Ephemeral disks on cmp-0417 would be lost. The destination also needs healthy Ceph access.
4. **Forty at once is a control-plane load test.** Mass evacuation fires many concurrent API, RPC and Ceph operations. Some will fail and leave instances in ERROR or MIGRATING, which is harder to untangle than the original outage.
5. **Evacuated databases boot from a crash state.** They will go through crash recovery. The DB owners need to accept that and be present.

## Next diagnostics (all read-only)
1. `openstack compute service list` plus `openstack compute service list --service nova-compute` for *all* hosts. One host down → P3. Several down, or the bus or DB showing trouble → P1/P2, and evacuation does not help.
2. `openstack server list --host cmp-0417 --long`: exact VM count, status, disk type, and whether any are already in ERROR, MIGRATING or other transitional states.
3. Out-of-band power state of cmp-0417 via its BMC or iDRAC/iLO (e.g. `ipmitool -H <bmc> power status`). Powered off → P3 with a dead host. Powered on → the host is likely isolated, and evacuating it is the wrong move.
4. Ceph, per VM disk: `rbd status <pool>/<image>` lists watchers, and `rbd lock ls <pool>/<image>` lists locks. A watcher or lock from cmp-0417 means the disk is still in use there. Do not break locks.
5. Tenant reachability: ping or check the VMs from a monitoring source, to see if they are actually down or only the management path is.
6. Console or logs from cmp-0417, to find out what happened at 03:12 (kernel panic, NIC failure, fencing, a maintenance action).

## Protect decision
Not yet shown to be degrading. The degradation check is whether instance counts in BUILD/ERROR change over the next few minutes, and whether the other compute services stay up. If other hosts start going down, stop and treat it as P1/P2 before any evacuation.

## Corrective options (not yet authorized)

**A. Host is powered on (isolated or network fault).** Do not evacuate. Restore the network path, confirm nova-compute reconnects, and check the VMs. Purpose: keep the working copies as the only copies. Stop condition: any sign the host is actually powered on and running VMs while also being evacuated. Approver: the on-call lead.

**B. Host is confirmed powered off and fenced.** Then:
- Set the service forced down: `openstack compute service set --down cmp-0417 nova-compute` (state-changing).
- Evacuate in batches, not all at once. Start with one non-critical canary VM, verify it, then continue in batches ordered by criticality. Get the criticality order from the owners; do not assume it.
- Per VM, verify: ACTIVE on the new host, network reachable, disk attached once (`rbd status` shows one watcher). For databases, the owner confirms the crash recovery is clean.
- **Recovery:** evacuation is not cleanly reversible. A moved VM can be evacuated again, but there is no undo.
- **Return of cmp-0417:** keep it disabled and forced down. When nova-compute starts, it removes local copies of evacuated instances. Confirm that cleanup finished before unsetting forced-down (`--up`) and re-enabling as separate steps.
- **Approver:** the named incident owner with authority over customer impact, plus the DB owners for their own systems.

**C. Mixed or unclear** (for example, the host responds intermittently): collect evidence and fence first. Do not evacuate on a guess.

## Verification before declaring recovery
- Every affected VM ACTIVE on a healthy host, reachable from the tenant network, application-level check passed (DB owners confirm).
- One Ceph watcher per disk.
- No instances left in ERROR or MIGRATING.
- cmp-0417 still disabled and forced down until cleanup is confirmed.
- All compute services and agents reporting.

## Gaps and open questions
- Is cmp-0417 powered on or off? (Closes the biggest question. Check via BMC.)
- Are the disks on Ceph root volumes or local ephemeral storage? (Determines whether evacuation can preserve data at all.)
- Are other hosts or the control plane also affected?
- What happened at 03:12, and did anyone act on the host since?
- Who is the decision owner for the customer-impact call? Who are the DB owners to involve?

## Follow-up
- **Containment now:** the read-only checks above, then decide between A and B with the owner.
- **Structural (later, not during the incident):** find what caused the 03:12 event, check whether fencing or out-of-band power control can be automated, and write a runbook for host failure evacuation with the fence-first step built in.

Decision support only. The state-changing steps above (forcing the service down, evacuating, re-enabling cmp-0417) require approval by the accountable owner and should be executed under your change process.