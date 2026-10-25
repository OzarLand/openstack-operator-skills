## Bottom line

Full compliance in 21 days with live migration only, and no downtime for anyone, probably isn't feasible on 8 hosts of spare capacity. The numbers below show why. The plan that can work runs in two lanes:

- **Lane 1, owner-agreed restarts.** Uses no spare capacity. Its limit is coordination with owners, not capacity.
- **Lane 2, live migration for critical, migratable workloads.** Uses the spare pool in a rolling pattern.

The security deadline doesn't move. What changes is how each workload is treated, and that is a decision for the accountable owner. It needs to be made by about day 3, while there is still room to act on it.

## Requirement and constraints

- **Mandatory:** kernel and QEMU fix on all 300 compute hosts by about 2026-11-15 (21 days from today).
- **Known constraints:** 3 availability zones, about 8 hosts of free capacity, SR-IOV in use.
- **Observed:** nothing yet. All figures so far are reported by you.
- **Exposure if delayed:** not stated. Security needs to say which hosts matter most. A QEMU escape is most relevant where guests are untrusted, so hosts running untrusted tenant workloads should go first.
- **Question for security:** does a kernel livepatch cover the CVE? A livepatch removes the host reboot for the kernel part, but QEMU still requires each instance to be restarted or migrated onto the patched binary.

## Scope

| Item | Status |
|---|---|
| Hosts per AZ | Gap (assume ~100 each; unverified) |
| Free capacity per AZ | Gap (8 total; split unknown) |
| Nova, libvirt and QEMU versions | Gap |
| Storage model (shared or local) | Gap; local disks mean block migration |
| SR-IOV hosts and physnets | Gap |
| Measured drain and reboot times | Gap |

## Workload classes

| Class | How identified | Strategy | Downtime | Owner sign-off |
|---|---|---|---|---|
| A. Critical, migratable | Owner says critical; no SR-IOV, PCI, vGPU or large-memory constraint | Live migration to patched hosts (Lane 2) | None expected | Owner confirms criticality |
| B. Restart-tolerant | Owner accepts a restart in an agreed window | Coordinated restart in place (Lane 1) or cold migrate | Restart window | Owner agrees window |
| C. Not live-migratable | SR-IOV direct ports, PCI passthrough, vGPU on older versions, large-memory workloads without auto-converge | Restart or cold migrate, unless the release proves otherwise | Restart | Owner agrees, or exception |
| D. Unknown criticality | Owner has not answered | Treat as A for planning, so it takes the capacity-bound path | None expected | Escalate to project owner |

Notes:

- **SR-IOV:** treat as class C until your release and NIC driver are verified to support live migration of direct ports. Even where it is supported, a destination needs free VFs on the same physical network, so the 8 spare hosts may not qualify.
- **Unknown criticality** is a gap, not "low". Keep these instances in the capacity-bound path until owners respond.
- **Criticality table:** send the template in `criticality-table-template.md` to project owners today, with a response deadline of about day 3.

## Capacity check

Hours needed ≈ (300 ÷ B) × T

- **B** is hosts processed concurrently across the fleet. It is bounded by spare capacity per AZ, minus a reserve of one host per AZ for failures.
- **T** is the cycle time per host: drain, migrate, patch, reboot, verify, re-enable. Not measured yet.

| B (concurrent hosts) | T = 2 h | T = 4 h | T = 6 h | T = 8 h |
|---|---|---|---|---|
| 2 | 300 h | 600 h | 900 h | 1200 h |
| 4 | 150 h | 300 h | 450 h | 600 h |
| 6 | 100 h | 200 h | 300 h | 400 h |

Available time:

- **24/7 operation:** 21 × 24 = 504 h. B = 4 works only if T ≤ about 6.7 h.
- **Daytime only** (15 working days × 10 h = 150 h): B = 4 needs T ≤ 2 h. B = 6 needs T ≤ 3 h.

These are illustrative values, not measurements. The conclusion holds unless T is much shorter than you'd expect. Live migration of every instance through 8 hosts' worth of capacity is the bottleneck. Restart-tolerant workloads (Lane 1) don't draw on that pool, which is why they matter.

Also, free capacity counts only after fragmentation. The 8 hosts' worth is usable only if the scheduler can pack it, and only within the right AZ.

## Sequencing

1. **Patch the 8 spare hosts first.** They are empty, so this costs nothing. Verify with a test instance. They become the patched landing zone and stay as spare capacity.
2. **Drain unpatched hosts only onto patched hosts.** Migration from newer libvirt/QEMU to older is not supported, so once a host is patched, instances can move onto it but not back.
3. **Each drained and patched host re-enters as spare** and becomes a destination for the next batch. Total free capacity stays roughly constant through the campaign.
4. **Keep AZs separate.** Respect the reserve per AZ. Don't drain two hosts in one AZ beyond its spare.
5. **SR-IOV hosts** need their own landing zone, matched by physical network and VF availability. Check this before scheduling any SR-IOV drain.
6. **Lane 1 hosts** can be patched in parallel with Lane 2, within owner windows and the per-AZ rules.
7. **Keep the campaign separate** from other changes in the same window.

## Per-host procedure

1. **Read-only:** list instances on the host. Confirm each has a class and an owner who has been informed.
   `openstack server list --all-projects --host <host>`
2. **Read-only:** confirm service state and AZ.
   `openstack compute service list --service nova-compute`
3. **State-changing:** disable `nova-compute` on the host, with a reason, so nothing new is placed on it.
   `openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute`
4. **State-changing:** move Lane 2 instances to a patched host, then verify each one is active and reachable.
   `openstack server migrate --live-migration [--host <dest>] [--block-migration] <server>`
5. **State-changing, Lane 1:** restart or cold-migrate class B and C instances in their agreed window. A guest-level reboot does not start a new QEMU process, so use stop/start or a hard reboot.
6. **Read-only:** confirm the host is empty, or holds only agreed-restart instances.
7. **State-changing:** patch and reboot. Verify kernel and QEMU versions.
   `virsh version`
8. **Read-only:** confirm the running QEMU processes use the patched binary. A process started before the patch still runs the old binary. After a package update, `/proc/<pid>/exe` can show "(deleted)", which indicates a replaced binary. Verify this on your distribution before relying on it.
   `ps -o pid,lstart,args -C qemu-system-x86_64` and `ls -l /proc/<pid>/exe`
9. **State-changing:** re-enable the compute service. Smoke-test with a new instance.
   `openstack compute service set --enable <host> nova-compute`

**Never use evacuation for planned maintenance.** Evacuation is for hosts that have failed.

## Boundaries and stop conditions

Set these before the campaign starts. Figures are placeholders until measured.

- **Max concurrent drains per AZ:** spare hosts in that AZ, minus one reserve.
- **Max concurrent migrations:** from your Nova settings and baselines. Verify `max_concurrent_live_migrations` for your release.
- **Stop when:**
  - migration failures exceed a threshold you set, or migration time exceeds 2× your baseline;
  - a destination behaves unexpectedly;
  - critical-workload latency or error rate breaches its agreed threshold;
  - free capacity drops below the reserve;
  - monitoring has blind spots;
  - the decision owner is unavailable.
- **Resuming after a stop is a new decision**, not a continuation.

## Decision rights and communication

| Decision | Owner (name to fill) |
|---|---|
| Accept the deadline, or a phased exposure | Security, with the accountable executive |
| Accept capacity risk and the stop rules | Platform owner |
| Restart windows and downtime, per workload | Project owners, via the criticality table |
| Deadline exceptions | Named exception owner, with a review date |
| Schedule communication to tenants | Platform team, with notice to owners |

Suggested notice to tenants: at least 5 working days before their restart window, with the window and the expected impact.

## Campaign completion criteria

- Every host patched and verified: kernel and QEMU versions confirmed.
- Every instance either started or migrated since the patch, or listed as an exception with an owner.
- No instance left on an unpatched binary without being recorded.
- Compute services enabled and healthy; smoke test passed per AZ.

## Exceptions

| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| SR-IOV or PCI instances the owner won't restart | Not live-migratable; no restart agreed | Restrict new placement on unpatched hosts; tenant isolation review | TBD | TBD |
| Unknown-criticality workloads not answered by deadline | No owner input | Escalate; keep in capacity-bound path | TBD | TBD |

## Gaps and questions

1. **Requirement:** exact CVEs and packages; does a livepatch count; is a phased rollout with documented exceptions acceptable to security?
2. **Per-host data:** instance count, flavors, and utilisation distribution (to estimate usable free capacity after fragmentation).
3. **Per-AZ data:** host count and free capacity per AZ; which AZ the 8 hosts are in.
4. **Versions:** Nova, libvirt, QEMU, distribution, and whether the release supports live migration of SR-IOV direct ports and NUMA or pinned instances.
5. **Storage:** shared or local instance disks.
6. **SR-IOV and passthrough:** how many hosts and instances, physical networks, VF counts, NIC models.
7. **Measured timings:** drain and reboot durations from your last maintenance.
8. **Criticality:** owners for each project, and their answers.
9. **Working-hours policy and tenant blackout periods.**
10. **Overcommit policy:** could it be adjusted temporarily? This is a risk decision, not a default.

## Follow-up

- **Keep the criticality table current** after the campaign, as a document or as metadata on instances and projects. It is the input to future capacity planning.
- **Set a standing headroom target.** A forced 3-week campaign on roughly 3% headroom is a lifecycle finding, not an accident. Put it on the platform roadmap.
- **Consider a landing-zone pattern for future campaigns:** tag patched hosts (for example with a Placement trait or an aggregate) so new instances land on them.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can publish this as a shareable page or draft the criticality-table request for the project owners.