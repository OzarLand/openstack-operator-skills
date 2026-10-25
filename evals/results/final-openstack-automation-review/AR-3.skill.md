## Summary

**Verdict: safe with changes.** I reviewed the description only, since no script or code was shown, so nothing here has been run or checked against your cloud. The idea is sound, but the one-liner is not safe as written. The 24h rule is absent from it, and it has no scope limits or stop conditions. It also can't tell a dead build from an instance that still holds data. I'd run it in report-only mode first, then enable deletion with a count cap.

**Top risks:**
1. **ERROR doesn't mean abandoned.** Failed resize, migrate, rebuild or evacuate operations can leave ERROR instances that still have recoverable disks or volumes. Deleting them destroys the evidence and the recovery option.
2. **An ERROR spike is an incident signal.** A RabbitMQ, Galera, Neutron or Cinder problem can produce dozens of ERROR instances at once. A blind nightly delete runs when you most need to investigate, and it hides the pattern.
3. **`--all-projects` has no bounds.** It runs as admin, with no project exclusions and no maximum count.

## Purpose and whether to automate

The problem is real and the cleanup is mostly execution rather than judgement (Reported). Two cautions:
- ERROR instances that keep accumulating are a symptom. If the same fault keeps recurring, such as no valid host, a port binding failure or a volume attach failure, the script will clean up after it indefinitely (Book: Ch. 16, "automating an unresolved workaround"). Capture the fault message before deleting so the cleanup also feeds root-cause work.
- The quota and capacity-report effect depends on your release and how usage is counted. Verify that ERROR instances actually inflate those numbers, and consider filtering them out of the capacity report as a complementary fix.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| "This instance is junk" | Judgement, unless the criteria are tight and written down | Not yet | The cloud owner should sign off on the criteria below |
| Delete, which is irreversible | Destructive | No | Add caps, an audit log and an opt-out |
| Whether to run during an incident | Judgement | No | A threshold breach should skip deletion and alert |

## Scope and blast radius

- **Tenants:** all projects. Exclude service and admin projects, and anything managed by another controller. Octavia amphorae, Heat stacks, Magnum clusters and autoscalers can be harmed by deleting underneath them (verify what you run).
- **Attached resources:** deleting an instance deletes volumes flagged `delete_on_termination`, and may release ports. Verify what that covers on your cloud. I'd skip instances with volumes attached, or at least log them.
- **Count:** unbounded in the one-liner.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | Add a report-only mode, and run it for 1–2 weeks first |
| Explicit scope | No | Add a project exclusion list and an opt-out tag or metadata key |
| Age filter | Missing from the one-liner | See the next section |
| Stop condition | No | Abort and alert if more than N candidates, or if the count is far above its normal baseline |
| Pre-checks | No | Per instance: `task_state` is empty, not locked, no opt-out tag, no attached volumes |
| Post-checks | No | Confirm the instance is gone and the count dropped |
| Idempotency | Yes | Re-running only touches what is still in ERROR |
| Concurrency lock | No | Wrap in `flock` |

**The 24h filter.** "Older than 24h" should mean "in ERROR and unchanged for 24h", which is `updated_at`, not `created_at`. A 3-day-old instance that failed a resize an hour ago would pass a created-at test.
- `openstack server list --changes-before <timestamp>` filters on `updated_at`. I believe it needs compute microversion 2.66 or later (verify for your client and release).
- Consider 48–72h if tenants need time to notice and report failures.

## Failure and recovery

- **No undo:** deletion is irreversible, and the only mitigation is the audit log. Write ID, name, project, flavor, host, fault message, attached volumes and timestamps to a retained file before deleting.
- **Failures:** `xargs -n1` keeps going when a delete fails and returns 123 at the end. That is acceptable only if you capture the exit code and alert on it.
- **Empty list:** GNU `xargs` without `-r` runs one `openstack server delete` with no arguments, giving a noisy error. Use `xargs -r`.

## Observability

Record when it ran, how many candidates it found, how many it deleted, how many failed, and the reason for any skip. Export the counts as a metric and alert on failure. Also log the daily ERROR count over time, because that trend is useful capacity and reliability data in itself.

## Ownership and maintainability

Name an owner. Put the script in version control with a README stating its criteria, and use a dedicated service account with a restricted role, not a full admin credential. Someone other than the author should be able to explain it and disable it during an incident. A single documented kill switch, such as a lock file that makes it exit, would cover that.

## Findings

| # | Severity | Finding | Suggested change |
|---|---|---|---|
| 1 | Blocking | No age filter, so it deletes fresh failures and in-flight recoveries | Filter on `updated_at` older than the cutoff |
| 2 | Blocking | No stop condition on mass deletion, and no cap | Abort and alert above a fixed N or above baseline |
| 3 | Major | No audit trail before an irreversible delete | Log full details, including the fault message, to a retained file |
| 4 | Major | No exclusions for service projects or controller-managed instances | Use a project allowlist or denylist, plus an opt-out tag |
| 5 | Major | Instances with volumes, a non-empty `task_state` or a lock are treated like dead builds | Pre-check and skip them, and report them for humans |
| 6 | Major | No dry-run phase | Run report-only first; the cloud owner approves the criteria and then enables deletion |
| 7 | Minor | `xargs` without `-r`, and failures are swallowed | Use `-r`, capture the exit code, alert |
| 8 | Minor | Overlapping runs, a broad credential, no owner | Use `flock`, a restricted service account, a named owner |

## Sketch (state-changing, untested, for a non-production trial)

```bash
#!/usr/bin/env bash
set -euo pipefail
exec 9>/var/lock/stale-error-reaper.lock; flock -n 9 || exit 0
DRY_RUN=${DRY_RUN:-1}; MAX_DELETE=${MAX_DELETE:-20}
CUTOFF=$(date -u -d '-24 hours' +%Y-%m-%dT%H:%M:%SZ)
LOG=/var/log/stale-error-reaper/$(date -u +%F).jsonl

ids=$(openstack --os-compute-api-version 2.66 server list --all-projects \
        --status ERROR --changes-before "$CUTOFF" --not-tags keep -f value -c ID)
n=$(grep -c . <<<"$ids" || true)
(( n > MAX_DELETE )) && { echo "ALERT: $n candidates > cap $MAX_DELETE, skipping" >&2; exit 2; }

for id in $ids; do
  openstack server show "$id" -f json >> "$LOG"   # audit trail: fault, project, volumes, task_state
  # per-instance pre-checks go here: task_state empty, not locked, no volumes, project not excluded
  [[ $DRY_RUN == 1 ]] || openstack server delete "$id" || echo "FAILED $id" >&2
done
```

## Questions for the author

1. Which ERROR causes dominate today (build failures versus failed resize or migration)? A week of the report-only output would answer this.
2. Do ERROR instances hold volumes, and does your release count them in quota and in the capacity reports?
3. Do Octavia, Heat, Magnum or autoscalers create instances in the projects this would touch?
4. Who owns the criteria, and do tenants get notified before or after deletion?
5. What compute microversion and client version are in use?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.