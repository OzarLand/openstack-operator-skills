## Summary

**Verdict: not safe to run on prod as written. It could be made safe with changes (see the list below).**

**What it does (Observed, from the YAML you pasted):** It runs on every host in the `compute` group at once. It updates all packages to the latest version, ignores any failure, then reboots every host. It has no `serial`, no drain or migration step, and no checks. The default `ansible.builtin.reboot` just reboots and waits for SSH to come back.

**Top risks:**
- Every hypervisor can reboot at about the same time, so every running VM goes down together.
- Failures are swallowed, so a failed update still leads to a reboot.
- Nothing checks that a host is healthy again after it reboots.

**Assumptions I'm making:** The `compute` group is your OpenStack hypervisors, and you have not shown me the inventory. I don't know your instance storage, your spare capacity or which workloads matter most. I have not run `--check`, and I'm reviewing the YAML only.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Install all available updates, including kernel, libvirt and QEMU | Execution, but the content is unreviewed | Unknown | Pin or review the update set, and test it on a canary host first |
| Continue after an update failure | Judgement | No. `ignore_errors: true` makes it by default | Remove it and make failure stop the host and the batch |
| Reboot now | Disruptive to tenant workloads | Unknown | Gate it behind drain, a human go and a window |
| Which VMs are disrupted, and how | Judgement about business criticality | No | Decide beforehand per workload: live migrate, cold migrate or coordinated restart |

## Scope and blast radius

All hosts in `compute` run in parallel, up to the Ansible `forks` limit (default 5). If your group has more hosts than that, they roll in waves of 5. That does not protect you. Five hosts down together can still exceed your spare capacity, and nothing makes the waves follow failure domains such as racks, AZs or aggregates.

The play also does not check whether `compute` is empty or unexpectedly large, and it does not check whether the group includes GPU, SR-IOV or other special hosts. I don't know what is in your inventory.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Dry run | No | `dnf` supports `--check`, but `reboot` does not tell you much in check mode. Run the play with `--check --diff` anyway, and use `dnf check-update` to preview the package list |
| Explicit scope | Partly | A whole group, with no `--limit` discipline |
| Batching (`serial`) | **No** | Nothing limits how many hosts patch at once |
| Stop conditions | **No** | There is no `max_fail_percentage` and no `any_errors_fatal`, and `ignore_errors: true` removes failure as a signal |
| Pre-checks | **No** | It does not check for running instances, spare capacity, cluster health or whether the host is already disabled |
| Drain / disable scheduling | **No** | It does not disable the nova-compute service on the host or migrate instances off |
| Post-checks | **No** | `reboot` only waits for SSH. A host with SSH up but libvirt, nova-compute or networking broken counts as success |
| Confirmation | No | There is no pause or approval step for a destructive play |
| Idempotency / re-run | Partial | A re-run is mostly fine for dnf. A reboot after a half-finished update is not safe |
| Concurrency lock | No | Two operators or a pipeline could start overlapping runs |

## Failure and recovery behaviour

- If an update fails, for example a dnf lock, a repo outage, a broken dependency or a half-applied transaction, the error is ignored and the host reboots into an unknown state.
- If you interrupt the run, some hosts will have rebooted and some will not, with no record of which.
- If a host does not come back, `reboot` times out (the default is 10 minutes). Because there is no `serial`, the other hosts have already gone down by then.
- There is no rollback path. You would need dnf history or snapshots, and the playbook doesn't use them.
- **Version-skew risk (verify for your release):** a partially patched fleet can have a mix of libvirt/QEMU versions. Live migration direction constraints could then block moves later, so the order in which you patch matters.

## Observability

Nothing records which hosts were patched, which packages changed or which kernel version each host ended on. It also does not mark hosts as in maintenance. Monitoring will alert for every host at the same time, and the alerts will look like an outage. At minimum, set a maintenance window or silences, and have the play log pre- and post-update package versions and kernel versions per host.

## Ownership and maintainability

I can't tell from the file who owns it, whether it is in version control or whether it has been tested. It also seems to assume the person running it knows the unwritten rules, such as "don't do all of them at once." That is control debt. The playbook should hold those rules.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | **Blocking** | `hosts: compute`, no `serial` | All compute hosts can reboot together, causing a full tenant outage | Add `serial:` with a small batch, such as 1 host for the first run and the number your spare capacity allows later, with batches that respect failure domains |
| 2 | **Blocking** | `reboot` task | It reboots hosts that still have running VMs, with no drain | Disable scheduling and live migrate or coordinate the VMs off each host first. Planning that needs workload classification (see below) |
| 3 | **Blocking** | `ignore_errors: true` | A failed update does not stop the reboot, and the failure is hidden | Remove it. Add `any_errors_fatal` or `max_fail_percentage: 0` at least for the first batches |
| 4 | Major | whole play | No post-reboot health check | After reboot, assert kernel version, that nova-compute and libvirt are active, that the compute service shows `up` and enabled, and that the network agent is up. Then re-enable scheduling. Ideally, boot and delete a test VM on the host |
| 5 | Major | `name: '*'`, `state: latest` | An unreviewed update set, which can include kernel, QEMU, libvirt, OVS and any pinned or excluded packages | Check that `exclude` and version locks are right. Test the same package set on a canary host, and capture the list of updates first |
| 6 | Major | whole play | No pre-checks | Check spare capacity, that the control plane is healthy, that no other maintenance is running and that you are inside the window |
| 7 | Major | whole play | No confirmation and no concurrency lock | Add a `pause` or pipeline approval before the reboot stage, and a lock so two runs can't overlap |
| 8 | Minor | `reboot` defaults | Default timeout and no `reboot_timeout`, `test_command` or `post_reboot_delay` | Set them to match your hardware's boot time (physical servers with long firmware init often exceed defaults) |
| 9 | Minor | whole play | No logging of package or kernel changes, no `no_log` needs identified | Record before/after versions and the run's owner and time |
| 10 | Minor | whole play | Owner, tests and documentation unknown | Name an owner, keep it in git and add a short runbook |

## What a safer shape looks like

This is a sketch to test in non-production first. It is not a drop-in fix. `state-changing` unless labelled.

```yaml
- hosts: compute
  become: true
  serial: 1                 # raise only after the first runs prove capacity and stop conditions
  max_fail_percentage: 0
  any_errors_fatal: true
  pre_tasks:
    # read-only: assert maintenance window, control plane health, spare capacity
    # state-changing: disable nova-compute scheduling on this host
    # state-changing: drain per workload class (live migrate / cold migrate / coordinated restart)
    # read-only: assert no instances remain (or only those with agreed handling)
  tasks:
    - name: update packages           # no ignore_errors
      ansible.builtin.dnf:
        name: '*'
        state: latest
      register: dnf_result
    - name: reboot if needed
      ansible.builtin.reboot:
        reboot_timeout: <set from your boot time>
      when: dnf_result.changed
  post_tasks:
    # read-only: assert kernel, libvirt, nova-compute, network agent up
    # state-changing: re-enable scheduling
    # read-only: capability check, such as boot/ping/delete a test VM on this host
```

I'd also keep these points in mind:
- Roll out in stages: one canary host, then a small batch, then the rest, with a pause between stages.
- Do not use "stop nova-compute and evacuate" as a faster drain. Evacuation assumes the host is dead and must be fenced first, and a healthy host being patched is a different case. For planning the drain method, GPU/SR-IOV instances, sizing and ordering, the `openstack-maintenance-planning` skill covers that. I can run it if you'd like.

## Questions for the author

1. What is in the `compute` group (how many hosts, which AZs and aggregates, any GPU, SR-IOV or large-memory hosts)?
2. Is instance storage shared (for example Ceph) or local? That decides whether live migration works.
3. How much spare capacity do you have per failure domain, and which workloads can't tolerate a restart?
4. Has this exact playbook run in prod before, and what happened? Were VMs drained by hand beforehand?
5. Who approves the maintenance window, and who owns this playbook?
6. Is there a test environment or a canary host where the same update set was tried?
7. If you share the inventory or variables, please redact credentials first.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.