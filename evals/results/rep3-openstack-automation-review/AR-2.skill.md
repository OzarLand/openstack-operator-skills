## Summary

**Verdict: not safe to run on prod as written. It is safe with changes, and the changes are not small.** I only have the playbook text. The inventory, the workloads on `compute`, and the OpenStack setup are unknown to me, so this reviews the design only. I'm assuming `compute` means OpenStack hypervisors. Nothing has been run or checked-mode tested.

**What it does:** On every host in `compute` at once, it runs `dnf update '*'` and ignores any failure. It then reboots every host straight away. The reboot has no drain, no batching and no health check.

**Top risks:**
1. Every hypervisor reboots at the same time, so every VM goes down at once.
2. A failed update doesn't stop anything, so hosts reboot on a half-applied update.
3. Nothing checks that a host is healthy again before the next step.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | **Blocking** | `hosts: compute`, no `serial` | The blast radius is the whole compute fleet. All guests lose service together, and there is no spare capacity to take them. Failure domains aren't respected. | Add `serial` (start at 1 host, or one per failure domain), plus `max_fail_percentage: 0` or `any_errors_fatal`. Size how many hosts can be out at once from your actual spare capacity (unknown to me). |
| 2 | **Blocking** | `reboot` task | Guests are not drained first. Instances are either killed or resumed by `resume_guests_state_on_host_boot`. Which one happens depends on your config (verify for your release). Live migration needs a working source and destination, and a mixed-version libvirt/QEMU fleet during patching can restrict migration direction. | Disable scheduling on the host, live-migrate or otherwise handle the instances by workload class, confirm the host is empty or acceptably handled, and only then reboot. Pet, GPU/SR-IOV and large-memory instances need their own plan. See `openstack-maintenance-planning`. |
| 3 | **Major** | `ignore_errors: true` | If the update fails (repo down, dependency conflict, scriptlet error), the play continues and reboots into an unknown package state. Failure is never reported. | Remove it. Register the result and `assert` success. A failed host should stop the run and leave a clear failure. |
| 4 | **Major** | `name: '*'`, `state: latest` | The package set isn't reviewed or pinned. Kernel, libvirt, QEMU, OVS and container runtime updates all land together. If you run Kolla or containerized services, the host update also interacts with them. Repos aren't pinned, so hosts can get different versions. | Use a controlled repo snapshot or a mirror. Use `--check` or `dnf check-update` to preview. Look at what changes in libvirt, QEMU and the kernel. Test on a non-prod canary first. |
| 5 | **Major** | No post-checks | A successful reboot only means the host answered SSH. It doesn't mean `nova-compute` is up, networking agents are up, or instances can be placed. The next host could start on top of an unhealthy one. | After each batch, check that the compute service is `up`/`enabled`, the network agent is alive, and the expected instances are back. Gate the next batch on this and re-enable scheduling only after it passes. |
| 6 | **Major** | No pre-checks | There is no check for spare capacity, existing alerts, cluster health or a pending reboot. Nothing says what to do if a host was already unhealthy. | Check control-plane and storage health first. If you use Ceph or other shared storage, confirm it stays healthy as each node goes down. |
| 7 | **Major** | No recovery path | If a kernel or driver update stops a host booting, nothing says what happens next (console access, rollback, stuck instances). | Know the dnf history / previous-kernel rollback and out-of-band access before starting. Decide the stop condition and who calls it. |
| 8 | **Minor** | `reboot` defaults | The default timeout may be too short for large servers with long firmware POST. Reboots aren't conditional. | Set `reboot_timeout`. Reboot only when needed (kernel or core library changed, e.g. `needs-restarting -r`). |
| 9 | **Minor** | Observability and ownership | There is no logging of what changed per host, no owner and no run record. | Log per-host changes. Name an owner. Keep the playbook in version control with a run record. |
| 10 | **Minor** | Concurrency | Two runs could overlap. | Use a pipeline lock or a single entry point. |

## Judgement versus execution

Running `dnf` and rebooting is mechanical. Deciding to take a hypervisor out of service is not. It depends on which workloads are critical and which can't be moved, and that is a business decision. I'd keep it under human authority, or make it semi-automated. The automation can prepare the batch, run pre-checks and propose the host order, and an engineer approves each batch. Don't let it decide on its own that going on is fine.

## Questions for you
1. Is `compute` OpenStack hypervisors? If so, which release and what storage backend (shared or local)?
2. What is spare capacity, and how many hosts can you lose at once?
3. Which instances can't live-migrate (GPU, SR-IOV, local disk, pets)? What are your tenants' maintenance expectations?
4. Is the change window agreed and who owns the decision to proceed?
5. Is there a staging or canary host to try this on first?
6. How is `resume_guests_state_on_host_boot` set?

A safer shape would be one canary host first, then `serial: 1` (or one per failure domain). It would loop through disable scheduling, drain, update (failing hard on error), reboot if needed, run health checks, re-enable and verify, and stop on any failure. I can draft that, or the maintenance plan with the capacity sizing, if you want.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.