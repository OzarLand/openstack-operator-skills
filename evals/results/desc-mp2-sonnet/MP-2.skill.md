**No. Don't do this. Evacuation is built for a host that has failed, not for planned maintenance.**

**Why the "faster" plan is risky even on shared Ceph**

1. **Nova can't tell a stopped nova-compute from a dead host.** "Service down" only means the agent stopped reporting. The guests are still running under libvirt/QEMU on that host. Evacuate rebuilds each instance on another host without touching the originals.
2. **That gives you two live copies of the same VM on the same RBD disks.** The old QEMU process still holds the volumes. The new one starts on the same images. Without fencing, this risks filesystem corruption and split-brain (duplicate IPs and MACs, two writers). Nova's guard is "service is down", and you would have just satisfied it by stopping the service.
   - Ceph exclusive locks and blocklisting can reduce the corruption risk. Don't treat them as your safety net. Whether the old client is actually blocked depends on your RBD feature and config. Please verify that rather than assume it.
3. **Evacuation is a restart, not a migration.** Every VM goes down and is rebuilt elsewhere, so you take downtime on every workload, including the critical ones that live migration would have kept up. "Faster" here means moving the cost to your consumers.
4. **Evacuation doesn't give you the patching guarantees you need.** Nothing in this approach is verified per instance, and the old processes are still running on the host you're about to patch.
5. **You skip the decisions that belong to the workload owners.** Which workloads may be restarted is a business decision, not an infrastructure one.

**What's actually slow, and what to do instead**

Live migration is probably slow for one of a few reasons: busy guests that dirty memory faster than it copies, too few concurrent migrations, or network bandwidth. These are tunable. Auto-converge or post-copy helps with the first. Raising concurrency within what your network and Ceph can absorb helps with the others. Use your own baselines to set the limit.

A plan that is both faster and safe:

- **Classify workloads** with the consuming teams (criticality, acceptable downtime), plus technical migratability: PCI passthrough and `direct-physical` ports can't live-migrate.
- **Live-migrate the critical, migratable ones.**
- **Cold-migrate or restart the ones whose owners agree to downtime.** This is the fast path your colleague wants, but done safely. Cold migration (`openstack server migrate`) stops the guest on the source cleanly, then moves and starts it. No dual-run risk.
- **Check capacity per failure domain**, since that determines how many hosts you can drain in parallel. More parallel hosts is the real speed-up.
- **Mind libvirt/QEMU direction.** If the patch changes QEMU or libvirt, patch an empty landing-zone batch first. Migrating from a newer version to an older one isn't supported. Kernel-only patches don't have this constraint.
- **Per host:**
  1. Disable the compute service with a reason (state-changing).
  2. Move instances according to their class.
  3. Verify the host is empty, or that only agreed-restart instances remain.
  4. Patch and reboot.
  5. Check power state afterwards. By default (`resume_guests_state_on_host_boot=False`), guests that stayed on the host come back SHUTOFF and need starting.
  6. Re-enable the service.

Instances still running on the old QEMU binary aren't protected by the patch. Track each one until it has been migrated or restarted since.

**The one case where evacuate is right:** a host that has genuinely failed. Even then, fence it first (power off or isolate) so it can't still be running the guests.

Share these and I can draft a concrete plan with sequencing and stop conditions:
- Host count and failure domains
- Spare capacity
- Whether the patch touches libvirt/QEMU
- The release you run
- Whether a criticality table exists

Decision support only. Any state-changing steps above (disabling services, migrations, restarts, reboots) need approval from the accountable owner and should run under your change process.