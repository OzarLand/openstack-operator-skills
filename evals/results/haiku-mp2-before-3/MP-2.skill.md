**No, don't do this.** Stopping nova-compute doesn't stop the VMs. The QEMU processes keep running on that host, and `evacuate` starts a second copy elsewhere. Shared Ceph makes that worse, not better.

**Why it's dangerous**

- **Split-brain on shared storage.** Both the original and the evacuated instance can end up writing to the same RBD volumes if the original comes back, or if its QEMU process is still alive. That is silent data corruption. Nova does not fence the source host.
- **`evacuate` refuses a host that is still up.** To get past that check you need `--force`, which removes the guard you're relying on. Only use it after the host is confirmed powered off.
- **Evacuation is a crash recovery.** Every guest loses RAM state and gets an unclean power-off. Applications without crash consistency can corrupt data or need manual repair. That is much worse than a live migration, and it is a restart for every VM, not only the ones you need to move.
- **Patching needs the host to go down anyway.** Evacuation moves VMs off the host, but the outage is not avoided. You also lose the controlled ordering a live migration gives you.

**Why live migration is slow, and what to check first**

With shared Ceph there is no disk copy, so live migration time is almost entirely memory transfer. The usual causes are:

- **`max_concurrent_live_migrations`** (nova, default 1). Draining a host one VM at a time is often the real bottleneck. Raise it, and keep the spare capacity you have per failure domain in mind.
- **Dirty-page rate.** Busy VMs never converge. Enable `live_migration_permit_auto_converge` and/or `live_migration_permit_post_copy` in `[libvirt]`. Post-copy is the faster option for large, busy guests, but a failure during post-copy can kill the guest, so use it deliberately.
- **Migration network.** Check that migrations use a dedicated, sufficiently fast network (`live_migration_inbound_addr` / `live_migration_uri`) and aren't competing with Ceph traffic.
- **Non-critical VMs.** Cold migrate or stop/start them with a planned restart. Shared storage keeps this quick, and it avoids the memory copy completely.

**If the campaign truly needs a non-live path**, do it as a planned procedure, not a colleague's shortcut:

1. Disable the service (`openstack compute service set --disable`) so nothing new lands there.
2. Move or stop the workloads deliberately, with graceful shutdown for those that need it.
3. Fence the host (power it off via BMC/IPMI) and confirm it is off before running any `evacuate`.
4. Only then evacuate the remaining VMs that need to keep running.

I'd also take a short look at the `openstack-maintenance-planning` skill if you want a workload-by-workload plan. It covers classifying which VMs need live migration, cold migration or a coordinated restart, and how many hosts you can patch at once given your spare capacity.