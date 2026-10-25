## Summary

**Verdict: not safe as written. Safe with changes, and the "is it junk?" decision should only be partly automated.**

The job lists every ERROR instance in every project and deletes it, one at a time. The planned 24h filter doesn't fix the main risk. Several details below depend on your release and backends, so verify them (rule 8).

Top risks:
1. **ERROR doesn't mean junk.** It covers failed builds, but also long-running VMs that hit a failed resize, migration, rebuild or evacuation, or a host or RPC fault. Their disks and data may be intact and recoverable. If "older than 24h" means `created`, a VM that is months old and went ERROR an hour ago gets deleted tonight.
2. **A mass-ERROR event is an incident, not clutter.** RabbitMQ, scheduler, Neutron or Cinder trouble, or a host failure, can flip hundreds of instances to ERROR. The job would delete them all, along with the `fault` evidence and any chance of recovery. There is no count cap or stop condition.
3. **Deletion has side effects.** It can destroy ephemeral disks and boot volumes with `delete_on_termination`. It also detaches data volumes and can leave orphaned ports or floating IPs. Deleting tenant resources is irreversible.

## Purpose and whether to automate

The goals are valid: ERROR instances count against quota, and they skew capacity reports. Two points:
- **Repetition is evidence.** If ERROR instances pile up nightly, something upstream keeps failing. A cleanup job hides that and removes the evidence. Ask why they appear.
- **Capacity reports** may not need deletion at all. For failed builds, placement allocations are normally released, so the confusion is probably a reporting-filter problem. This is an assumption to verify.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Delete a resource (mechanical) | Execution | n/a | Fine to automate once the target is certain |
| "This tenant's ERROR instance is junk" | **Judgement** | Not stated | Needs an agreed policy with tenant owners, not a cron assumption |
| "Old enough" (>24h) | Policy proxy | Not stated | Use a signal that means "never ran", not age alone |

## Scope and blast radius

- `--all-projects` with no project allow-list or exclusion list.
- No cap, so the blast radius equals however many instances are in ERROR tonight.
- `xargs -n1` keeps going after individual failures. It exits 123 at the end, which nobody reads from cron.
- GNU `xargs` without `-r` runs once with no argument on an empty list. This is harmless but sloppy.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | Add a report-only mode, and make it the default |
| Explicit scope | No (all projects) | Add allow/deny lists and a "never launched" criterion |
| Confirmation | No | Not needed per run if the policy is agreed. Needed for anything outside the narrow class |
| Stop conditions | No | Abort if count > N, or if ERROR count jumps against the previous night |
| Pre-checks | No | Check the instance still looks ERROR and unchanged just before deleting. Check the API and RabbitMQ are healthy |
| Post-checks | No | Confirm the instance is gone, and that quota and orphaned ports and volumes are as expected |
| Idempotency / lock | Partly (re-delete is harmless) | Add `flock` so runs can't overlap |

## Suggested design

1. **Report-only for 2–4 weeks.** Log id, project, created, updated, `fault` message, `launched_at`, host and attached volumes. Count by fault cause. This is read-only and shows you what's in the pile.
2. **Age on the right clock.** `created` is the wrong signal. Use time-in-ERROR, such as `updated`, or `--changes-before` on `server list` (needs compute API ≥ 2.66; check your release). Even `updated` can be reset by metadata or tag changes.
3. **Split the population.**
   - *Never ran* means `OS-SRV-USG:launched_at` is empty and the fault is a build or scheduling failure. This is the class to auto-delete, with a grace period of about 24–72h.
   - *Previously ran* means `launched_at` is set. Don't auto-delete. Send a per-project report, give owners a longer window (for example 7–14 days), and treat it as an escalation. Many of these are recoverable with `reset-state` plus a hard reboot or rebuild, which is a human decision.
4. **Cap and trend.** Abort and alert if the candidate count exceeds a threshold, or if it is far above the 7-day median. A spike goes to an engineer as an incident.
5. **Archive evidence before deleting.** Write the `server show` JSON, including the fault, to a log or object store.
6. **Dedicated least-privilege identity.** Use an application credential or service user restricted to list and delete, not the admin openrc. Keep secrets out of the crontab and the logs.
7. **Observability.** Log each action, emit metrics (candidates, deleted, failed, skipped), alert on failures, and send a summary to a channel owners read.
8. **Ownership.** Name an owner, keep the script in version control, and write a short runbook. Someone other than the author should be able to explain it.

Rough shape (untested sketch, flags to verify against your client and API version):

```bash
# read-only: build candidate list; state-changing step is gated behind --apply
openstack server list --all-projects --status ERROR -f value -c ID \
 | while read -r id; do
     openstack server show "$id" -f json > "$EVIDENCE_DIR/$id.json"   # read-only
     # filter: launched_at empty, updated older than threshold, project not excluded
   done
# if candidates > MAX: alert and exit non-zero
# if --apply: openstack server delete "$id"  (per-id error handling, count failures, stop after K)
```

## Findings

| # | Severity | Finding | Suggested change |
|---|---|---|---|
| 1 | **Blocking** | Deletes previously running instances that merely errored, which can destroy recoverable data | Limit auto-delete to never-launched instances. Send the rest to owners |
| 2 | **Blocking** | No cap or stop condition, so an incident-driven ERROR spike is mass-deleted | Count cap and trend check. Alert instead of deleting |
| 3 | Major | Age is ambiguous and probably `created` | Use time-in-ERROR (`updated`, `--changes-before`) |
| 4 | Major | No dry run, no evidence retention | Report-only default, archive `server show` output |
| 5 | Major | Tenant policy isn't agreed, so it's an undelegated judgement | Get a named owner to approve the policy and notify projects |
| 6 | Minor | `xargs` error handling, no `-r`, no lock, no logging or metrics | Wrap in a script with `flock`, per-item results and alerting |
| 7 | Minor | Credential scope unknown | Dedicated least-privilege credential |

## Questions for you

- Who owns the "ERROR is disposable" policy, and have tenants agreed to it?
- What currently produces the ERROR instances (failed builds, or resize/migration/host faults)? A week of the report-only output would show this.
- Is boot-from-volume with `delete_on_termination` common? Do you use `reclaim_instance_interval` (soft delete)?
- Does the capacity report actually need the instances gone, or just filtered out?
- Which release and compute API version is this? It affects the filters.

I haven't run anything against your cloud. This review covers the command and description you gave, not an actual script.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can draft the report-only script and a short runbook if you want them.