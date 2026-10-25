## Summary

**Verdict: not safe to run as is.** It needs redesign before it goes into cron. Your goal is sound, and part of it can safely be automated.

**What it does (Observed, the script as pasted).** Every minute it lists `nova-compute` services. For each one that is `down` and `enabled`, it asks Nova to evacuate every server on that host, across all projects, and then disables the service. The only evidence it uses is Nova's heartbeat-based `state == 'down'`.

**Top risks**
1. **No fencing (Blocking).** A missed heartbeat doesn't prove the host is dead. The script evacuates without making sure the old instances are stopped.
2. **No limit on how many hosts it acts on (Blocking).** A RabbitMQ, DB, conductor or network problem makes many or all computes look `down` at once. The script would then try to evacuate the whole cloud one minute later.
3. **Failures and re-runs are unmanaged (Major).** There is no error handling, no lock and no logging. Cron runs it every minute, and possibly on several controllers.

## Purpose and whether to automate

- The problem is real and understood: a compute host dies and workloads need to come back without a 3 a.m. page.
- Detecting the failure and fencing the host are good candidates for automation, and fencing is the safeguard the script is missing.
- The decision to evacuate is a judgement. It depends on whether the host is really dead, whether the storage is shared, how much capacity is left and which workloads matter. Per the skill's principles, that stays under human authority unless a named owner has explicitly delegated it with limits. I see no sign of such a delegation (Gap).

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| "Host is dead" (line 4) | Judgement. It rests on one heartbeat signal. | Unknown | Require a second signal plus fencing. |
| Evacuate all servers (lines 5–6) | Judgement. It is disruptive and could cause duplicate VMs or data loss. | Unknown | Fence first, add caps, and get explicit sign-off. |
| Disable the service (line 7) | Execution | n/a | Fine, but do it before evacuating. |

## Scope and blast radius

- **Target set (Observed).** All down, enabled computes and all their servers in all projects (lines 3, 5). Nothing is bounded.
- **Correlated failure.** `state` is derived from heartbeats that travel over the message bus and DB. If those misbehave, every compute can show `down` together. The script cannot tell that apart from a real hardware failure.
- **Capacity.** There is no check that the remaining hosts can absorb the load. A burst of evacuations can fail with NoValidHost and leave servers in ERROR.
- **Local storage (Assumption/Gap).** If instances use local ephemeral disks, evacuation rebuilds them from the image and the disk contents are lost. I don't know your storage backend. With shared storage (e.g. Ceph), the risk shifts to two copies of a VM writing to the same disk if the "dead" host is only partitioned.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Fencing (power off via BMC or isolate) | No | Blocking. Needs to be a precondition for evacuation. |
| Preview / dry run | No | Add `--dry-run` that prints host and servers. |
| Explicit scope | No (implicit "all", lines 3, 5) | Add a host allowlist and an exclusion list. |
| Stop condition | No | Halt if more than N hosts, or more than X% of the fleet, are down. That pattern indicates a control-plane or network event. Also halt if RabbitMQ or Galera are unhealthy. |
| Pre-checks | No | Check API, bus and DB health, and that the host is unreachable by a second path (BMC or ping). |
| Post-checks | No | Verify servers reach ACTIVE on another host, not just that the API call returned. |
| Concurrency lock | No | Use `flock`. If cron is on several controllers, run it on one only, or use a leader lock. |
| Timeout / retry bounds | No | Cron fires every minute whatever happened before. |

## Failure and recovery behaviour

- **Unhandled exceptions (line 6).** `evacuate_server` is asynchronous and can fail with 409 (a server mid-rebuild or in a bad state), 400 or 5xx. Any exception aborts the whole script. Other dead hosts are skipped, and `disable_service` (line 7) never runs for that host. The next run repeats the same thing every minute.
- **In-flight evacuations.** An evacuation can still be in progress when the next minute starts. The server may still be listed on the old host, so the script can issue duplicate evacuate calls (verify behaviour for your release).
- **Lazy generator (line 5).** `servers(...)` is a paginated generator that is consumed while the servers are changing. Wrap it in `list()`.
- **Flapping hosts.** A host that reboots or comes back after a network blip may still be running the original guests. Nova destroys evacuated guests at nova-compute startup, which helps, but it does not cover a host that stays alive while partitioned from the controller.
- **Silent state.** After the script disables a service, nobody is told. A recovered host stays disabled until someone notices. Re-enabling must be a human decision.
- **Recovery path.** None. Nothing records which servers were moved from where, so an engineer reconstructing the sequence would have to rely on Nova's migration records.

## Observability

- There is no log, metric or alert. Cron email is the only trace, and only if it is configured.
- Nothing tells a human that "an automated evacuation of N VMs from host X just happened".
- There is no kill switch, such as a lock file or flag that disables the automation without editing cron.

## Ownership and maintainability

- Unknown: owner, repository, tests, review, and who besides the author can explain it at 3 a.m.
- The `prod` cloud entry presumably holds admin credentials in `clouds.yaml`. Check who can read that file.
- The `disable_service(svc, host, binary)` signature has changed across openstacksdk versions. Pin the SDK version and test the call (verify for your version).

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | Blocking | lines 4–6 | Evacuates on heartbeat alone, with no fencing. This risks duplicate VMs and disk corruption, or data loss on local-disk VMs. | Fence via BMC/STONITH first, then mark the service force-down, then evacuate. If fencing fails, page a human and do nothing else. |
| 2 | Blocking | line 3 | No cap on hosts handled. A bus, DB or network fault would trigger a mass evacuation. | Abort and page if more than N hosts (or X%) are down at once, or if RabbitMQ/Galera/API health checks fail. |
| 3 | Major | line 6 | No exception handling. One failed call blocks all later hosts and the disable step. | Wrap each server and host in try/except, log, and continue or stop deliberately. |
| 4 | Major | whole script | No lock. Cron every minute, plus possibly several controllers, gives overlapping or tripled evacuations. | `flock -n`, and a single designated runner. |
| 5 | Major | lines 6–7 | Evacuate before disable. The disable also never records what was done. | Disable (and force-down after fencing) first. Record each action. |
| 6 | Major | lines 5–6 | No capacity check, no batching, no filtering by server state. | Evacuate in small batches, check headroom, and skip servers the owner excluded. |
| 7 | Major | whole script | No logging, alerting or kill switch. | Structured log, notification on every action, and a disable flag. |
| 8 | Minor | line 5 | Lazy generator consumed while state changes. | `list(...)` it first. |
| 9 | Minor | line 7 | SDK signature is version-dependent. | Pin and test the version. |
| 10 | Minor | n/a | Owner, tests and documentation are unknown. | Put it in version control with a named owner and a runbook. |

## Options (conditions and trade-offs)

- **A. Fully automatic.** Choose this only if the owner has explicitly delegated it, fencing exists and has been tested, and the guardrails above are in place. It gives the best night-time experience but carries the highest consequence. Masakari or a Pacemaker-based setup may already cover much of this (verify for your release).
- **B. Automate detection and fencing, with a human go for evacuation.** The script confirms the host is dead, fences it, force-downs it, then pages the on-call with the list of VMs and a one-command evacuation. Waking up costs some sleep, but the judgement stays with a person.
- **C. Tiered.** Auto-evacuate only workloads that an owner has marked tolerant (for example by tagged aggregate or flavour). Everything else follows B. This reduces night pages without delegating the whole fleet.

My recommendation is B or C first. Collect a few months of evidence (how often hosts actually die, whether fencing works and whether evacuations succeed), then widen the delegation if it holds up.

## Questions for the author

1. What is the instance storage: shared (Ceph/NFS), local, or a mix? Are most VMs volume-backed?
2. Do you have BMC/IPMI/Redfish access, or any fencing, from the controller?
3. How many computes are there, how much spare capacity, and what is `service_down_time`?
4. How many controllers will run this cron? Is there any leader election?
5. Has a named owner accepted the risk of auto-evacuating all projects? Are there workloads that must never be moved automatically (GPU, pinned, licensed)?
6. Has this ever been exercised, even against a test host with its network cut or its BMC powered off?
7. Which openstacksdk and Nova releases are in use?

I reviewed the code as pasted and did not run anything. All of the behaviour I describe is as I understand the Nova API, so verify it for your release before relying on it.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.