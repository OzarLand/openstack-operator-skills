## Summary

**Verdict: not safe to run on prod as written. It is safe with changes.** The change itself is small and mechanical, but the task as written has four problems:

- **The credential is exposed.** The RabbitMQ password is in plaintext in the playbook. I've written it as `<redacted>` below. Treat it as exposed, because you pasted it into this session, and rotate it if this playbook is in git or chat history.
- **The restart is unbounded.** The handler restarts `nova-compute` on every host in `compute` at the same moment.
- **There is no preview, no pre-check and no post-check.**
- **The new URL is never verified.** Nothing checks that it is correct before it is rolled out everywhere.

**What it does:** it sets `[DEFAULT] transport_url` in `/etc/nova/nova.conf` on every host in `compute`. If the value differs, it restarts `openstack-nova-compute` on those hosts. The value is a two-node `rabbit://` URL with `nova:<redacted>@10.0.0.11:5672,nova:<redacted>@10.0.0.12:5672/`. I have only seen the task, not the inventory or the current config.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Overwrite `transport_url` | Execution, once the correct value is known | Unknown | Fine, provided the value is verified first |
| Restart nova-compute everywhere | Execution, but with fleet-wide effect | No | Batch it and gate it |
| Which hosts get changed | Implicit, taken from the `compute` group | Unknown | Make the scope explicit and bounded |

## Scope and blast radius

- `hosts: compute` is every compute node. A wrong value plus a simultaneous restart means every compute loses the message bus at once.
- Running instances should keep running, because the libvirt guests are independent of nova-compute. These effects are likely if the URL is wrong (verify for your release):
  - Scheduling and the API lose control of the hosts.
  - Builds, deletes, migrations and snapshots fail.
  - Hosts show as down, and any auto-evacuation tooling you have could then fire.
- If the `compute` group is empty or wrong, Ansible silently does nothing or hits the wrong hosts. That is an assumption I can't check.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | `--check --diff` works with `ini_file`, but you have to run it. |
| Explicit scope | Partly (`hosts: compute`) | There is no `serial` and no canary host. |
| Confirmation | No | No `pause` and no approval step. |
| Stop conditions | No | No `max_fail_percentage` or `any_errors_fatal`. |
| Pre-checks | No | Nothing checks that the old URL works, that RabbitMQ is reachable, or that the credential is valid. |
| Post-checks | No | Nothing checks that the service came up and reconnected. A successful restart does not mean the host is usable. |
| Idempotency | Yes | `ini_file` only reports a change when the value differs. |
| Backup | No | `backup: true` is missing, so the old value is not preserved. |
| Secret handling | No | No `no_log`, and the secret sits in the playbook. |

## Failure and recovery

- **Handler timing:** handlers run at the end of the play. A failure on one host can leave some hosts with the new config and some with the old, and Ansible may skip handlers on failed hosts. Use `meta: flush_handlers` inside the batch. Verify the behaviour in your Ansible version.
- **Rollback:** there is no recovery path as written. Without `backup: true` you are reconstructing the old URL from memory.
- **Mixed state:** a half-applied run leaves a mixed fleet, but a re-run is safe because the task is idempotent.

## Observability

Nothing records which hosts changed or which were restarted. Capture `--diff` output with the secret masked, and save the run log. Define in advance how you will see each compute reconnect.

## Ownership and maintainability

Editing `nova.conf` directly may be overwritten by your deployment tooling (Kolla-Ansible, Puppet, or similar) at the next run. If so, the fix will quietly revert, or it will start a config fight. Fix the source of truth as well. Also confirm who owns this playbook and where it is kept.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | Blocking | `ini_file` value | The plaintext credential is in the playbook. | Use Ansible Vault or a secrets lookup, add `no_log: true`, and rotate if it has been shared. |
| 2 | Blocking | play and handler | There is no `serial` and no stop condition. A wrong URL restarts and breaks every compute together. | Add `serial: 1` for a canary host, then small batches. Add `max_fail_percentage: 0` or `any_errors_fatal`. |
| 3 | Major | whole play | No post-check. | After `flush_handlers`, assert the service is active and that nova reports the compute `up` before the next batch. Check the capability, not the exit code. |
| 4 | Major | task | No backup and no recorded old value. | Add `backup: true` and record the old URL out of band. |
| 5 | Major | value | The URL is unverified, and it has no `?ssl=` or vhost handling. | Confirm it against a known-good compute and the RabbitMQ cluster. Check that both nodes belong to the same cluster, the vhost `/` is intended, the user's permissions exist, and TLS settings match. |
| 6 | Major | whole play | Source of truth. | Check whether Kolla or other config management also owns this file. |
| 7 | Minor | handler | The service name `openstack-nova-compute` is distro-specific. | Confirm it on every host in the group, including mixed OS. |
| 8 | Minor | play | No pre-flight check on the old state. | Add a read-only task that reports the current value and the service state. |

## Suggested shape (proposal, test outside prod first)

```yaml
- hosts: compute
  become: true
  serial: 1            # canary first; raise to a small batch after it passes
  max_fail_percentage: 0
  vars_files: [vault.yml]   # holds nova_transport_url, encrypted
  tasks:
    - name: set transport_url
      community.general.ini_file:
        path: /etc/nova/nova.conf
        section: DEFAULT
        option: transport_url
        value: "{{ nova_transport_url }}"
        backup: true
      no_log: true
      notify: restart nova-compute

    - meta: flush_handlers

    - name: confirm service is active
      ansible.builtin.service_facts:
    - ansible.builtin.assert:
        that: ansible_facts.services['openstack-nova-compute.service'].state == 'running'
    # plus a check from a controller that this compute is `up` in the service list
  handlers:
    - name: restart nova-compute
      ansible.builtin.service:
        name: openstack-nova-compute
        state: restarted
```

## Order of work (what to do before prod)

1. **Read-only:** record the current `transport_url` on a few computes. Check that it is consistent and that `10.0.0.11` and `10.0.0.12` are both healthy RabbitMQ nodes.
2. **Read-only:** run `--check --diff` on one host. Mask the secret.
3. **State-changing:** run on a canary with `--limit`, then check that it shows `up` and handles a test operation.
4. **State-changing:** roll out in small batches, stopping on any failure.
5. **Approval:** the accountable owner of the compute fleet signs off on the window and the stop conditions. Do not run during an unrelated incident.

## Questions for the author

- Why does the URL need fixing? What is wrong with the current one: a node moved, a password changed, or a mismatch between hosts? If it is a symptom of a bigger RabbitMQ issue, that needs investigating first.
- Do all computes have the same OS and service name?
- Is `nova.conf` managed by something else?
- Is there a maintenance window, and who is on call for it?
- Is auto-evacuation or any fencing tooling enabled that would react to computes going down?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.