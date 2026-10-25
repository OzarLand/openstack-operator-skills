## Summary

**Verdict: safe with changes. Don't ship the one-liner as written.** The goal is reasonable, but this review covers the design only. You haven't shown me a script, an environment or any output. The pipeline does mechanical work (list, then delete) and also decides that every ERROR instance in every project is junk. That decision is a judgement call, and the one-liner has no safeguards around it.

Top risks:
1. **Age.** The CLI has no "older than 24h" filter, and `created_at` is the wrong clock. A 2-year-old VM that went ERROR an hour ago, for example after a failed resize, migration or rebuild, would count as old. Use time-in-ERROR instead.
2. **Not all ERROR instances are junk.** Failed builds that never ran are junk. Failed resizes, migrations, rebuilds and evacuations on real workloads are not. Deleting them destroys ephemeral disks. It also deletes attached volumes if `delete_on_termination` is set. Both are irreversible.
3. **Incident bursts.** A RabbitMQ, scheduler or Neutron problem can push hundreds of instances to ERROR at once. Your job would then delete them, along with the `fault` messages you need to diagnose the incident, with no threshold and no alert.
4. **Silent failure and no record.** There is no `pipefail`, no `xargs -r`, no log of what was deleted, no lock and no cap.

## Purpose and whether to automate

- **Assumption:** ERROR instances count against instance, core and RAM quota. Verify this for your release.
- **Assumption:** ERROR instances that never got a host don't hold hypervisor capacity. If your capacity reports show otherwise, the reports are probably querying the wrong thing.
- **Hypothesis:** the stale ERROR instances come from a handful of recurring causes, such as failed builds or `NoValidHost`.

Nightly deletion treats a symptom. Repeated cleanup isn't stability, and it hides a signal. If the ERROR count is steady, something upstream keeps producing failures. I'd keep the report and the cleanup separate, and put the weekly ERROR count and its causes on a dashboard.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Run `server delete` on a given ID | Execution | n/a | Automate |
| "ERROR means disposable" for any project | **Judgement** (owner or policy) | Unknown. Needs an agreed policy | Narrow it to a class that is provably safe (see below) |
| "Older than 24h" | Judgement (what clock? what grace?) | No | Define it as time since last update, with a longer grace for projects with real workloads |
| Continue when the count is abnormal | Judgement | No | Stop and alert instead |

## Scope and blast radius

- **Scope:** every project, with admin credentials, and the selection is implicit "all". A wrong or overly broad filter has no ceiling.
- **Blast radius:** destructive and irreversible, including volumes and ports tied to the instance. Cinder volume deletion behaviour depends on the boot settings. Verify this in your environment.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | Add report-only mode |
| Explicit scope | No | Restrict to a defined class and add an exclusion list (tag, project or metadata opt-out) |
| Stop conditions | No | Abort if the candidate count is above N, or above X% of recent history |
| Pre-checks | No | Skip locked instances and anything with an in-flight `task_state`. Check that the API is healthy |
| Post-checks | No | Confirm the instances are gone and the failure count is 0 |
| Idempotency | Mostly (deleting a deleted ID just errors) | Handle the "not found" error quietly |
| Concurrency lock | No | Use `flock` |
| Audit trail | No | Record ID, project, name, host, fault, volumes, created and updated times, and the caller before deleting |

## Failure and recovery

- `xargs` without `-r` runs `openstack server delete` once with no argument when the list is empty. That gives a spurious error every night.
- Without `pipefail`, a failed list can look like "nothing to do".
- There is no undo. The only recovery is the audit log plus backups, so the log is the safeguard that matters most.

## Observability and ownership

- Needs: a log of what ran and what it deleted, a metric of candidates versus deleted, an alert on abort or on failures, a named owner and a documented kill switch (disable the cron entry).
- It should be readable by someone other than its author, and kept in version control.

## Findings

| # | Severity | Finding | Suggested change |
|---|---|---|---|
| 1 | **Blocking** | Age filter is missing. If it's based on `created_at`, it matches recently failed long-lived VMs | Filter on time since last update with `--changes-before`, which needs compute API 2.66 or later (verify for your release) |
| 2 | **Blocking** | Deletes all ERROR instances regardless of what they are | Start with the safe class: no host, never ran, no task in progress, not locked, no attached volumes |
| 3 | **Major** | No cap, abort threshold or alert | Cap each run (e.g. 20–50) and abort on bursts, since a burst usually means an incident, not stale clutter |
| 4 | **Major** | Fault evidence is destroyed | Write a JSON record per instance before deleting |
| 5 | **Major** | Tenant data deleted without notice | Notify project owners, or tag first and delete after a grace period |
| 6 | Minor | No `pipefail`, `xargs -r`, lock or logging | See the sketch below |
| 7 | Minor | Needs an owner, a repo and a runbook | Name an owner and a review date |

## Suggested rollout

1. **Report-only for 2–4 weeks** (state-changing steps disabled). Group the candidates by cause, project and host.
2. **Agree the policy** with whoever owns tenant resources. Define the safe class, the grace period and the opt-out.
3. **Enable deletion** for that class only, with the cap and abort threshold.
4. **Fix the capacity reports** so they don't depend on this cleanup.

Here is a sketch for steps 1–3. It is untested and should be tried in a non-production environment first.

```bash
#!/usr/bin/env bash
set -euo pipefail
exec 9>/var/lock/stale-error-cleanup.lock; flock -n 9 || exit 0

DRY_RUN=${DRY_RUN:-1}; MAX=${MAX:-25}
CUTOFF=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)

openstack --os-compute-api-version 2.66 server list --all-projects \
  --status ERROR --changes-before "$CUTOFF" --long -f json > /var/log/stale-error/candidates-$(date +%F).json

# Keep only unlocked instances with no host and no task in progress (field names depend on client version)
# Then: if count > MAX -> alert and exit non-zero
# If DRY_RUN=0: write the audit record, delete each ID, collect failures, alert if any
```

## Questions for the author

- What produces the stale ERROR instances today (failed builds, failed resizes, host failures)? Do you have numbers?
- Do any tenants rely on ERROR instances for debugging, or on `reset-state` recovery?
- Which compute API and client versions are in use, and is `--changes-before` available?
- Who owns the deletion policy, and who gets alerted when the job aborts?
- Are you sure ERROR instances inflate the capacity reports? If so, how? That may be a reporting fix rather than a cleanup job.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.