## Plan: draining cmp-12 for the DIMM replacement

This is a planned hardware repair, so the host needs a managed drain. **Never use `evacuate`.** It is for failed, fenced hosts only. cmp-12 is healthy, so evacuating it risks two copies of a guest running against the same disk.

### Facts and gaps

- **Reported:** about 20 VMs. Two use PCI passthrough GPUs. One is a big in-memory database. The outage is about 1 hour, tomorrow.
- **Not known:** the release, the libvirt and QEMU versions, the storage model (shared or local), the failure domain, spare capacity elsewhere, the owners and their downtime tolerance, the CPU models, and whether the GPUs are flavor-based passthrough or vGPU. I'm not guessing at any of these.

### Workload classes

| Class | Strategy | Downtime | Sign-off |
|---|---|---|---|
| About 17 ordinary VMs | Live migrate, but only after the owner classification below. Tolerant ones can be cold-migrated or restarted. | None, or a short restart | Owner for any restart |
| 2 passthrough GPU VMs | **Cannot live-migrate** if they use flavor-based passthrough (`pci_passthrough:alias`). Options: (a) cold-migrate to another GPU host, if one has free GPUs. (b) Shut down cleanly and leave them on cmp-12 until the repair is done. (c) If they are vGPU, live migration may work on 2024.1 or later with libvirt 8.6 or later, QEMU 8.1 or later and kernel 5.18 or later. Verify this for your release. | Real downtime (a, b), roughly the repair window | GPU job owners |
| In-memory DB | Live migration may never converge, because pages change faster than they copy. It needs auto-converge or post-copy, which you must check is enabled and tested. Otherwise use a **coordinated application-level shutdown**, either a clean DB stop and cold migration or a stop and restart in place. | Short to moderate, depending on the DB's persistence and reload time | DB owner and business owner |

The in-memory DB is the risky one. Even if live migration is possible, rehearse it or schedule a quiet window. Also confirm the DB's own failover or replica options with its owner, which may be better than moving the VM.

### Preconditions (today)

1. **Get the owner list for all ~20 VMs** (read-only):
   - `openstack server list --all-projects --host cmp-12 --long`
   - Ask each owner for criticality, acceptable downtime, and who can approve a restart.
2. **Check the release and the GPU type** (read-only):
   - Look at the flavors and extra specs of the 2 GPU VMs.
   - Check libvirt, QEMU and the Nova version.
   - Check `resume_guests_state_on_host_boot` on cmp-12. The default is `False`, so guests stay `SHUTOFF` after the reboot.
3. **Capacity check.** The destination needs room for the migrating VMs' RAM, vCPU and disk, in the same failure domain, while cmp-12 is out.
   - Required: the sum of the VMs you will move (the DB alone is large).
   - Available: spare on the other hosts in that domain, minus the reserve.
   - If you can't absorb it, more VMs have to be restarted or cold-migrated, and that is the owners' call.
4. **Confirm destinations** for GPU cold migration: free matching GPUs, CPU model compatibility, and libvirt/QEMU not older than the source.
5. **Confirm the DIMM and technician window**, and that no other change shares the window.

### Per-host procedure (tomorrow)

1. **State-changing:** disable the compute service with a reason (`openstack compute service set --disable --disable-reason "DIMM replacement" cmp-12 nova-compute`). New placements stop.
2. **State-changing:** live migrate the ordinary VMs, a few at a time, and verify each one (ACTIVE on the destination, reachable, performance normal). Use block migration only if the disks are local, and expect more network and storage load.
3. **State-changing:** handle the DB as agreed with its owner (see above), and verify the application afterwards.
4. **State-changing:** handle the GPU VMs as agreed (cold-migrate, or clean shutdown).
5. **Read-only:** confirm what remains on cmp-12 is only what you agreed to leave, with the power state recorded.
6. The technician powers off, replaces the DIMM and powers on. Confirm the full memory is seen and the memory tests are clean.
7. **Read-only:** confirm nova-compute and the agents are up.
8. **State-changing:** start any agreed-restart VMs (`openstack server start`), and have the owners confirm the application is reachable.
9. **State-changing:** re-enable the compute service. Test with a small VM.
10. Move the VMs back only if the owners want it. It is not required.

### Stop conditions

- A migration fails or runs far past what you normally see.
- A VM looks degraded on the destination.
- Spare capacity falls below the reserve.
- An owner is unavailable for a sign-off.
- The DB shows data or replication problems.

Resuming after a stop is a new decision.

### Decision rights

- Infrastructure runs the drain.
- VM owners decide whether a restart or downtime is acceptable.
- The DB and GPU owners sign off before any shutdown.
- Someone named tells consumers the schedule.

### Open questions for you

1. Which release is this, and is the storage shared (e.g. Ceph) or local?
2. Are the GPU VMs flavor passthrough or vGPU? Is there a spare GPU host?
3. How large is the DB VM, what are its persistence and failover options, and how tolerant is its owner?
4. What is the spare capacity in cmp-12's failure domain?

If you paste the server list and the flavor extra specs, I can turn this into a concrete per-VM table and a capacity calculation.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.