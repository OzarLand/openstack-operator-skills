Not as written. I'd fix a few things first.

**Problems**

1. **`ignore_errors: true` on the update.** If the dnf transaction fails (broken dependency, repo outage, disk full), the play carries on and reboots anyway. That can leave a half-updated host rebooting into a bad state. Remove it. A failed update should stop that host.

2. **No `serial`.** With `hosts: compute` and no batching, every host updates and reboots at the same time. If that group is a cluster, a pool behind a load balancer, or hypervisors running VMs, you lose all capacity at once. Use something like `serial: 1`, or a small percentage such as `10%`.

3. **No failure threshold.** Add `max_fail_percentage: 0` (or `any_errors_fatal: true`) so a bad patch stops the rollout after the first failing batch. Otherwise it keeps going through the fleet.

4. **No drain or health checks.** If these nodes carry workloads, the playbook should drain them first (cordon/evacuate, or remove from the LB) and confirm they're healthy afterwards before it moves on.

5. **Unconditional reboot.** Reboot only when needed, so you don't bounce hosts that didn't change. On RHEL-family systems, `dnf needs-restarting -r` returns 1 when a reboot is required.

6. **Reboot has no timeout or post-check.** Set `reboot_timeout` and a `test_command`, and ideally verify key services and the kernel version afterwards.

**Safer sketch**

```yaml
- hosts: compute
  become: true
  serial: 1                  # or "10%"
  max_fail_percentage: 0
  tasks:
    # - drain / remove from LB here

    - name: update packages
      ansible.builtin.dnf:
        name: '*'
        state: latest

    - name: check if reboot needed
      ansible.builtin.command: dnf needs-restarting -r
      register: needs_reboot
      changed_when: false
      failed_when: needs_reboot.rc not in [0, 1]

    - name: reboot
      ansible.builtin.reboot:
        reboot_timeout: 900
        test_command: systemctl is-system-running --wait
      when: needs_reboot.rc == 1

    # - health check, then re-enable in LB here
```

**Before running on prod**

- Run with `--check --diff` on a single host first. `dnf` check mode only partly simulates a real update, so it's a sanity check and not a guarantee.
- Run against a canary or staging host with `--limit` before the full group.
- Confirm you have snapshots or backups, and a maintenance window.
- Confirm repos are pinned or mirrored, so you aren't pulling an unvetted latest.

If you tell me what the `compute` group runs (Kubernetes, OpenStack, a plain LB pool), I can add the right drain and health-check steps.