**No. Don't use evacuate for planned patching.** It's faster only because it skips the safety checks that make a migration safe.

**Why it's dangerous**

- **Stopping `nova-compute` doesn't stop the VMs.** The guests keep running under libvirt/QEMU on the host. Nova will show the service as "down" and let you evacuate, but it can't tell "service stopped" from "host dead".
- **Evacuate rebuilds each instance elsewhere while the original may still be running.** That gives you the same VM twice, both pointing at the same Ceph RBD volumes. The result is split-brain, with two writers on one disk and a real risk of filesystem or database corruption. Evacuation assumes the source host is dead or fenced (powered off or isolated). A stopped service doesn't meet that condition. *(Observed in the mechanics reference: "failed hosts only, host fenced first".)*
- **Shared Ceph makes this worse, not safer.** The shared storage is why the colleague's idea looks attractive. It's also why a double-running instance can damage data. Ceph RBD exclusive locks only reduce the risk. They are not a fence you should rely on here.
- **Every instance is hard-restarted.** Evacuation rebuilds and boots the guest elsewhere with no memory state. That's a crash-restart for every workload, including critical ones that could have been live-migrated with no downtime.
- **Capacity and compatibility checks are weaker.** Rebuilt instances land wherever the scheduler puts them, with no landing-zone or failure-domain control.
- **It doesn't deliver the patch anyway.** If you evacuate a host that hasn't been fenced, the old QEMU processes keep running there. A patch only protects instances that were migrated or restarted onto patched binaries.

**What speeds up the campaign without that risk**

1. **Disable `nova-compute` on the host** with a reason, so nothing new lands on it. This is the legitimate version of your colleague's first step. *(State-changing.)*
2. **Classify workloads, then pick a strategy per class.**
   - Critical and migratable: live migration.
   - Tolerates downtime, owner agreed: cold migration (`openstack server migrate`) or a coordinated restart. This is the fast path for non-critical VMs and is safe, because the instance is stopped cleanly before it moves.
   - Not live-migratable (PCI passthrough, SR-IOV, vGPU, fast-dirtying memory): cold migrate or restart, agreed with the owner.
3. **Tune live migration instead of abandoning it.** On Ceph you don't need block migration, so the disk isn't copied. If migrations stall on busy guests, look at auto-converge or post-copy and the migration bandwidth and concurrency settings. Verify these for your release.
4. **Parallelise across failure domains.** Drain several hosts at once, but no more than the spare capacity in each rack or AZ allows.
5. **Patch an initial batch first as a landing zone.** Migration from newer to older libvirt/QEMU isn't supported, so move instances only toward patched hosts.

**If a host really has failed mid-campaign**, evacuation is correct, but only after fencing the host (power it off or isolate it). That's an incident, not a maintenance method.

**What I'd need to build the real plan** (I have none of this yet, so I won't assume it):
- Host count, failure domains, and spare capacity per domain
- Nova, libvirt and QEMU versions, and CPU models
- Which instances use passthrough, SR-IOV, vGPU or pinning
- A criticality table from the consuming teams (who tolerates a restart, and for how long)
- Why live migrations are slow now (guest dirty rate, network, concurrency limits, or stuck migrations). The cause decides which fix helps.

I can turn this into the full campaign plan once you send those. To make progress now, the most useful single input is the criticality table. Most of the speed-up comes from not live-migrating workloads that can simply be cold-migrated.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.