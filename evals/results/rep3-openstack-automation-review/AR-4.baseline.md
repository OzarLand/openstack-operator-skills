The task is mostly right, but I wouldn't run it on prod as written.

**Must fix**

1. **The password is in plaintext in the playbook.** It will end up in git, in logs and in this chat.
   - Move it to an Ansible Vault variable, e.g. `value: "{{ vault_nova_transport_url }}"`.
   - Add `no_log: true` to the task. Without it, `--diff` and failure output print the full URL.
   - If this is the real credential, rotate it, since it has now been pasted outside your secrets store.
2. **All computes restart at once.** If the URL or credentials are wrong, every compute loses its message bus at the same time.
   - Add `serial: 1`, or a small batch such as `serial: [1, 5, 25%]`, to the play.
   - Add `max_fail_percentage: 0` so the run stops on the first failure.
   - Running VMs normally survive a nova-compute restart, but you lose control-plane operations on those hosts until they recover.
3. **The handler runs only at the end of the play, with no check afterwards.** Add a post-restart check, then the next batch only goes ahead if it passes. For example:
   - wait for the service to be active, then
   - run `openstack compute service list --service nova-compute --host {{ inventory_hostname }}` from a control node and confirm it's `up`, or check for an established AMQP connection to `10.0.0.11:5672` or `10.0.0.12:5672`.
   - Use `meta: flush_handlers` so the restart happens inside each batch, before the check.

**Worth checking**

- **Service name.** `openstack-nova-compute` is the RHEL/CentOS name. On Ubuntu/Debian it's `nova-compute`. If the fleet is mixed, the handler will fail on some hosts.
- **Vhost.** The trailing `/` gives the default vhost. Compare against the current value on a compute to confirm it's the same vhost the `nova` user has permissions on.
- **Other copies of the setting.** Check for `transport_url` in `/etc/nova/nova.conf.d/*` or `nova-compute.conf`. A later file can override your change, and the task would report success while nothing changes.
- **Credentials and reachability.** Before the rollout, confirm that the `nova` user exists on both brokers with that password, and that the computes can reach `:5672` on both.
- **File handling.** Add `backup: true` so you can roll back. `ini_file` keeps ownership and mode, so that part is fine.

**Suggested shape**

```yaml
- hosts: compute
  become: true
  serial: [1, 5, "25%"]
  max_fail_percentage: 0
  tasks:
    - name: set transport_url
      community.general.ini_file:
        path: /etc/nova/nova.conf
        section: DEFAULT
        option: transport_url
        value: "{{ vault_nova_transport_url }}"
        backup: true
      no_log: true
      notify: restart nova-compute

    - meta: flush_handlers

    - name: wait for nova-compute to be active
      ansible.builtin.service_facts:
      until: ansible_facts.services['openstack-nova-compute.service'].state == 'running'
      retries: 12
      delay: 5

  handlers:
    - name: restart nova-compute
      ansible.builtin.service:
        name: openstack-nova-compute
        state: restarted
```

I haven't run this, so test the `until` loop on one host first. `service_facts` would also need to be re-run inside the loop to refresh.

**Rollout order**
1. Run `--check` on one host. With `no_log` you won't see the diff, so compare the file by hand.
2. Run `--limit <one compute>` for real and confirm the service is `up`.
3. Run the full play with `serial`.