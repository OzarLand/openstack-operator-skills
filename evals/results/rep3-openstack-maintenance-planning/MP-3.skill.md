# Plan: draining cmp-12 for a DIMM swap

You've given me no output from the platform, so every number, version and backend below is a **gap** (listed at the end), not a fact. The plan depends on three things: how the GPU VMs and the database are classified, and whether the other hosts have room.

## Requirement and constraints
- **Fixed:** cmp-12 is powered off for about 1 hour tomorrow, so the VMs must be off it, or deliberately and agreeably down, by then.
- **Flexible:** how each VM gets there. Business criticality decides that, not the tooling.
- This is a hardware swap, not a libvirt/QEMU patch. The "newer to older QEMU" ordering constraint and the landing-zone idea don't apply, unless the technician also updates firmware or the OS.
- **Don't use evacuation.** Evacuation is for failed hosts. cmp-12 is up, so it would risk two copies of the same VM.

## Workload classes
| Class | VMs | Strategy | Needs sign-off from |
|---|---|---|---|
| Ordinary VMs | about 17 (assumed) | Live migrate if the owner wants no downtime. Otherwise the owner shuts them down cleanly and starts them after. | Owners of any critical VM |
| PCI-passthrough GPU VMs | 2 | **Cannot be live-migrated** (flavor-based passthrough; verify that's how they attach). Choose **A**: cold migrate to another GPU host with a free matching device. Choose **B**: a clean shutdown by the owner and a start after the swap. | GPU VM owners |
| In-memory database | 1 | Decide with the DB owner (options below). | DB owner, who must name a person |

**GPU options.**
- **A: cold migrate.**
  - It needs a free GPU of the same alias on another host, and enough capacity there.
  - It costs a short downtime.
- **B: shut down and restart in place.**
  - It works if a roughly 1-hour outage is acceptable, and it needs no spare GPU.
  - It costs about an hour of downtime.
- If the GPUs are busy with long jobs, ask the owners about checkpointing or timing before choosing.

**Database options.** I'd rank them like this, but the owner decides.
1. **Application-level failover.**
   - If it has a replica or standby, fail over, then stop or cold-migrate the old primary.
   - It gives the least risk and the least downtime. It also sidesteps the migration problem entirely.
2. **Planned stop, then restart.**
   - The DB flushes or snapshots, shuts down cleanly, and either restarts after the swap or cold-migrates now.
   - The real downtime is the stop time plus the time to reload data into memory. Ask for that figure.
3. **Live migration with auto-converge or post-copy.** This only works if both are enabled and have been tested on this platform.
   - A write-heavy in-memory DB may never converge.
   - Post-copy has a risk: if the network drops mid-migration, the VM can be lost.
   - Don't try it for the first time on this VM tomorrow. If it's attempted, do it only with the owner present, a tested rollback and a stop condition.

## Capacity check (read-only inputs needed)
- Per failure domain (rack, AZ or aggregate), check that **free vCPU, RAM and disk on the other hosts ≥ the total of everything leaving cmp-12**, plus a reserve you set.
- Pay special attention to the DB's RAM. It needs one destination with that much contiguous free memory.
- If the destinations are short, fewer VMs get live-migrated. More are shut down by agreement. That is better than forcing migrations the platform can't absorb.
- Don't invent the margin. Use your own baselines.

## Sequence

**Today (before the change window)**
1. *Read-only.* `openstack server list --all-projects --host cmp-12 --long`. Confirm the VM count and get flavors, project owners, and each VM's volume or local-disk storage.
2. *Read-only.* Check which VMs use passthrough, SR-IOV or vGPU ports, and which have NUMA/pinned flavors.
3. *Read-only.* Check the compute service list, free capacity on the other hosts, and whether they share the failure domain. Also confirm that the GPU hosts have free matching devices.
4. Get owner decisions in writing for the 2 GPU VMs, the DB and any VM marked critical. Confirm who communicates the schedule.
5. Dry-run what you can. Check whether auto-converge or post-copy is enabled (read-only), and test live migration of one throwaway VM to the intended destination.

**Tomorrow, in order**

1. **Disable scheduling** on cmp-12 *(state-changing)*: `openstack compute service set --disable --disable-reason "DIMM replacement" cmp-12 nova-compute`. Verify that no new VMs land there.
2. **DB first.**
   - Run the agreed option (failover or planned stop).
   - Verify the application's health from the owner's side, not only from Nova.
3. **GPU VMs.** Cold migrate or shut down per the owners' decision *(state-changing)*. Verify device attachment and application access on the new host. For a cold migrate, confirm the resize only after the owner checks it.
4. **Ordinary VMs.**
   - Live migrate in small batches, with a concurrency limit from your own baselines. If you have no baselines, start at 1 and increase carefully.
   - Check each VM after the move: status ACTIVE on the new host, reachable, performance acceptable.
   - If instance disks are local, this needs block migration, which loads the network and storage.
5. *Read-only.* Confirm cmp-12 is empty, or that only the VMs agreed to stay down remain. Record each remaining VM with its power state.
6. *Read-only.* Check `resume_guests_state_on_host_boot` on cmp-12. If it's `False` or absent, the VMs left on it come back **SHUTOFF** after boot. Plan to start them by hand.
7. Hand over to the technician. Power off, swap, power on.
8. *Read-only.* Verify the host: memory shows the full expected size, ECC errors are clear, nova-compute and network agents are up, and no stale instances are reported.
9. Start any VMs that stayed on the host and are expected to run *(state-changing)*: `openstack server start <vm>`. Have owners confirm the applications are reachable.
10. Re-enable the compute service *(state-changing)*. Optionally boot a test instance first.
11. VMs that were moved can stay where they are. Rebalancing is optional and is a separate decision.

## Stop conditions
- Migrations fail or slow beyond your baseline.
- A critical workload degrades past the agreed threshold.
- Free capacity on the other hosts drops below the reserve.
- The DB or GPU owner is unreachable while their VM is still on cmp-12. **Don't power off the host with those VMs running.**
- The technician is ready but the host isn't empty. Don't compress the steps. Move the window instead.
- After any stop, resuming is a new decision, not an automatic retry.

## Decision rights
- **DB owner:** failover, stop or live-migration.
- **GPU VM owners:** downtime or cold-migration timing.
- **Owners of critical ordinary VMs:** live migration versus clean shutdown.
- **A named change owner:** go or no-go, and the schedule announcement to consumers.

## One caution about the DIMM
Because the DIMM is faulty, the host may already be logging memory errors. If it's throwing uncorrectable errors or crashing, this stops being planned maintenance and becomes an incident for `openstack-incident-analysis`. Check the host's memory error logs first. Also consider doing the migrations sooner than tomorrow if the host is degrading.

## Gaps (what I need to firm this up)
1. The `openstack server list --host cmp-12 --long` output, redacted if needed.
2. How the GPU VMs attach (flavor-based PCI alias, vGPU, other), and whether any other host has a free matching GPU.
3. The DB's size, write rate, whether it's replicated, and how long a reload takes.
4. Free capacity on the other hosts, their failure domains, and the storage type (shared or local).
5. The running OpenStack release and the live-migration settings (auto-converge, post-copy, concurrency).
6. Whether this is hardware-only, or whether the technician also updates firmware, the OS or libvirt/QEMU.
7. Who the consumer owners are and who communicates.

If you paste the VM list and the capacity numbers, I can turn this into a per-VM table with the strategies filled in and a concrete batch order.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.