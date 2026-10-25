## Plan to drain cmp-12 for the DIMM replacement

This is based only on what you told me. I haven't inspected the platform, so nothing here is observed. The unknowns are listed under Gaps.

### Requirement and constraints
- **Requirement:** cmp-12 is powered off for about 1 hour tomorrow (2026-10-26) for the DIMM swap. Reported.
- **Exposure if delayed:** the DIMM is faulty. I don't know whether it is logging correctable or uncorrectable errors, so the risk of an unplanned crash is a gap. If the host crashes before the swap, you are in an evacuation case, not planned maintenance.
- **This is hardware work, not a libvirt/QEMU patch.** The newer-to-older migration constraint and the "landing zone" idea don't apply. A VM that live-migrates to any compatible host is fine.

### Scope and gaps
These need answers before tomorrow:
- **Capacity:** which failure domain (rack, AZ, aggregate) cmp-12 is in, and how much free CPU, RAM and disk the other hosts in it have. You need room for about 20 VMs, including the database's RAM, minus any VMs that will stay.
- **Release:** the OpenStack, libvirt and QEMU versions. They decide whether the GPU VMs can live-migrate.
- **Storage:** whether instance disks are on shared storage such as Ceph or local. Local disks need block migration, which loads the network and storage.
- **CPU model:** whether the destination hosts have a compatible CPU model.
- **Criticality:** whether a criticality table exists, and who owns each VM. This is the first deliverable. The infrastructure team can't decide which VMs may be disrupted.
- **Host state:** whether cmp-12 is stable enough to run migrations. A failing DIMM can crash the host mid-drain.
- **Hardware:** whether a spare GPU host exists.

### Workload classes

| Class | Strategy | Downtime | Sign-off |
|---|---|---|---|
| ~17 ordinary VMs | Live migration (block migration if disks are local). Cold migrate any owner tolerates. | Near zero | Owners informed. The critical ones should be named explicitly. |
| 2 GPU passthrough VMs | **Not live-migratable** if flavor-based PCI passthrough (`pci_passthrough:alias`), which is the usual case. Choose between a coordinated shutdown, or a cold migration to another GPU host if one has free GPUs of the same type. | Downtime for the whole window or for the cold-migration time | Owners agree on the window and on whether they accept downtime. |
| In-memory DB | Don't assume live migration works. A large, write-heavy memory footprint can dirty pages faster than they copy, so it may never converge. Choose below. | Depends on the option | The database owner decides. |

**Options for the in-memory database.** The right one depends on your release, network and how write-heavy the database is.
1. **Live migration with auto-converge or post-copy enabled.** It stays up but may throttle the guest or risk the VM if the link fails mid post-copy. Rehearse it first on a similar VM, or watch it closely and abort if it stalls. This needs a compatible destination with enough free RAM.
2. **Application-level failover.** If a replica exists, fail over, stop the primary VM, and resync afterwards. This is usually the safest for an in-memory database, but I don't know whether you have a replica.
3. **Planned shutdown and cold migration.** Flush or snapshot to disk, stop, migrate, start. It costs downtime plus the time to reload memory. Check the reload time, since a cold start of a large in-memory database can take much longer than the hardware hour.
4. **Leave it on cmp-12 and shut it down gracefully.** This is the least effort but gives the longest outage, and it is only suitable if the owner accepts that.

My default recommendation is option 2 if a replica exists, otherwise option 1 after a test migration, with option 3 as the fallback. This is a default, not a rule.

**SR-IOV caution.** If any of the other ~17 VMs use SR-IOV `direct` ports, they can live-migrate since Train, but they lose that interface briefly. Ask the owners.

### Capacity check
The formula, since I have no numbers: free RAM, vCPU and disk in cmp-12's failure domain, excluding cmp-12, must be at least the total of the VMs you plan to live-migrate, plus your normal reserve. If you plan to cold migrate the GPU VMs, a GPU host with matching free GPUs must exist. If capacity is short, move fewer VMs and accept restart-in-place downtime for the rest. Don't force migrations the platform can't absorb.

### Per-host procedure

**Today (before the window)**
1. *Read-only:* list the VMs: `openstack server list --all-projects --host cmp-12 --long`. Match each to an owner and class.
2. *Read-only:* check destination capacity and CPU model. Check storage type and the Nova/libvirt/QEMU versions.
3. *Read-only:* check cmp-12 itself (hardware logs, `compute service list`) so you know the DIMM isn't about to take it down.
4. Send owners the schedule. Get sign-off on the GPU and database plans.
5. *Read-only:* check `resume_guests_state_on_host_boot` on cmp-12. With the default `False`, any VM left on the host stays `SHUTOFF` after boot, and someone must start it.
6. Test-migrate a non-critical VM if you haven't done a live migration recently. This shows the baseline for time and network load.

**Window (all state-changing; approval per your change process)**
1. Disable the scheduler on the host: `openstack compute service set --disable --disable-reason "DIMM replacement" cmp-12 nova-compute`.
2. Handle the database first (option 1, 2 or 3 above), since it is the longest and riskiest step.
3. Live-migrate the ordinary VMs in small batches: `openstack server migrate --live-migration [--block-migration] <server>`. Check after each that the VM is ACTIVE on the destination and reachable. Keep concurrency at your known-good level, which I can't supply.
4. Shut down the GPU VMs gracefully, or cold-migrate them if a GPU host is free. Confirm the owner's application is stopped cleanly.
5. Confirm cmp-12 is empty with `openstack server list --all-projects --host cmp-12`. Record anything left, with its power state.
6. Power the host off. The technician swaps the DIMM.
7. After boot, check memory (the full amount shows up, no ECC errors), the nova-compute service and the network agents.
8. Re-enable the host: `openstack compute service set --enable cmp-12 nova-compute`.
9. Restart the GPU VMs (or cold-migrate them back), have each owner confirm the application works, and decide whether the database moves back. Don't rebalance in a hurry.

**Do not use `openstack server evacuate` for any of this.** It is for failed, fenced hosts. On a host that may still be running its VMs, it risks two copies of the same VM writing to the same disk.

### Stop conditions
Stop and re-decide with the owner if:
- migrations fail or run well past your baseline;
- the database migration doesn't converge;
- destination capacity falls below your reserve;
- cmp-12 shows signs of crashing (then it becomes an incident, and you should switch to the incident-analysis path);
- monitoring is blind or the approver is unreachable.

Resuming after a stop is a new decision.

### Decision rights
- **Owners:** each VM owner, plus the database owner, approve downtime and the chosen option.
- **Platform lead:** approves the window and the stop calls.
- **Communication:** someone named to tell consumers the schedule.

### Completion criteria
- cmp-12 is back with full memory and no errors, and its service and agents are up.
- Every VM is running where the owner expects it, or intentionally off.
- The GPU and database owners have confirmed their applications work.

### Follow-up
Record the criticality table, and record how long the database and GPU moves took. This is useful for future capacity planning.

### Questions for you
1. Is there a replica of the in-memory database?
2. Do you have a second GPU host with free matching GPUs?
3. Is instance storage shared (Ceph) or local?
4. What release are you on?
5. How much free capacity do the other hosts in cmp-12's failure domain have?

I can turn this into a one-page runbook or a stakeholder notice once you answer.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.