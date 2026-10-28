## Short answer

I'd advise against the cron job as described. Put the effort into finding the cause. If you still want a stop-gap, build a detect-and-propose tool, not an auto-migrator.

This is a design review. I haven't seen your platform, code or metrics. The cause-side claims below are known patterns for this symptom, not findings about your hosts.

## Why not automate the migration

**Observed (your report):** `dedicated` VMs show 10-20% steal. Live migration clears it for a few days, then it returns. You have done this about 15 times this month.

**Hypothesis:** Migration only moves the symptom. The recurrence is evidence that the cause is still there. Nova pins the guest's vCPUs and nothing else. The usual causes sit in the host configuration:

1. Host threads or IRQs run on the CPUs in `cpu_dedicated_set` because the host isn't isolated (`isolcpus`, `nohz_full`, `rcu_nocbs`, or a tuned profile).
2. QEMU emulator threads share the vCPUs' pinned CPUs. This is the default unless the flavor sets `hw:emulator_threads_policy`.
3. Two domains pin overlapping host CPUs.
4. `cpu_dedicated_set` doesn't match what the domains actually use.

A destination host configured like the source reproduces the problem. That fits "gone for a few days, then back".

Automating a workaround you haven't explained makes the problem happen faster and at scale. The cron job would also remove the pressure that is currently forcing you to look at the cause.

## What the automation would decide

| Decision | Execution or judgement? | Concern |
|---|---|---|
| Is steal > 5% a real problem? | Judgement | Steal measured inside the guest can be noisy. Is 5% over what window? |
| Disrupt this tenant's VM now | Judgement | Live migration pauses the guest, and pinned, latency-sensitive workloads are the ones that notice. Has the owner delegated that? |
| Pick a destination | Judgement | The scheduler may land on another host with the same fault. |

## Safer path

**1. Diagnose first (read-only, on an affected compute).** Don't migrate the VM before capturing this. Migrating destroys the evidence:
- `virsh vcpupin <instance>`, `virsh emulatorpin <instance>`, and the `<cputune>` section of `virsh dumpxml <instance>`.
- `cat /sys/devices/system/cpu/isolated` and `/proc/cmdline`.
- `ps -eLo pid,tid,psr,comm | awk '$3==<pinned-cpu>'` for each pinned host CPU.
- `/proc/interrupts` counts on the pinned CPUs.
- `cpu_dedicated_set`, `cpu_shared_set` and `vcpu_pin_set` in nova.conf. For Kolla that is `/etc/kolla/nova-compute/nova.conf`.

**2. Find the pattern across your 15 migrations.** I'd want to know:
- Are the source hosts the same few computes?
- Is the flavor the same?
- What changed in the days before steal returned (kernel or tuned updates, new VMs, a different workload)?

Please send these, with credentials redacted.

**3. Fix the cause (state-changing, each needs its approver).**
- **Emulator threads:** set `hw:emulator_threads_policy=share` on the flavor and define `[compute] cpu_shared_set` on every host. It only affects new or resized instances. Existing VMs need a resize to a new flavor or a rebuild.
- **Host isolation:** configure `isolcpus` and related settings to match `cpu_dedicated_set`. This needs a reboot, so the instances must be moved or stopped first. Do one host, measure, then roll out.

Both are documented in the reference material, but they are unverified. The lab evidence covers only the diagnosis and the emulator-thread move. It does not cover host isolation or any migration, and the steal result after the emulator-thread change wasn't recorded. Check against your release.

## If you still need a stop-gap

Make it semi-automatic, with a bounded scope and an exit condition. Detect and propose, and let a human approve.

- **Detector (read-only):** a cron job that reads steal at the hypervisor or guest level over a sustained window (say, N consecutive samples; pick the baseline from your own data). It also records the host, flavor, `virsh vcpupin` and `emulatorpin`. Then it opens a ticket or alert, which doubles as the data for your root-cause hunt.
- **Proposal:** it prints the exact `openstack server migrate --live-migration ...` command and the proposed destination. An engineer runs it.
- **If you must auto-act**, all of these are needed:
  - Explicit written delegation from the VM owners, and a named owner of the tool.
  - A dry-run mode that is the default.
  - Hard limits: one migration at a time, a daily cap per host and per VM, and no VM migrated twice in 7 days.
  - A stop condition. If the same VM is selected again within the window, or total migrations exceed the cap, it halts and pages. A repeat is evidence the cause is unfixed.
  - A pre-check that the destination has free dedicated CPUs and is not itself showing steal.
  - A lock file so runs can't overlap.
  - A post-check on capability: the migration shows `completed`, the instance is `ACTIVE` on the destination, and steal is checked on the new host after a delay.
  - Logging of every decision to a durable place.
  - An expiry date on the tool, set to when the root-cause fix lands.

## Open questions

- Which release and deployment tool are you on (Kolla-Ansible?), and is the host isolation configured at all?
- Are the affected VMs on the same hosts or flavors?
- Who owns these workloads, and who may approve disrupting them?
- How does a live migration of these VMs behave today (pause length, failures)?

If you send the `virsh` and host outputs from one affected VM, I can help work out which cause fits. After that I can draft the detector script or the flavor and host-isolation change plan.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.