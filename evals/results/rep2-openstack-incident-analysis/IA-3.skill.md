## Summary

**Verdict: safe with changes, and only in stages. Don't go straight to unattended auto-migration.** This review covers the design as you described it. No code was shown, and I haven't touched your infrastructure.

What you described is a cron job that finds guests with steal above 5% on `hw:cpu_policy=dedicated` instances and live-migrates each one. Everything about the symptom below is **Reported**, not Observed.

Top risks:
1. It automates a workaround for a problem nobody has diagnosed. "Steal goes away for days after a move, then returns" says the cause is tied to where the VM sits, such as host state or neighbors. Migration only resets that placement.
2. It can turn a host-level problem into a migration storm.
3. It can move the victim and leave the culprit running, or push the problem onto a healthy host.

## Purpose: should this be automated at all?

Pinned vCPUs on dedicated cores shouldn't normally see 10–20% steal. The cause is usually something else using those physical cores or their SMT siblings. Fifteen manual migrations a month is a repeated workaround, and repetition is evidence the problem is still open. A technically successful migration also doesn't prove the problem is gone.

My recommendation is to build the detector and the guardrails now, and diagnose in parallel. Treat auto-migration as a temporary, owned workaround with an exit condition (see "Rollout").

**Hypotheses to test** (none are established):
- Host or emulator threads, vhost-net, Ceph or OVS threads, or IRQs run on cores that are in `cpu_dedicated_set`. Possible causes are missing `isolcpus`/`cpu-partitioning`, or `reserved_host_cpus` or `cpu_shared_set` overlapping the dedicated set.
- Emulator threads aren't isolated (`hw:emulator_threads_policy`).
- A neighbor VM's pinning overlaps with the victim's, for example after a past config change or a mixed shared/dedicated host.
- Something on the host accumulates over days and is cleared by VM churn: THP compaction, NUMA balancing, KSM, or a periodic job.
- Your steal metric is misleading. It may be a guest-side number from a nested or oversubscribed hypervisor.

**Read-only diagnostics, run now:**
1. Compare `cpu_dedicated_set`, `cpu_shared_set`, `reserved_host_cpus`, the kernel cmdline (`isolcpus`, `nohz_full`) and tuned or systemd `CPUAffinity` on an affected source host against a clean host.
2. On an affected host, run `virsh vcpupin` and `virsh emulatorpin` for the victim and its neighbors, and check for overlaps.
3. Find what else runs on the victim's physical cores, for example with `ps -eLo pid,tid,psr,comm` filtered to those CPUs.
4. Read `/proc/<qemu-pid>/task/<tid>/schedstat`. The run-delay column gives a host-side measure of how long vCPU threads wait for a core, and it needs no guest cooperation.
5. Build a table of every migration so far: VM, source, target, flavor, tenant, NUMA node, date steal returned. Look for source hosts that show up repeatedly, victims that recur, and anything that correlates with the "few days" interval. This also answers "what changed?"

## Decisions the automation would take

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Is steal real and sustained? | Execution, if defined well | n/a | Use a window such as a 15-minute average over 3 consecutive samples, not one reading |
| Is this VM the victim or the cause? | **Judgement** | No | Don't assume. Log both the VM and its host co-tenants |
| Disrupt a tenant workload (live migration pause, possible convergence failure) | **Judgement** | Needs a named owner | Get an explicit written delegation for a bounded class of VMs |
| Pick the target host | Execution, if left to the scheduler | n/a | Let Nova schedule. Don't hand-pick |
| Is this a host problem? | **Judgement** | No | Detect it and stop, then page a human |

## Scope and blast radius

Candidates are chosen by a metric query, so a bad query, a metrics outage or a mislabeled series can change the target set. Cap it hard:
- **Global:** at most 1 migration in flight, at most N per hour, and at most M per day (start with 3 and 10).
- **Per host:** if 2 or more VMs on one source host are over the threshold, **don't migrate any of them**. Alert instead, because that pattern points to a host problem and migrating everything off wastes your spare pinned capacity.
- **Per VM, cooldown:** don't migrate the same VM twice within 7 days. If steal comes back inside that window, the move isn't the fix, so stop and page.
- **Empty or garbage input:** treat zero metrics or a metrics-source error as "do nothing and alert", never as "no steal".
- **Exclusions:**
  - Instances with PCI or SR-IOV devices, local storage without a block-migration plan, or very large or write-heavy memory.
  - Instances tagged `no-auto-migrate` (a metadata or flavor tag your tenants can see).
  - Anything the scheduler can't place on pinned capacity.

## Safeguards

| Safeguard | Design requirement |
|---|---|
| Dry run | Default mode is log-only ("would migrate X from A, reason: steal 14% over 15 min"). Run it for 2 weeks and compare against your manual decisions. |
| Explicit scope | Allowlist by host aggregate or flavor, not "all servers". |
| Confirmation | Phase 2 is a human "go" per migration (see Rollout). |
| Pre-checks | VM is ACTIVE with no task_state, no migration is in flight on the source or target, and the source and target nova-compute services are up and enabled. Check that spare pinned capacity exists, and don't run if headroom is low. |
| Migration call | `openstack server migrate --live-migration <vm>` with no `--host`. The exact CLI flags and the handling of pinned instances depend on your release, so verify for your release. |
| Timeout and abort | Poll the migration. If it doesn't finish in T minutes, run `openstack server migration abort`, then stop and page. |
| Post-checks | Check the capability, not the exit code. The VM is ACTIVE on a new host, it still answers on a health check you define, and steal measured over the next 30 minutes is below threshold. If steal is still high on the target, **stop automation entirely** and page. |
| Idempotency | Keep state in a ledger file or DB and re-read it each run. A re-run after a crash must not start a second migration for the same VM. |
| Concurrency lock | `flock` on a lockfile, with a timeout longer than the max migration time. |
| Kill switch | A flag file such as `/etc/steal-migrator/DISABLE`, checked at the start of every run and between steps. |

## Failure and interruption

- **Migration fails or stalls:** the VM should stay on the source. Verify this behavior for your release and backend. The script must never retry in a loop; one retry at most, then page.
- **Script killed mid-run:** the ledger records "started" before the call and "finished" after. On the next run, any "started" without "finished" blocks all new migrations until a human clears it.
- **Cron fires on a stale lockfile:** alert on a lock held longer than the max duration. Don't break it automatically.
- **Metrics source down:** do nothing and alert.

## Observability

- Every action goes to a structured log and a ledger: timestamp, VM, source, target, steal before and after, decision reason, migration ID, outcome.
- Send an alert or chat notification on each migration, on every stop condition, and when the daily cap is reached.
- Add a "last successful run" heartbeat, so a silently dead cron job gets noticed.
- The ledger is also your diagnostic dataset, so keep it queryable.

## Where steal should be measured

Steal is a guest-side number. Your options:
- **Guest exporters** (node_exporter in the tenant). This depends on tenants and you can't rely on it.
- **Host-side run-delay** from `schedstat` on the QEMU vCPU threads. It's measurable for every VM and is the more robust choice.
- **QEMU guest agent.** This is intrusive and not recommended.

I don't know what you collect today. If you use Prometheus, I'd have an alert rule produce the candidate list. The cron job then consumes that list, acts only on it, and applies the caps and cooldowns above.

## Findings

| # | Severity | Finding | Suggested change |
|---|---|---|---|
| 1 | **Blocking** if unattended from day one | Auto-disrupting tenant workloads is a judgement that needs explicit delegation, and none exists yet | Start semi-automated (Rollout phase 2), and get a named owner's written decision before phase 3 |
| 2 | **Blocking** | No host-level aggregate stop condition. A bad host would trigger a migration storm | Per-host threshold: 2 or more victims means alert only |
| 3 | **Major** | No cooldown. A recurring victim would be migrated forever, and repeated recovery isn't stability | 7-day per-VM cooldown, then page |
| 4 | **Major** | Success judged by migration status | Post-check steal on the target for 30 minutes |
| 5 | **Major** | Root cause unknown. Automation makes the workaround invisible, so the cause never gets fixed | Run the diagnostics above in parallel and set a review date |
| 6 | **Minor** | Ownership, tests and documentation unspecified | Version control, a named owner, a runbook, and a non-production test with fake candidates |

## Rollout

1. **Dry run only (about 2 weeks):** detect and log what it would do, with no actions. Compare it with what your team actually did by hand.
2. **Semi-automatic:** the job raises a ticket or chat message containing the evidence, the proposed migration and the pre-check results. An engineer approves with one command. This removes most of the toil and keeps the decision with a person.
3. **Bounded auto:** only after phase 2 shows consistent, low-risk results. It needs a named owner, a documented scope, the caps and cooldowns above, and an **exit condition**, for example "retire this when the root cause is fixed, or review it in 90 days".

## Questions for you

1. How is steal measured today (guest exporter, host metrics, something else), and at what resolution?
2. Are the affected VMs concentrated on certain hosts, flavors or tenants? Does the ledger of your 15 migrations show repeat victims?
3. Which release and storage backend (shared Ceph or local disk)? That decides block-migration needs and the behavior on a failed migration.
4. How much spare pinned-CPU capacity exists per aggregate? Auto-migration has nowhere to go if headroom is thin.
5. Who owns the decision to disrupt these tenants, and do they accept brief live-migration pauses?
6. Did anything change shortly before this started (kernel, tuned profile, Nova upgrade, new flavors, new tenants)?

Once you've answered the first three, I can write the detector and the ledger/guardrail skeleton, with dry-run as the default and the kill switch built in.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.