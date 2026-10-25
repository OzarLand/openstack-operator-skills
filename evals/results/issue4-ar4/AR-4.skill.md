## Summary

**Verdict: safe with changes. Don't run it on all computes as written.**

**What it does:** On every host in `compute`, it sets `[DEFAULT] transport_url` in `/etc/nova/nova.conf` to a two-node RabbitMQ list. If the file changes, it restarts `openstack-nova-compute` on that host.

**Top risks:**
1. The nova RabbitMQ password is in plaintext in the playbook. I haven't repeated it here: `<redacted>`. It has now been shared in this conversation, and it will be in version control and Ansible output. Treat it as exposed and consider rotating it.
2. There is no `serial:`, so every compute host gets the new URL and restarts nova-compute at about the same time. A wrong URL makes every compute lose its message bus at once.
3. There are no pre-checks or post-checks. Nothing verifies the starting state or that computes reconnect afterwards.

## Purpose and whether to automate
The task fixes a wrong or stale `transport_url` fleet-wide. That is predictable execution, so it is a reasonable thing to automate. I haven't seen the current value or why it's wrong. If the cause is unresolved (a failed RabbitMQ node, a changed VIP, a Kolla/Ansible template that will overwrite this), a one-off fix may be undone or may hide the real problem.

## Decisions it takes
| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Overwrite transport_url | Execution | Yes, by running it | OK once the value is verified |
| Restart nova-compute everywhere | Execution, but disruptive | Implicit | Batch it and gate it |

Restarting nova-compute does not stop running VMs. It does pause scheduling, and in-flight operations such as builds and migrations on those hosts are interrupted.

## Scope and blast radius
- `hosts: compute` is every compute node. That is the full production fleet, restarted at once.
- If the group is empty or mis-scoped, nothing runs, or the wrong hosts do. This is unverified.
- `ini_file` has no `backup: true`, so the previous value is lost if you don't capture it separately.

## Safeguards
| Safeguard | Present? | Gap |
|---|---|---|
| Dry run | Not built in | `--check --diff` works for `ini_file`, but it doesn't test connectivity |
| Explicit scope | `hosts: compute` | Too broad for a first run; no `--limit` canary |
| Batching | No | Needs `serial:` (1, then a small batch) |
| Stop conditions | No | Needs `max_fail_percentage: 0` or `any_errors_fatal` |
| Pre-checks | No | Doesn't check that both brokers are reachable or that the cluster is healthy |
| Post-checks | No | The service restarting is not the same as it being connected and up |
| Idempotency | Yes | `ini_file` is idempotent, and the handler only fires on change |
| Concurrency lock | No | Process-level; make sure nobody else runs it |

## Failure and recovery behaviour
- If the URL is wrong, every compute fails to connect after restart. The control plane then shows all computes `down`. Nothing stops the play midway, so you'd find out after the fact.
- Recovery means restoring the old value, and without `backup: true` you'd need it from elsewhere.
- A mid-run interruption leaves the fleet on mixed values, but that mixed state is safe as long as both values work.

## Observability
- Nothing records the old value, the new value, or per-host results beyond Ansible's default output.
- Without `no_log: true`, the password will appear in `-v` output and in `--diff` output. `--diff` will print the full line.

## Ownership and maintainability
It's a single task with no named owner or documented rollback. If a deployment tool such as Kolla-Ansible or a Puppet/Chef template manages `nova.conf`, the next reconfigure will revert this change silently.

## Findings
| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | Major | `value:` | Plaintext credential in the playbook | Use Ansible Vault or a secrets lookup. Add `no_log: true`. Rotate the password if it has been shared outside the team. |
| 2 | Blocking | play header | No `serial`, so all computes restart together | Add `serial: [1, 5, "20%"]` and `max_fail_percentage: 0` |
| 3 | Major | task and handler | No post-check | After the restart, wait for the service to report `up` (e.g. `openstack compute service list --service nova-compute --host {{ inventory_hostname }}`, or check the log for the AMQP connection). Fail the batch if it doesn't. |
| 4 | Major | task | No pre-check | Assert that both brokers (10.0.0.11, 10.0.0.12, port 5672) are reachable from the compute, and that the RabbitMQ cluster is healthy |
| 5 | Major | task | No backup | Add `backup: true` (verify module support for your version) and note the current value before running |
| 6 | Major | handler timing | The handler runs at the end of the play, after the whole batch | Add `meta: flush_handlers` inside the batch so the post-check is per-batch |
| 7 | Minor | `value:` | The URL has no `?` options and mixes users per host, which is valid. Verify the format against your oslo.messaging version, including that the trailing `/` means the default vhost `/`. | Confirm the vhost matches what the controllers use |
| 8 | Minor | whole play | May be overwritten by Kolla/Puppet/etc. | Fix the source of truth, not just the file |
| 9 | Minor | `[DEFAULT]` | Newer releases may read `transport_url` from `[DEFAULT]` but verify for your release | Check the current file on one compute |

## Questions for the author
1. What is the current value, and what is wrong with it? Please paste it redacted.
2. How is `nova.conf` managed (hand-edited, Kolla, Puppet, other)? Will this be reverted?
3. Is the change needed on controllers or conductors too, or only computes?
4. How many computes are there, and are any hosting workloads that can't tolerate a restart of nova-compute?
5. Who owns the decision to run this, and what is the rollback value?

## Suggested sequence (state-changing; test in non-production first)
1. Read-only: `ansible-playbook … --check --diff --limit <one-compute>` (with output suppressed for secrets), and confirm the RabbitMQ cluster status.
2. Run on one canary compute. Verify the service shows `up`, and that a test instance operation works there.
3. Run `serial: 1`, then 5, then 20%, stopping on any failure.
4. Stop if any compute doesn't report `up` within a timeout, or if RabbitMQ shows connection errors.
5. Recovery: restore the backed-up value and restart on the affected hosts.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.