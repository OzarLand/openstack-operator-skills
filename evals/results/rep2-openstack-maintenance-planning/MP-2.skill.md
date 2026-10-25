**No. Don't use evacuate for planned patching.** It's the wrong tool even though the storage is shared Ceph. Your colleague is right that it's faster, but it gets that speed by giving up the safety that live migration provides.

**Why it's wrong**

1. **Evacuate is for hosts that have already failed.** Nova rebuilds the instance on another host, using the same disk on shared storage. It does not move a running guest. Every instance is down for the whole rebuild and boot, with no memory or state carried over. You'd be taking an outage on every VM to save migration time.
2. **"Nova-compute shows down" doesn't mean the VMs are down.** When you stop nova-compute, the guests keep running under libvirt/QEMU. Evacuating from a host whose instances are still running can start a second copy of the same VM on another host.
3. **Two copies of one VM on Ceph can corrupt the volume.** The original may still hold the RBD image while the new one boots on it. Without fencing, you can end up with two writers on one disk. The safe order is to power off or isolate the host first, and by then you've already caused the outage. Shared storage makes this more dangerous, not safer.
4. **Evacuate gives you no control.** It can't tell a database from a throwaway test VM. Migration lets you choose per workload, with owner agreement. Evacuate takes everything down at once.
5. **Patching doesn't need it.** Stopping nova-compute doesn't patch anything. A hypervisor/QEMU patch only protects instances that have been moved or restarted since. Evacuating off a still-running host also leaves the stale guests running there.

If the host genuinely fails mid-campaign, evacuate is the right tool, after fencing. That's the incident process, not the patching plan.

**How to make the campaign faster**

Live migration being too slow is a real problem, but it's a capacity and classification problem:

- **Split workloads by what the owner will accept.** Business criticality, from the consuming teams, decides this. Live-migrate only what has to stay up. For workloads that tolerate downtime, use cold migration (`openstack server migrate`) or a coordinated restart in an agreed window. That's faster than live migration and has a defined, agreed outage instead of a surprise one.
- **Some VMs can't live-migrate anyway.** Flavor-based PCI passthrough, `direct-physical` ports, and memory-heavy guests that dirty pages faster than they copy are in this group. SR-IOV `direct` ports can migrate since Train, but the guest briefly loses that interface. These need cold migration or restart whatever you choose. *(Verify for your release.)*
- **Tune live migration instead of abandoning it.** Check whether auto-converge or post-copy is enabled for busy guests, and look at the migration bandwidth and concurrency limits. Set concurrency from your own baselines, not a generic number.
- **Patch a landing-zone batch first**, if the patch touches libvirt/QEMU. Migration from newer to older isn't supported, so move instances only toward patched hosts. A kernel-only patch doesn't have this constraint.
- **Parallelize per failure domain.** Drain several hosts at once only if spare capacity covers it in each rack or AZ, not just overall.
- **Per host:** disable nova-compute with a reason, move instances by class, confirm the host is empty or holds only agreed-restart guests, then patch and reboot. Check `resume_guests_state_on_host_boot`: at the default `False`, restarted guests come back `SHUTOFF` and someone has to start them. Then verify and re-enable the host.

**Questions that would let me draft the real plan**

- How many hosts, and what are the failure domains (rack, AZ, aggregate)?
- Is the patch kernel-only, or does it change libvirt/QEMU?
- Is there a criticality table from the consuming teams? If not, collecting it is step one.
- Which release are you running, and do you use PCI passthrough, SR-IOV, vGPU or pinned instances?
- What's the deadline, and who can accept an exception if it can't be met safely?
- Why is live migration slow in your case (bandwidth, busy guests, concurrency limits)? Observed numbers would help.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.