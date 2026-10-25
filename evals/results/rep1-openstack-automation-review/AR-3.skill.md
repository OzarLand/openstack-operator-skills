## Summary

**Verdict: safe with changes, and not as written.** I'd start semi-automated: report nightly, and delete automatically only a narrow class of instances. This is a design-only review. You gave me the one-liner and no script, so I haven't seen your real code or run anything.

**What the one-liner does.** It deletes every ERROR instance in every project. It has no age filter at all, because `--status ERROR` is the only condition. Anything that fails at 23:59 is deleted at 00:00.

**Top risks**
1. **Age is not the right test.** ERROR doesn't only mean "failed to build". An instance that has run for a year can go ERROR after a failed resize, live migration, rebuild or revert. It may still have a running guest, local disk data and attached volumes. "Created more than 24h ago" matches all of those, and deletion is irreversible.
2. **Deletion is a tenant-owned judgement.** Deleting is mechanical, but deciding that someone's instance is junk is a policy decision. It needs explicit delegation, ideally written down with tenants.
3. **It hides a signal.** A steady stream of ERROR instances usually points at the scheduler, RabbitMQ, Ceph, Neutron or a bad compute host. A nightly purge erases the evidence and makes a recurring fault look like stability.

## Decisions the automation takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Delete a given instance | Execution | n/a | Fine once the target is certain. |
| "ERROR means junk" | **Judgement** | Not as far as I know. Assumption. | Get an agreed policy from the cloud owner and tenants. |
| "24h is long enough" | Judgement | No | Use a grace period set per class (below). |
| Delete an instance that previously ran | **Judgement, high consequence** | No | Exclude it from automation. Report it to the owner. |

## Scope and blast radius

- **Scope.** `--all-projects` with admin credentials means every tenant, including the ones you don't know about. The target set is implicit "all ERROR".
- **Age filter.** `openstack server list` has `--changes-before` (compute API 2.66 or later), but it filters on `updated_at`, not `created_at`. An instance that errored recently could look old, or the reverse, depending on which field you test. Check the available columns and microversion for your release. Fetching `created` and `updated` per instance and comparing them yourself is the most explicit option.
- **Empty and huge result sets.** On empty input, GNU `xargs` still runs `openstack server delete` once with no arguments unless you pass `-r`. At the other extreme, a RabbitMQ or scheduler incident can put hundreds of instances into ERROR in one night. The one-liner would delete all of them with no sign that it happened.
- **Collateral.** Deleting an instance can also remove ephemeral data and volumes with `delete_on_termination`. It releases floating IPs and ports, and a reclaim or soft-delete setting may change what is recoverable. Verify for your release.

## Safeguards

| Safeguard | Present? | Gap |
|---|---|---|
| Preview / dry run | No | Add a default dry-run mode that prints the target list. |
| Explicit scope | No | Select by class, not by status alone. |
| Confirmation | No | Reasonable for a narrow class. Not for "ran before and now ERROR". |
| Stop conditions | No | Abort and alert if the count is above N or a fraction of the fleet, or if the ERROR rate jumped. |
| Pre-check | No | Re-read status immediately before each delete, since state can change between list and delete. |
| Post-check | No | Confirm the instance is gone, and alert on those stuck in `deleting`. |
| Idempotency | Roughly | A rerun is harmless, but errors are swallowed. |
| Concurrency lock | No | Use `flock` so two runs can't overlap. |
| Evidence capture | No | Log ID, project, name, created, updated, host, fault message and attached volumes before deleting. |

## Failure and recovery

- `xargs -n1` carries on after a failed delete. Failures don't stop the run and won't alert anyone unless you check `xargs`'s exit status (123 when any call failed).
- There is no recovery path once an instance is deleted. The only protection is deciding the target set correctly beforehand, which is why the filter matters most.
- Deleting can hang if the compute host is down. Don't loop on retries. Report those instances.

## A safer shape

I'd split ERROR instances into classes. These are options, and your tenants and policy decide which apply.

1. **Failed-build ERROR.** The instance never ran: no host assigned or a scheduling or build fault, no volumes attached, and older than a grace period. This is the only class I'd consider for unattended deletion. The grace period is a policy choice, so 24h is a reasonable start and 3–7 days is gentler.
2. **ERROR after having run.** It has a host, attached volumes, or a fault from resize, migrate or rebuild. Never auto-delete. Report it to the project owner and the platform team, since it may be recoverable with `reset-state` or may need a post-incident look.
3. **Mass events.** When the count is above the threshold, delete nothing. Alert, and treat it as an incident and preserve evidence (see `openstack-incident-analysis`).

Rollout:
- **Phase 1:** a report-only nightly job, with evidence logged and counts trended. It's also useful on its own as a capacity and health signal.
- **Phase 2:** a tag-then-delete flow that notifies owners and deletes after a grace period.
- **Phase 3:** unattended deletion for class 1 only, with a dry-run flag, `flock`, a per-run cap, and logs sent to your central logging.

Also use a dedicated service user with only the roles it needs, not a general admin account. If you can't verify that the job ran, or that it didn't, it shouldn't be deleting anything.

## Capacity reports

Check what actually confuses your reports. ERROR instances usually count against project quota. Whether they hold placement allocations or compute resources varies by failure point and release, so verify that for your release. If the issue is only reporting, excluding ERROR from the report may fix it without deleting anything.

## Findings

| # | Severity | Finding | Suggested change |
|---|---|---|---|
| 1 | **Blocking** | No age filter in the one-liner. | Filter on a timestamp you've verified. |
| 2 | **Blocking** | Matches previously-running instances, so irreversible data loss is possible. | Restrict auto-delete to failed-build class. |
| 3 | **Major** | No dry run, no cap, no stop condition on mass ERROR. | Add all three. |
| 4 | **Major** | No evidence capture, and it hides recurring faults. | Log before delete and trend the counts. |
| 5 | **Major** | Judgement not explicitly delegated. | Written policy with an accountable owner. |
| 6 | Minor | `xargs` without `-r`, errors swallowed, no lock, no alerting on failure. | Use `-r`, check exit status, add `flock` and failure alerts. |
| 7 | Minor | No owner and no documentation. | Name an owner, keep it in version control, and write a short runbook. |

## Questions for you

1. How many ERROR instances exist now, and what do their faults say? Run these read-only: `openstack server list --all-projects --status ERROR --long -c ID -c Name -c "Project ID" -c Host` and `openstack server show <id> -c fault -c created -c updated` on a sample.
2. Do you already see ERROR instances that were running before? If so, how do owners handle them today?
3. Who owns the policy, and have tenants been told?
4. Which compute API microversion and release are you on? That decides the filters and the soft-delete behaviour.
5. What exactly confuses the capacity reports: quota usage, placement, or the instance counts?

If you paste a redacted sample of that output, I can draft the job as report-only first, then the class-1 delete behind a dry-run flag.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.