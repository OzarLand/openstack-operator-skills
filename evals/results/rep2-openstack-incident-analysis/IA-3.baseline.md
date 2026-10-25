Yes. The design below is mostly about keeping the automation from making things worse. I'd also treat the 15 manual migrations as data about a root cause, which I cover first.

## Find the cause first

A guest with dedicated CPUs shouldn't see 10-20% steal. Steal on a pinned vCPU means something on the host is preempting that vCPU thread. Migration helps because the VM lands on different physical cores, and the problem returns because the new placement degrades over time. Common causes:

- **Overlap between pinned and shared cores.** Check `cpu_dedicated_set` against `cpu_shared_set` and `isolcpus`, and check what else is allowed to run on the dedicated cores.
- **Emulator and I/O threads.** QEMU emulator threads, vhost-net and kernel threads can land on the pinned cores. Look at `hw:emulator_threads_policy`.
- **SMT siblings.** A noisy sibling thread may belong to another tenant. Check `hw:cpu_thread_policy`.
- **IRQ affinity and host daemons.** Examples are irqbalance and NIC queues on pinned cores.
- **Drift over time.** New VMs, host agents or cgroup changes that gradually put work on those cores.

To check this, run `perf sched` or look at `/proc/<qemu-pid>/task/*/schedstat` on an affected host. The `run_delay` field for the vCPU threads shows who is stealing time. Also log which source hosts and which pCPUs your 15 migrations came from. If a few hosts account for most of them, fix or drain those hosts. That is better than migrating VMs off them forever.

## Automation design

**Detection**
- Prefer host-side measurement of vCPU `run_delay` (libvirt `domstats` or schedstat). It needs no guest agent and can't be gamed by the guest. Guest-side `node_cpu_seconds_total{mode="steal"}` in Prometheus also works.
- Require sustained steal, for example the 15-minute average above 5% for two consecutive checks. A single sample will cause false migrations.

**Triggering**
- A Prometheus alert that calls a small webhook runner is better than cron. It gives you history, labels and silencing.
- If you do use cron, wrap it in `flock` so runs can't overlap.

**Safety rails** (the important part)
- **Dry-run by default.** Log what it would do for a week before enabling it.
- **Per-VM cooldown**, such as 7 days. If a VM is flagged again inside the cooldown, alert a human instead of migrating it again.
- **Global rate limit**: one migration in flight, with a cap per hour and per day. A host-wide problem could otherwise trigger a migration storm.
- **Host-level check.** If more than N VMs on one host have steal, don't migrate them. Alert and consider disabling the compute service for scheduling.
- **Preconditions**: the VM is ACTIVE with no task in progress, and has no recent failed migration.
- **Destination**: let the scheduler choose, but exclude the source host. Skip any destination host that is itself showing steal.
- **After the migration**: wait for it to finish, then recheck steal after about 30 minutes. If it's still high, alert and stop.
- **Kill switch**: a file or flag that disables the job.
- **Auth**: a dedicated service account with only the permissions needed to migrate.

**Things to watch for**
- Live migration of pinned, NUMA-topology VMs can fail or stall on busy guests, and it costs the guest some performance. Tune auto-converge or post-copy for the worst cases.
- You'd be moving the victim, not the noisy neighbor. If the cause is a neighbor, the job can end up shuffling victims around.

The command is `openstack server migrate --live-migration <uuid>`, or `--host <dest>` if you pick the destination yourself.

I can write the script, with the detection, rate-limit state and dry-run logging, and a diagnostic script for the root-cause hunt. Which would you like first? It would help to know whether you have Prometheus and whether you prefer host-side or guest-side metrics.