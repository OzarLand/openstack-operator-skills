## Summary

**Verdict: not safe to run on prod as written. It needs changes first.** I'm assuming `compute` is your OpenStack compute group. You haven't confirmed that, and I haven't seen your inventory, how many hosts are in it, or what runs on them. This is a review of the code you pasted, not of anything I ran. I haven't run `--check` or contacted any host.

As written, the playbook runs `dnf update '*'` on every host in `compute` in parallel, ignores any failure, and then reboots all of them. Ansible's default is up to 5 hosts at once (`forks`), and there is no `serial`. If your group has more than 5 hosts, they are done in batches of 5. Nothing in the playbook looks at what VMs are on a host. Every guest on a rebooted host goes down with it.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | **Blocking** | play level (no `serial`) | There is no batch limit. Hosts are patched and rebooted in forks-sized groups, so you can lose far more capacity than you have spare. | Add `serial: 1` for the first run. Raise it only after you've sized spare capacity per failure domain. |
| 2 | **Blocking** | `reboot` task | Nothing drains the host. VMs are not live-migrated, evacuated or stopped before the reboot. Tenant workloads take unplanned downtime. | Disable the nova-compute service on the host, migrate or coordinate the VMs off, and confirm the host is empty before it patches and reboots. |
| 3 | **Blocking** | `ignore_errors: true` on the update task | A failed or partial `dnf` transaction (broken dependencies, repo outage, a half-applied kernel or libvirt/QEMU update) is ignored, and the play reboots the host anyway. | Remove it. Make failure stop the play. Add `any_errors_fatal` or `max_fail_percentage: 0` so one bad host halts the campaign. |
| 4 | Major | whole play | There are no post-reboot checks. The `reboot` module only waits for SSH to return. A host that is up but has nova-compute down, libvirt failing or networking broken looks like success, and the next batch starts anyway. | Add checks that test the capability: the compute service is `up` and enabled, libvirt and the network agent are healthy, and a test VM can schedule or migrate. Fail the play if any check fails, and re-enable the host only after they pass. |
| 5 | Major | `name: '*'`, `state: latest` | The playbook takes whatever the repos hold on the day. That can include a major kernel, libvirt or QEMU bump, or packages from unvetted repos. | Pin and stage repo content, review the update list per host, and test it on a canary host first. |
| 6 | Major | no kernel or libvirt/QEMU handling | If some hosts are patched and others aren't, live migration between old and new QEMU can fail, and the direction matters. (Verify for your release.) | Plan migration direction and check the QEMU and libvirt versions across the group before you start. |
| 7 | Major | whole play | There's no pre-check, no preview, and no confirmation. You can't see what it will do before it does it, and an empty or wrong group isn't caught. `--check` will also tell you little here, because the reboot is skipped. | Add pre-checks that assert starting health and spare capacity. Print the target host list and the pending updates before acting. Require an explicit go for the production run. |
| 8 | Minor | play level | There is no concurrency lock, no logging of what changed per host, and no stated owner. Two overlapping runs would be bad. | Add a run lock. Log the package changes and reboot time per host. Name an owner. |
| 9 | Minor | `reboot` task | It uses the default reboot timeout. Slow-booting hypervisors can fail spuriously. | Set `reboot_timeout` and `post_reboot_delay` to match your hardware. |

## What the playbook delegates

It decides to disrupt workloads on every `compute` host, but it takes that decision without any business context. Which hosts can go down, when, and what runs on them are all judgement calls. Unless your organisation has explicitly delegated that to automation, those calls should stay with a human, or the playbook should be semi-automated: it prepares and checks, and an engineer approves each batch.

## Questions for you

- How many hosts are in `compute`, and across how many failure domains?
- Are guests on shared storage or local disk? Live migration depends on this.
- How much spare capacity do you have? Can you drain N hosts at once?
- Which workloads can't be migrated or interrupted?
- Is there a maintenance window and a named approver?
- Have you tried this on a staging or canary host? Any history of past runs?

## Suggested shape (a proposal to test in non-prod first)

I haven't written it into a file. Every step below that touches a host is state-changing.

```yaml
- hosts: compute
  become: true
  serial: 1
  any_errors_fatal: true
  tasks:
    # pre-checks (read-only): host healthy, spare capacity available
    # state-changing: disable nova-compute on host, drain VMs, assert host is empty
    - name: update packages
      ansible.builtin.dnf:
        name: '*'
        state: latest
      # no ignore_errors
    - name: reboot
      ansible.builtin.reboot:
        reboot_timeout: 1800
    # post-checks (read-only): compute service up, libvirt and network agent healthy
    # state-changing: re-enable the host only after checks pass
```

To go further, I can use the maintenance-planning skill to size batches and choose a migration method per workload, or the change-review skill to review the first production run as a change.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.