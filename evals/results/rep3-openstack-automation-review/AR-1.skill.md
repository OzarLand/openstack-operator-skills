## Summary

**Verdict: not safe, redesign.** The script automates a judgement ("this host is dead, so its VMs are safe to restart elsewhere") that it can't make. I would not put it in cron as written.

**What it does (Observed, from the code you pasted):** every minute it lists `nova-compute` services. For each one that is `down` and `enabled`, it evacuates every instance of every project on that host, and only then disables the service. Nothing else happens: no fencing, no checks, no limits, no logging.

**Top risks:**
1. It evacuates without fencing. Nova's "down" state only means the heartbeat is missing, not that the host is dead. If the host is alive but partitioned, you get two copies of each VM writing to the same volumes, which can corrupt data.
2. There is no cap on how many hosts it acts on. A RabbitMQ, DB or conductor problem can make every compute look down at once, and the script then evacuates the whole cloud.
3. Instances on local, non-shared disk may be rebuilt from the image, which loses their data. Whether that applies depends on your storage, which I don't know.

## Purpose and whether to automate

The goal is to avoid night pages, and that's legitimate. But the failure it targets (a compute host down) has several causes, and the right action differs for each: a dead host, a hung nova-compute, a partition, or a bus or DB outage. The script treats them all as "evacuate". Evacuation is a disruptive, hard-to-reverse decision. The book's position is to automate execution and keep judgement with humans unless the organization has explicitly delegated it. I'd treat that as the standard here, and I don't see evidence of an explicit delegation. Please say if one exists.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Host is dead (`state == 'down'`) | Judgement (uncertain diagnosis) | Unknown | Require fencing, which proves it |
| Evacuate every VM of every tenant | Judgement (disrupts workloads) | Unknown | Gate on fencing, capacity check and a threshold |
| Let the scheduler choose targets | Judgement | Unknown | Check capacity first |
| Disable the service | Execution | n/a | Do it first, with a reason |

## Scope and blast radius

- **Observed:** `all_projects=True` and no limit on hosts or instances. The scope is every compute host and every tenant.
- **Correlated failure:** nova's "down" comes from heartbeats written through the message bus and DB. If those fail, many or all computes go "down" together. This is a hypothesis about how it would fail, but it's a well-known failure mode, and nothing in the script stops it.
- **Capacity (Assumption: unknown):** the script doesn't check that the remaining hosts can absorb the load. One real host failure could leave VMs in ERROR or overload the survivors.
- **Overlap:** if this runs on more than one controller, every controller evacuates the same host.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Fencing (power off via BMC or isolate the host) | No | Blocking: nothing proves the host is not running its VMs |
| Preview / dry run | No | There is no way to see what it would do |
| Explicit scope | No | The default is every host |
| Stop condition / threshold | No | Nothing like "more than N hosts down, stop and page" |
| Pre-checks | Partial | Only `state`/`status`. No check of capacity, bus/DB health, or last heartbeat age |
| Post-checks | No | It doesn't confirm the VMs are ACTIVE and reachable on new hosts |
| Idempotency | Weak | See the next section |
| Concurrency lock | No | At a one-minute interval, evacuations that take longer than a minute will overlap with the next run |
| Confirmation | No | Nobody approves it, by design, which is why the other safeguards matter more |

## Failure and recovery behaviour

- **Disable comes after evacuation.** While evacuations run, the scheduler can still place new VMs on the dead host. Disable first.
- **Silent loss of failed work.** Once the service is disabled, the `status == 'enabled'` filter skips it forever. If some evacuations failed, nobody retries them and nobody is told.
- **No error handling.** An exception on one server (a conflict, a wrong state, a timeout) aborts the loop. The host may be left half-evacuated and never disabled, so it gets picked up again next minute and the cycle repeats.
- **Fire and forget.** `evacuate_server` returns when the request is accepted, not when it finishes. The script reports nothing on outcomes.
- **Recovery path:** none. If evacuation caused split-brain or data loss, there is no undo. If the host comes back, it stays disabled with no reason recorded, and someone must remember to re-enable it.
- **Instance states:** it sends evacuate for every instance without checking its state, so it will hit instances that are already being migrated or rebuilt.

## Observability

There is no logging, no alert, and no record of what it evacuated or when, and no kill switch other than removing the cron line. In the morning you would not know what ran at 03:12 or why.

## Ownership and maintainability

I can't judge this from the script alone. The questions I'd ask are: who owns it, is it in version control, has it been tested against a real host failure in a non-production environment, and could someone other than the author explain it during an incident? The `cloud='prod'` entry in `clouds.yaml` also needs admin rights on the controller, so that credential's storage and permissions matter. Please redact any secrets before you share the file. SDK method signatures such as `disable_service` and `evacuate_server` vary by openstacksdk version, so check them against the version you run.

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | Blocking | line 5 | Evacuates with no fencing. A live but partitioned host leads to duplicate VMs and storage corruption. | Fence first (power off via BMC or isolate), confirm it succeeded, and only then evacuate. Treat a failed fence as a stop. |
| 2 | Blocking | whole loop | No cap on the number of hosts. A bus or DB outage could trigger a cloud-wide evacuation. | Abort and page if more than N hosts, or more than X% of hosts, are down. |
| 3 | Blocking | line 5 | Local-disk instances may lose data when rebuilt. This depends on your storage. | Split by storage type. Evacuate automatically only for shared or volume-backed instances, and leave the rest for a human. |
| 4 | Major | line 6 vs 5 | Disable happens after evacuation, so new VMs can land on the dead host. | Disable first, with `disabled_reason`, or set the forced-down flag. |
| 5 | Major | cron | No lock, so runs overlap, and multiple controllers each run it. | Use `flock`, and run it on one controller only. |
| 6 | Major | line 5 | No error handling. One failure aborts the host, and failed evacuations are never retried or reported. | Wrap each action in try/except, log per instance, and alert on failures. |
| 7 | Major | whole script | No capacity or health pre-check (target capacity, bus/DB, heartbeat age, how long it has been down). | Require the host to be down for several minutes before acting. Check the control plane is healthy first. |
| 8 | Major | whole script | No post-check. | Verify the instances are ACTIVE and reachable on the new host. |
| 9 | Minor | whole script | No logging, notification or kill switch. | Log structured output, send a notification, and add a disable flag file. |
| 10 | Minor | cron | A one-minute interval is more aggressive than evacuation needs. | A longer interval plus a down-duration requirement reduces flapping. |

## Recommendation: semi-automate

You want fewer night pages, and that doesn't need a script that evacuates unattended. A staged approach:

1. **Now:** run the script in report-only mode (list the hosts and instances it would evacuate) and send the result as an alert with the hostname and instance count. This is read-only. You then decide in a minute instead of investigating from scratch.
2. **Next:** add fencing and the checks above, and have the on-call approve with one command, such as a confirmation prompt, a flag, or a chat button.
3. **Only later**, if the organization explicitly delegates the decision (a named owner accepts the risk), automate the full flow. Do this for a narrow, well-understood class of hosts, with fencing as a hard precondition, a threshold, and an easy stop.

Before that, test it on a non-production environment with a real failure, ideally including a partition where the host stays alive.

## Questions for the author

- Is there fencing today (BMC/IPMI/Redfish access, or switch isolation)?
- What storage do instances use: shared (Ceph, NFS) or local disk? What share of instances are on each?
- How many computes are there, and how much spare capacity?
- Has a bus or DB outage ever made multiple computes show as down?
- Has anyone approved unattended evacuation, and who owns the consequences?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.