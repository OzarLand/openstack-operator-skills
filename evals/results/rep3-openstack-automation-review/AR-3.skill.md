## Summary

**Verdict: not safe as written. Safe with changes, and I'd start semi-automated.** This is a design-only review. I haven't seen a script, cron entry, or credentials, and I haven't run anything.

The one-liner does what you describe, but it has no age filter at all. It deletes every ERROR instance in every project, including ones that went ERROR a minute ago. Even with the 24h filter added, the bigger problem is that "ERROR" doesn't mean "junk".

Top risks:
1. **Wrong selection:** the age condition is missing.
2. **ERROR instances can hold real data.** A previously running VM can land in ERROR after a failed resize, migration, evacuation, or host or storage problem. Its disk and volumes may be the only copy.
3. **A wave of ERRORs is an incident signal, not garbage.** Deleting them destroys the fault messages and the recoverable instances.
4. **No cap, preview, log, or stop condition.** It runs as admin across all projects.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Delete an instance | Mechanical | n/a | Fine to automate once the target is decided |
| "This tenant's instance is junk" | **Judgement** (owner or agreed policy) | No (assumed) | Get a written policy from the platform owner, or notify tenants first |
| "24h is long enough" | Judgement | No | Needs an owner. Tenants may be debugging or recovering inside that window |
| "A mass of ERRORs is normal" | Judgement | No | Add an automatic stop instead |

## Scope and blast radius

- **Scope:** every project, with admin credentials. The target set is whatever the API returns. An API error or partial result silently shrinks or changes the set.
- **Data loss (Assumption, verify for your backends):** deleting an instance can also delete boot-from-volume volumes where `delete_on_termination` is set. It also releases ports and floating IPs. Check what your tenants actually do.
- **Evidence loss:** the `fault` message and the host and scheduler trail go with the instance.
- **Empty input:** with GNU xargs, empty input still runs `openstack server delete` once with no argument. That's noisy rather than dangerous. Use `xargs -r`.
- **Unknown:** how many ERROR instances you have today, and how many new ones appear per night. Both set the right cap.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | Add a report-only mode as the default |
| Explicit scope | No (implicit "all") | Filter by age, class, and project allowlist or denylist |
| Confirmation | No | Needed at least until the policy is trusted |
| Stop conditions | No | Abort if the count exceeds N, or jumps against the 7-day baseline |
| Pre-checks | No | Skip locked instances, instances with attached volumes, and instances on a host in a known-bad state |
| Post-checks | No | Confirm the instances are gone and the quota is released |
| Idempotency | Mostly (deleting twice is harmless) | Check the exit code per instance |
| Concurrency lock | No | Use `flock` |
| Error handling | No | Add `set -o pipefail`. A failed `list` currently looks like "nothing to do" |

## Failure and recovery

- **Recovery:** none. Deletion is irreversible. If `reclaim_instance_interval` is set, soft delete may give a window, but that applies to instances that were running (verify for your release and config). It won't help for volumes or ports.
- **Interruption:** a half-finished run is harmless, because the next run just continues.
- **Silent failure:** instances stuck deleting, or a changed API response, would go unnoticed without logging.

## Observability and ownership

- **Needed:** a log of every ID, project, name, `created_at`, `updated_at`, and fault message before deletion. Also a per-run count, an alert on abort, and a named owner.
- **Ownership:** the cron job needs an owner, version control, and a runbook that someone other than the author can follow.
- **Credentials:** use a dedicated, least-privilege service account rather than a personal admin credential.

## Findings

| # | Severity | Finding | Suggested change |
|---|---|---|---|
| 1 | **Blocking** | No age filter in the stated command | Filter on time in ERROR. `--changes-before <ts>` filters on `updated_at`, which fits "stuck in ERROR for 24h" better than `created_at`. It needs compute API microversion 2.66+, so verify for your release |
| 2 | **Blocking** | ERROR may mean a recoverable, previously running VM | Restrict auto-deletion to instances that never ran (for example `launched_at` empty and a build or scheduling fault, no volumes). Everything else goes to a human |
| 3 | **Blocking** | No mass-event stop condition | Abort and alert if the candidate count is above a cap or well above the baseline. Treat it as an incident and don't delete |
| 4 | **Major** | Deleting a tenant's resources by assumption | Notify owners, with a grace period, or tag instances for deletion and delete after a delay. Get a policy sign-off from the platform owner |
| 5 | **Major** | Pipeline failure modes | `set -euo pipefail`, `xargs -r`, a per-ID exit code, and a rate limit |
| 6 | **Major** | No audit trail | Log the full pre-deletion record to a file or ticket system |
| 7 | **Minor** | Admin credentials, no lock, no owner | Service account, `flock`, named owner, runbook |
| 8 | **Minor** | Root cause not addressed | If ERRORs recur, track the fault reasons. Nightly cleanup hides the problem, and "repeated recovery is not stability" |

## Recommended path

1. **Now (read-only):** nightly report of ERROR instances older than 24h. Include project, name, created and updated times, fault message, and whether they ever launched or have volumes. Send it to the platform team, and to tenants if you can.
2. **After 2–4 weeks of data:** if most entries are never-launched build failures, automate deletion for that class only. Use a count cap, a grace period or notification, a log, and an alert.
3. **Leave the rest manual:** ERROR instances that previously ran, or that have volumes, stay with a human.

This also gives you evidence for the quota and capacity claim. I haven't verified that ERROR instances distort your capacity reports. It depends on whether they hold a host or placement allocation, so check that in your data.

## Questions for you

- How many ERROR instances exist now, and what do their fault messages say?
- Do tenants use boot-from-volume, and what is `delete_on_termination`?
- Is `reclaim_instance_interval` set?
- Who owns the decision to delete tenant resources, and do tenants have a notice period?
- Which release is this, for the microversion check?

I can draft the report-only script next if you want it.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.