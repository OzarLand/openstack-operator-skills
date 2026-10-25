**No. Don't use evacuate for planned maintenance.** It's the wrong tool. On shared Ceph it can also corrupt data.

**Why it's dangerous**

- Evacuate is for hosts that have already failed. Nova rebuilds the instance on another host and assumes the old host is dead.
- Stopping `nova-compute` does not stop the guests. The QEMU processes keep running on the host. "Service down" only means the control plane can't see the host.
- If you evacuate while the originals are still running, the same instance runs on two hosts at once. Both write to the same RBD image. Ceph's exclusive lock helps, but you can't rely on it to prevent corruption. Duplicate IPs and MACs are also likely, and the result is split-brain.
- Nova checks that the service is down, not that the host is fenced. A "down" nova-compute does not prove the VMs are off. A hung service, a message-bus problem or a stopped agent all look the same.
- Evacuate rebuilds from the instance definition. It is not a migration. Live RAM state is lost and every guest takes a hard restart. Ephemeral and local data, if there is any, is lost. Some instances may need extra handling or fail to rebuild.
- That makes it a disruptive, unannounced reboot of every VM, even on a good day.

If the colleague's plan also powers the host off before evacuating, the split-brain risk goes away. But you've then turned a patching campaign into a deliberate outage of everything on the host. You'd be using the failure-recovery path as a routine procedure.

**What to do about slow live migration**

These are the usual causes and fixes. Please confirm each against your own environment:

- **Classify by business criticality, not by technical convenience.** Only workloads that can't tolerate a restart need live migration. The rest can be cold-migrated or restarted in a window the owner agrees. That cuts the live-migration load a lot. Nova can't tell which workloads tolerate a restart, so the consuming teams have to say.
- **Memory-heavy guests that never converge.** Enable auto-converge or post-copy, or treat those guests as restart/cold-migrate candidates.
- **Concurrency.** Tune the number of parallel migrations from your own baselines. Check whether the migration network or `live_migration_*` settings (bandwidth, tunnelled or not) are the bottleneck.
- **Pipeline the work.** Drain the next host while the current one is being patched. The limit is spare capacity per failure domain, not migration speed.
- **Order for the libvirt/QEMU patch.** Migration from newer to older libvirt/QEMU isn't supported. Patch a small empty batch first as a landing zone, then move instances only toward patched hosts. For a kernel-only patch this doesn't apply.
- **Shared Ceph already helps.** There's no block migration, so only RAM is copied.

**Per-host flow**

1. Disable `nova-compute` with a reason. This is state-changing.
2. Move instances by class: live migrate, cold migrate, or agreed restart.
3. Check the host is empty, or that only agreed-restart instances remain. Check `resume_guests_state_on_host_boot` (the default is `False`), because guests that stay come back SHUTOFF after the reboot.
4. Patch and reboot, then verify.
5. Start the agreed-restart instances and have their owners confirm.
6. Re-enable the service.

Also note that instances still running on the old QEMU binary aren't patched until they've been migrated or restarted. Track that per instance.

**Missing information**

- How many hosts, and what are the failure domains (rack, AZ, aggregate)?
- Which release, libvirt and QEMU versions, and what CPU models?
- Is anything on local disk, or is it all on Ceph?
- Are there PCI passthrough, SR-IOV or vGPU instances?
- How much spare capacity is there per failure domain?
- Does a criticality table exist?
- What is the actual deadline, and what is slow about the live migrations (a few huge guests, or throughput overall)?

With those I can size the campaign and draft the full plan.

If a host fails during the campaign, evacuation becomes relevant, but only after fencing. The incident-analysis skill covers that case.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.