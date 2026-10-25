Yes, though I'd treat the cron job as a stopgap and use it to find the root cause. Steal on pinned vCPUs shouldn't happen, and a problem that clears on migration and returns in days points at something on the source host.

## Likely root causes (check these while the automation runs)
- **Pinning overlap:** `cpu_dedicated_set` and `cpu_shared_set` overlap on some computes, or the old `vcpu_pin_set` is still set. Shared-policy VMs and host processes then land on the "dedicated" cores.
- **Host work on pinned cores:** qemu emulator threads, vhost/ovs threads, IRQs and kernel threads. Check `hw:emulator_threads_policy`, `isolcpus` or `systemd CPUAffinity`, and `irqbalance`.
- **SMT siblings:** a noisy neighbour on the hyperthread sibling. Check `hw:cpu_thread_policy=isolate` or `require`.
- **Time-dependent causes:** the problem returning after days suggests something like a cron job, log rotation, or a new VM landing on overlapping cores.

The tuning-data log in the design below will show which of these it is.

## Cron design

**1. Detection**
- Measure on the host, not in the guest. For each domain, read `run_delay` from `/proc/<qemu-pid>/task/<vcpu-tid>/schedstat`, or use the libvirt exporter's `libvirt_domain_vcpu_delay_seconds`. It's cheap and doesn't depend on guest agents.
- If you only have guest `/proc/stat` steal, that works too, but it's less reliable.
- Don't act on one sample. Require steal above 5% averaged over a window (say 15 minutes) for N consecutive runs. This avoids reacting to spikes.
- Check at the host level first. If many VMs on one host show steal, the host is the problem. Alert, disable the compute service (`openstack compute service set --disable`), and drain it deliberately. Don't migrate VMs one at a time off a bad host.

**2. Action**
- Run `openstack server migrate --live-migration <uuid>` with no target host, so the scheduler picks one and applies the NUMA and pinning claim. Don't pick destinations yourself.
- Only act on VMs that are `ACTIVE` with no task_state, and that have no opt-out tag or metadata.
- Take a lock with `flock` so runs can't overlap. Run one migration at a time per run.

**3. Guardrails** (these matter most for automated migration)
- **Per-VM cooldown:** for example, no more than one migration per 72 hours.
- **Per-VM cap:** if a VM has been migrated 3 or more times in 7 days, stop and alert. That means the cause isn't the host.
- **Global rate limit:** for example, no more than 3 migrations per hour and a limit per source host, so a bad metric can't cause a migration storm.
- **Failure handling:** if a migration errors or times out, alert and don't retry in a loop. Memory-heavy VMs may need `auto-converge` or post-copy to complete.
- **Dry-run mode** as the default for the first week.
- **Post-check:** after migration, re-measure after about 30 minutes. If steal is still above 5%, alert.

**4. Record the data for the root cause**
Log a JSON line per event with the VM, source host, destination host, pinned host CPUs, NUMA node, steal %, and the host's other pinned VMs. After a couple of weeks, check whether the affected VMs cluster on certain hosts, cores, or NUMA nodes.

## Implementation choices
- A systemd timer or an Alertmanager webhook is better than raw cron if you already run Prometheus. The alert gives you the "sustained for X" logic, and a small handler does the migration.
- Python with `openstacksdk` is easier to test than bash for the guardrails above.

If you tell me how you collect metrics (Prometheus with the libvirt exporter, guest agents, or something else) and your OpenStack release, I can write the script with the dry-run mode and the guardrails.