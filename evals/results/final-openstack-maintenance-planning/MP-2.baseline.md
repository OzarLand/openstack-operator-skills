**Not a good idea for planned patching.** Evacuate is built for dead hosts, and using it on a live one has two problems.

**1. Split-brain risk.** "nova-compute is down" only means the Nova agent stopped. The qemu processes keep running on the hypervisor. If you evacuate while the original guests are still alive, Nova starts a second copy of each VM on another host using the same RBD images. Ceph's exclusive locks can reduce the damage, but they aren't a safe fence, and you can end up with corrupted disks. Evacuate assumes the source host is fenced, meaning powered off or otherwise guaranteed to have no running guests. Stopping a service doesn't do that.

**2. It's a crash-restart, not a migration.** Every guest is rebuilt and booted on the new host with no graceful shutdown. That means downtime plus filesystem or database recovery for each VM. It is faster only because it skips preserving the VM's running state, and you pay for that in guest outages.

**Better options**

- **Make live migration faster.** This is usually where the real gain is:
  - Set `live_migration_permit_post_copy = true` (or at least `live_migration_permit_auto_converge`) so busy guests converge instead of stalling.
  - Raise `max_concurrent_live_migrations`, and use a dedicated, fast migration network.
  - Check for `live_migration_bandwidth` caps, and for timeouts that abort large or busy guests.
  - Migrate several hosts' VMs in parallel, and drain with `openstack server migrate --live-migration` in a loop.
- **Skip migration for some patches.** Nova-compute and other agent updates don't need a drain, because restarting the agent doesn't touch running guests. Only kernel, qemu or libvirt updates need a reboot.
- **Cold-migrate tolerant VMs.** `openstack server migrate` (no `--live-migration`) shuts the guest down cleanly and starts it on another host. On shared Ceph it's quick and avoids the crash-restart problem. Use it for VMs that can take a short, clean reboot.
- **If you use evacuate anyway,** fence the host first (IPMI power-off or STONITH), and only then run `openstack compute service set --down` if needed and evacuate. Treat it as a controlled crash with the downtime that implies, and make sure the owners accept that.

For a patching campaign, I'd start by tuning live migration and splitting hosts into "no reboot needed", "live-migrate" and "cold-migrate OK". I can sketch the config changes or a drain script if you want.