**Not as written.** The two biggest problems are that it reboots everything at once and that it reboots even when the update fails.

**Problems**

1. **No `serial`.** Ansible runs each task across all hosts in `compute` in parallel. Every compute node would update and reboot at the same time, so you'd lose all your capacity at once.
2. **`ignore_errors: true` on the update.** If dnf fails (broken repo, dependency conflict, disk full), the play carries on and reboots a half-updated host. Remove it.
3. **No drain or health gate.** If these nodes run VMs, containers or jobs, nothing moves workloads off before the reboot, and nothing checks the node is healthy afterward before the next batch starts.
4. **No `max_fail_percentage` or `any_errors_fatal`.** A bad update would roll through the whole fleet instead of stopping after the first batch.
5. **The reboot has no `reboot_timeout` or `post_reboot_delay`, and no post-checks.** The default timeout is 10 minutes. A slow-booting host will fail the play, and a host that comes back up broken won't be noticed.
6. **It reboots unconditionally.** Hosts that got no kernel or core-library update are rebooted anyway.

**Safer version**

```yaml
- hosts: compute
  become: true
  serial: "10%"            # or 1 for a first run; size to your spare capacity
  max_fail_percentage: 0   # stop the rollout if any host in a batch fails
  tasks:
    - name: pre-check - disk space on /
      ansible.builtin.assert:
        that: (ansible_mounts | selectattr('mount','equalto','/') | first).size_available > 2000000000

    # - drain / cordon / migrate workloads here (site-specific)

    - name: update packages
      ansible.builtin.dnf:
        name: '*'
        state: latest
      register: upd

    - name: check whether a reboot is needed
      ansible.builtin.command: needs-restarting -r
      register: nr
      failed_when: nr.rc not in [0, 1]
      changed_when: false

    - name: reboot
      ansible.builtin.reboot:
        reboot_timeout: 1800
        post_reboot_delay: 30
      when: nr.rc == 1

    - name: post-check - services healthy
      ansible.builtin.command: systemctl is-system-running
      register: sr
      until: sr.stdout == "running"
      retries: 10
      delay: 15
      changed_when: false

    # - undrain / re-enable scheduling here
```

(`needs-restarting` comes from `dnf-utils`, or `yum-utils` on older systems.)

**Before running on prod**

- Run it with `--check --diff --limit <one host>`, then for real on one canary host, before the full rollout. Note that `--check` won't show dnf failures.
- Confirm that the repos are pinned or mirrored, so the package set is what you tested in staging.
- Make sure you have a snapshot or rollback path (`dnf history undo`, VM snapshots) and a maintenance window.
- If `compute` includes hypervisors or cluster members (OpenStack, Kubernetes, Ceph, etc.), fill in the drain and undrain steps. Rebooting those without draining is the highest-risk part.

If you tell me what `compute` runs, I can fill in the drain and health-check steps for it.