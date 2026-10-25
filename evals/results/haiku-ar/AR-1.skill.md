## Summary

**Verdict: not safe. Redesign before it runs unattended.**

As written, the script evacuates every server off any compute host whose `nova-compute` service reports `down`, then disables that host. It does this every minute, with no fencing, no limit on how many hosts it will act on, no dry run, no lock, and no log. The signal it acts on (`state == 'down'`) only means the Nova API has not heard a heartbeat from that service recently. It does not show that the host is dead, and evacuation depends on exactly that.

The likely bad outcomes at 3am are:
- **Duplicated running VMs** on shared storage: the original host is still running guests after its `nova-compute` agent or its messaging path failed, and the evacuated copy starts elsewhere.
- **Mass evacuation** triggered by a controller or RabbitMQ blip that makes many computes miss heartbeats at once.
- **Data loss** for instances whose disks are local to the host.

Your goal is right, but this script buys the sleep by taking the most consequential action in the stack without a judgement step.

**Evidence basis:** Observed: the pasted snippet only (9 lines, no file name or context). Assumption: Nova and openstacksdk behave as I describe below. I have not run this or checked it against your release, so verify the points marked "verify" before relying on them.

## Purpose and whether to automate

- **Problem:** restore VM service when a compute host fails outside business hours. This is a valid goal.
- **Is the problem understood?** Not yet. Nothing in the script establishes why the service is down, whether the host is alive, or whether its guests are still running.
- **Should the action be automated now?** Detection and notification can be automated safely. Evacuation can only be automated after host failure is confirmed by something independent of the Nova heartbeat, which in practice means fencing. Until then, this is a semi-automation case: the script should detect, gather evidence and page, and an engineer should decide.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Treat `state == 'down'` as "host is dead" | Judgement, from one signal that can be wrong | No | Require independent confirmation (fencing or power state) |
| Evacuate every server on the host | Judgement: disruptive, moves tenant workloads | No | Human decision, or opt-in per server |
| Include stopped, ERROR, non-HA, or special-hardware servers | Judgement | No | Exclude by policy, not by default |
| Choose target host | Execution (scheduler) | n/a | Acceptable, but check capacity first |
| Disable the compute service | Execution, but only meaningful after evacuation is verified | n/a | Only after verified evacuation, or by a human |

## Scope and blast radius

- **Target selection is implicit "all":** `conn.compute.services(binary='nova-compute')` (line 3) returns every compute host, and the loop acts on any that match. There is no count guard, so one bad heartbeat window on many hosts evacuates the cloud.
- **Servers included without filter:** `servers(all_projects=True, host=svc.host)` (line 5) returns all servers, regardless of status, HA policy, storage type, or whether a migration is already in flight.
- **Scale:** one mistake repeats every minute until someone stops the cron job.

## Safeguards

| Safeguard | Present? (evidence) | Gap |
|---|---|---|
| Preview / dry run | No | No flag to print the planned actions |
| Explicit scope | No (line 3, line 5) | Implicit all computes and all projects |
| Confirmation | No | Nothing requires a human go for a disruptive action |
| Monitoring | No | No logging, no output, no alert |
| Stop conditions | No | No threshold on hosts down, servers affected, or failures |
| Pre-checks | Partial: line 4 checks `state` and `status` only | No duration check, no re-check of the host, no fencing, no capacity check |
| Post-checks | No | Evacuation is asynchronous; success is never verified (server ACTIVE on new host) |
| Idempotency | Partial: `disabled` status acts as an implicit marker (line 4), but it is only set if no exception occurs (line 7) | Re-runs repeat evacuations on the same servers |
| Concurrency lock | No | Cron starts a new run every minute even if the last one is still going |
| Fencing (precondition for evacuation) | No | Central gap; see finding 1 |

## Failure and recovery behaviour

- **Exception in the inner loop:** an error from `evacuate_server` (for example a 409 conflict or no valid host) aborts the run. `disable_service` is skipped, the host stays `enabled`, and the next minute repeats the attempt on servers that are still on the host. Servers already evacuated may be re-targeted.
- **Asynchronous evacuation:** `evacuate_server` returns once Nova accepts the request, not when the server is running elsewhere. Servers still show the old host for a while, so the next run may call evacuate again on them. Verify the exact behaviour (task_state checks and conflict responses) for your Nova release.
- **Recovery path:** none. There is no record of which servers moved where, and no way to roll back. Re-enabling the host and any evacuated servers is manual.
- **Errors are swallowed or only visible in cron mail:** no try/except, no log, no structured output.

## Observability

- Cron output is the only record, and it may go to a mailbox nobody reads or to `/dev/null`.
- Nothing records what it changed (which servers, from which host, to which host).
- No way to see that it is currently running, or to stop it quickly other than editing the crontab.

## Ownership and maintainability

- The script has no owner, documentation, tests, or version pin for openstacksdk. The `disable_service(svc, svc.host, 'nova-compute')` call relies on positional arguments; verify the signature for the installed SDK version.
- It runs as the `prod` cloud, which means admin credentials in `clouds.yaml` on a controller, used unattended. A bug in this script has full admin reach, and nobody but its author can explain its behaviour during an incident. That is control debt, even though it is only 9 lines.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | **Blocking** | lines 4–7 | Evacuates without fencing. Nova's view that `nova-compute` is down does not prove the host or its guests are stopped. If guests still run on shared storage, two copies can write to the same disks. | Require fencing (out-of-band power-off via BMC/Redfish, verified off) as a precondition for every evacuation. Or evaluate an existing instance-HA tool such as Masakari (verify fit for your release). |
| 2 | **Blocking** | lines 3–4 | No bound on the number of hosts acted on. A controller or RabbitMQ blip can make many computes look down at once. Nova's default `service_down_time` is short (60s, verify for your release), so a transient event can trigger a cloud-wide evacuation. | Hard stop if more than 1 compute (or N%) is down in the same window. Require the state to persist for several consecutive checks (e.g. 3–5 minutes) before acting. |
| 3 | **Blocking** | lines 5–6 | No check of storage backend before evacuating. On local-disk instances, evacuation rebuilds from the image and the data on that disk is lost. On shared storage, finding 1 applies. | Check each server's storage type and skip, or handle separately, anything not on shared storage. Record the decision. |
| 4 | **Major** | lines 4–7 | Not idempotent across minute-by-minute runs. Evacuation is async; an exception skips the disable step, so the host stays `enabled`, and every run retries. | Make each action idempotent: track in-flight evacuations (state file or Nova server state), wait for verification, and disable only after success. Catch per-server errors and continue or stop explicitly. |
| 5 | **Major** | whole script | No lock. A cron job every minute will overlap with itself if an evacuation runs long. | Wrap with `flock -n` (or equivalent) so only one run is active. |
| 6 | **Major** | line 5 | Evacuates everything on the host: stopped, ERROR, mid-migration, non-HA, pinned, special-hardware servers. Some of these should not move without a human decision. | Opt-in per server (metadata or tag) or an explicit exclusion list. Log and page for anything skipped. |
| 7 | **Major** | line 4 | Maintenance collision. Stopping `nova-compute` for patching or a reboot looks identical to a failure. The only maintenance marker the script checks is `status`, which only works if the maintenance procedure disables the service first. | Make the maintenance procedure set a marker (disabled status plus a reason), and have the script skip any host carrying it. Verify this in a runbook. |
| 8 | **Major** | lines 1–2 | Unattended admin credentials on a controller with no scoping, no audit trail, and no owner. | Run it as a dedicated service account, under an owner who is paged on failure, with logs retained. |
| 9 | **Major** | whole script | No observability. A failure, an evacuation, or a no-op all look the same to the operator. | Structured logging (host, server, source, target, result, timestamp) and an alert on any action taken. |
| 10 | **Minor** | line 6 | No capacity check before evacuating. Mass evacuation fills the remaining hosts, and later evacuations fail, which feeds finding 4. | Compare the total evacuation demand to free capacity per failure domain before acting. |
| 11 | **Minor** | whole script | No dry-run mode, no error handling, no docstring, no tests, no SDK version pin. | Add a dry-run flag that prints intended actions, test against a staging cloud with fault injection (kill `nova-compute`, partition RabbitMQ), and document the owner. |

## What would make it acceptable

**Stage 1 (safe now): detect and page.** A read-only check every minute. If a compute service has been down for a set duration (3–5 minutes), log it, list the servers that would be affected with their storage type and HA flag, and page on-call. Nothing changes in the cloud. This tells you whether the detection logic is right before anything acts.

**Stage 2: confirm the host is actually dead.** Add fencing, verified by reading the power state from the BMC after power-off. Without this, you do not have a precondition for evacuation. Also evaluate an existing instance-HA tool before writing your own.

**Stage 3: automate evacuation only when all of these hold:**
- fencing is confirmed;
- the host has been down for N consecutive checks;
- at most one host is affected (or the N% limit is not exceeded);
- a dry run has been reviewed for the last few real events;
- each server is in scope by policy and on shared storage;
- the capacity check passes;
- each server is verified ACTIVE on its new host within a timeout;
- a kill-switch file stops it immediately;
- a lock prevents overlapping runs;
- every action is logged and alerted.

Test all of this in staging with injected faults before it touches production.

## Questions for the author

1. Do you have fencing today? Which mechanism, and when was it last tested?
2. Are instance disks on shared storage (for example Ceph RBD) or local to the compute hosts?
3. How many compute hosts do you run, and how often has `nova-compute` flapped in the past? What did the last real compute failure cost you?
4. Which workloads must never be moved automatically?
5. What does your maintenance procedure do before stopping `nova-compute`? Does it disable the host first?
6. Which OpenStack release and openstacksdk version are in use? The behaviour above needs checking against them.
7. Who owns this script, and who gets paged if it misfires?

Decision support only. The state-changing steps above (fencing, evacuation, disabling services, changing the cron job) require approval by the accountable owner and should be executed under your change process.