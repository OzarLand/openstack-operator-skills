**Verdict:** the URL format is correct, but I wouldn't run this on prod as written. Here is what I'd fix, most important first.

**1. The password is in plaintext and will be logged.**
- The credential sits in the playbook, so it will end up in git.
- `ini_file` also prints the value in task output and in `--diff`. With `no_log`, the diff is hidden too.
- Move the password to Ansible Vault and add `no_log: true`.
- You've pasted it into this chat, so if it's the real password, rotate it after the change.

**2. Every compute restarts at once.**
- If the new URL is wrong, `nova-compute` goes down on the whole fleet at the same time.
- Use `serial` (one host, then 10%, then the rest) and `max_fail_percentage: 0` so the run stops at the first failure.
- Restarting `nova-compute` doesn't kill running instances, but you lose the control plane for them while it's down.

**3. The service name is distro-specific.**
- `openstack-nova-compute` is the RHEL/CentOS name. On Debian/Ubuntu it's `nova-compute`.
- If `compute` is a mixed group, the handler fails on the other family, and only after the config has already changed.

**4. No backup, no pre-check, no post-check.**
- Add `backup: yes` so you can roll back.
- Add a `wait_for` on 10.0.0.11:5672 and 10.0.0.12:5672 from each compute before changing anything.
- After the restart, confirm the service reconnects, for example by checking `openstack compute service list` for `up` or grepping the log for "Connected to AMQP". A `meta: flush_handlers` followed by that check, inside the serial batch, makes the rollout self-gating.

**5. Smaller points to confirm.**
- **Vhost:** the trailing `/` means the default vhost. If your current URL uses a different vhost, this overwrites it.
- **Escaping:** the password is alphanumeric, so it's fine. Special characters would need URL-encoding.
- **Other config sources:** make sure nothing else sets `transport_url`, such as a `nova.conf.d/*.conf` drop-in or a Kolla/TripleO/Puppet template. Those will either override this or revert it on the next run.
- **Rabbit user:** check that the `nova` user exists with permissions on both rabbit nodes.

**Suggested revision**

```yaml
- hosts: compute
  become: true
  serial: [1, "10%", "100%"]
  max_fail_percentage: 0
  vars:
    nova_service: "{{ 'openstack-nova-compute' if ansible_os_family == 'RedHat' else 'nova-compute' }}"
    rabbit_hosts: ["10.0.0.11", "10.0.0.12"]
  tasks:
    - name: rabbit reachable from this host
      ansible.builtin.wait_for:
        host: "{{ item }}"
        port: 5672
        timeout: 5
      loop: "{{ rabbit_hosts }}"

    - name: set transport_url
      community.general.ini_file:
        path: /etc/nova/nova.conf
        section: DEFAULT
        option: transport_url
        value: "rabbit://{{ rabbit_hosts | map('regex_replace', '^(.*)$', 'nova:' ~ vault_nova_rabbit_pass ~ '@\\1:5672') | join(',') }}/"
        backup: yes
      no_log: true
      notify: restart nova-compute

    - ansible.builtin.meta: flush_handlers

    - name: nova-compute is running
      ansible.builtin.service_facts:
    - ansible.builtin.assert:
        that: ansible_facts.services[nova_service + '.service'].state == 'running'

  handlers:
    - name: restart nova-compute
      ansible.builtin.service:
        name: "{{ nova_service }}"
        state: restarted
```

I haven't run this. The `regex_replace` line is a bit clever, so you could write the URL out with two vaulted variables instead.

**Rollout**
1. Run `--check` on one host. The diff is suppressed by `no_log`, so check the result manually.
2. Run `--limit <one compute>`, then confirm in `openstack compute service list` and the nova-compute log that it's `up` and connected.
3. Run the full group.

I can also write the vault setup or an inventory-based version if you want.