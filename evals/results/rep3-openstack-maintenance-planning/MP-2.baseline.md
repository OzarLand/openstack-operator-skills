**No, not as described.** Stopping `nova-compute` doesn't stop the guests, so the colleague's procedure is unsafe.

**Why it's dangerous**
- Stopping the service leaves the libvirt/QEMU guests running on the host. Nova only marks the service "down" after missed heartbeats (`service_down_time`, 60s by default).
- `evacuate` is built for dead hosts. It assumes the old instances are gone and starts a second copy of each VM on another host, using the same RBD volumes.
- You then have two live VMs writing to the same Ceph image, which is split-brain. RBD's exclusive lock and blocklisting reduce the risk, but they aren't a guarantee, and you shouldn't build a patching process on them.
- When `nova-compute` comes back, it destroys the stale local copies. Until then, both copies are running.

**It also isn't faster in a useful way**
- Evacuated guests are hard-rebuilt on the new host, like a crash-reboot. Memory state is lost, there's no graceful shutdown, and filesystems are only crash-consistent.
- You get downtime for every VM, which is the cost live migration was meant to avoid.

**If you want to use evacuate anyway, do it correctly**
1. Fence the host first, by powering it off through IPMI/BMC. A hard power-off is the only real guarantee the guests are dead.
2. Run `openstack compute service set --down <host> nova-compute`, which marks the service forced-down. This needs compute API microversion 2.11 or later.
3. Evacuate.

At that point you have effectively crashed the host on purpose, which is a heavy way to do routine patching.

**Better ways to speed up the campaign**
- **Tune live migration.**
  - Raise `max_concurrent_live_migrations`.
  - Enable `live_migration_permit_auto_converge` and `live_migration_permit_post_copy`. Post-copy fixes the case where busy guests never converge.
  - Check `live_migration_bandwidth` and the network used for migration traffic. A dedicated or faster network often matters most.
- **Migrate in parallel.** Disable the host with `openstack compute service set --disable`, then script the live migrations across several hosts at once.
- **Use cold migration for guests that tolerate a short outage.** Stop the VM gracefully and run `openstack server migrate`. On shared Ceph there is no disk copy, so this is fast and clean.
- **Rolling batches.** Patch several hosts at once if you have the spare capacity.

If you tell me how many VMs per host and what your migration times are now, I can suggest which of these is likely to help most.