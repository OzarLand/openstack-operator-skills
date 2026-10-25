Not as written. I'd fix a few things before it touches prod.

**Problems**

1. **`hosts: compute` with no `serial`.** Every host patches and reboots at once, so the whole compute tier goes down together. Add `serial` (e.g. `serial: 1`, or `10%`) so you roll through in batches.

2. **`ignore_errors: true` on the update.** If dnf fails on a host (broken repo, dependency conflict, partial transaction), the play carries on and reboots that host anyway. Remove it. Better, use `any_errors_fatal: true` or `max_fail_percentage` so a failing batch stops the rollout instead of spreading.

3. **No drain or health check.** Nothing takes the host out of the load balancer or scheduler first, and nothing confirms it's healthy afterward. If these are hypervisors or k8s/OpenStack nodes, you need to evacuate or cordon before the reboot and check services afterward. Otherwise you'll reboot workloads that are still running.

4. **Reboot happens unconditionally.** Reboot only when needed. Register the dnf result and check `needs-restarting -r`, or check whether the kernel or core libraries changed.

5. **`reboot` has no timeout or post-check.** Set `reboot_timeout` and a `test_command`, so a host that comes back broken doesn't look like success.

6. **`state: latest` on `'*'` has no guardrails.** That means a surprise major bump of whatever is in the repos that day. Consider pinning to a tested snapshot or repo, or at least running it on staging first, and adding `exclude` for packages you hold back (kernel, database, container runtime, and so on).

**Sketch of a safer version**

```yaml
- hosts: compute
  become: true
  serial: "10%"
  max_fail_percentage: 0
  tasks:
    - name: pre-check (host healthy, drain from LB/scheduler here)
      ansible.builtin.debug:
        msg: "replace with drain / health check"

    - name: update packages
      ansible.builtin.dnf:
        name: '*'
        state: latest
      register: dnf_result

    - name: check if reboot needed
      ansible.builtin.command: needs-restarting -r
      register: needs_reboot
      failed_when: needs_reboot.rc not in [0, 1]
      changed_when: false

    - name: reboot
      ansible.builtin.reboot:
        reboot_timeout: 900
        test_command: systemctl is-system-running --wait
      when: needs_reboot.rc == 1

    - name: post-check (verify services, re-add to LB/scheduler)
      ansible.builtin.debug:
        msg: "replace with health check / undrain"
```

**Before prod**
- Run it against staging or a canary host first, with `--check --diff` and then for real.
- Make sure you have a rollback path (snapshots, or `dnf history undo`).
- Run it in a maintenance window.

If you tell me what "compute" is (VMs behind an LB, hypervisors, k8s workers), I can fill in the actual drain and health-check steps.