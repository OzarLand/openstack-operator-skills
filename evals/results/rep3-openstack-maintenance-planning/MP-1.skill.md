# Compute host patching plan: kernel + QEMU, 300 hosts, 3 AZs, 3 weeks

The plan below uses only the numbers you gave me. Where I assume something, I say so.

## Requirement vs strategy
- **Fixed:** every compute host has the kernel and QEMU fix within 3 weeks. Security owns this.
- **To design:** how to do it safely with about 8 hosts of free capacity and unknown workload criticality.
- **Exposure if delayed:** I don't know the CVE severity or whether it is exploitable across tenants. Ask Security this early, because it decides what a deadline exception costs.

## What matters most
1. **Capacity sets your speed.** Rolling patching works like this: drain a batch into free capacity, patch it, and it becomes free capacity again. Your batch size per AZ can't exceed the spare in that AZ, minus any reserve you keep.
2. **Your spare may not be usable as-is.** "8 hosts worth" is probably fragmented across many hosts, and it may be uneven across AZs. It also isn't interchangeable. SR-IOV VMs need free VFs on the same physnet, and pinned or hugepage flavors need matching NUMA room.
3. **QEMU is in the patch, so order matters.** Live migration from newer QEMU to older isn't supported. Patch a landing zone first and move VMs only toward patched hosts.
4. **A host reboot doesn't patch a running VM's QEMU unless that VM moved or restarted.** Track patch status per instance, not just per host. Verify for your setup whether a hard reboot through Nova or a migration is what recreates the QEMU process. A guest-internal reboot normally doesn't.
5. **Unknown criticality is a gap, not "low".** Asking tenants which workloads can tolerate a restart is also your biggest lever. Restart in place needs no free capacity.

## Capacity check
*Assumptions: about 100 hosts per AZ (even split) and about 12 working days of rolling after about a week of prep. The split of free capacity across AZs is unknown.*

| Batch size per AZ | Batches per AZ (~100 hosts) | Needed per day (12 days) | Max cycle time (8h day) |
|---|---|---|---|
| 1 | 100 | ~8 | ~1h |
| 2 | 50 | ~4 | ~2h |
| 3 | ~34 | ~3 | ~2.9h |

- With about 2–3 spare hosts per AZ, a batch of 2 uses all your spare and leaves no reserve for a host failing mid-campaign. A batch of 1 is the safer choice, and it needs a cycle of about 1 hour to meet the deadline.
- A full drain, patch, reboot, verify and re-enable cycle is unlikely to take 1–2 hours if you live-migrate everything. **Plan on not being able to live-migrate everything within 3 weeks at this spare.** The pilot's measured cycle time decides this, so don't guess it now.
- **Levers, strongest first:**
  1. Add temporary free capacity per AZ (borrowed, new or decommissioned hosts). Batch size scales roughly linearly with it.
  2. Restart in place for owner-approved tolerant workloads. It needs no destination capacity.
  3. Risk-order the hosts and take an explicit, time-boxed exception for the tail.
  4. Ask tenants to delete unused VMs.

## Workload classes
Nova sees instances, not business processes. Collect the criticality table (shared template) from the consuming teams, **by project, in week 1**.

| Class | How identified | Default strategy | Sign-off |
|---|---|---|---|
| Critical, migratable | Tenant says so; silent tenants default here | Live migration to patched hosts | None |
| Tolerates restart | Tenant states acceptable downtime and window | Restart in place or cold migration in an agreed window | Project owner |
| SR-IOV `direct` port | Port `vnic_type` | Live migration if the release is Train or later, NIC and driver support is verified, and the owner accepts a brief interface loss | Project owner |
| Not live-migratable (PCI passthrough flavors, `direct-physical` ports, memory-heavy VMs) | Flavor and port data | Cold migration or coordinated restart | Project owner; downtime agreed |
| Cannot be done before the deadline | Owner request or technical blocker | Exception | See exceptions |

The silent-tenant default is a conservative treatment, not a finding about the workload. Tell tenants the default and the cutoff date.

**SR-IOV specifics:**
- Inventory the ports and flavors first (read-only), for example `openstack port list --long` filtered by vnic type, and the flavors that have `pci_passthrough:alias`.
- Pilot one volunteer SR-IOV instance end to end.
- After each reboot, verify the VF count and PF config persisted *before* re-enabling the host. Kernel updates can break that.
- Spare capacity for these VMs must sit on SR-IOV hosts of the same physnet, so plan landing zones for them separately.

## Sequencing
- **Pre-step (state-changing):** make the free capacity usable as empty hosts, or at least as contiguous room, in each AZ. Prefer packing destinations and use a scheduler weigher or aggregate so new VMs land on patched hosts first.
- **Landing zone:** patch the empty hosts first, about 2–3 per AZ, with a pilot in one AZ first. After that, every drained and patched host becomes the next landing zone.
- **Failure domains:** don't drain beyond an AZ's spare. Consider finishing one AZ before the next, so a problem doesn't hit all three. This costs speed, so the pilot numbers decide.
- **Risk order within the window:** most exposed hosts first (for example multi-tenant or public-facing), then the rest. Get this from Security.
- **Don't stack changes** in the same window as other changes.

Timeline (3 weeks):
- Days 1–5: inventory, tenant criticality request, release and version facts, pilot.
- Days 6–17: rolling waves.
- Days 18–21: stragglers, exceptions, verification.

## Per-host procedure
Never use evacuation for maintenance. It is for failed hosts only.
1. Confirm the host's instances are classified and owners informed. *(read-only)* `openstack server list --all-projects --host <host> --long`
2. Disable the service with a reason. *(state-changing)* `openstack compute service set --disable --disable-reason "<change id>" <host> nova-compute`
3. Move instances by class: live, cold, or leave agreed-restart ones. *(state-changing)* Verify each: active, reachable, performance acceptable.
4. Verify the host is empty, or that only agreed-restart instances remain. *(read-only)* Record the remaining instances' power state. Read `resume_guests_state_on_host_boot` on the host. At the default (`False`), guests come back `SHUTOFF`.
5. Patch and reboot. *(state-changing)* Verify the kernel and QEMU versions, the compute service and agents, and the SR-IOV VF state.
6. Start the agreed-restart instances that should be running and have owners confirm the application. *(state-changing)*
7. Optionally boot a test instance, then re-enable compute. *(state-changing)*

## Stop conditions
Set these before day 1, using your own baselines for the numbers (I won't invent them):
- Migrations failing, or slowing beyond the baseline.
- Free capacity in an AZ falling below the reserve you choose.
- A critical workload crossing its agreed performance threshold.
- Unexpected behavior on a destination host.
- Monitoring blind spots.
- The decision owner being unreachable.

After a stop, resuming is a new decision.

## Decision rights
- **Security:** confirms the requirement and the exposure, and agrees the risk order.
- **Project owners:** approve restarts and downtime for their workloads.
- **A named business owner:** accepts deadline exceptions, with compensating controls and a review date.
- **Platform lead:** owns stop and resume decisions.
- **One named person:** communicates the schedule to tenants.

## Completion criteria
- Every host is patched and verified.
- Every instance is migrated or restarted since the patch, or listed as an exception with an owner.
- Every agreed-restart instance is confirmed running, or intentionally left off.
- No instance is unknowingly still on the old QEMU.

## Exceptions
| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| *(to be filled)* | | | | |

## Gaps I need from you
1. Free capacity per AZ and per aggregate, plus VM density per host.
2. OpenStack release, libvirt and QEMU versions, and CPU models.
3. Whether instance storage is shared or local (local needs block migration, which adds network and storage load).
4. Counts of SR-IOV `direct`, `direct-physical`, PCI passthrough, vGPU and pinned or large-memory instances.
5. Whether any criticality metadata or tenant contacts already exist.
6. Security's view: CVE exploitability and which hosts carry the most exposure.
7. Whether you can get temporary capacity.

## Follow-up
- Keep the criticality table as living metadata (project or instance properties).
- Add a patching scenario to capacity planning.
- If every campaign eats this much capacity, put lifecycle headroom on the roadmap.

If useful, I can turn this into a shareable page for Security and the tenant owners. I can also draft the tenant criticality request or the read-only inventory script.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.