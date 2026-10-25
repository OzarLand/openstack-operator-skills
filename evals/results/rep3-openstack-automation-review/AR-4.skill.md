## Summary

**Verdict: safe with changes. Don't run it on all computes as written.**

The play sets `transport_url` in `/etc/nova/nova.conf` on every host in `compute`. It lists two RabbitMQ nodes, `10.0.0.11` and `10.0.0.12`. If the file changes, a handler restarts `openstack-nova-compute` on all hosts at once. The edit itself is simple and mostly idempotent. The risks are the credential in the file, the fleet-wide restart, and the lack of any check that the new URL works.

Top risks:
1. The RabbitMQ password is hardcoded in the playbook. I haven't repeated it here (`<redacted>`). It has been exposed in this conversation, so treat it as compromised and consider rotating it.
2. Every compute restarts at once, and a wrong URL takes them all off the message bus together.
3. There are no pre-checks, post-checks or stop conditions.

This is a review of the code you pasted only. I haven't run it, and I haven't seen your inventory, your current `nova.conf`, or your RabbitMQ topology.

## Purpose and whether to automate

The purpose is stated ("fix the RabbitMQ URL") but the cause isn't. I don't know why the URL is wrong, or whether it is wrong on all computes or only some. If the cause is a Kolla or other deployment-tool template that rendered the wrong value, this task will be overwritten at the next reconfigure. That is a workaround turning into accidental architecture. Changing a single config line across a fleet is a reasonable thing to automate, as long as the safeguards below are in place.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Set the value on all `compute` hosts | Execution | Unknown | Fine once the correct value is confirmed |
| Restart nova-compute when the file changes | Execution with impact: RPC to those hosts is interrupted. Running instances normally keep running (verify for your release). | Unknown | Make it serialized and gated |
| Choose which hosts count as "compute" | Depends on the inventory | Unknown | Verify the group contents first |

## Scope and blast radius

- `hosts: compute` is the whole fleet. Nothing limits it with `serial`, `--limit`, or a canary host.
- The handler restarts on every changed host in parallel, up to the `forks` limit. While those hosts are restarting, they can't take new instances, handle operations like live migration, or report in.
- A wrong value (a typo, a wrong port, or credentials RabbitMQ rejects) means nova-compute can't connect on any host. The fleet looks "down" to the control plane at once.
- **Unknown:** whether the `compute` group includes hosts that shouldn't get this value (a different cell, an aggregate on its own RabbitMQ, or the control nodes).

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | Not in the file | Use `--check --diff` first. `ini_file` supports it, but diff output would print the secret unless `no_log` is set. Handlers don't run in check mode. |
| Explicit scope | Partly (`hosts: compute`) | No `serial`, no canary, no check of group contents |
| Confirmation | No | Add a pause before the full rollout |
| Stop conditions | No | Add `max_fail_percentage: 0` or `any_errors_fatal`, plus health asserts between batches |
| Pre-checks | No | Not checked: that the broker nodes are reachable from the computes, that the credentials work, or the current value |
| Post-checks | No | The handler only proves the service restarted. Check that nova-compute reconnects and its service state is `up` in `openstack compute service list`. |
| Idempotency | Mostly | `ini_file` is idempotent. Without `backup: true`, there is no rollback copy of the old file. |
| Concurrency lock | No | Another run or a deployment-tool run could overlap |

## Failure and recovery behaviour

- With no `backup: true`, the old `nova.conf` is gone after the run, and recovery depends on someone remembering the old value.
- Handlers run at the end of the play, only on hosts that changed. If the play fails partway, handlers may not run on hosts that were already changed. Those hosts then have the new config but are still running with the old one until their next restart, and the next restart picks up the new value unexpectedly. Consider `meta: flush_handlers` inside a batched block.
- With a broken URL, a restart of nova-compute leaves the host unable to talk to the bus. There is no automatic rollback.

## Observability

- Nothing records which hosts changed or what the old value was. Run with a log and `--diff`, with the secret masked.
- If `no_log` is missing, the password can appear in Ansible output, AWX/Tower job history, or CI logs.

## Ownership and maintainability

- The URL is hardcoded and duplicated. Move it to a variable and put the secret in Ansible Vault or your secrets manager.
- I don't know who owns this playbook or whether it is in version control.
- If your deployment tool (Kolla-Ansible or similar) manages `nova.conf`, this will conflict with it. Fix the source, for example `/etc/kolla/config/nova.conf` or the templated variable, instead of patching the rendered file.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | Blocking | `value:` line | The password is in plain text in the playbook, and now in this chat. | Rotate it. Use Vault or a variable, and add `no_log: true` to the task. |
| 2 | Blocking | `hosts: compute`, handler | Fleet-wide, parallel restart with no stop condition. | Add `serial: 1` for the first batch (a canary), then a small percentage. Add `max_fail_percentage: 0`. |
| 3 | Major | whole play | No pre-check or post-check. | Before: test TCP to `10.0.0.11:5672` and `10.0.0.12:5672` from each host. After: `meta: flush_handlers`, then wait until the host's nova-compute service is `up` before the next batch. |
| 4 | Major | `ini_file` task | No backup of the old file. | Add `backup: true`. Record the old value first. |
| 5 | Major | `value:` | The URL format needs checking. In `rabbit://` URLs with several hosts, each host usually carries its own `user:pass@host:port`, with a vhost after the final `/`. Yours looks right for that format. Confirm that the user exists on the broker and has permissions on the vhost, and that this is the intended vhost (here `/`). | Test with a known client against each broker node. Verify for your oslo.messaging release. |
| 6 | Major | whole play | Possible conflict with the deployment tool that manages `nova.conf`. | Confirm how `nova.conf` is generated and fix it at the source. |
| 7 | Minor | whole play | No `become` scope, tags, owner or log. | Add a comment naming the owner. Log runs. |
| 8 | Minor | handler | Service name `openstack-nova-compute` is RPM-style. Debian and Ubuntu use `nova-compute`. Containerized deployments restart containers instead. | Check `compute` has a single distribution. |
| 9 | Minor | `section: DEFAULT` | In some releases `transport_url` may belong in `[DEFAULT]` (it does today), and cells may override it. | Check `[DEFAULT]` and any other `transport_url` lines in the file. |

## Suggested shape (a proposal to test in non-production first)

```yaml
- hosts: compute
  become: true
  serial: [1, "10%", "25%"]
  max_fail_percentage: 0
  vars:
    nova_transport_url: "{{ vault_nova_transport_url }}"
  tasks:
    - name: pre-check broker reachability
      ansible.builtin.wait_for:
        host: "{{ item }}"
        port: 5672
        timeout: 5
      loop: ["10.0.0.11", "10.0.0.12"]

    - name: set transport_url
      community.general.ini_file:
        path: /etc/nova/nova.conf
        section: DEFAULT
        option: transport_url
        value: "{{ nova_transport_url }}"
        backup: true
      no_log: true
      notify: restart nova-compute

    - ansible.builtin.meta: flush_handlers

    - name: post-check nova-compute is up (run from a control host, not shown)
      # e.g. delegate_to a controller and assert the service is 'up'
      ansible.builtin.debug:
        msg: "replace with an assert on `openstack compute service list`"

  handlers:
    - name: restart nova-compute
      ansible.builtin.service:
        name: openstack-nova-compute
        state: restarted
```

## Questions for the author

1. Why is the URL wrong now? Was it edited by hand, or does something regenerate it?
2. What manages `nova.conf` (Kolla-Ansible, another deployment tool, or Puppet)? Will it revert this?
3. Is the new value already confirmed to work? Has it been tested on one host?
4. What's in the `compute` group, and are there other cells or aggregates?
5. Has the password been rotated, and who owns the secret?
6. Who approves a fleet-wide nova-compute restart, and is there a maintenance window?
7. What's the rollback if computes can't connect?

Please redact credentials before pasting inventory or configs in future.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.