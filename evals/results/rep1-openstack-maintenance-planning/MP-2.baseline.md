Not as described. It's fast, but it's the wrong tool, and it can corrupt data.

**Why it's risky**
- **Stopping nova-compute doesn't stop the guests.** The VMs keep running on the source host with their RBD volumes open. Evacuate assumes the host is dead, and it starts a second copy of each instance elsewhere on the same Ceph images. That's a split-brain situation. RBD's exclusive lock isn't fencing here, and two qemu processes writing to one image can corrupt the filesystem.
- **To make it safe, you'd have to fence the host first.** That means powering it off or killing every qemu process. At that point each instance has had a hard crash, not a migration.
- **Evacuate is a rebuild-and-boot.** Each guest loses its memory state and goes through a cold boot, so downtime is minutes per VM.
- **It's an unusual path.** You'd have to mark the service down, either by waiting for the heartbeat timeout or with `openstack compute service set --down`. When nova-compute restarts after patching, it also has to clean up the stale local domains. This path exists for failures, and routine use will surface edge cases at bad moments.

**Better options**
1. **If some downtime per VM is acceptable, do a cold migrate.** Run `openstack server stop`, then `openstack server migrate` (or `--live-migration` after the stop isn't needed). The host is up and healthy, the guest shuts down cleanly, and the disks are already on Ceph, so it's quick and safe.
2. **If you want to keep live migration, tune it.** Most slowness comes from busy guests that never converge.
   - Set `live_migration_permit_post_copy = true` and `live_migration_permit_auto_converge = true` in nova.conf.
   - Raise `max_concurrent_live_migrations`.
   - Use a dedicated or faster migration network with `live_migration_inbound_addr`.
   - Drain several hosts in parallel, since shared storage means only memory is copied.
3. **Check whether you need to move VMs at all.** Only kernel, qemu or libvirt patches require a drain. Userspace-only patches don't.

For a patching campaign I'd go with tuned live migration, plus cold migrate for the few guests that won't converge. Keep evacuate for real host failures.