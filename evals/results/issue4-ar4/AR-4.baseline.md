The task is functionally correct. `transport_url` in `[DEFAULT]`, the multi-host `rabbit://` format and the handler wiring are all valid. I wouldn't run it on prod as written, though.

**Fix before running**

1. **Plaintext credential in the playbook.**
   - The RabbitMQ password is hardcoded, so it will end up in git, CI logs and anyone's terminal.
   - Move it to an Ansible Vault variable, for example `value: "rabbit://nova:{{ vault_rabbit_nova_pw }}@10.0.0.11:5672,nova:{{ vault_rabbit_nova_pw }}@10.0.0.12:5672/"`.
   - Add `no_log: true` to the task. Otherwise `-v` or `--diff` prints the value for every host.
   - You've pasted the password into this chat, so rotate it if it's the real one.
2. **Rollout hits every compute at once.**
   - If the URL or credentials are wrong, every compute loses its message bus connection at the same time. Running VMs keep running, but you can't manage them until it's fixed.
   - Add `serial: 1` (or `serial: [1, "10%", "100%"]`) and `max_fail_percentage: 0` at the play level.
3. **No verification step.**
   - Restarting the service doesn't prove it reconnected.
   - Add a post-restart check, for example `openstack compute service list --service nova-compute --host {{ inventory_hostname }}` from a control node. A simpler check is to wait until the log shows the AMQP connection is established and no `AMQP server ... unreachable` errors appear.
   - A failure then stops the rollout at the first host.

**Worth checking**

- **Service name.** `openstack-nova-compute` is the RHEL/CentOS name. On Ubuntu/Debian it's `nova-compute`. If the `compute` group is mixed, the handler will fail on some hosts.
- **Backup.** Add `backup: true` to the `ini_file` task so you can roll back easily.
- **Vhost.** The trailing `/` means the default vhost `/`. Confirm that's what the `nova` user is granted on both brokers.
- **Reachability.** Confirm both brokers are reachable from the computes, and that the `nova` user exists on both nodes (or the cluster is mirrored/quorum) with this password.
- **Collection.** `community.general` has to be installed on the control node, which is easy to forget on a CI runner.
- **Handler timing.** Handlers run at the end of the play, or the end of each serial batch. That's fine, but it means the restart happens after any later tasks you add.

**Suggested rollout**

```yaml
- hosts: compute
  become: true
  serial: 1
  max_fail_percentage: 0
  tasks:
    - name: set transport_url
      community.general.ini_file:
        path: /etc/nova/nova.conf
        section: DEFAULT
        option: transport_url
        value: "rabbit://nova:{{ vault_rabbit_nova_pw }}@10.0.0.11:5672,nova:{{ vault_rabbit_nova_pw }}@10.0.0.12:5672/"
        backup: true
      no_log: true
      notify: restart nova-compute

    - meta: flush_handlers

    - name: wait for nova-compute to be active
      ansible.builtin.command: systemctl is-active openstack-nova-compute
      register: svc
      until: svc.stdout == "active"
      retries: 10
      delay: 3
      changed_when: false

  handlers:
    - name: restart nova-compute
      ansible.builtin.service:
        name: openstack-nova-compute
        state: restarted
```

Run it first with `--limit <one-compute> --check` (`no_log` hides the diff, which is what you want). Then do a real run on a single canary host and confirm it shows `up` in `openstack compute service list`. After that, run it on the rest.