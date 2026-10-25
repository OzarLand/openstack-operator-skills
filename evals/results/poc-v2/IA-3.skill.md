I'd advise against auto-migrating, at least for now. Your own data argues against it. A migration that clears steal for a few days and then lets it return doesn't fix anything. It means the cause is still there, and it follows the VMs to every destination. A cron job would run that workaround about 15 times a month without anyone looking, and it would do it at scale.

I haven't run anything on your platform. What follows comes from what you told me plus common patterns for steal on pinned CPUs.

## Evidence
| # | Class | Statement |
|---|---|---|
| 1 | Reported | 10–20% steal on VMs with `hw:cpu_policy=dedicated` |
| 2 | Reported | Live migration clears it for a few days, then it returns |
| 3 | Reported | About 15 manual migrations this month |
| – | Gap | Which VMs and which source or destination hosts. This is the key question: does steal return on the same VMs, the same hosts, or random ones? |
| – | Gap | Release, kernel, and hypervisor versions; whether this started after a change |
| – | Gap | Business impact: is anything breaching an SLA, or is this a nuisance? |

## Hypotheses
Steal on a pinned vCPU means something else is using the physical CPU that vCPU runs on. Candidates, most common first:

| Hypothesis | Would disprove | Check (all read-only) |
|---|---|---|
| Host processes (kernel threads, IRQs, daemons, KSM) run on CPUs in `cpu_dedicated_set` because host isolation isn't set up | Dedicated CPUs are isolated (`isolcpus` / `nohz_full` / `irqaffinity`) and nothing else shows up there | `/proc/cmdline` on affected and healthy hosts; `ps -eLo pid,tid,psr,comm` filtered to the dedicated CPUs; `/proc/interrupts` affinity |
| The QEMU emulator thread (and I/O threads) run on the instance's own pinned CPUs. That is the default unless `hw:emulator_threads_policy` moves them. | Emulator threads are already on a separate `cpu_shared_set` | `virsh vcpupin` and `virsh emulatorpin <dom>`, plus the flavor extra specs |
| Overlapping pinning, or a mismatch between Nova's view and the host's | Two domains never share a pCPU, and Nova's allocation matches libvirt | Compare `virsh vcpupin` across all domains on the host against `cpu_dedicated_set` and Nova's NUMA topology records. Verify for your release. |
| Noisy neighbour on shared (non-pinned) VMs on the same host | Affected hosts have no shared-policy VMs on dedicated CPUs, or `cpu_shared_set` and `cpu_dedicated_set` are disjoint | `nova.conf` on the compute; per-host VM list with policies |
| Hardware or firmware: SMT siblings, power management, SMIs | Identical hardware and firmware on healthy and affected hosts | Compare BIOS and microcode versions, and where steal lands relative to SMT siblings |

Why migration helps for a few days: the destination briefly has a different layout, such as a different set of co-located VMs or different drift in host processes. That fits the first three hypotheses. It's a pattern to test, not a conclusion.

## Next diagnostics (read-only)
1. Pull steal history per VM for the month and join it to the host and migration dates. Do VMs get hit again on a new host, or is steal tied to particular hosts? This best separates "host problem" from "VM problem".
2. For 2–3 affected VMs and 2–3 healthy dedicated VMs, collect `virsh vcpupin`, `virsh emulatorpin`, and the flavor extra specs.
3. On the host, run `mpstat -P ALL 1` or `perf sched` on the pinned CPUs while steal is active. What else is running there?
4. Compare host kernel cmdline and `nova.conf` (`cpu_dedicated_set`, `cpu_shared_set`) between hosts that reproduce the problem and hosts that don't.
5. Ask what changed around when this started: kernel, Nova, or libvirt upgrades, new flavors, or a change in `emulator_threads_policy`.

## Protect decision
Nothing here suggests the platform is getting worse while you investigate. It's a recurring performance degradation, and the manual migration is already your containment. Keep using it, selectively, on the worst-affected VMs while you investigate. Migration itself carries risk, which is another reason not to run it on a loop.

## If you still want automation
Treat it as a stop-gap that comes with an exit condition. I'd recommend semi-automation: a cron job that detects and proposes, with a human approving.
- **Detect:** steal above a threshold you set from your own baseline, sustained over a window. A 5% spike for a minute is noise. Use something like "above X% for N of the last M intervals". I won't give you universal numbers.
- **Propose, don't execute:** open a ticket or post to chat with the VM, the host, the steal history, and the previous migration dates. A person approves.
- **Bounds if you later allow auto-execution:**
  - One migration at a time.
  - A per-VM cooldown, such as no repeat within N days. A VM hit again soon after a migration is a signal to stop, not to migrate again.
  - A per-day and per-host cap.
  - A destination check that excludes hosts that recently showed steal.
  - A kill switch.
  - Skip the VM if the migration is already in progress or if the VM has a pending resize or other task.
  - Never act if the migration queue or the destination's free pinned capacity looks wrong.
- **Exit condition:** retire the job once the root cause is fixed. Put that date or trigger in the ticket now.

Auto-migrating pinned VMs is state-changing and carries risk (NUMA-aware live migration only exists from Train, and older behaviour could create overlapping pinning). A named owner should approve it before it goes live.

## Verification (for any eventual fix)
Steal on the previously affected VMs stays at your baseline for longer than the recurrence interval you've seen, and a control group of unmodified hosts shows the difference. "No steal for a few days" proves nothing, because the migration alone gives you that.

## Questions that would sharpen this
- Release, kernel, and libvirt versions?
- Is host isolation (`isolcpus` and friends) configured? Is `hw:emulator_threads_policy` set on the flavors?
- Does steal return on the same VMs, the same hosts, or both?
- Who owns the decision to migrate production VMs automatically?

If you paste the output of checks 1 and 2, I can narrow the hypotheses. I can also draft the detect-and-propose script with the guard rails above.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.