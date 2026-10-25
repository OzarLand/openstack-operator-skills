Automating this is reasonable, but a cron job that migrates VMs treats the symptom. Steal that returns after a few days on pinned VMs usually has a host-side cause, so look for that first.

## Diagnose in parallel
With `cpu_policy=dedicated`, guest steal means something else is running on those pCPUs. Check these on the affected hosts:
- **Host overlap:** `cpu_dedicated_set` and `cpu_shared_set` (or the older `vcpu_pin_set`) may overlap with host processes. Also check that `isolcpus` or systemd `CPUAffinity` keeps host daemons off the pinned cores.
- **Emulator and I/O threads:** with `hw:emulator_threads_policy` unset, QEMU emulator threads and vhost-net threads share the pinned cores. Heavy network or disk I/O in one VM then shows up as steal in its neighbours.
- **SMT siblings:** a busy sibling thread of a pinned core costs throughput. Look at `hw:cpu_thread_policy=isolate` or `require`.
- **IRQ affinity:** check `irqbalance` and NIC queues landing on guest cores.
- **Pattern in your 15 migrations:** do the source hosts repeat? Does the steal return on the destination, and how does the hosts' load drift over the days? If one noisy VM triggers it on its neighbours, migrating the victims never fixes the cause.

You can check from the host with `perf sched` or `pidstat -t` on the affected cores to see what else runs there. `/proc/<qemu-pid>/task/*/schedstat` gives per-vCPU run-queue wait.

## Detection
- **Metric:** use `rate(node_cpu_seconds_total{mode="steal"}[5m])` from the guest's node_exporter. If you can't run agents in guests, read the host-side equivalent from vCPU thread schedstat (`run_delay`).
- **Sustained, not spiky:** alert only when the 15-minute average is above 5% and the 5-minute average is also above it. A single reading will trigger on transient noise.
- **Where it runs:** a Prometheus alert plus a webhook is cleaner than polling from cron. If you want cron, have the script query the Prometheus HTTP API for `avg_over_time(...) > 0.05`.

## Migration guardrails
These matter more than the detection logic:
1. **Host-level check first.** If two or more VMs on the same host show steal, flag the host and alert a human. Optionally `nova service-disable` it, but don't migrate every VM off it.
2. **Per-VM cooldown.** Don't migrate the same VM more than once per N days. If it recurs sooner, escalate instead of looping.
3. **Global rate limit.** Allow at most 1–2 concurrent migrations and N per hour, so a fleet-wide metric glitch can't trigger a mass evacuation.
4. **Eligibility.** Only migrate `ACTIVE` instances with no task_state, no ongoing migration, and no tag opting out (for example metadata `no-auto-migrate=true`).
5. **Let the scheduler pick the target.** Run `openstack server migrate --live-migration <id>` without `--host`. Pinned and NUMA instances need a destination with free dedicated cores, and the scheduler checks that for you.
6. **Timeouts.** Poll `openstack server migration list`. If a migration hasn't converged after about 20 minutes (CPU-heavy guests often don't), run `nova live-migration-force-complete` or `live-migration-abort`, and alert.
7. **State and audit trail.** Keep a small SQLite or JSON file with `(vm, from_host, to_host, steal_before, steal_after, ts)`. It drives the cooldown, and after a few weeks it shows whether specific hosts are repeat offenders.
8. **Verify the result.** 30 minutes after the migration, re-measure steal. If it's still high, record it and don't migrate again.
9. **Operations:** use `flock` so runs can't overlap, a `--dry-run` flag (run it that way for a week first), and a notification such as Slack or email for every action.

## Skeleton
```
every 5 min (flock):
  candidates = prom_query(steal 15m avg > 5% AND 5m avg > 5%)
  group candidates by host
  for host with >= 2 candidates: alert "host problem", skip
  for vm in candidates:
      skip unless eligible (status, tag, cooldown, no active migration)
      stop if global rate limit hit
      record steal_before; live-migrate; log
  for pending migrations: check status, timeout handling, post-check steal
```

Tell me your stack (Prometheus or something else, OpenStack release, whether you can run agents in guests) and I can write the actual script with `openstacksdk`. If you can give me per-host steal data from the past month, I can also help find the pattern in the root-cause check.