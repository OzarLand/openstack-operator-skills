This is a plan skeleton built on your numbers. Everything else is marked as a gap. Nothing here has been run, and I have no access to your cloud.

## Requirement and constraints
- **Fixed (Reported):** kernel + QEMU fix on all 300 hosts within 3 weeks, set by Security.
- **To design:** how to get there safely. The deadline stays fixed, and you shouldn't quietly compress safety to meet it. If the plan below can't make it, Security's accountable owner decides on the exposure trade-off. Present that trade-off to them. Don't absorb it silently.
- **Key fact:** a QEMU fix protects only instances that were migrated or restarted after the host was patched. A patched host with old guests still running is not done. Track status per instance as well as per host.

## Scope
- **Reported:** 300 hosts, 3 AZs, about 8 hosts of free capacity in total, some tenants with SR-IOV.
- **Assumption:** about 100 hosts per AZ. Please verify.
- **Gaps** (each needs `openstack` output or inventory from you):
  - How the 8 spare hosts are spread across AZs. 8 doesn't divide evenly by 3, so one AZ may have as little as 1–2 hosts' worth.
  - Shared vs local instance storage. Local disks mean block migration, which loads network and storage.
  - Release, libvirt and QEMU versions, and CPU models (these limit migration targets).
  - Whether the fix changes the QEMU/libvirt version or is a patch-level update. This decides whether the landing-zone ordering below matters.
  - Whether the SR-IOV hosts are a separate aggregate, how many VFs are free per physnet, and which port types are in use.

## Workload classes
Nova only sees instances. It can't tell you which ones matter, so that has to come from tenants.

| Class | How identified | Strategy | Downtime | Sign-off |
|---|---|---|---|---|
| A. Migratable, any criticality | Normal flavor, no passthrough (read-only: flavor and port inspection) | Live migration to a patched host | None | None per VM |
| B. SR-IOV `direct` port | Port `binding:vnic_type=direct` | Live migration, possible since Train (verify for your release). The guest loses that interface briefly while it is unplugged and re-plugged, so owner acceptance is needed. The destination needs a free VF on the same physnet. | Brief NIC loss | Project owner |
| C. Not live-migratable | `direct-physical` ports, flavor-based PCI passthrough, and very memory-heavy or write-heavy guests unless auto-converge or post-copy is on | Cold migration or coordinated restart. For these, restart is a technical necessity. | Restart time | Project owner |
| D. Owner unknown | Empty owner or criticality cell | Treat conservatively: live migrate if possible. Never restart without an owner decision. | None | Escalate to the project owner |

- Don't ask for a per-VM table, because 300 hosts means thousands of instances. Collect criticality **per project**, using the [criticality table template](/tmp/osk-eval-8vmnmog2/.claude/skills/openstack-maintenance-planning/references/criticality-table-template.md). The columns are criticality, acceptable downtime, recovery expectations, blackout dates, owner, and the agreed strategy.
- Make the first-week deadline explicit. If you want "no answer means the default strategy applies" for tenants who don't reply, that rule needs sign-off from whoever owns the tenant relationship. It must never mean "restart".
- Most capacity pressure comes from classes A and B. Class C and any agreed-restart workloads can be rebooted in place and need no spare capacity. Getting tenants to agree to restart windows for tolerant workloads is the best lever you have.

## Capacity check
Formula: hosts that can be in maintenance at once per AZ ≤ (spare host-equivalents in that AZ − reserve you want to keep for an unplanned host failure).

- With 8 spare hosts over 3 AZs, an even spread gives about 2.67 per AZ, so guarantee 2. That means up to 2 hosts in flight per AZ if you keep no reserve.
- **Recommendation to decide:** run **1 host per AZ at a time**, 3 in parallel overall. This keeps about 1–2 hosts' worth of reserve per AZ, so an unplanned host failure mid-campaign doesn't collide with the campaign. Go to 2 per AZ only if tenant load and AZ spare capacity (once known) allow it.
- **Throughput check** (assuming about 15 working days and 100 hosts per AZ):
  - 100 hosts ÷ 15 days ≈ 7 hosts per AZ per day at 1 host at a time.
  - That is roughly one full drain, patch, reboot and verify cycle per hour in an 8-hour day, with no slack.
  - **I can't tell you if that's feasible.** It depends on your measured live-migration rate, which you don't have yet. Measure it in the pilot (see Sequencing).
  - If one at a time can't hit the deadline, the options are 2 per AZ (less reserve), extended hours, more restart-tolerant tenants, or an exception with a longer deadline for a defined set of hosts.
- **The campaign is rolling:** spare capacity is consumed by one batch only. Patched hosts rejoin and become destinations for the next batch. The 8 spare hosts are not a one-time budget.
- **Check separately:** free VFs per physnet on patched SR-IOV hosts, and per-AZ capacity. The platform total of 8 is the wrong number to plan against.

## Sequencing
1. **Landing zone first.** The ~8 free hosts are empty, so patch them first with no tenant impact. They become the patched destinations. This matters most if QEMU/libvirt versions change, because migration from newer to older QEMU isn't supported. Only move instances toward patched hosts.
2. **Pilot** of 1–2 hosts per AZ, including one SR-IOV host. Use it to measure migration duration and failures and to validate the per-host procedure. Don't scale up until the pilot results are reviewed.
3. **Waves.** Order by risk, not alphabetically. Do hosts with only class A/B instances first, then hosts with agreed-restart workloads in their windows. Leave the hardest class C hosts for last, when you know more.
4. **AZ rule:** never more than the agreed number of hosts down per AZ. No other changes during the campaign window.
5. **CPU model compatibility** can restrict which source hosts can drain to which destinations. Check it before building waves.

## Per-host procedure
1. Read-only: list the host's instances (`openstack server list --all-projects --host <h> --long`), confirm each is classified and owners are informed.
2. State-changing: disable nova-compute with a reason.
3. State-changing: move instances by class. Live migrate A and B, cold migrate or restart C. Verify each: active on the destination, reachable, performance acceptable.
4. Read-only: verify the host is empty, or that only agreed-restart instances remain. Read `resume_guests_state_on_host_boot` for those instances. The default is `False`, so they come back SHUTOFF.
5. State-changing: patch and reboot. Verify the kernel, QEMU version, compute service and agents.
6. State-changing: start agreed-restart instances that should be running (`openstack server start`) and have the owner confirm the application works.
7. State-changing: re-enable the compute service.
8. Record per instance that it has been migrated or restarted since the patch.

**Do not use evacuation for planned maintenance.** It is for failed hosts only, and it can duplicate guests that are still running.

## Boundaries and stop conditions
Set the numbers from your pilot baselines. Stop the campaign if any of these happen:
- Migrations fail or slow beyond the pilot baseline.
- A destination behaves differently than expected.
- A critical workload's performance crosses its threshold.
- AZ spare capacity drops below the reserve.
- Monitoring has blind spots.
- The decision-maker is unreachable.

Resuming after a stop is a new decision.

## Decision rights and communication
- **Project owners** approve restarts and SR-IOV interface interruption for their own workloads.
- **Platform or change owner** approves each wave.
- **Security's accountable owner** accepts any deadline exceptions.
- **Someone named in advance** sends the schedule to tenants. Do this in week 1, with blackout dates collected.

## Campaign completion criteria
- All 300 hosts are patched and verified.
- Every instance has been migrated or restarted since the patch, or is on the exception list with an owner.
- Agreed-restart instances are confirmed running, or deliberately left off by their owners.
- No instance remains on the old binary unknowingly.

## Exceptions
| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| To be filled | e.g. class C with no agreed window | Isolation or network restriction, to be defined | Project owner + Security | Set per exception |

## Suggested 3-week shape
- **Week 1:** collect the project-level table, inventory the gaps, patch the empty landing-zone hosts, run the pilot, and measure migration rates.
- **Weeks 2–3:** run waves at the proven rate, handle class C and exceptions, then finish with a verification sweep.

## Open questions
1. How are the 8 spare hosts spread across the 3 AZs?
2. Shared or local storage? Which release and which libvirt/QEMU versions?
3. Does the fix change the QEMU/libvirt version?
4. How many SR-IOV instances are there, and which port types (`direct`, `direct-physical`, passthrough flavors)?
5. Who owns tenant communication, and who can accept an exposure exception?
6. Do you have a measured live-migration baseline?

## Follow-up
Keep the criticality table as a living input to capacity planning. If every patching round consumes this much capacity, raise it as a platform lifecycle issue.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.