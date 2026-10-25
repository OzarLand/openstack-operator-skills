Automating this is reasonable, but it treats a symptom. A VM with dedicated pinning shouldn't see 10-20% steal at all, and the fact that it comes back after a few days points to something specific on the hosts. I'd build the automation with guardrails and use it to collect the data that finds the cause.

## Detection

- **Best signal (host side):** for each VM, read `/proc/<qemu-pid>/task/<vcpu-tid>/schedstat`. The second field is run-queue wait time. On pinned vCPUs, nonzero wait means something else is competing for that core. It's more reliable than guest-reported steal, and you don't need agents in guests.
- **Alternative (guest side):** `node_cpu_seconds_total{mode="steal"}` in Prometheus, if you already scrape guests.
- **Trigger on a sustained condition, not a spike:** for example, steal above 5% in at least 4 of the last 5 samples at 5-minute intervals. Use `rate()` over a window, not instantaneous values.
- **Run it as a small daemon or a cron job with a state file or SQLite, not a stateless script.** It needs history for cooldowns and rate limits.

## Safeguards

1. **Dry-run mode by default.** Run it for a week and just log what it would do.
2. **Rate limits.** One migration in flight at a time, a cap of about 3 per day, and a per-VM cooldown (around 24h).
3. **Host-level check first.** If several VMs on the same host show steal, the host is the problem. Alert or disable the host with `nova service-disable` instead of migrating everything off it.
4. **Eligibility checks.** The VM must be `ACTIVE` with no task in progress. Skip VMs with PCI passthrough or other things that make live migration risky. Skip anything tagged or in a "don't touch" list.
5. **Let the scheduler pick the destination.** Don't pass an explicit host. Check that the destination isn't one that recently showed steal, because bad hosts attract the next migration.
6. **Post-migration verification.** Wait 15-30 minutes and re-measure. If steal is still high, mark the VM "needs human", stop retrying, and alert.
7. **Circuit breaker.** If more than N migrations fail or don't fix things in 24h, stop all automation and page someone.
8. **Audit log.** For every action, record the VM, source host, destination host, steal before and after, and timestamp.

## Using it to find the root cause

Log the source host's state each time it fires, then look for patterns across your ~15 manual events:

- **Same hosts over and over?** Look at those hosts' `cpu_dedicated_set` against `cpu_shared_set` and `reserved_host_cpus`. Overlap or a missing reservation is the classic cause.
- **SMT siblings:** are shared-policy VMs, or host processes, running on the hyperthread siblings of the dedicated cores? Consider `hw:cpu_thread_policy=isolate`.
- **Emulator threads and IO threads:** the default `hw:emulator_threads_policy` lets QEMU emulator threads compete on the vCPU cores. Try `share` or `isolate`.
- **Host noise on those cores:** check `irqbalance`, kernel threads, ksoftirqd, OVS or Ceph daemons, and whether the cores are in `isolcpus` / `nohz_full`. Run `perf sched` or `pidstat -t` on the affected cores during an event.
- **Timing:** does it return as neighbors grow, or after a periodic job such as backups or log rotation?

If the cause turns out to be, say, emulator threads landing on pinned cores, one flavor change fixes it for good and the automation becomes a safety net.

## Implementation sketch

```
loop every 5 min:
  for each compute host:
     for each VM: sample vCPU schedstat -> steal% (delta over interval)
  update state (rolling window per VM)
  candidates = VMs breaching threshold sustained, eligible, not in cooldown
  if host has >= 2 candidates: alert "host issue", skip migrations
  if breaker open or in-flight migration or daily cap hit: skip
  pick worst candidate -> `openstack server migrate --live-migration <vm>` (no host arg)
  poll until ACTIVE/ERROR, wait, re-measure, log result
```

I can write this as a Python script using `openstacksdk` for Nova and a small SQLite state store, with the dry-run flag and the host-level check included. Two things would help me tailor it: how you collect metrics today (Prometheus, Gnocchi, or nothing) and which OpenStack release you're on.