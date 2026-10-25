**Yes. The main reason is split-brain, not speed.** Nova marks `cmp-0417` down because `nova-compute` stopped reporting. That doesn't mean the VMs stopped. The agent could have crashed while libvirt keeps the guests running, or the host could be partitioned from the control plane. If the guests are still running and you evacuate, the same Ceph RBD images get attached to a second host. Two writers on one database disk corrupts it, and nothing alerts you. Nova does not fence the old host for you, so you have to.

Before the mass evacuate, I'd check this:

1. **Is the old copy still running?**
   - Check whether the host responds on ping, SSH, or the BMC/IPMI console.
   - Check Ceph for active clients on the disks: `rbd status <pool>/<instance-disk-uuid>` lists watchers. If `cmp-0417` still holds a watch, the VM may be alive there.
2. **Fence it.** Power off `cmp-0417` through the BMC (`ipmitool -H <bmc> chassis power off` or your equivalent), then confirm the power state is off. If the host can't be powered off, the fallback is to blocklist its Ceph client (`ceph osd blocklist add <client-addr>`), but only after you're sure which client that is.
3. **Evacuate in batches, not all 40 at once.** Start with the customer databases. Don't use `--force`, since it skips the scheduler and can overcommit the target hosts. Watch capacity between batches with `openstack hypervisor list` and `openstack hypervisor show`.
4. **Check for things evacuation can't move cleanly.** Look for ephemeral disks on local storage, PCI/SR-IOV ports, pinned CPUs or NUMA placement, and anything with a host-specific config. These will fail or come up wrong on a new host.
5. **After each database boots**, check it for crash-consistency problems before putting it back in service.

If the on-call has a reason to believe the VMs are already dead, such as a confirmed hardware failure with the power off, then steps 2 and 3 are quick and the risk is small. Without that confirmation, a few minutes spent on the fence check is much cheaper than recovering a corrupted customer database.