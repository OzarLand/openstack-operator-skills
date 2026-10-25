## Summary

**Verdict: not safe to run on prod as written. It's safe with changes.** The intent is fine, since this is a mechanical config fix. But the playbook has a blocking secret-handling problem and no limit on how many computes it touches or restarts at once.

**What it does (as I read it):** On every host in the `compute` group, it sets `[DEFAULT] transport_url` in `/etc/nova/nova.conf` to a two-node RabbitMQ URL. If the file changed, it restarts `openstack-nova-compute` on that host. Nothing in the playbook limits how many hosts are handled at the same time.

**Top risks:**
1. The RabbitMQ password is in plaintext in the playbook. It also appears in my copy of the paste. Treat it as exposed and plan to rotate it.
2. The handler restarts nova-compute on all computes at once. If the new URL is wrong, every compute loses its message bus together.
3. There are no pre-checks, post-checks or stop conditions, and no way to preview the change.

## Purpose and whether to automate

Setting a single option on many hosts is predictable work, so automating it is reasonable. Two things aren't established from what you showed me:
- **Reported:** you say it "fixes" the URL. I don't know what is wrong with the current value. Is it a wrong host, a wrong password, or a missing second broker? The fix should match the real cause.
- **Assumption:** the `compute` group contains only compute nodes that should have this value, and all of them use the same RabbitMQ cluster and the same `nova` credentials.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Overwrite transport_url everywhere | Execution | Yes, by running it | Fine once the target value is verified |
| Restart nova-compute whenever the file changes | Execution | Implicit | Needs batching and a health gate |
| Which hosts are in scope | Judgement, delegated to the inventory | Unknown | Make the scope explicit |

## Scope and blast radius

- `hosts: compute` is every compute, with no `serial`, `--limit` or `max_fail_percentage` (play header, line 1).
- If the URL is wrong, all computes lose RPC at the same time. Running instances usually keep running, but you lose control of them: no start, stop, migrate or build, and the scheduler sees the hosts as down.
- Instances on these hosts would also stop sending power-state and resource updates. That makes any auto-evacuation or monitoring tied to service state unreliable. Whether you have any is unknown.
- **Unknown:** the number of computes, whether they span multiple failure domains, and whether a bad restart would hit workloads that can't tolerate control-plane loss.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | Partly. `ini_file` supports `--check --diff`. | Run it. The diff will print the secret unless `no_log` or masking is used. |
| Explicit scope | No (`hosts: compute`) | Add `--limit` for a canary, then a staged rollout. |
| Batching | No | Add `serial` (1, then 10%, and so on). |
| Stop conditions | No | Add `max_fail_percentage: 0` or `any_errors_fatal`. |
| Pre-checks | No | Check that the brokers answer on 5672 and that the credentials work. |
| Post-checks | No | The handler only restarts the service. It doesn't check that the service came back and rejoined. |
| Idempotency | Yes, `ini_file` only changes the file when the value differs. | Fine. |
| Backup | No | Add `backup: true`, which keeps a timestamped copy. |
| Secret hygiene | No | See Finding 1. |

## Failure and recovery behaviour

- **Ordering:** Handlers run at the end of the play, after all tasks on a host. Without `serial`, the config change and the restart both go out to all hosts together.
- **Restart without verification:** A wrong URL is only visible after the restart. The service will start, fail to connect to RabbitMQ and sit there. `state: restarted` reports success anyway.
- **Rollback:** Nothing is kept, so you would need to know the old value from somewhere else. `backup: true` fixes that.
- **Interruption:** If the run dies midway, hosts are split between the old and new URL. A re-run is safe because the task is idempotent. A host whose config changed but whose restart never happened keeps running on the old value until the next restart. Re-running won't trigger the handler for it, because the file already matches.
- **Possible mismatch:** `/etc/nova/nova.conf` is edited directly. If this platform is deployed with Kolla-Ansible or similar, the next reconfigure or deploy could overwrite this change. That would reintroduce the old value at an unexpected time. Which tool manages the file is unknown, so please confirm.

## Observability

- No record of which hosts changed, apart from the Ansible output.
- The unmasked task output and diff will show the password in terminal logs, CI logs or AWX job history.
- After the run, you want proof that the service reconnected, not just that the service restarted.

## Ownership and maintainability

- The password sits in a playbook, so it is probably in version control now, and it will be copied wherever the playbook goes.
- A hard-coded value in a task becomes a second source of truth next to the deployment tool's configuration. That is the start of accidental architecture.
- Unknown: who owns this, who approved it, and whether it is tested anywhere other than prod.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | **Blocking** | `value:` line | Plaintext RabbitMQ credentials (`<redacted>`) are in the playbook, in the diff output and in the logs. **Treat the password as exposed and consider rotating it.** | Move the URL into Ansible Vault or your secrets store. Pass it as a variable and add `no_log: true` to the task. If you rotate the password, coordinate it with the broker change. |
| 2 | **Blocking** | play header and handler | All computes are changed and restarted at once, with no stop condition. | Add `serial: [1, "10%", "25%"]`, `max_fail_percentage: 0` and a canary run via `--limit` first. |
| 3 | **Major** | handler | There is no check that the service recovered. | After the restart, wait until the service reports up, for example by checking `openstack compute service list` for that host from a control node. Use `ansible.builtin.assert` so a failure stops the batch. |
| 4 | **Major** | task | There is no backup, so rollback depends on knowing the old value. | Add `backup: true`, and record the current values before you start (read-only `grep transport_url`). |
| 5 | **Major** | task | The new value is not verified before it is written. | Add a pre-check that tests the broker ports (`wait_for`) and that the user can authenticate. Also decide whether it needs `/` as a vhost (the trailing `/` in the URL is the default vhost). Confirm that is the vhost nova uses. |
| 6 | **Major** | task | `/etc/nova/nova.conf` may be managed by another deployment tool. | Confirm the config source. If Kolla or another tool manages it, change the value there instead, or this fix gets reverted. |
| 7 | **Minor** | task | `ini_file` with a non-`[DEFAULT]` section could matter. In recent releases `transport_url` may be in `[DEFAULT]`, but check your release. | Verify against your release's docs and your current file. |
| 8 | **Minor** | whole file | No owner, no tests, no run log. | Record the owner and run it in a test environment first. |

## Questions for the author

1. What is wrong with the current `transport_url`, and how do you know the new value is right? Please paste the old value, redacted.
2. How many computes are in the `compute` group, and are they split across AZs or aggregates?
3. Is nova.conf managed by Kolla-Ansible, TripleO or another tool?
4. Is the user `nova` the right RabbitMQ user for computes, and is `/` the right vhost?
5. Does the playbook need the second broker listed because of a cluster change, or is this a one-off correction?
6. Is there an auto-evacuation or fencing system that reacts to compute service state while this runs?
7. Who approves this change, and what's the rollback trigger?

## Suggested shape (to test outside prod first)

```yaml
- hosts: compute
  become: true
  serial: [1, "10%", "25%"]
  max_fail_percentage: 0
  vars:
    nova_transport_url: "{{ vault_nova_transport_url }}"
  tasks:
    - name: pre-check brokers reachable
      ansible.builtin.wait_for: { host: "{{ item }}", port: 5672, timeout: 5 }
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

    # post-check: confirm this host's compute service is up again,
    # e.g. delegate_to a control node and assert on the service list
  handlers:
    - name: restart nova-compute
      ansible.builtin.service:
        name: openstack-nova-compute
        state: restarted
```

I haven't run this or any check mode. It is a design proposal, and the post-check is left as a stub for your environment.

**Suggested run order:** (1) rotate or secure the credential, (2) `--check --diff` with masking on one host, (3) canary on one non-critical compute, (4) verify the service is up and RPC works, (5) staged rollout.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.