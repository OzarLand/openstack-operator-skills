## Requirement and constraints

- **Fixed (Reported):** all 300 compute hosts get the kernel + QEMU fix within 3 weeks. Security sets this, and it doesn't change.
- **To design:** how we get there. The requirement defines *what*. Capacity and workload criticality decide *how safely* we get there.
- **Facts that shape the plan:**
  - About 8 hosts' worth of free capacity in total (Reported).
  - 3 AZs.
  - Some SR-IOV tenants. These VMs can't be live-migrated, so they need a restart or cold migration.
  - Business criticality is unknown. Nova sees instances, not business processes.
- **Exposure:** I don't know the CVE severity or whether it is exploitable guest-to-host. Ask Security, because it sets how much disruption is justified.

## Scope and gaps

I won't invent numbers. Please give me these:

| Gap | Why it matters |
|---|---|
| Hosts per AZ (100 each?) and spare capacity per AZ | The capacity limit is per AZ, not global |
| Shared storage or local disks | Local disks need block migration, which loads network and storage |
| libvirt/QEMU versions, CPU models, aggregates | Decide which hosts can be migration targets |
| Count of SR-IOV instances, hosts and physnets | Largest non-migratable class |
| Count of PCI passthrough, vGPU and pinned/NUMA instances | Same |
| Nova release | Live-migration limits vary by release (verify against your release docs) |
| Measured live-migration throughput and concurrency baseline | Everything about timing depends on this |

## Capacity check

- **Formula:** per AZ, hosts drainable at once = spare capacity in that AZ minus the reserve you decide to keep.
- **Your numbers:** 8 spare hosts' worth across 3 AZs is about 2.7 per AZ if evenly split (Assumption). Free capacity is often uneven or fragmented across hosts, so the real figure may be lower.
- **Consequence:** draining one host needs about one host of room in the same AZ. That allows **1–2 hosts per AZ at a time**, so **3–6 hosts in flight across the cloud**. Two per AZ leaves almost no reserve.
- **Throughput check:**
  - Each AZ has about 100 hosts to do in roughly 15 working days.
  - That is about 7 hosts per AZ per day.
  - With 2 per batch, that is 3–4 full drain, patch, reboot and verify cycles per AZ per day. A cycle must therefore finish in about 2–3 hours of wall-clock time.
  - Whether that is achievable depends on your measured migration times. This is the main schedule risk.
- **Conclusion:** the campaign is feasible only with a *differentiated* strategy. Live-migrating everything with 8 spare hosts is probably too slow to hit 3 weeks safely. The fix is to avoid live migration wherever the owner agrees to a restart.

## Workload classes

| Class | How identified | Strategy | Downtime | Sign-off |
|---|---|---|---|---|
| A. Critical, migratable | Owner says critical; no passthrough or SR-IOV | Live migrate to patched hosts | Near zero | Project owner |
| B. Tolerates restart | Owner agrees in the table | Restart in place on reboot, or cold migrate in a window. This needs no spare capacity. | Minutes | Project owner |
| C. Non-migratable (SR-IOV, PCI, vGPU) | Technical data from ports and flavors | Cold migrate or restart in an agreed window | Agreed | Project owner (mandatory) |
| D. Unknown owner or criticality | Default until answered | Treat as critical. Live-migrate if technically possible, otherwise escalate. | – | Escalate to project owner |

An empty criticality cell means unknown. It doesn't mean low.

**SR-IOV specifics (verify for your release):**
- Cold migration needs a free VF on the same physnet at the destination.
- Landing hosts therefore need SR-IOV capacity in the same AZ.
- Check how each tenant's MAC, IP and VLAN handling behaves across a restart.
- Notify these tenants first, because they need the longest lead time.

**Getting criticality without knowing which VMs matter:**
1. Export instances per project with `openstack server list --all-projects` (read-only).
2. Send each project owner the shared table (columns: criticality, acceptable downtime, recovery expectations, deadlines, owner, agreed strategy).
3. Give a short deadline, for example 3–4 days, and say that silence means class D: treated as critical, with no restart.
4. Enrich the table with technical flags (SR-IOV, pinned, large memory) from flavors and ports.
5. Build the table right after approval. It is the first deliverable and it blocks all disruptive work except the landing zone.

## Sequencing

- **Landing zone first.** Newer libvirt/QEMU to older isn't supported, so instances can move onto patched hosts but not back. Patch the first batch on spare capacity, empty hosts first (no migration needed). Then migrate only toward patched hosts.
- **Day 1–3:** patch hosts that are already empty or nearly empty, 1–2 per AZ, and grow the patched pool. Run a pilot on one host per AZ to measure drain time and surface surprises. Use that to recompute the schedule.
- **Then:**
  - **Rolling per AZ:** each patched host frees capacity as it returns, so the batch size stays constant.
  - **Parallel across AZs:** if one AZ lags, rebalance effort.
  - **Class B in bulk:** restart-tolerant workloads can be done without migration. This is the lever that saves time.
  - **Class C:** schedule in agreed windows.
- **Failure domains:** never exceed the per-AZ batch size. Check CPU model compatibility between source and target.
- **Keep the campaign isolated:** no other changes in the same windows.
- **Exception path:** workloads that can't be touched by the deadline get an exception with an owner, a compensating control and a review date, not silence.

## Per-host procedure (per host, rolling)

1. **Read-only:** `openstack server list --all-projects --host <host>`. Confirm every instance is classified and the owner informed.
2. **State-changing:** `openstack compute service set --disable --disable-reason "<reason>" <host> nova-compute`.
3. **State-changing:** move instances by class, with live migration only toward patched hosts. Verify each one: ACTIVE on the destination, reachable, performance acceptable.
4. **Read-only:** confirm the host is empty, or that only agreed-restart instances remain.
5. **State-changing:** patch and reboot. Verify the host is healthy and that the compute service and network agents are up.
6. Optionally boot a test instance on it.
7. **State-changing:** re-enable the compute service.
8. Record per instance that it has run on a patched QEMU since the patch.

**Never use evacuation for this.** It is for failed, fenced hosts only.

An instance still running on the old QEMU is not protected. Patching the host does nothing for it until it is migrated or restarted. Track it per instance, not only per host.

## Boundaries and stop conditions

Set these from your own baselines, which I don't have:
- Maximum hosts per AZ at once, and maximum concurrent migrations.
- Stop if:
  - migrations fail or slow beyond baseline,
  - free capacity in an AZ falls below the agreed reserve,
  - a critical workload crosses its performance threshold,
  - monitoring is blind,
  - the decision-maker is unavailable,
  - a destination behaves unexpectedly.
- Resuming after a stop is a new decision.

## Decision rights and communication

| Decision | Owner |
|---|---|
| Which workloads may restart | Project or tenant owners |
| Accepting a deadline exception | Security plus the accountable manager (name them) |
| Authorizing batch size, mass migrations and restarts | Change authority |
| Notifying tenants | Platform team, via a schedule published at least once, with SR-IOV tenants first |

## Campaign completion criteria

- All 300 hosts patched and verified.
- Every instance migrated or restarted since the patch, or listed as an exception.
- No instance running on an unpatched binary unknowingly.
- Compute services and agents healthy.

## Exceptions

| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| Unknown at this time | – | – | – | – |

## Questions that would change the plan most

1. Per-AZ spare capacity and host counts.
2. Measured live-migration times and concurrency limits.
3. Number of SR-IOV, PCI and pinned instances, and their physnets.
4. Whether local disks are used.
5. How exploitable the issue is, and whether Security would accept a slip for a few specific workloads.

## Follow-up

- Keep the criticality table as a living document or as instance and project metadata.
- Add maintenance scenarios to capacity planning.
- If every campaign eats this much capacity, 8 spare hosts out of 300 is a lifecycle problem for the roadmap.

If the pilot shows 3 weeks can't be met without disruption, take that exposure trade-off to Security with numbers. Don't quietly compress the safety margins.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.