**Verdict: don't automate the live migration as described. Automate detection and evidence collection, and keep the migrate decision with a human until you've found the cause.**

This is my read of your description only. I haven't seen your hosts, configs or metrics.

## Why

You said the steal goes away after a migration and comes back in a few days, and that you've done this about 15 times this month. The recurrence is evidence that the cause is still on the platform. Migration only moves the VM to a host where the cause isn't (yet) hitting it. A cron job would hide that signal and repeat the workaround at higher volume. Another team ran into the same pattern: repeated live-migration of pinned-CPU VMs relocated the symptom, and they stopped migrating and investigated instead.

Live migration also has its own risk. It dirties memory and can stall or fail. It needs free dedicated cores on the destination. It can cause a brief performance dip, and a pinned VM that moves lands on cores that may be contended in the same way.

## Likely causes (hypotheses, not findings)

The usual causes of steal on pinned guests are:

1. **Host processes on the dedicated cores.** Kernel threads, IRQs, KSM, or daemons run on CPUs in `cpu_dedicated_set` because host isolation isn't configured (`isolcpus`, systemd `CPUAffinity`, IRQ affinity).
2. **QEMU emulator threads on the pinned CPUs.** This is the default unless `hw:emulator_threads_policy` moves them.
3. **Overlapping pinning, or a mismatch between Nova's view and libvirt's actual pinning.** NUMA-aware live migration only exists from Train, and older behaviour could itself create overlap.

"Gone for days, then back" suggests something that changes over time. Candidates are a scheduled host job, KSM or page-merging activity, or new or migrated VMs landing on overlapping cores.

## Read-only checks to run first

- **Look at your own history.** For the ~15 migrations, tabulate source host, destination host, flavor, VM age, and days until recurrence. If the same hosts or flavors keep appearing, that points to the cause. This costs nothing.
- **Compare affected hosts with clean ones.** Check the kernel cmdline (`isolcpus`, `nohz_full`), `nova.conf` `[compute] cpu_dedicated_set` and `cpu_shared_set`, and IRQ affinity. Also check whether KSM and irqbalance are active.
- **Check per-VM pinning on an affected VM.** Run `virsh vcpupin <dom>` and `virsh emulatorpin <dom>`. Check that no two dedicated VMs share a pCPU. Check that nothing in the shared set overlaps the dedicated set.
- **See what else runs on those cores during a steal episode.** Use `ps -eLo psr,pid,comm,pcpu` filtered to the pinned CPUs, plus `/proc/interrupts` and `perf sched` or `pidstat -t` if available. This is the most direct check, and it needs an episode in progress.
- **Check whether steal is per-VM or per-host.** If every pinned VM on a host shows it, suspect host noise. If one VM does, suspect its pinning or emulator threads.

I don't know your OpenStack release, your steal source (guest `/proc/stat`, node_exporter, Prometheus), or whether the 5% is sustained or a spike. Those answers change the checks above.

## If you want a cron job now: semi-automation

This is a stop-gap with an exit condition (remove it when the cause is fixed).

**Detect (read-only, cron):**
- Compute steal over a sustained window, for example the average over 15–30 minutes above 5%. Use a window rather than a single sample so spikes don't trigger it.
- When it fires, capture an evidence snapshot automatically: VM and host, `vcpupin` and `emulatorpin`, the top threads on the pinned cores, and the host's kernel cmdline and relevant configs. This snapshot is what gets you to the root cause, and it is gone after the migration.

**Propose:** Post to chat or a ticket with the snapshot and the exact command, for example `openstack server migrate --live-migration <vm>`. Flag whether the destination has enough free dedicated cores.

**Human decides** and runs it. You keep control of the timing, the workload owner's input, and the recurrence trend.

## If you insist on auto-migrating

The job should meet all of these before it touches production:

| Guardrail | Why |
|---|---|
| Dry-run is the default, with an explicit enable flag | Lets you see what it would do before it does it |
| Max 1 migration in flight, and a daily cap (for example 3) | Limits the blast radius if the detector misfires |
| Per-VM cooldown, and a **circuit breaker** (a VM hit twice in N days stops auto-migration and alerts) | Recurrence is the signal you need, and this stops the job from masking it |
| Skip VMs with an opt-out tag or a critical-workload tag | The business owner decides which VMs may move |
| Never fall back to cold migrate or evacuate | Those are disruptive and a different decision |
| Check the migration state, and stop if one is running or stuck | Avoids overlapping migrations |
| Post-check: steal below threshold and instance healthy afterward, not just exit code 0 | The capability is what matters |
| `flock` to prevent overlapping runs, and a kill-switch file | Gives you a fast way to stop it |
| Log every decision and action, and alert on every migration | You must know when it ran and what it changed |
| Named owner, in version control, with a removal condition | Otherwise it becomes control debt |

Even with all of this, the job spends capacity and migration risk to hide a cause you haven't found.

## Questions that would sharpen this

1. Which OpenStack release and hypervisor stack (libvirt/QEMU versions)?
2. Do affected VMs cluster on certain hosts, flavors or ages? Do you have the tabulated history of the ~15 migrations?
3. Is host isolation configured, and is `hw:emulator_threads_policy` set on the flavors?
4. How is steal measured today, and over what window?
5. Who owns the decision to migrate these VMs, and are any of them tenant-critical?

I can write the detector and evidence-snapshot script if you share the metric source. I can also draft the history table or the host comparison once you have output.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.