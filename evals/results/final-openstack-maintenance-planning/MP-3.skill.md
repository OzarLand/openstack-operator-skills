## Plan: draining cmp-12 for the DIMM replacement

I haven't inspected your system. Everything below is **Assumption** or **Reported** unless I say otherwise. The gaps I need closed are listed at the end.

### Requirement and constraints
- **Requirement (fixed):** cmp-12 powered off for about 1 hour tomorrow for a DIMM swap.
- **Execution strategy (to design):** the 3 special VMs decide the plan. The ~17 ordinary VMs are mostly a capacity question.
- **If delayed:** the DIMM is faulty. I don't know whether it is producing correctable or uncorrectable ECC errors. If errors are escalating, that affects the risk of waiting, so check the BMC/EDAC counters.

### Workload classes
| Class | How identified | Strategy | Downtime | Sign-off |
|---|---|---|---|---|
| ~17 ordinary VMs | `openstack server list --all-projects --host cmp-12` (read-only) | **Live migrate** to other hosts, or cold migrate if the owner tolerates a restart | none, or a brief restart | project owners for any restart |
| 2 × PCI-passthrough GPU VMs | flavor/image properties with `pci_passthrough:alias` (verify) | **Cannot be live-migrated.** Cold migrate to a host with a free matching GPU, or shut down and start again on cmp-12 after the work | Yes. Shutdown to restart is about 1 hour for restart in place, shorter for cold migration to a free GPU host | GPU workload owners |
| 1 big in-memory DB | memory size and write rate | See below. This is the main decision. | Depends on option | DB owner, who decides, not infra |

**In-memory DB: options (the owner picks):**
1. **Live migrate with auto-converge or post-copy.** This is only appropriate if the release and hypervisor support it, it's enabled on the compute hosts, and a dry-run has shown it converges. Otherwise a high dirty-page rate means it never converges. Risk: long migration, performance degradation, or a failed or aborted migration. Post-copy can't be safely aborted midway. *Verify for your release.*
2. **Application-level failover.** If the DB has a replica or cluster, fail over to the standby, then stop the VM. This is usually the safest and shortest-impact path. Check replica health and lag first.
3. **Planned shutdown with a clean persist and reload.** Flush or snapshot, stop the VM, migrate cold, and reload. Downtime is the reload time for a large dataset, which may exceed the hardware work itself. This is the fallback if 1 and 2 aren't viable.

My recommendation: option 2 if a replica exists, otherwise option 3 with a rehearsed reload time. Use option 1 only if it has been tested on this platform. Don't try it live on the day without a rehearsal.

### Capacity check (formula, since I have no numbers)
For the compute hosts in cmp-12's **failure domain** (rack/AZ/aggregate, unknown), the free capacity on the **remaining** hosts must cover the following. This is vCPU, RAM and disk, all three.

`free(other hosts, same domain) ≥ Σ(~17 ordinary VMs) + DB VM + 2 GPU VMs (if moved) + your agreed safety reserve`

Pay particular attention to the DB's RAM. It needs one host with enough contiguous free RAM, and a large VM may fit on only one or two hosts. For the GPU VMs you need two free matching GPUs, with the same alias and vendor/product, and ideally the same flavor and aggregate. If you don't have them, the GPU VMs must stay on cmp-12 and be shut down.

### Sequencing
1. **Today (read-only prep).** Get the host inventory and confirm the capacity and GPU availability. Rehearse or size the DB option. Get owner sign-offs and send the schedule to consumers.
2. **Check version compatibility.** Check libvirt/QEMU versions and CPU models on cmp-12 versus the targets. Live migration from newer to older libvirt/QEMU is unsupported. Don't mix patch levels carelessly.
3. **Do not stack other changes** into this window.

### Per-host procedure (tomorrow)
1. *(read-only)* Confirm each VM's owner and class is signed off. Capture a baseline: `openstack server list --all-projects --host cmp-12`, `openstack compute service list --service nova-compute`, and the DB and GPU VM health.
2. *(state-changing)* Disable scheduling on the host: `openstack compute service set --disable --disable-reason "DIMM replacement <ticket>" cmp-12 nova-compute`. This doesn't touch running VMs.
3. *(state-changing)* Handle the DB first, per the chosen option, and verify the app is healthy (replica in sync or the DB is up) before moving on.
4. *(state-changing)* Live migrate the ordinary VMs in small batches, one or a few at a time, within your known concurrency baseline. Verify each is ACTIVE on the destination and reachable. Use `--block-migration` only if disks are local, which loads the network and storage.
5. *(state-changing)* Handle the GPU VMs: notify the owner, shut down cleanly, then cold migrate (`openstack server migrate`, confirm after verifying) or leave stopped on cmp-12. Verify the GPU is visible in the guest after the restart.
6. *(read-only)* Confirm cmp-12 is empty or holds only the agreed stopped VMs.
7. Technician powers off, replaces the DIMM and boots. *(read-only)* Verify with memtest or BMC/EDAC that the full memory is present with no new errors, that `nova-compute` and the network agents are up, and that hypervisor memory totals are as expected.
8. *(state-changing)* Re-enable: `openstack compute service set --enable cmp-12 nova-compute`. Launch a test instance if you have a standard one.
9. Restore the GPU VMs and DB per their plans, and verify. Leave the other VMs where they landed. There's no need to move them back.

**Do not use evacuation.** That is only for failed hosts, and cmp-12 is up and running its VMs.

### Stop conditions
Stop and re-decide, with the decision owner named below, if:
- A migration fails or runs well beyond your baseline.
- The DB shows a performance degradation beyond the agreed threshold, or the migration isn't converging.
- Capacity on the remaining hosts drops below the reserve.
- The GPU doesn't reappear in the guest.
- Anyone with decision authority is unreachable.
- Monitoring is blind.

If cmp-12's DIMM begins producing uncorrectable errors during the drain, the situation changes to an incident. Say so and I'll switch to the incident approach.

### Decision rights
- Owners of the DB and the two GPU workloads approve their downtime or approach.
- The platform lead approves the migration batch.
- Someone named communicates the window to consumers.

### Completion criteria
cmp-12 re-enabled and healthy, all 20 VMs accounted for and verified on their final hosts, the GPU VMs have their GPUs, the DB is healthy and consistent, and a short write-up exists.

### Gaps and questions (please answer)
1. Release, hypervisor, libvirt/QEMU versions (are auto-converge and post-copy enabled?).
2. Storage: shared (Ceph?) or local disks?
3. Failure domain of cmp-12 and free capacity (vCPU/RAM/disk) on the other hosts in it.
4. Are there free matching GPUs elsewhere?
5. DB: RAM size, replica or cluster available, and how long a reload takes?
6. Do the other ~17 VMs have owners who've said whether they tolerate a restart? Is there a criticality table?
7. Is the DIMM error rate escalating?
8. Who is the named approver?

If you paste the outputs of `openstack server list --all-projects --host cmp-12 --long`, `openstack hypervisor list --long`, and the flavor details for the 3 special VMs, I'll turn this into a concrete runbook with numbers.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.