**No, don't do that.** Stopping `nova-compute` doesn't stop the VMs, so evacuating from it can start a second copy of each instance while the first is still running.

**What goes wrong**

- `nova-compute` is only the management agent. Stopping it leaves libvirt and the qemu processes running, so the guests keep running on the host with their disks open.
- The host still has the VMs' IPs, MAC addresses and OVS/OVN port bindings. Once Nova rebuilds the instances elsewhere, you can get duplicate IPs and ARP conflicts on the network.
- Evacuation doesn't fence the source. Nova checks that the compute service is down, not that the hardware is off.
- On shared Ceph, two qemu processes can write to the same RBD images. RBD's exclusive-lock feature reduces this risk but doesn't remove it, and it depends on how your cluster and libvirt are configured. Don't rely on it as a fence.
- When `nova-compute` comes back, it may clean up the evacuated guests, but only after the damage is possible. The cleanup isn't a safeguard.
- Evacuate is also a crash-style restart of every guest, which is worse for tenants than a live migration.

**Why live migration may be slow, and what to fix**

With shared storage, live migration copies only RAM and device state, not disks. If it's slow, the usual causes are:

- **Serialization.** Nova's `max_concurrent_live_migrations` defaults to 1 on the compute side, so a mass drain runs one VM at a time. Raise it, carefully, based on what the migration network can handle.
- **Migration bandwidth.** Check the network the migrations use. A dedicated migration network helps, and `live_migration_inbound_addr` can point at it.
- **High dirty-memory VMs.** These never converge. Consider `live_migration_permit_auto_converge` (it slows the guest down) or post-copy for those workloads, and accept longer migrations or a planned restart for the worst ones.
- **Scheduling order.** Drain the least-loaded hosts first and move the most memory-intensive VMs when the cluster is quiet.

**If the host has to be taken down**

1. Disable the compute service (`openstack compute service set --disable --disable-reason "patching" <host> nova-compute`) so nothing new lands there.
2. Live-migrate the VMs off, in batches sized to your concurrency limit.
3. For any VM that won't migrate, decide with its owner between a clean shutdown and a cold migration, not evacuation.
4. Only after the host is empty, patch it.
5. If you ever do need evacuation (the host is really dead), first power the host off through its BMC or IPMI, then confirm no qemu processes remain. Only then evacuate.

Before the campaign, check your nova release, the `max_concurrent_live_migrations` value, the migration network, and the RBD exclusive-lock setting. I haven't seen your cluster, so those are the things I'd verify rather than assume. The OpenStack maintenance-planning and incident-analysis guidance also says to confirm a host is truly dead before any evacuation.