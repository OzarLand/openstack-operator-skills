**My recommendation is to semi-automate this first, not to build auto-migrate yet.** Build a cron job that detects steal, collects evidence and proposes the migration. A human approves it. This is a design-level review, since no code exists yet.

## Why not fully automatic yet

**1. The cause isn't understood, and the migrations are masking it.** A dedicated-CPU VM shouldn't see 10–20% steal, because its pCPUs aren't supposed to be shared. (Reported: you've migrated by hand about 15 times this month, and steal clears for a few days.) Automating that makes the workaround run faster and hide the cause better. Repeating a workaround is evidence there's a real problem. Repeated recovery isn't stability.

Migration changes which host and which pCPUs the VM gets. That points to something specific to the cores or host it was on. These are hypotheses, not findings:
- Host processes or IRQs landing on cores that are meant to be isolated. This could come from `cpu_dedicated_set` not matching `isolcpus` or the systemd `CPUAffinity` settings, or from IRQ affinity.
- Emulator or I/O threads competing with vCPU threads (check `hw:emulator_threads_policy`).
- Overlap between `cpu_shared_set` and the dedicated set, or SMT siblings of pinned cores serving other work.
- Something on the host that grows over days, such as page cache or compaction, kswapd, a leaking agent, or a noisy neighbor added after the move.
- A measurement problem, such as how steal is being read (guest `/proc/stat` vs host-side).

**2. "Migrate it" is a judgement, not just execution.** Detecting steal is execution. Deciding to disrupt a tenant's pinned workload is a judgement about risk. Live-migrating a pinned VM can fail or hit post-copy and convergence problems. It re-pins NUMA, and the target may be just as bad. Unless someone has explicitly delegated that to automation, it should stay with a human. Who owns that decision for these tenants?

## Read-only diagnostics to run first

Use the ~15 manual cases you already have:
- Make a table of instance, source host, destination, time, steal before and after, and days until recurrence. Check whether the sources cluster on a few hosts or a few flavors.
- On affected hosts, run `virsh vcpupin` and `virsh emulatorpin` for the VM. Compare those cores with `isolcpus`, `cpu_dedicated_set` and IRQ affinity (`/proc/interrupts`, `/proc/irq/*/smp_affinity_list`).
- Run per-core `mpstat -P ALL` and `perf sched` on the host for the affected cores, to see what else runs there.
- Ask what changed about when it started: a kernel, tuned profile, flavor change or new workload type.

All of these are read-only. If the pattern turns out to be one host or one core range, the fix is a config change, not a migration job.

## Design for the semi-automated version

**Detection (read-only)**
- Use a sustained signal, such as the average over 30 minutes or at least N consecutive samples above 5%, not a single spike. Without that, the job will flap.
- Decide where steal is measured. Guest-side needs an agent or exporter, and host-side comes from libvirt or your metrics. I need to know what you have.
- Only consider instances that are ACTIVE, have no task_state and aren't already migrating.

**Evidence package (read-only)**
- For each hit, record the instance, host, pinned cores, flavor and steal history. Also record the last migration (this is what shows repeat offenders), the candidate destination's current steal, and its free dedicated-CPU capacity.
- Send it to chat or a ticket as a proposal with the exact command to run.

**Action (state-changing, human-triggered)**
- A wrapper such as `steal-migrate <instance> --dry-run` is the default. It needs `--confirm` to act.
- Let the scheduler choose the destination. Don't force `--host`, because that bypasses the scheduler's NUMA and capacity checks. Exclude hosts that are already showing steal.
- Verify the result: migration status is `completed`, the instance is ACTIVE on the new host, it's reachable, and steal is lower 15–30 minutes later. Verify the outcome, not the command's exit code.

## If you later want it fully automatic

This only makes sense after the cause is understood, or after a decision to accept the workaround for a set period. Then the following safeguards are required:

| Safeguard | Design |
|---|---|
| Scope | Opt-in, not opt-out. Use a flavor or metadata tag, such as `auto_steal_migrate=true`. Exclude PCI/SR-IOV passthrough, GPU, hugepage and other non-live-migratable instances. |
| Rate limits | Cap each run at 1 migration, with a small daily maximum. Allow one concurrent migration per host. |
| Per-VM cooldown | If the same VM is migrated twice in 14 days, stop acting and escalate. That means the cause is the VM or the fleet, not one bad host. |
| Kill switch | A file or flag that disables the job without editing cron, plus `flock` so runs can't overlap. |
| Stop conditions | Halt everything on any failed or stuck migration, any instance left in ERROR, a compute service down, or the destination showing steal after the move. Resuming is a new human decision. |
| Timeouts | Abort a migration that hasn't converged within N minutes (verify the abort behavior for your release). |
| Credentials | A dedicated service user with only the role needed for live-migrate (verify your release's policy defaults). Don't put `clouds.yaml` secrets in the cron environment or in logs. |
| Audit | Log every decision, including the ones where it did nothing, with the steal values and the migration ID. Send a notification on each action. |
| Ownership | A named owner, version control and a short runbook, so someone other than you can explain it during an incident. |

Two things the job must never do:
- Never use `evacuate` for this.
- Never run migrations in bulk after a threshold breach. A fleet-wide event, such as a host-level problem or a bad measurement, would otherwise trigger mass migrations.

## What I need from you

1. How is steal measured today: guest agent, node exporter, or something else?
2. Which release are you on, and what is the storage (shared Ceph, local, volume-backed)? That determines live-migration risk.
3. What do the 15 cases look like: same hosts, same flavors, same tenants? Do you have the data?
4. Who owns the decision to move a tenant's pinned VM, and is it acceptable to do it unattended?
5. Is there spare dedicated-CPU capacity per failure domain? Each migration needs somewhere to land.

If you answer these, I can draft the detection and evidence-collection script in dry-run-only mode.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.