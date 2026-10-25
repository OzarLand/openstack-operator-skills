Before automating, I'd spend an hour on root cause. Automating the migration treats a symptom that is probably coming from the host side.

## Why this is suspicious
With `hw:cpu_policy=dedicated`, vCPUs are pinned 1:1 to host cores, so steal shouldn't come from other guests. Steal that appears on pinned VMs and goes away after a move usually means something on the host is competing for those pCPUs. Likely causes:

- **Emulator threads and I/O threads.** If `hw:emulator_threads_policy` isn't set, QEMU's emulator threads run on the same pCPUs as the vCPUs.
- **Host kernel work on the pinned cores.** This includes IRQ affinity, kworkers, ksoftirqd, and OVS/DPDK or other host daemons. Check that `isolcpus`, `nohz_full` and `irqbalance` are configured to exclude the dedicated set.
- **`cpu_shared_set` overlapping `cpu_dedicated_set`** in nova.conf on some computes.
- **SMT siblings.** A noisy VM on the sibling hyperthread looks like steal. Check `hw:cpu_thread_policy`.
- **Drift over days.** Things that build up slowly, such as memory fragmentation, a host daemon growing, or new VMs landing on sibling cores, would explain steal returning after a few days.

Compare the 15 affected VMs. If the source computes cluster on a few hosts or share a config trait, the fix is on the host, not a migration.

## Detection
- **Measure on the compute node, not in the guest.** For each QEMU process, sum `run_delay` from `/proc/<pid>/task/<tid>/schedstat` over the vCPU threads. That is the time a vCPU was runnable but not on a CPU. It needs no guest agent and can't be spoofed by guest clock issues. Alternatively, query Prometheus with `node_cpu_seconds_total{mode="steal"}` from the guests.
- **Require a sustained breach.** For example, steal above 5% for at least 15 of the last 20 minutes. Short bursts shouldn't trigger a migration.
- **Check the host first.** If two or more VMs on the same compute breach at once, the host is the problem. In that case, alert and optionally disable the host with `nova service-disable` instead of migrating each VM.

## Migration logic
1. **Pick the target.** Let the scheduler choose, with no explicit host: `openstack server migrate --live-migration <vm>`. Passing a host bypasses the scheduler's NUMA and pinning checks. Exclude the source host and any host that has recently had steal.
2. **Check preconditions.** The VM is ACTIVE, has no migration in progress, and has no locks or tags such as `no-auto-migrate`.
3. **Run migrations one at a time, cluster-wide.** Use a lock file or a DB row.
4. **Verify afterwards.** Wait for ACTIVE on the new host, then re-measure steal after 10 minutes. If it is still high, don't migrate again. Alert.

## Guardrails (these matter most)
- **Cooldown per VM**, for example no more than one automatic migration per 48 hours. This prevents ping-ponging between two bad hosts.
- **Global rate limit**, for example at most 2 migrations per hour and 5 per day. A bad host or a bad deploy can otherwise trigger a migration storm.
- **Dry-run by default.** Log what it would do for a week before enabling it.
- **Alert on every migration**, so the manual toil becomes visible data. Log the VM, source and target, steal readings, and host.
- **Handle migration failure.** Live migration can fail to converge on busy VMs, or stall. Set a timeout, and on failure alert and don't retry.
- **Give owners an opt-out.** Latency-sensitive or DPDK tenants may not want surprise migrations.
- **Kill switch.** A file such as `/etc/steal-migrate.disabled` that makes the job exit immediately.

## Structure
Cron every 5 minutes isn't ideal because you need a sliding window. I'd run a small Python script, either as a systemd timer or a long-running service, that does the following:

1. Samples `run_delay` per VM every 60s and keeps a ring buffer in memory or SQLite.
2. Computes the rolling steal percentage.
3. Applies the host-correlation, cooldown and rate-limit checks.
4. Calls the migration through openstacksdk, or the CLI at first.
5. Writes events to a SQLite or log table.

I can write that skeleton with dry-run mode, the sampling code and the guardrails. To do that I need to know:
- Do you run the script on each compute or from a central control host?
- Do you have Prometheus data for steal?
- What is your OpenStack release?

I'd also like to see one affected VM's flavor extra_specs and the source hosts' nova.conf `[compute]` section.