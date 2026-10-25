## Summary

**Verdict: not safe — redesign.** I would not put this in cron as written. Wanting to avoid night pages is reasonable, but this script hands a judgement to a heartbeat. It also has no fencing, no limits and no error handling, and it runs every minute.

**What it does (observed in the code):** every minute it lists `nova-compute` services that are `down` and `enabled`. For each one it evacuates every instance of every project on that host, then disables the service. This review covers the code only. I haven't seen your storage backend, your fencing setup or your `service_down_time`, so I list those as gaps below.

**Top risks:**
1. **No fencing (Blocking).** A missed heartbeat doesn't mean the host is dead. If the host is alive but isolated, evacuation starts a second copy of each VM while the original is still running. With shared storage such as Ceph or NFS, both copies can write to the same disk and corrupt it.
2. **Wrong-cause mass evacuation (Blocking).** The `down` state is nova-compute's heartbeat arriving through RabbitMQ and the database. A RabbitMQ partition, a DB problem or a network fault near the controller can make many or all computes look down at once. This script would then try to evacuate the whole cloud, and during a control-plane incident that is the worst time for it.
3. **Unbounded scope, no stop condition (Blocking).** Nothing limits how many hosts or instances one run touches, and there is no check that spare capacity exists.
4. **Retry loop with no error handling (Major).** One exception stops the run before `disable_service`. The next run, a minute later, repeats the same work.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| "This host is dead" | Judgement (uncertain diagnosis) | Not shown | Needs fencing as proof, or a human |
| Evacuate all tenants' VMs | Judgement (disrupts workloads) | Not shown | Gate on fencing, capacity and a named owner's approval |
| Disable the service | Execution | n/a | Do it first, not last |
| Run again 60 seconds later | Judgement (no stop rule) | Not shown | Add lock, rate limit and circuit breaker |

## Scope and blast radius

- The scope is every `nova-compute` host and every project, with `all_projects=True`. That is the widest possible, and nothing limits it.
- An empty or wrong result is not handled. If the API returns a misleading service list during an incident, the script acts on it.
- The loop runs hosts and instances one after another with no batching and no check on the failure domain.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | Add a mode that prints what it would evacuate |
| Explicit scope | No (implicit "all") | Add a per-run host cap and an allowlist or exclude list |
| Confirmation | No | Needs a human go, or an explicit written delegation |
| Monitoring | No | No log and no notification |
| Stop conditions | No | Stop if more than N hosts or more than X% of computes look down |
| Pre-checks | Partial: only `state` and `status` | Check the host is fenced, check spare capacity, check RabbitMQ and DB health, check the instance state |
| Post-checks | No | Verify instances reach ACTIVE and are reachable, not just that the API call returned |
| Idempotency | Weak | Evacuation is asynchronous. The next minute the instances may still show the old host, so the script sends duplicate requests. Nova may answer 409, which is an unhandled exception here. |
| Concurrency lock | No | A run longer than 60 seconds overlaps with the next one. Use `flock`. |

## Failure and recovery behaviour

- **Disable happens last.** Between detecting the failure and `disable_service`, the scheduler can still place new VMs on the dead host.
- **No `try/except`.** One bad instance stops the loop, so later instances are not evacuated and the host is not disabled. Next minute it repeats.
- **Instance types are not considered.** Servers in SHUTOFF or ERROR are evacuated and rebuilt too. Instances on local disk are rebuilt from the image, so their ephemeral data is lost. Volume-backed instances may survive. GPU, PCI passthrough and pinned instances may have no valid target. Check all of this for your release and backend.
- **Rollback is unclear.** After a wrong evacuation, the original host's copies are cleaned up when nova-compute restarts, and that cleanup is destructive. Whether data is recoverable depends on the storage backend, which I don't know.
- **Version check (verify against your openstacksdk version).** `evacuate_server` and `disable_service` signatures have changed between SDK releases, so confirm the call works as intended. Also check what `evacuate_server` does when you pass no target host.

## Observability

The script gives no record of when it ran, what it evacuated or why. Cron mail is the only trace, and only if it is configured. There is no alert to a human and no switch to stop it quickly other than editing cron. The credentials in `clouds.yaml` for `prod` are admin-level and sit on the controller, so protect that file and its cron environment.

## Ownership and maintainability

I don't know the owner, where the code lives, or how it was tested. An auto-evacuation script that only its author can explain is control debt. Nobody woken at night by the side effects will know what it did. It is also a workaround for something: a bad network, flaky hardware or a lack of fencing. Repeating the workaround automatically hides that cause.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | Blocking | line 4 | Evacuates on `state == 'down'` without fencing | Fence first (IPMI/BMC power-off or switch isolation) and require it succeeded. Then mark the service forced-down in Nova and evacuate. |
| 2 | Blocking | lines 3–4 | No cap and no circuit breaker. A control-plane fault can trigger evacuation of every host | Abort and page if more than 1 host (or a set % of hosts) is down at once. Handle one host per run. |
| 3 | Blocking | line 5 | `all_projects=True` and no capacity or instance-type check | Check capacity in the target aggregate first. Exclude instance types you can't safely rebuild. |
| 4 | Major | lines 3–7 | No error handling. One failure aborts the run, and the next run repeats it | Wrap each action, log errors and stop on the first unexpected one. |
| 5 | Major | line 7 | Disable comes after evacuation, so scheduling can still reach the host | Disable first with a `disabled_reason`, then evacuate. |
| 6 | Major | cron | Runs every minute with no lock. Evacuations are async and runs will overlap | `flock`, state file recording hosts already handled, and a minimum wait before acting. |
| 7 | Major | whole | No dry run, no log, no notification | Add `--dry-run` as the default and require an explicit flag for live runs. Log to a file and send a message on every action. |
| 8 | Minor | whole | No owner, tests or docs | Name an owner, put it in version control, test it on a lab cloud with fenced hosts. |

## Better design: semi-automate

The goal is "don't wake me for a dead host." That is achievable without delegating the judgement blindly.

1. **Detect and collect evidence automatically.** Script a read-only check: which service is down, is the BMC reachable, is RabbitMQ and the DB healthy, how many hosts are down, and what instances and capacity are involved. Send that to the on-call person with a proposed action.
2. **Allow full automation only under written delegation.** If the owner explicitly accepts the risk, auto-evacuate only when all of these hold: exactly one host is down, other hosts and messaging are healthy, fencing succeeded, spare capacity exists, and the daily evacuation count is under a limit. Anything outside those conditions pages a human.
3. **Add controls to the above.** Dry-run default, `flock`, a kill switch (for example a file that disables it), logging, and verification that instances come back ACTIVE and respond.
4. **Think about what may stay manual.** If the hosts don't have fencing today, the main step is adding it. Without fencing, a human decision at night is safer than this script.

## Questions for the author

- What failure is this designed for (power loss, kernel panic, network)? How often does it happen?
- Is instance storage shared (Ceph, NFS) or local? Are volume-backed instances common?
- Is there out-of-band fencing available (BMC/IPMI, switch control)? Is it tested?
- What is `service_down_time`, and has a RabbitMQ or DB outage ever made several computes look down together?
- Who is the named owner who accepts the risk of automatic evacuation, and has anyone approved it?
- Which tenants and instance types (GPU, SR-IOV, pinned, large memory) run in the cloud?
- Has this run in a lab with a real host failure?

I did not run this or contact your cloud. These are findings from reading the code.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.