Not as written. I'd fix a few things before running it on prod.

**Main problems**

1. **`reboot` hits every host at once.** With no `serial`, Ansible patches and reboots the whole `compute` group in parallel (up to `forks`, default 5, per batch). If those hosts run production workloads, you could drop most of your capacity at the same moment. Add `serial` (for example `serial: 1`, or `10%`), or use a rolling strategy per rack or availability zone.

2. **`ignore_errors: true` on the update.** If the update fails partway, for example from a repo outage, a dependency conflict, or a broken scriptlet, the play carries on and reboots a half-updated host. Remove it. If you want to tolerate some failures, use `max_fail_percentage` or `any_errors_fatal` so a bad run stops the rollout.

3. **The reboot is unconditional.** It reboots even when nothing changed, such as when no kernel or core library was updated. Register the dnf result and reboot only when needed. `dnf-utils`/`dnf needs-restarting -r` is the usual check on RHEL-family systems.

4. **No drain or health gate.** Nothing takes a host out of rotation (load balancer, scheduler, or hypervisor evacuation if these are virtualization hosts) before the reboot. Nothing checks that services are healthy afterward either. Without a gate, the next batch starts even if the first one came back broken.

5. **No reboot timeout and no post-reboot check.** The default `reboot_timeout` is 600s. Hosts with long firmware or fsck times can exceed that. Add a `test_command` or a `wait_for` on the services you care about.

**Smaller things**

- `state: latest` on `'*'` pulls in every update, including major-version bumps of things like the kernel, container runtime, or database clients. For monthly patching you may want to pin the repo snapshot or use `security: true` so the result is reproducible and staging matches prod.
- Run `--check --diff` first. dnf's check mode is limited, though, so it only shows what would be installed.
- Run it on staging or one canary prod host before the full fleet.
- Take snapshots or confirm backups for stateful nodes.

**A safer shape**

```yaml
- hosts: compute
  become: true
  serial: 1                      # or "10%"
  max_fail_percentage: 0
  tasks:
    - name: drain node
      # your LB/scheduler/evacuation step here
      ansible.builtin.debug: msg="replace with real drain"

    - name: update packages
      ansible.builtin.dnf:
        name: '*'
        state: latest
      register: patch

    - name: check whether reboot is required
      ansible.builtin.command: dnf needs-restarting -r
      register: needs_reboot
      failed_when: needs_reboot.rc not in [0, 1]
      changed_when: false

    - name: reboot
      ansible.builtin.reboot:
        reboot_timeout: 1800
        test_command: systemctl is-system-running --wait
      when: needs_reboot.rc == 1

    - name: health check
      # verify services, then return node to rotation
      ansible.builtin.debug: msg="replace with real health check"
```

I don't know your environment, so the drain and health-check steps are placeholders. What `compute` hosts do (Kubernetes nodes, hypervisors, batch workers) determines what those should be. If you tell me, I can fill them in.