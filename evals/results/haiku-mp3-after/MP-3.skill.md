## Requirement and constraints

- **Mandatory:** replace the faulty DIMM in cmp-12. The work is hardware, not a version change, so there is no libvirt/QEMU ordering constraint.
- **Downtime:** about 1 hour of power-off. Any VM left on cmp-12 is down for that hour plus boot time, so the plan is to empty the host, or to get explicit owner agreement for each VM that stays.
- **Exposure:** the DIMM is already faulty. If it produces uncorrected errors or the host crashes before the window, the same VMs are affected without any plan. Check the ECC error history now (see step 1). If it is getting worse, the window itself is a decision to bring forward.

## Scope

- **Hosts:** cmp-12 only. Its failure domain (AZ, aggregate, rack) is not known.
- **Versions, CPU model, storage model:** not known. Whether instance disks are on shared storage or local is needed to know if block migration is required.
- **Gaps:** inventory of the ~20 VMs (flavors, sizes, owners), free capacity on other hosts, and which hosts have free GPUs.

I checked the working directory and it contains only the OpenStack skill definitions, no inventory, so every number below is a gap.

## Workload classes

| Class | How identified | Strategy | Downtime | Owner sign-off |
|---|---|---|---|---|
| **In-memory DB** (1 VM) | Largest RAM flavor; possibly hugepages or pinned CPUs | Live migration with auto-converge or post-copy, if the dirty rate allows. Otherwise cold migration in an agreed window. | Live: none expected, but unverified. Cold: full VM downtime. | DB owner: approves the method, window, and a pre-move backup or snapshot. Check for an application-level replica first. |
| **GPU VMs** (2) | Flavor with PCI passthrough alias | **Not live-migratable.** Cold migration to a host with a free matching GPU. | Full VM downtime (reboot) | Owner: accepts the cold move, verifies the GPU in the guest afterwards. |
| **Other VMs** (~17) | Everything else | Live migration within capacity. Block migration only if disks are local. | None expected | Owner informed; sign-off only for any VM that cannot be moved. |

The GPU VMs are the hard constraint: if no other host has two free GPUs of the right type, they cannot leave cmp-12 and must take the hour of downtime. The DB is the second constraint, since it needs one destination with enough free RAM.

## Capacity check

Per failure domain D that could receive VMs from cmp-12:

- Free RAM(D) ≥ RAM of VMs moving to D, plus the DB's RAM and overhead if it goes there.
- Free vCPU(D) ≥ vCPU of VMs moving to D.
- Free GPUs of the required type(D) ≥ 2 if both GPU VMs go to D, or 1 each if split.
- If the DB is pinned or uses hugepages, its destination must have a matching free NUMA node.

Use placement allocations, not the hypervisor's "free" numbers, since overcommit makes those misleading. Conclusion: **unknown until the numbers are collected.** If the GPU or DB constraints fail, the answer is a documented exception (the VM stays and takes the downtime), not a forced move.

## Sequencing

1. Move the **DB** first. It is the most constrained, and if its migration fails the plan changes.
2. Move the **GPU VMs** next. Their target host must have free GPUs, so reserve it before anything else lands there.
3. Live-migrate the rest, filling hosts that are not the DB or GPU targets.

No landing zone or version ordering is needed, provided the destinations have a compatible CPU model. Do not batch more than the agreed concurrency per failure domain.

## Per-host procedure

1. **[read-only]** Inventory: `openstack server list --all-projects --host cmp-12 --long`. Record flavors, PCI aliases and power state.
2. **[read-only]** Check the guest resume setting on cmp-12 (`resume_guests_state_on_host_boot`). If it is `False`, a restarted host does not start its guests, so every VM left behind must be started by hand.
3. **[read-only]** Check the ECC history on cmp-12 (`edac-util -s` or `ras-mc-ctl --errors`, or the BMC SEL). This confirms the risk and the urgency.
4. **[read-only]** Find GPU and RAM capacity on the candidate hosts. Get the DB's live-migration parameters from the platform config. Option names and defaults change by release, so verify them for your version.
5. **Owners** approve the strategy per VM. Notify everyone with the schedule.
6. **[state-changing]** Disable the compute service on cmp-12 with a reason: `openstack compute service set --disable --disable-reason "DIMM replacement <change-id>" cmp-12 nova-compute`.
7. **[state-changing]** Migrate the DB, then the GPU VMs (cold migration: `openstack server migrate <server>`, then confirm the resize after verification), then the rest (`openstack server migrate --live-migration [--block-migration] <server>`).
8. **[read-only]** Verify each move: the instance is ACTIVE on the destination, reachable, and performing normally. For GPU VMs, the owner checks the GPU inside the guest. For the DB, the owner checks its health and replication.
9. **[read-only]** Confirm cmp-12 is empty: `openstack server list --all-projects --host cmp-12`. Only VMs the owner has agreed to leave should remain.
10. **[state-changing]** Shut down cmp-12 and do the DIMM replacement.
11. **[read-only]** After boot, check that the memory is fully recognized (BIOS/BMC inventory, `free -h`, ECC counters at zero).
12. **[state-changing]** Start the host's services, verify nova-compute and the agents are up, then re-enable: `openstack compute service set --enable cmp-12 nova-compute`.
13. **Optional:** rebalance later in a separate change. Do not move VMs back as part of this window.

Evacuation is not used. cmp-12 is healthy and still running its VMs, and evacuation is for failed hosts only.

## Boundaries and stop conditions

- Stop if a live migration fails or runs past the agreed time, or the DB's performance drops below its threshold.
- Stop if a GPU VM cannot get a matching GPU, or the owner withdraws approval.
- Stop if capacity in the destination failure domain falls below the reserve.
- Stop if cmp-12 fails during the campaign. That becomes an incident, handled with `openstack-incident-analysis`, not a planned evacuation.
- Resuming after a stop is a new decision.

## Decision rights and communication

- **DB owner:** method, window, backup requirement, and whether a planned outage is acceptable.
- **GPU VM owners:** acceptance of the reboot, and GPU verification after the move.
- **Platform owner:** capacity reserve, concurrency, and the go/no-go decision.
- **Change approver:** the schedule, and the decision to bring the window forward if the ECC history is getting worse.

## Campaign completion criteria

- cmp-12 patched or repaired, and healthy, with nova-compute enabled.
- Every VM is either running on its destination (migrated and verified) or listed as an exception with its owner.
- No VM is left on cmp-12 unknowingly.

## Exceptions

| Workload | Reason | Compensating control | Owner | Review date |
|---|---|---|---|---|
| Any GPU VM with no free GPU elsewhere | No matching GPU available | Downtime accepted for the window | Owner: TBD | TBD |
| DB, if no host has the RAM and live migration fails | Capacity or dirty-rate constraint | Planned cold migration or owner-agreed downtime | DB owner: TBD | TBD |

## Gaps and questions

1. How many free GPUs of the required type exist on other hosts in the same AZ/aggregate?
2. What is the DB's RAM size, is it on hugepages or pinned CPUs, and does it have a replica?
3. Do the instances use shared storage (Ceph) or local disks?
4. What is the current ECC error count on cmp-12, and is it rising?
5. What is `resume_guests_state_on_host_boot` set to in your deployment?
6. Who approves each decision, and what is the exact window?

## Follow-up

- Record the actual downtime per VM and whether the DB move was live or cold. This tells you whether the plan was realistic.
- Keep the criticality table for these VMs current, so the next campaign does not start from zero.
- If GPU capacity is the bottleneck, that is a capacity problem for the platform roadmap, not only for this window.

Decision support only. The state-changing steps above (disabling the service, migrations, the shutdown, and re-enabling) require approval by the accountable owner and should be executed under your change process.