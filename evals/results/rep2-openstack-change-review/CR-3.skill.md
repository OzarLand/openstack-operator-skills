## Summary

**Verdict: Not ready.** Four of the seven gates fail or are unknown, and the plan can't recover from a bad outcome. The target date of next week should not drive this decision.

**Review depth:** Full. This is a five-service control-plane upgrade on production. It crosses a schema point of no return, and the only recovery path has never been exercised by anyone still on the team.

**Top risks**
1. **No demonstrated recovery.** The last control-plane restore test was 2 years ago, by someone who has left. The recovery gate fails.
2. **Skipped `online_data_migrations`.** This is a hard prerequisite, and it was never run after the last upgrade. The next Nova schema sync can refuse to run, or the upgrade can fail partway through.
3. **Unreviewed carried patches and policy.** 9 local patches (2 in the Nova scheduler) have not been checked against the target release. Policy changes haven't been looked at either.

(All of this is Reported. I've seen no command output, configs or patch contents.)

## Objective and four questions
- **Objective:** Unknown. "Upgrade next week" is not a problem statement. Is it because the current release is leaving maintenance, a security issue, a needed feature, or the calendar? This decides whether waiting is the larger risk (see Reconsider below).
- **Capability created or protected:** Unknown, depends on the objective.
- **Existing capability affected:** Identity (Keystone) and image, volume, network and compute provisioning.
- **Operational burden added:** Unknown.
- **Operability after delivery:** Currently weak. Recovery knowledge left with the engineer, and nobody has been named as owner.

## Starting state
- **Reported:** The Nova online data migrations were skipped after the last upgrade. The starting state is therefore **not trusted**: the data may be only partly migrated.
- **Unknown:** Platform health now, other changes in the same window, current and target release names, and the Galera, RabbitMQ, OS, Python and storage/network backend versions.

## Scope and blast radius
Five services are upgraded at once, and Keystone is the dependency for everything.
- **Nova:** Placement, conductor, API and every compute node. The two scheduler patches can change placement behavior for all new instances.
- **Neutron:** The contract phase needs all neutron-servers stopped, so there is a Neutron API outage. Treat it as a potential point of no return.
- **Keystone:** Token and policy changes reach every service and every automation account.
- **Cinder and Glance:** Volume and image operations.
- **Shared:** One database, one message bus, and the consumers' workflows (policy and API behavior changes).
- **Running workloads:** The data plane should be unaffected if the order is followed, but this is unverified.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | No named owner has accepted the failure case. API outage windows (Neutron contract) aren't described. |
| Recovery | **fail** | Restore test is 2 years old and was done by a departed engineer (Reported). Never demonstrated by the current team. |
| Evidence | **fail** | No staging run reported. No `*-status upgrade check` output. Patches and policy unreviewed. |
| Owner | unknown | No owners named per service or for recovery. |
| Authority | unknown | Approver not named. |
| Blast radius | unknown | No batching plan for computes or scope limits. |
| Mandatory requirements | unknown | Security or regulatory constraints not stated. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Release-note claim that the tool supports the jump | **Reported only.** This is a promise, not a test. Verify against the vendor docs for your exact versions. | unknown |
| OS, Python, RabbitMQ, MariaDB, network and storage backends support the same jump | unknown. SLURP covers OpenStack services only. | unknown |
| Both releases are consecutive SLURP releases (or adjacent) | unknown, confirm the actual names | unknown |
| `nova-manage db online_data_migrations` completed | **fail** | unknown |
| `nova-status`, `neutron-status`, `cinder-status`, `placement-status`, `keystone-status` and `glance-status` upgrade checks, run with the **target** code | not done | unknown |
| 9 patches triaged: still needed, merged upstream, or broken by the target | **fail**, not started per you | unknown |
| The 2 Nova scheduler patches rebased and tested against the target scheduler/Placement behavior | **fail** | unknown |
| Policy review (secure-default RBAC, `enforce_new_defaults`, `enforce_scope`, local policy overrides) tested against real users and automation | **fail**, "haven't looked" | unknown |
| Rehearsal in a representative environment with the deployment tool | unknown | unknown |
| Backups of database, Fernet and credential keys, and configs that are **restorable** | **fail** until a restore is shown | unknown |
| Migration headroom and window length for compute batches | unknown | unknown |
| Monitoring that will work on the new release | unknown | unknown |
| A runbook with decision points that someone other than its author can use | unknown | unknown |

## Recovery
- **Method:** Restore from backup, or roll forward. Neither has been exercised.
- **Point of no return (candidates):** Completed schema migrations, the Neutron contract phase, and any removed old keys. After these, "rollback" means a full database restore, which is untested.
- **Exercised?** No. The last test was 2 years ago, by someone who is no longer here.
- **Evidence to preserve before starting:** Database dumps with a verified restore, Fernet and credential keys, all configs and policy files, the list of the 9 patches with their diffs, and a pre-change inventory of services and versions.
- **What proceeding anyway means:** If the upgrade fails after a schema change, nobody on the team has shown they can bring the control plane back. The accountable owner would be accepting an open-ended control-plane outage.

## Execution boundaries and stop conditions
Define these before the window. I can't set thresholds for you. I need your baselines.
- **Boundaries to define:** Compute batch size, API restrictions during the Neutron contract, a freeze on resource creation if needed.
- **Stop if:**
  - any status check returns failure,
  - an expected dependency behaves differently,
  - monitoring can't see the effect,
  - the restore path isn't credible,
  - the scheduler behaves differently in test (placement outcomes),
  - capacity for the batch is missing,
  - the decision authority is unavailable.
- Resuming after a stop is a new decision.

## Verification
Design these before execution:
- End-to-end checks: create and delete an instance, volume, image and network, then boot from a volume.
- Dependencies healthy: services up, Placement and the bus consistent, Galera healthy.
- Nothing new broke: policy tests for real users and automation accounts.
- Scheduler patch behavior compared with the previous release.
- Then an observation period (length is yours to set).

## Decision rights
- **Technical assessor:** unknown
- **Capability owner:** unknown
- **Accountable:** unknown
- **Decision maker:** unknown
- **Consumer communication:** unknown

## Gaps and questions
1. What is the objective, and what happens if the date slips by a month (is a release going out of maintenance)?
2. What exact releases are involved, and what do the deployment tool's release notes say about your OS, RabbitMQ and MariaDB versions?
3. Has any rehearsal run? If not, is a staging environment available?
4. What do the 9 patches do? Which have upstream equivalents?
5. How many online data migrations are pending (read-only check: `nova-manage db online_data_migrations --max-count` in a dry mode, per your release docs, run by your DBA)? Why were they skipped?
6. Who can own and run a restore?
7. What is the window length and the compute count?

## What would make this Ready with conditions
In order:
1. **Do a restore exercise first** (restore the database and bring up a test control plane). Time it and write it down. This is the book's pattern when recovery is undemonstrated.
2. **Finish the Nova online data migrations** on the current release, in a controlled step, and verify.
3. **Run the target-release status checks** and fix what they flag.
4. **Triage the 9 patches** and test the 2 scheduler ones against the target.
5. **Review policy** against real users and automation, in staging.
6. **Rehearse the full upgrade** including the deployment tool.
7. Name owners and an approver, then write the runbook and verify it with someone other than its author.

Reconsider the date, not the upgrade. A delay of weeks for items 1 to 3 is sequencing. If you must go ahead next week anyway, the accountable owner would be accepting an untested control-plane recovery. That doesn't change the verdict.

## Decision record (draft)
- **Change / decision:** Upgrade Nova, Neutron, Cinder, Glance and Keystone, skipping one release via SLURP
- **Date:** unknown (proposed: next week)
- **Decision owner / Capability owner / Technical assessor:** unknown
- **Objective:** unknown
- **Current state:** Online data migrations skipped since the last upgrade (Reported). 9 local patches (2 in the Nova scheduler). Restore last tested 2 years ago by a departed engineer. Policy not reviewed.
- **Evidence:** Release notes claim the tool supports the jump (Reported). No test results shown.
- **Uncertainty:** Everything under Gaps and questions.
- **Options considered:** (1) Upgrade next week. (2) Postpone and close the gaps first. (3) Upgrade after a restore exercise and rehearsal.
- **Trade-offs:** Option 1 saves time but risks an unrecoverable control plane. Options 2 and 3 cost weeks and keep the old release longer. Confirm the old release's maintenance status.
- **Selected option:** Recommended: 2/3. Not yet decided by an owner.
- **Recovery:** Not credible today. Restore must be demonstrated.
- **Stop conditions:** As above.
- **Verification:** As above.
- **Follow-up:** Remove patches the new release makes unnecessary, document the restore procedure, and re-run the review if the date changes. If risk is accepted, record an expiry for it.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process. Release-specific mechanics are summarized from the book and change between releases; verify against upstream and vendor docs.