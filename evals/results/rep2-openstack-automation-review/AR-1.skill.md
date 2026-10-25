## Summary

**Verdict: not safe, redesign.** I would not put this in cron as written. Detecting a down host automatically is fine. Deciding to evacuate on that signal alone is a judgement the script can't make safely.

**What it does (as I read it):** every minute, it lists every `nova-compute` service. For each one that is `down` and `enabled`, it asks the scheduler to evacuate every instance from every project on that host. After that it disables the service. Nothing is checked, capped, logged or fenced, and nothing needs a human go-ahead.

**Top risks:**
1. There is no fencing. A missed heartbeat doesn't prove the host is dead (Book Ch. 10). If the host is alive but unreachable, you get two copies of each VM. With shared Ceph or volumes, that means corruption.
2. Control-plane faults look like mass compute failure. `state` comes from service heartbeats going through RabbitMQ and the DB. A RabbitMQ partition, a conductor problem or a DB blip can make every compute look down. The script would then try to evacuate the whole cloud.
3. There is no scope limit, rate limit or capacity check. Nothing stops it from piling a dead host's load onto survivors until they overload.

## Purpose and whether to automate
The goal is clear: don't be woken at night for a dead hypervisor. Evacuation after a real host failure is a legitimate thing to want. But the script is a heartbeat-to-evacuate reflex, and the author's rule is to automate execution, not judgement (Ch. 16). "Is this host really dead?" is the judgement. Fencing is what turns it into something a machine can decide.

## Decisions it takes
| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| "Host is dead" from `state == 'down'` (L4) | Judgement | No evidence of it | Require fencing (out-of-band power-off or switch isolation) as a precondition |
| "Disrupt and move every tenant VM" (L5-6) | Judgement | Unknown | Cap per host and per run, with a named owner who accepts the consequence |
| Where to place VMs (scheduler, no `host=`) | Mixed | n/a | Check capacity first; exclude special cases |
| Disable the service (L7) | Execution | n/a | Do this first, not last (see findings) |

## Scope and blast radius
- **Observed from the code:** `all_projects=True` and no filter on tenant, flavor or state. Every compute host and every instance is in scope.
- **Unknown:** how many computes you have, and what share of capacity is spare. Also unknown: whether storage is shared Ceph or local, and whether you have pinned, GPU or SR-IOV instances. I won't assume any of these.
- The worst case is "all hosts look down", and the script has nothing to stop that.
- If more than one controller runs this cron, every controller does it.

## Safeguards
| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | Add a mode that only prints the host and the instances it would evacuate |
| Explicit scope | No (implicit "all", L3-5) | Allow-list or host cap |
| Confirmation | No | None for a disruptive action |
| Stop conditions | No | No halt if more than N hosts are down, on a high down fraction, or on any error |
| Pre-checks | No | No fencing, no check for maintenance, no confirmation the host is down beyond one heartbeat sample |
| Post-checks | No | Nothing confirms the instance is ACTIVE and reachable on the new host |
| Idempotency | Partial | A re-run is only safe if the final disable happens (see failure section) |
| Concurrency lock | No | Cron every minute means overlapping runs, since evacuate is asynchronous and slow |
| Monitoring | No | See observability |

## Failure and recovery behaviour
- **No error handling (L5-7).** If one `evacuate_server` call raises, the script dies before L7. The service stays `enabled` and `down`. The next minute it retries the instances still on that host, which can include ones mid-rebuild. A failure partway through leaves a partial state and no record of it.
- **Disable comes after evacuate.** Disable first, so the host is out of play and the next cron tick doesn't re-select it. (A down host is probably already filtered by the scheduler, but verify for your release.)
- **Evacuation destroys data in some setups.** Without shared instance storage, evacuation rebuilds from the image and local ephemeral data is lost. Behaviour varies by release and backend, so verify for yours.
- **No recovery path.** There is no log of what moved from where. When the host comes back, nothing deals with the stale copies. If the host was alive, you now have duplicates and no way to say which is right.
- **Instance state is ignored.** The script doesn't check for ERROR, a task already in progress, or a locked instance.
- **Planned work.** A host being rebooted for maintenance while still `enabled` gets evacuated. This is a likely cause of surprise.
- **No grace period.** With a one-minute cron, a single missed heartbeat window (60s `service_down_time` by default; verify) can trigger a mass evacuation.

## Observability
Cron mail is the only output, and there is none: no log, no metric, no alert. It could evacuate a host at 03:00 and nobody would know until tenants complained. The real fault (the dead host) also still needs a human, and repeated recovery is not stability (Ch. 9). I could not find the mechanism that tells someone it ran.

## Ownership and maintainability
- **Unknown:** who owns it, whether it is in version control, and whether it has been tested against a real or simulated failure. The script holds `prod` admin credentials, so redact `clouds.yaml` if you share it.
- It looks simple, so it will feel trustworthy. It's the kind of automation only its author can explain during an incident, which makes it control debt.

## Findings
| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | Blocking | L4-6 | Evacuates on heartbeat loss with no fencing; risk of split-brain and data corruption | Fence first (IPMI/Redfish power-off or network isolation); evacuate only after fence is confirmed |
| 2 | Blocking | L3-7 | No cap or stop condition; a control-plane fault can trigger a whole-cloud evacuation | Abort and page if more than N hosts (or a fraction) are down; process at most one host per run |
| 3 | Blocking | whole script | No human decision point for a disruptive action | Page with the evidence and a one-command approve, or delegate explicitly with an owner and a limit |
| 4 | Major | L3-7 | No lock; overlapping runs or multiple controllers | `flock` or a leader-only job |
| 5 | Major | L5-7 | No error handling; failure mid-loop leaves half-state and a retry loop | Disable the service first; catch errors per instance; stop on first failure and alert |
| 6 | Major | L6 | No capacity check, so evacuees can overload survivors; local-storage data loss possible | Check spare capacity; verify shared-storage behaviour; exclude special cases |
| 7 | Major | whole script | No dry run, post-check or logging | Dry-run flag; log hosts, instance IDs, results; verify ACTIVE and reachable |
| 8 | Major | L4 | Maintenance windows and flapping hosts trigger it; no grace period | Require down for N minutes, skip hosts marked in maintenance, and don't touch a host again within a cooldown |
| 9 | Minor | whole script | Owner, versioning, tests and runbook unknown | Put it in version control, name an owner, test in a non-production cloud |

## Direction I'd recommend
1. **Automate now:** detect and alert (down for N minutes, with a cross-check such as ping, BMC and RabbitMQ health) and prepare the evidence: host, instance list, storage type, spare capacity. Everything is `read-only` at this stage.
2. **Semi-automate the action:** one command or button on the alert, run by the on-call engineer. It fences, runs `mark_forced_down`, then evacuates in small batches, then verifies.
3. **Consider full automation later,** only once fencing is reliable and tested, with explicit delegation from a named owner, hard caps and the stop conditions above. Also look at upstream tooling for this (Masakari, for example) before maintaining your own. Verify fit for your release.

## Questions for the author
- What is your storage: shared Ceph, local disks, volume-backed?
- Is out-of-band power control (IPMI/Redfish) available on every compute, and tested?
- How many computes, and how much spare capacity per failure domain?
- Have you seen all computes flap down at once (RabbitMQ or DB trouble)? What happened then?
- Who is the named owner who accepts the risk of auto-evacuating?
- Do any instances use pinning, GPU, SR-IOV or anti-affinity?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.