**No. Don't do it. Stopping nova-compute and evacuating is the wrong tool for planned maintenance, and it can corrupt data.**

**Why it's dangerous**

- **Stopping nova-compute doesn't stop the VMs.** The guests keep running under libvirt/QEMU. "Shows down" only means the service stopped reporting. It does not mean the instances are off.
- **Evacuate rebuilds the instance on another host from the same Ceph volume.** The original guest is still alive and still writing to the same RBD image. Two running copies on one disk can corrupt the filesystem. Evacuation assumes the source host is dead and fenced (powered off or isolated). A healthy host with only its service stopped is not fenced.
- **Ceph shared storage makes this worse, not safer.** Shared storage is what makes evacuation work after a real failure. It is also why the double-writer risk is real here. RBD exclusive locks reduce the risk, but they are not a fencing guarantee you should patch against.
- **It isn't faster in the way that counts.** Evacuate restarts every guest, so each one takes a hard outage. Live migration keeps them running. If migrations are slow, that is a capacity or tuning problem to fix. Evacuation doesn't fix it. It turns slow migrations into downtime for every workload on the host.

**What I'd do instead** (plan only, nothing run)

1. **Classify workloads with their owners.** Some may tolerate a restart. Others must stay up. The owners decide that, not the infrastructure team.
2. **Use the right operation per class:**
   - Critical and migratable: live migration.
   - Tolerates downtime, or not live-migratable (PCI passthrough, `direct-physical` ports, very write-heavy memory): cold migration, or a coordinated restart in place. This is the legitimate fast path, and it's agreed with the owner.
3. **Disable nova-compute with a reason first.** This is state-changing and stops new placements.
4. **Patch and reboot only after the host is empty,** or holds only instances the owner agreed to restart. Check `resume_guests_state_on_host_boot`. The default `False` means guests come back `SHUTOFF` after the reboot.
5. **Re-enable the service.**

**Ways to speed up live migration** (verify these for your release):

- Raise the number of concurrent migrations, based on your own baselines and not a generic number.
- Enable auto-converge or post-copy for busy guests.
- Use a dedicated migration network.
- Drain a whole failure domain's worth of hosts in parallel, only as far as spare capacity allows.
- If you're patching libvirt/QEMU, patch an empty landing-zone batch first. Migration from newer to older libvirt/QEMU isn't supported, so instances can only move toward patched hosts.

**What I need from you to turn this into a real plan**

- Host count and failure domains (rack, AZ, aggregate).
- Current libvirt/QEMU versions and CPU models.
- Whether the patch touches libvirt/QEMU or only the kernel.
- Spare capacity per failure domain.
- Whether a criticality table exists with the consuming teams.
- Which instances use PCI passthrough, SR-IOV or vGPU.
- Your current live-migration timings and concurrency.

I haven't seen any of this yet, so I'm not assuming it. Tell me what you have and I'll draft the full campaign plan.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.