## Plan to drain cmp-12 for the DIMM replacement (~1 h, tomorrow)

I haven't inspected your cloud. Everything below is **Reported** (your message) or **Assumption**. Gaps are listed at the end.

### Requirement and constraints
- The host must be powered off for about 1 hour. The date is fixed.
- A faulty DIMM can crash the host unplanned, so the work is worth doing. A planned drain is much safer than waiting for that crash.
- **Do not use `evacuate`.** It is only for failed, fenced hosts. In a planned drain, the VMs are still running on the host.

### Workload classes
| Class | VMs | Strategy | Downtime | Sign-off |
|---|---|---|---|---|
| Ordinary VMs | ~17 (assumption) | Live migration if criticality is high; otherwise cold migration, or restart in place if the owner agrees. | None, or short. | Project owners. |
| PCI passthrough GPU | 2 | **Cannot be live-migrated** if they use flavor-based passthrough (verify for your release). Options: cold migrate to another GPU host with a free matching device, or shut down for the window and start again afterwards. | Yes, and it must be agreed. | GPU workload owners. |
| In-memory database | 1 | Depends on how fast it dirties memory. See the options below. | Possibly. | DB owner. |

**Database options**, with their conditions:
- **Live migration with auto-converge or post-copy.** This works if the platform has it enabled (verify). It avoids downtime but slows the guest, and a failure mid-migration is a risk. Rehearse it on a similar VM first.
- **Coordinated shutdown, then cold migrate or restart.** The owner flushes or snapshots, stops the DB cleanly, and the VM is moved or restarted. This gives predictable downtime and reload time. The in-memory reload time may be much longer than the 1 h window, so ask the owner for it.
- **Failover to a replica.** If a replica or HA pair exists, fail over before the window. This is usually the safest option, but it needs the owner to run it.

I recommend the replica failover if it exists. Otherwise I recommend a coordinated stop. Treat live migration as an owner-approved alternative, not the default.

### Capacity check
For the destination hosts in cmp-12's failure domain (rack, AZ or aggregate), you need free capacity of at least cmp-12's used vCPU, RAM and disk. Add margin from your own baselines. The GPUs additionally need **2 free, matching GPU devices** on other hosts. If there are none, those VMs stay down for the full window. All of this is currently unknown. I need free capacity per host, the GPU inventory, and whether disks are on shared storage. Local disks mean block migration, which adds network and storage load.

### Per-host procedure
1. **Tonight or this morning, read-only.**
   - Run `openstack server list --all-projects --host cmp-12 --long` and classify each VM.
   - Read `resume_guests_state_on_host_boot` on cmp-12. With the default (`False`), any VM left on the host stays `SHUTOFF` after the reboot.
   - Check destination capacity, CPU model compatibility, and libvirt/QEMU versions. Live migration from a newer version to an older one is unsupported.
2. **Before the window.** Get owner sign-off and send notices. The DB owner and both GPU owners should confirm their approach explicitly.
3. **Disable scheduling (state-changing).** Run `openstack compute service set --disable --disable-reason "DIMM replacement" cmp-12 nova-compute`.
4. **Move VMs in order:**
   - Coordinated stops first: the DB and the GPU VMs.
   - Then live migrations of the critical ordinary VMs, with a limit on concurrent migrations taken from your own baselines.
   - Then the cold migrations.
   - Verify each VM after its move: it is `ACTIVE`, reachable, and the owner confirms the application works.
5. **Confirm cmp-12 is empty.** Re-run the server list. Any VM that stays must be on a recorded list of agreed restarts.
6. **Power off and replace the DIMM.** Check the DIMM and memory test (technician). After boot, verify that the full RAM is visible, there are no ECC/MCE errors in the logs, and the nova-compute and Neutron agents are up.
7. **Re-enable the service (state-changing).** Run `openstack compute service set --enable cmp-12 nova-compute`. Start any VMs that the owners expect to be running and that are `SHUTOFF`. They stay `SHUTOFF` after the reboot unless `resume_guests_state_on_host_boot` is true. Optionally validate with a test instance.
8. **Moving VMs back is optional.** Do it only if needed for balance or GPU placement, and only with owner agreement.

### Stop conditions
- Migrations fail or are much slower than your baseline.
- The DB shows degraded performance during migration.
- Destination capacity drops below your reserve.
- The decision owner is unreachable.

Resuming after a stop is a new decision.

### Decision rights
- The infrastructure team runs the drain.
- Each workload owner decides on downtime for their VM.
- A named change approver authorises the disruptive steps. Name them before tomorrow.

### Gaps and questions
1. What are the OpenStack release, the storage backend (shared or local), and the failure-domain layout?
2. Are the GPUs flavor-based passthrough or something else, and do other hosts have free matching GPUs?
3. What is the DB's size, write rate, and replica or HA setup? How long does it take to reload?
4. Which of the ~20 VMs are critical, and is there a criticality table? If not, getting that list from the owners is the first task today.
5. What is the free capacity across the other hosts in the domain?
6. Do the destination hosts have the same or newer libvirt/QEMU and a compatible CPU model?

If you paste the output of the server list and the compute service list, I can turn this into a per-VM table with a specific strategy for each.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.