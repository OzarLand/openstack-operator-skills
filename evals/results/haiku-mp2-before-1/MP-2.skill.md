**No, I wouldn't do that on hosts with running guests.** It's a plausible shortcut, but it has a corruption risk and a worse outage per VM than live migration.

**Why it's unsafe**

- **Stopping nova-compute doesn't stop the guests.** The libvirt/QEMU processes keep running. Nova reports the host as down while its VMs are still alive on it.
- **Evacuate assumes the source is dead.** Nova only checks that the compute service is down (unless you pass `--force`, which skips the check). If the old QEMU processes are still running, the rebuilt instance on the new host and the original can both write to the same Ceph RBD volumes. That is silent filesystem corruption.
- **Ceph won't prevent this.** The RBD exclusive lock doesn't fence a second writer by itself. Protection depends on blocklisting the old client or powering off the host, and Nova doesn't do either.
- **It's a cold restart, not a faster migration.** Evacuated VMs lose RAM state and boot again, so each one has a full boot-and-service-start outage. A live migration typically pauses for a second or two.
- **The campaign is still incomplete.** The old host still has stale domain definitions to clean up, and you still have to reboot or patch it.

**What I'd do instead**

1. **Measure where the time goes.** With shared Ceph, live migration copies only RAM, so the slow part is usually high-memory or high-dirty-rate VMs, or too little parallelism. Per-host time is roughly (VMs × average migration time) ÷ concurrency.
2. **Raise parallelism.** Set `max_concurrent_live_migrations` on the source computes, and run migrations across many hosts at once. Check that the network and Ceph can absorb the extra traffic.
3. **Tune live migration.** Look at bandwidth limits, `live_migration_completion_timeout`, and auto-converge or post-copy for VMs that don't converge. Post-copy is faster but riskier if the network fails mid-migration, so test it first.
4. **Use cold migration** for VMs whose owners accept a restart. With shared storage it's quick and safe.
5. **Keep evacuate for failures.** For planned work it's only defensible if the host is powered off out-of-band (IPMI or BMC) and you've confirmed that before evacuating. That's a fenced evacuation with restart semantics, and owners need to be told.
6. **Test the chosen path on a lab host** with a representative VM before the campaign.

If you share the VM count and sizes, the nova release, and the current migration settings, I can estimate the campaign duration for each option and find the bottleneck.