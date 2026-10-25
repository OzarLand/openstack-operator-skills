**No, don't do this.** Stopping `nova-compute` does not stop the guests. The VMs keep running under libvirt/QEMU on the host, and `openstack server evacuate` then rebuilds a second copy of each instance elsewhere. Nova's check only asks whether the compute service is down, and it is down, so the check passes while the originals are still running.

**Why it's dangerous**

- **Two live copies of each instance.** The original QEMU process keeps running and writing to its disks while the evacuated copy boots on another host. Shared Ceph means both copies can point at the same RBD volumes, so you risk filesystem corruption. I wouldn't rely on Ceph's image locking to stop the original writer. Verify that for your release, but treat the original guests as still live.
- **No clean shutdown.** The guests get no shutdown signal and lose their RAM state, so the evacuated copies come up as crash-recovered. Anything that wasn't flushed is at risk.
- **It's a failure-recovery tool.** Evacuation is for hosts that have failed and been fenced (powered off or isolated) first. Nova's own guidance is never to evacuate a host that may still run its instances.
- **Ephemeral or local disks are lost** on evacuation, and nova-compute no longer knows what is actually running on the host.

**Why it isn't faster**

- Evacuation rebuilds each instance and boots it, so every workload has downtime. Live migration has none.
- Every instance on the host goes down at once, instead of being moved in controlled batches.
- You lose the ability to verify each move before continuing.

**What would actually speed up the campaign** (verify each against your release and measured baselines)

1. **Raise concurrency within safe limits.** Check `max_concurrent_live_migrations` and the migration network bandwidth. Concurrency is often the real bottleneck, not per-VM copy time.
2. **Patch in parallel across failure domains,** respecting each domain's spare capacity, rather than one host at a time.
3. **Move tolerant workloads by cold migration or a coordinated restart.** This is parallelizable and faster than live-migrating everything. Use the owner-agreed criticality table to decide which workloads qualify.
4. **Handle memory-heavy guests with auto-converge or post-copy,** if they can't converge on live migration.
5. **For hosts that must reboot anyway:** disable the service, stop or cold-migrate the tolerant instances, patch and reboot, and set `resume_guests_state_on_host_boot` to `True` (or start the instances explicitly afterwards). Check each instance's power state after the reboot.

**What I need to size this properly**

- Host count and failure domains (rack, AZ, aggregate), and how many hosts you can take down at once per domain.
- Which packages are changing: kernel only, or libvirt/QEMU too? If libvirt/QEMU, the patch order decides where instances can land, since migration from newer to older isn't supported.
- Workload classes and downtime tolerance from the consuming teams, and the instance types in use (PCI passthrough, SR-IOV, vGPU, NUMA-pinned, memory-heavy).
- Measured live-migration times and the current concurrency settings. These show whether live migration is really the bottleneck or just feels slow.

I haven't inspected your platform, so the numbers above are assumptions until you provide them.

Decision support only. State-changing steps above (disabling services, migrations, restarts, reboots) require approval by the accountable owner and should be executed under your change process.