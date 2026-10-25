**No, I wouldn't do this for a patching campaign.** Evacuation is a recovery tool for hosts that have actually failed, and using it for planned maintenance has a serious safety problem.

**The main risk: stopping nova-compute does not stop the guests.** The QEMU/libvirt processes keep running on the host. Nova marks the service down after its heartbeat times out, and evacuate then boots the same instances on another host from the same Ceph RBD images. If the original hypervisor is still running those VMs, two QEMU processes can write to the same disks, which corrupts filesystems. Ceph's exclusive lock reduces this risk but doesn't remove it, and you shouldn't depend on it. Nova cleans up orphaned domains only when nova-compute restarts, and you're planning to keep it stopped. Evacuation is only safe after the host is powered off or fenced (IPMI/BMC) and you've confirmed the guests are gone.

**Other problems with the plan:**
- Every evacuated VM is a hard, unclean reboot. You get the same downtime as a reboot without the graceful shutdown, and you'd still need to reboot the host for kernel or QEMU patches.
- Evacuate is designed for one-off recovery. Running it across a whole host turns a maintenance window into a mass incident.
- It only works for instances whose disks are on shared storage. Local-disk ephemeral instances can't be evacuated, and PCI, SR-IOV, GPU and pinned instances have their own constraints.

**What I'd do instead:**
1. **Find out why live migration is slow before changing the method.** With shared Ceph, a live migration only copies RAM, so slowness usually comes from high-dirty-rate VMs, a migration network that's too narrow, or low concurrency. Check `max_concurrent_live_migrations` (default 1 per compute), `live_migration_bandwidth`, and whether auto-converge or post-copy is enabled. Raising concurrency across hosts often gives most of the speedup.
2. **Use cold migration for workloads that can accept a short outage.** It's fast on Ceph because no disks are copied, but it needs a resize confirm.
3. **Drain properly.** Disable the compute service so nothing new lands on it, move the VMs off, confirm the host is empty, then stop nova-compute, patch, reboot and verify before re-enabling it.
4. **Keep evacuation as a break-glass procedure** for hosts that are truly dead, with a fencing step and a check that the source is gone before it runs.

If you share your nova release, the VM mix (memory size, pinning, PCI devices, local disks), and a sample migration log, I can help work out which of these fixes applies. The `openstack-maintenance-planning` skill also covers sizing and sequencing for the full campaign.