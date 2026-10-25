Before you automate, note that the migration is only a workaround. I'd spend an hour on the cause first, because a cron job that migrates VMs forever can hide a config bug. I'd also build the job with guardrails that make it surface the problem.

## 1. Why this probably recurs

A correctly isolated dedicated vCPU should show almost no steal. Steal on one means a host thread is competing for that physical core. Migration helps because the VM lands on different cores, and the problem returns when something lands on those cores again. Check these on an affected host:

- **Overlapping CPU sets.** Check `[compute] cpu_dedicated_set` against `cpu_shared_set`, and against the cores the host OS uses. Also check for leftover `vcpu_pin_set`.
- **Mixed hosts.** Shared-policy VMs, or host daemons such as ceph, OVS, or ksoftirqd/IRQs, may be running on cores that pinned guests use. `isolcpus` or systemd `CPUAffinity` may be missing.
- **Emulator and I/O threads.** With `hw:emulator_threads_policy` unset, QEMU emulator threads compete on the guest's cores.
- **SMT siblings.** Check whether the hyperthread sibling of a pinned core is used by something else. Look at `hw:cpu_thread_policy`.
- **Host-side evidence.** Run `virsh vcpupin <dom>` and `virsh emulatorpin <dom>`. Then on the affected pCPUs run `pidstat -t` or `perf sched` to see who else is running there.
- **Pattern.** Do the affected VMs cluster on certain hosts, flavors, or NUMA nodes? Fifteen migrations is enough data to tell.

## 2. Detection

- **Host-side (preferred).** Read `/proc/<qemu_pid>/task/<vcpu_tid>/schedstat`. The second field is cumulative run-queue wait in ns. Its delta over wall time is the steal the vCPU actually suffered. It needs no guest agent or tenant cooperation. Map libvirt domain to nova UUID to vCPU threads with `virsh qemu-monitor-command <dom> --hmp 'info cpus'`.
- **Guest-side alternative.** If you already scrape `node_cpu_seconds_total{mode="steal"}` from guests, use that. It only covers guests that run the exporter.
- **Trigger on sustained steal, not spikes.** For example, steal above 5% averaged over 10-minute windows, for 3 consecutive windows. Keep the state in a small sqlite file. Alert at a lower tier first, such as 2%.

## 3. Guardrails

| Guardrail | Why |
|---|---|
| Dry-run mode first (log and notify only) for a week | Validates thresholds with no risk |
| One migration at a time, `flock`, and a global cap (e.g. 3/day) | Bounds the blast radius if the detector misfires |
| Per-VM cooldown of 72h, and a circuit breaker after 2 migrations in 7 days that alerts a human and stops | Stops flapping and exposes the real root cause |
| Let the scheduler pick the target (no `--host`) | Forcing a host bypasses NUMA and pinning fit checks |
| Skip the destination if its own steal is high | Prevents moving a VM from one bad host to another |
| Opt-out tag in server metadata, and skip VMs not `ACTIVE` or with a `task_state` | Respects fragile or already-busy VMs |
| Exclude VMs with SR-IOV, PCI passthrough, or other non-migratable features | These fail or misbehave |
| Dedicated service account whose role is limited to live migrate and read | Least privilege |

## 4. Migration step

```
openstack --os-compute-api-version 2.30 server migrate --live-migration <uuid>
```

(`--block-migration` is auto-selected from API 2.25 on.) Then poll until the status is ACTIVE and the host has changed, with a timeout. Failed migrations leave the VM on the source, so alert and don't retry in a loop. Heavily writing guests may never converge. Look at `live_migration_permit_auto_converge` or post-copy, and set a completion timeout.

## 5. Verification and observability

- After 30 minutes, re-measure. If steal is still above 5% on the new host, flag it. That points at a systemic issue, not a bad neighbor.
- Emit metrics for steal per VM, migrations per host, and migrations that didn't fix the steal, plus a Slack or webhook notification per action.
- Treat the migration count per source host as the signal. If a few hosts keep producing victims, drain and fix them instead of migrating guests away.

## 6. Implementation

A systemd timer or cron every 5 minutes works. The script (Python with openstacksdk) is two parts:

1. A collector on each compute host, or a Prometheus exporter, that writes per-instance steal.
2. A controller running on one management node that reads the data, applies thresholds, cooldowns, and caps, and calls the API.

If you tell me your OpenStack release, whether you have Prometheus, and what the affected hosts have in common, I can write the controller script and the host collector. I can also help work through the root-cause checklist in section 1 first.