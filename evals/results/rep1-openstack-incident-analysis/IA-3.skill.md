## Summary

**Verdict: safe with changes, and only as a staged rollout.** A cron job that migrates any VM the moment steal exceeds 5% is not acceptable as described. This is a design-only review, since no code was shown.

You've migrated by hand about 15 times this month and the steal comes back each time. Repeated recovery is not stability, and the recurrence is evidence that a cause is still unfound. Automating the workaround would hide that cause, and it would also erase the evidence on the source host. Live migration of pinned VMs is a disruptive, judgement-laden action, not pure execution.

The strongest part of this design is a job that captures host-side evidence before each migration. That is worth building even if you never automate the migration.

## Purpose and whether to automate

- **Observed (your report):** steal of 10–20% on `hw:cpu_policy=dedicated` VMs. Migration clears it for a few days. About 15 manual migrations this month.
- **Unknown, so I'm not assuming:** your release, the CPU model and SMT state, how many VMs and computes are affected, and whether affected VMs cluster on particular hosts.
- **Why this matters:** with true dedicated pinning, guest steal means the host scheduled something else on that VM's physical CPU. Migration gives the VM a different set of physical CPUs. A "clean for days, then back" pattern fits something that moves around or builds up on the source. These are hypotheses to test, not conclusions:
  - Host threads running on the pinned cores. Examples are IRQs, ceph/OVS/nova-compute, and QEMU emulator or I/O threads. Check `cpu_dedicated_set` against `cpu_shared_set` and isolation settings.
  - Emulator threads not isolated (`hw:emulator_threads_policy`).
  - SMT sibling contention.
  - Dedicated and shared instances overlapping on one host.
  - Host throttling or SMIs.
  - NUMA misplacement.
  - Computes that are themselves virtualized.
- **Recommendation:** automate the detection and evidence collection now. Treat automated migration as a temporary, owned workaround with an exit condition, which is root cause found.

**Read-only diagnostics to run first.** Run these on an affected host while a VM is steal-affected, and on a healthy one for comparison:
- `virsh vcpupin`, `virsh emulatorpin` and `virsh numatune` for the domain.
- `/sys/devices/system/cpu/isolated` and the kernel cmdline.
- `nova.conf` `[compute] cpu_dedicated_set` and `cpu_shared_set`.
- Which threads currently run on the pinned pCPUs (`ps -eLo pid,tid,psr,comm`, or `perf sched`).
- `/proc/interrupts` deltas on those cores.
- The QEMU vCPU threads' `/proc/<tid>/schedstat` (run-queue wait time). This is a host-side steal proxy that needs no guest cooperation. Verify it for your kernel.

## Decisions the automation would take

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Is steal real and sustained? | Execution, if the definition is strict | n/a | Automate (window, multiple samples) |
| Disrupt this tenant VM now | **Judgement** (tenant context, criticality, dirty-page rate) | Not yet | Needs an owner's policy: allowlist or opt-in, windows |
| Pick the destination | Judgement-adjacent | No | Let the scheduler choose. Never force a host. Exclude recently affected hosts |
| Continue after a failure | Judgement | No | Never. Halt and page |

## Scope and blast radius

- **Per run:** one VM at a time. Pinned VMs need free dedicated cores and matching NUMA on the destination.
- **Over time:** the risk is runaway behaviour. Examples are a cluster-wide event where many VMs cross 5% at once, ping-pong between two marginal hosts, or fragmentation of pinning capacity.
- **Cap:** a maximum number of migrations per hour and per day, and per source and destination host.

## Safeguards

| Safeguard | Needed design |
|---|---|
| Preview / dry run | Default mode is `--dry-run`. The job logs "would migrate X because Y" and enforces mode via config, not a flag someone forgets |
| Explicit scope | Allowlist by flavor, aggregate or metadata tag. Never "all VMs" |
| Confirmation | Phase 2 (below) requires a human go for each migration |
| Detection | Sustained over a window (for example 15+ minutes, repeated samples). Don't trigger on spikes |
| Cooldown | Per-VM hold-down (for example several days). A VM that re-trips immediately is escalated, not re-migrated |
| Pre-checks | VM is `ACTIVE`, `task_state` is none, no migration in progress (`openstack server migration list`), cluster healthy, destination capacity exists, no maintenance in progress |
| Concurrency | `flock` and a "one migration cluster-wide" lock. Make the lock outlive the migration, because cron overlaps |
| Post-checks | VM is `ACTIVE` on a different host, **and** steal is below threshold after N minutes. Exit code 0 is not success |
| Stop conditions | Any migration failure or timeout, `ERROR` state, more than N migrations per day, many hosts affected at once, low destination capacity. Halt all automation until a human resets it |
| Kill switch | Disable file or flag checked at the start of each run |

## Failure and recovery behaviour

- **Failed or timed-out migration:** it normally rolls back to the source, but verify for your release and storage backend. Bound the migration time and don't retry blindly. Handle pinned-instance edge cases (no suitable NUMA fit) as "skip and alert".
- **Interrupted run:** the job must be idempotent. On the next run, reconcile from Nova state (the migration list and VM status), not from its own memory.
- **Landing on a bad destination:** record steal per host. If the destination also shows steal, stop. This is a host problem, not a VM problem.
- **Recovery path:** a human can stop the job (kill switch) and see what it did (log below). Reverting a migration is just another migration, so it has the same risks.

## Observability

- Structured log for every decision, including "did nothing", with VM, source, destination, measured steal, reason and outcome.
- Metrics exported: candidates detected, migrations attempted, succeeded and failed, post-check results, and **migrations per host per week**. A rising migration rate is the early warning that the workaround is failing.
- Alert on every automated action while it is new.
- **Evidence capture before each migration (read-only):** pCPU-to-thread mapping, `vcpupin`/`emulatorpin`, interrupt deltas, top threads on the pinned cores, and host-level steal for all VMs on that host. This is the most valuable output of the job.

## Ownership and maintainability

- Named owner, version control, a staging test, and a short runbook that someone other than the author can follow during an incident.
- Dedicated service account with only the rights needed. Live migration is admin-only by default (verify your policy). Keep credentials out of the crontab.
- Consider a systemd timer, or an alert rule that calls the job, instead of raw cron. Both give better logging and locking.
- Write down the exit condition: "remove when root cause fixed or migrations/week below X."

## Suggested rollout

1. **Phase 0, observe only (1–2 weeks):** detect, record evidence, alert. Test which hosts and which pCPUs are affected, and whether it clusters. This may reveal the cause by itself.
2. **Phase 1, semi-automatic:** the job proposes ("VM X on host Y, steal 14% for 30 min, evidence attached, suggested command"). An engineer approves. This is judgement-assisted and removes most manual effort.
3. **Phase 2, automatic for a narrow allowlist:** only after the owner explicitly accepts the disruption policy, with all the guardrails above, a rate cap, and the circuit breaker.

## Findings

| # | Severity | Finding | Suggested change |
|---|---|---|---|
| 1 | **Blocking** | Immediate auto-migrate on threshold delegates a disruption judgement with no stated owner or policy | Staged rollout. Owner defines the allowlist and windows |
| 2 | **Blocking** | No stop condition or rate cap, so it can run away (cluster-wide steal, ping-pong) | Circuit breaker and hard daily cap. Halt on any failure |
| 3 | Major | Auto-migration destroys the evidence on the source host | Capture host-side evidence before each migration |
| 4 | Major | Success defined as command exit | Post-check VM state, host change and steal after N minutes |
| 5 | Major | No cooldown or destination steal tracking | Per-VM hold-down and per-host steal record |
| 6 | Major | Overlapping cron runs and non-idempotent state | `flock`, plus reconcile from Nova state each run |
| 7 | Minor | Where steal is measured is unspecified | Prefer host-side schedstat or an agent. Define the threshold and window explicitly |
| 8 | Minor | No owner, tests, runbook or exit condition | See Ownership |

## Questions for the author

1. Do affected VMs cluster on specific computes or specific physical cores?
2. What are the OpenStack release, `cpu_dedicated_set`/`cpu_shared_set` settings, isolation method and SMT state?
3. Are there floating (shared-CPU) VMs or other services on the same hosts?
4. How do you measure steal today (guest, exporter or host)?
5. Who owns the decision to disrupt tenant VMs, and which workloads are off-limits?
6. What is the interval between recurrences, and does it correlate with anything that changed (load, deploys, host maintenance)?

I can draft the Phase 0 detector and evidence-collection script, or the Phase 1 proposal output, if you tell me how you collect metrics.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.