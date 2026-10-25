# Compute host patching plan: 300 hosts, 3 AZs, 3 weeks

The kernel and QEMU fix on all hosts within 3 weeks is the fixed requirement. How you get there is the part to design. With about 8 hosts of spare capacity (under 3%) and no criticality data, you can't live-migrate everything and you can't restart everything blindly. You need a differentiated strategy and a few decisions from named owners.

## Requirement and constraints
- **Mandatory (Reported):** kernel and QEMU fix on all 300 hosts, deadline 3 weeks.
- **Constraints (Reported):** about 8 hosts of free capacity in total, 3 AZs, some tenants with SR-IOV ports, and no workload criticality data.
- **Exposure if late:** unknown. Ask Security which vulnerabilities this closes, whether they are exploitable by tenants, and whether compensating controls exist. You need this if you end up asking for an exception.

## Scope: what I don't know yet
| Gap | Why it matters | How to close it |
|---|---|---|
| Spare capacity per AZ | The 8 hosts must be split by AZ. 3/3/2 is workable. 8/0/0 means two AZs can't be drained safely. | Per-AZ free vCPU, RAM and disk. |
| Hosts per AZ | I'm **assuming** about 100 each. | `openstack hypervisor list` grouped by AZ. |
| Storage model | Shared storage (Ceph) is cheap to migrate. Local disks need block migration, which loads network and storage. | Ask the storage owner. |
| Current libvirt/QEMU/kernel versions and CPU models | Decide migration direction and which targets are compatible. | Inventory of hosts. |
| Nova release | Decides whether SR-IOV, NUMA/pinned and vGPU instances can live-migrate. Verify for your release. | `nova-manage`, or the release notes of your deployment. |
| Server groups with anti-affinity | These restrict valid destinations and can block drains. | Check anti-affinity groups. |
| Which AZs have SR-IOV hosts and physnets | Spare capacity must be on SR-IOV-capable hosts to be useful for SR-IOV tenants. | Aggregate and flavor review. |
| How long a host drain takes | The pace of the whole campaign depends on it. | Measure it in the pilot. |

## Workload classes
Nova sees instances, not business processes. Criticality has to come from the tenants, so collecting it is the first deliverable. Use the shared table: project, instances, criticality, acceptable downtime, recovery expectations, blackout periods, owner, agreed strategy. Platform engineers fill in the technical-constraint column.

| Class | How identified | Strategy | Downtime | Sign-off |
|---|---|---|---|---|
| A. Critical and migratable | Tenant says so | Live migration, only with capacity in the same AZ | None expected | Tenant owner |
| B. Tolerates restart | Tenant says so | Cold migrate, or restart in place after reboot, in an agreed window | Minutes | Tenant owner |
| C. Not live-migratable (SR-IOV direct ports, PCI passthrough, vGPU, memory-heavy) | Flavor, port and device data (platform team) | Cold migration or coordinated restart | Agreed with owner, per instance | Tenant owner |
| D. Cannot be touched before the deadline | Tenant says so | Documented exception | n/a | Security and business owner |
| **Unknown (no answer)** | Default | Needs an explicit policy, see Decision 1 | | |

- **SR-IOV:** treat these as class C until you confirm your release can live-migrate them (verify for your release). Cold migration also needs free VFs on the same physnet at the destination.
- **Pinned/NUMA instances:** live migration is possible from Train onward. Check your release.
- **Prioritising outreach:** infra can't infer criticality, but it can find who to ask first. Look at the biggest projects, volume-backed instances, anti-affinity groups, instances with floating IPs, and long-uptime instances.

## Capacity check
The formula applies per failure domain. Spare capacity has to exist in **each** AZ, not in total:

> concurrent hosts drained in AZ ≤ (spare host-equivalents in AZ) − (failure reserve you decide to keep)

With your numbers, if the 8 hosts split 3/3/2, you can drain at most 2 hosts at once in each AZ with a reserve of 1. That drops to 1 in the AZ with only 2 spare, or zero if you keep no reserve. Note the trade-off: every host you use for maintenance is a host you can't use if a hardware failure hits mid-campaign.

**Throughput under those assumptions** (about 100 hosts/AZ, 2 concurrent per AZ, AZs run in parallel):
- 50 sequential batches per AZ.
- About 15 working days gives roughly 3.3 batches per AZ per day, so each batch (drain, patch, reboot, verify, return) must finish in about 2–3 hours of a working day.
- That's tight but not impossible with shared storage. With block migration, or running only 1 host at a time in some AZs, it is **not feasible**.

This is an estimate on assumed numbers. Measure real drain times in the pilot, and decide at the end of week 1 whether to continue, escalate, or widen the restart-tolerant population.

**Key lever:** the spare capacity doesn't limit how many hosts you patch overall. It limits how many are out at once. Hosts return to service after patching, so the spare is a rolling window. What limits you is how many instances need *live* migration at any moment, and that is where tenant answers help.

## Sequencing
1. **Landing zone first.** Patch the spare hosts first (in each AZ, while still empty). QEMU migration is supported old to new but not new to old, so instances can only move onto patched hosts. Verify this for your versions. For a kernel-only change the constraint doesn't apply, but you're doing both.
2. **Rolling per AZ.** Drain 2 hosts, patch, return, then repeat. Each patched host becomes the next landing zone.
3. **Pilot:** one AZ, one batch, one low-risk tenant, with both a live-migration run and a cold-migration run. Measure drain time and failure rate.
4. **Stagger AZs** at first. Run them in parallel only once you've seen that your control plane, network and storage handle it.
5. **No stacking:** keep this campaign free of other changes in the same windows.
6. **SR-IOV hosts as their own track.** They need their own landing zone with free VFs on the right physnet.

## Per-host procedure
Each step is a decision point. Don't continue past a failed verification.

1. **Read-only:** list instances and check classification and owner notification. `openstack server list --all-projects --host <host>`
2. **Read-only:** confirm the AZ still has capacity and the reserve is intact.
3. **State-changing:** disable the compute service with a reason. `openstack compute service set --disable --disable-reason "<ticket>" <host> nova-compute`
4. **State-changing:** move instances per class. Live: `openstack server migrate --live-migration [--host <dest>] [--block-migration] <server>`. Cold: `openstack server migrate <server>`, then confirm the resize after verification. Verify each instance is ACTIVE, reachable and performing on the destination.
5. **Read-only:** confirm the host is empty, or that only agreed-restart instances remain.
6. **State-changing:** patch and reboot. Verify kernel and QEMU versions, `nova-compute` and network agents up, no hardware errors.
7. **Optional:** boot a test instance on the host and check connectivity.
8. **State-changing:** re-enable. `openstack compute service set --enable <host> nova-compute`

**Never use evacuation for maintenance.** It is only for failed, fenced hosts.

## Patched binaries
A QEMU fix only protects instances that were migrated or restarted since the fix landed. An instance that stayed on an unpatched host is still running the old QEMU. Track per instance whether it has been moved or restarted since patching, or you'll declare completion with vulnerable guests still running.

## Boundaries and stop conditions
Set these before starting, from your own baselines (I'm not inventing numbers):
- Max hosts drained at once per AZ, and max concurrent migrations.
- **Stop** if: migrations fail or slow beyond the baseline, a destination behaves unexpectedly, critical-workload performance crosses the agreed threshold, AZ spare falls below the reserve, monitoring has blind spots, or the decision owner is unreachable.
- Resuming after a stop is a new decision, not an automatic continuation.

## Decision rights and communication
| Decision | Owner (name needed) |
|---|---|
| **Decision 1:** policy for tenants who don't answer (e.g., "no answer by date X means restart with N days' notice, live migration only where capacity allows") | Platform/business owner |
| Restart or downtime for a workload | The workload's owner |
| Deadline exception for any workload | Security and the business owner |
| Whether the deadline itself can move if the pilot shows it's infeasible | Security |
| Stop and resume during the campaign | Campaign lead |

Send the first tenant communication within the first couple of days: what's happening, the deadline, what you need from them (table plus any blackout periods), and what happens by default if they don't answer.

## Timeline
| Days | Work |
|---|---|
| 1–3 | Inventory, per-AZ capacity, criticality table sent, default policy decided, stop conditions set |
| 4–7 | Patch landing zones, pilot in one AZ, measure drain time |
| End of week 1 | **Gate:** projected completion vs deadline. Continue, widen the restart-tolerant population, or take the exposure question to Security. |
| Weeks 2–3 | Rolling waves across AZs, SR-IOV track in parallel, tracking per instance |
| Last 2–3 days | Reserve for stragglers, exceptions and re-verification only |

## Campaign completion criteria
Every host is patched and verified. Every instance has been migrated or restarted since the patch, or sits on the exceptions list with an owner. Compute services and agents are healthy. No instance remains on an unpatched binary unknowingly.

## Exceptions
| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| (to be filled) | | | | |

## Questions for you
1. How is the spare capacity split across the AZs, and how much is on SR-IOV-capable hosts?
2. Storage: shared or local disks?
3. What Nova release and what libvirt/QEMU versions are you on?
4. Who in the business can decide the "no answer" policy and accept exceptions?
5. Does Security accept a deadline extension, or compensating controls, for a small residual set?

## Follow-up
Keep the criticality table current as an input to capacity planning. If each campaign consumes this much capacity, spare capacity at 3% is a lifecycle problem to put on the roadmap.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can turn this into a tenant-facing criticality questionnaire or a per-AZ capacity worksheet once you have the numbers. I can also publish it as a shareable page if you want to circulate it to Security and the tenants.