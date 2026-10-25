## Summary

**Verdict: Not ready.** Two gates fail (Recovery, Evidence) and several others are unknown. Nothing you've told me shows a way back to a trusted state.

**Depth:** Full review. Five services are changing at once, including the Keystone and database schema changes, and a restore has never been shown to work.

**Top risks:**
1. **Recovery is unproven.** Nobody on the team has demonstrated a control-plane restore. The last test was 2 years ago, by someone who left. Upgrades include schema migrations that are hard to reverse, so a backup you can't restore is a gamble.
2. **`nova-manage db online_data_migrations` was never completed after the last upgrade.** Upstream treats it as a hard prerequisite of the next upgrade. Skipped migrations can make the next schema sync refuse to run, or leave data in a state the new code doesn't handle. You would find this out mid-window.
3. **The 2 Nova scheduler patches are untested against the target release.** The other 7 patches are unassessed. Policy changes haven't been looked at, so users or automation could lose permissions the moment the services restart.

## Objective and four questions
- **Objective:** *Unknown.* "Upgrade next week" is not a problem statement. What forces the date: end of maintenance for the current series, a security fix, a needed feature, or a vendor deadline? That decides how much delay is acceptable. If the current series is approaching End of Life, waiting has a real cost and I'd want to weigh it. If not, the date is just a plan.
- **Capability protected or created:** unknown.
- **Capability put at risk:** compute, network, volume, image and identity APIs, plus every consumer that depends on them.
- **Added operational burden and knowledge:** the 9 patches must be carried forward or retired, and the one person who understood recovery is gone.

## Starting state
- **Platform stability today:** unknown, no evidence provided.
- **Known-bad state (Observed, from your facts):** the previous upgrade was never finalized. The data migrations are outstanding, so the platform is not in a clean "fully upgraded" state.
- **Other changes in the window:** unknown. Please confirm there are none.

## Scope and blast radius
- Keystone failures reach every service and every user.
- A Nova failure reaches the scheduler and instance placement. The Nova API/conductor and compute agents are involved, and Placement must go first.
- Neutron's contract phase can mean a Neutron API outage. Treat it as a potential point of no return.
- Cinder and Glance affect volume and image operations. Whether running instances are disrupted depends on your backends, which I don't know.
- Failure domains, workload criticality and consumer inventory were not provided.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | No impact statement. No accountable owner has accepted the failure case. |
| Recovery | **fail** | Restore last tested 2 years ago (Reported), by a departed engineer. No credible, exercised way back. |
| Evidence | **fail** | No upgrade rehearsal mentioned. The patches and policy are unassessed. Tool compatibility rests only on release notes (Reported). |
| Owner | unknown | Owners per service not named. Restore knowledge has left with the engineer. |
| Authority | unknown | Approver not named. |
| Blast radius | unknown | No batching or scope limits described. |
| Mandatory requirements | unknown | No security or regulatory constraints stated. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Restorable backups (DB, config, Fernet/credential keys) shown by an actual restore | fail | unknown |
| Rehearsal in a representative environment, including the deployment tool | unknown | unknown |
| Outstanding `online_data_migrations` completed on the current release | fail | unknown |
| `*-status upgrade check` run for each project, using target-release code | unknown | unknown |
| 9 patches triaged: still needed, merged upstream, or conflicting | fail (2 Nova scheduler patches are the biggest risk) | unknown |
| Policy reviewed against real users and automation | fail | unknown |
| Non-OpenStack stack supports the jump (OS/Python, RabbitMQ, MariaDB, network and storage backends) | unknown | unknown |
| Compute batch capacity and window length | unknown | unknown |
| Monitoring works on the target release | unknown | unknown |
| Consumers informed | unknown | unknown |

On the deployment tool: its release notes saying the jump is supported (Reported) tell you the authors intend it to work. They don't tell you it works on your environment with your 9 patches. Likewise, SLURP only covers OpenStack services. Please also confirm that your current release is itself a SLURP release. Skipping is only valid between SLURP releases.

## Recovery
- **Method:** restoring the DB and control plane from backup, or rolling forward. Neither has been exercised.
- **Point of no return (Assumption, verify for your release):** completed schema migrations and Neutron's contract phase. After either, you can't simply reinstall the old packages. Recovery means a restore, which brings us back to the untested restore.
- **Evidence to preserve before starting:** full DB dumps, configs and policy files, the patch set, Fernet and credential keys, service and version inventory, and the pre-upgrade check output.
- **If this proceeds as planned:** a failed schema migration or a bad scheduler patch would leave you with no tested route back, a platform that may be partly on new code, and no one who has done a restore. That is the risk the accountable owner would be accepting.

## Execution boundaries and stop conditions
These are proposals for your own baselines to fill in. I don't set universal thresholds.
- Stop if a pre-upgrade check reports a failure or warning nobody can explain.
- Stop if a migration errors or takes far longer than the rehearsal.
- Stop if monitoring can't see the affected service.
- Stop if recovery stops being credible (for example, a backup fails verification).
- Stop if compute batches degrade critical workloads past the agreed threshold.
- Stop if the decision-maker is unreachable.
- Stopping and resuming later is a new decision.

## Verification
Design these before the window, not during it:
- Create and delete an instance, a volume, an image and a network end to end.
- Authenticate through Keystone as a normal user, a service account and your automation accounts.
- Check scheduling behavior against what the 2 patches change.
- Run the `online_data_migrations` completion check and confirm it reports nothing left.
- Confirm all services are healthy and watch an agreed observation period. The new state doesn't inherit trust from the old one.

## Decision rights
| Role | Who |
|---|---|
| Technical assessor | unknown |
| Capability owner | unknown (per service) |
| Accountable | unknown |
| Decision maker | unknown |
| Consumer communication | unknown |

## Gaps and questions
1. What is the driver for next week, and what happens if you wait a few weeks (EOL, security, vendor deadline)?
2. Which release are you on, and is it a SLURP release? Which is the target?
3. Why were the online data migrations never run? Is it known how much is outstanding (read-only check first)?
4. What do the 9 patches do? What do the 2 scheduler patches change, and are they upstream in the target?
5. What is the backup procedure, and where are the backups?
6. Has any rehearsal environment been built?
7. What do your OS, Python, RabbitMQ, MariaDB and storage/network backends run, and do they support the target?
8. Who are the owner, approver and on-call during the window?

## What would close the gaps (suggested order)
1. **Run a restore exercise** in an isolated environment from a current backup. The runbook should be written so someone other than its author can follow it. This also rebuilds team knowledge. State-changing only in the scratch environment.
2. **Take a fresh backup, then complete `online_data_migrations` on the current release.** This changes production data. It needs approval and a verified backup first. It should be a separate, earlier change with its own verification, not part of the upgrade window.
3. **Rehearse the full upgrade** in a representative environment with the deployment tool, the patches and a copy of the real policy.
4. **Triage the 9 patches** and run the status checks against target code (read-only).
5. **Review policy** against real users and automation.
6. **Then** pick a new date.

Moving the date is sequencing, not resistance. If the driver is a hard deadline, the accountable owner should see this record and decide explicitly. I can describe what they would be accepting, but I would not soften the verdict.

## Decision record (draft)
- **Change / decision:** Upgrade Nova, Neutron, Cinder, Glance and Keystone by one release via SLURP.
- **Date:** proposed for next week. Review verdict: Not ready.
- **Decision owner / Capability owner / Technical assessor:** unknown.
- **Objective:** unknown. Driver for the date not stated.
- **Current state:** previous upgrade not finalized (data migrations outstanding). Restore untested for 2 years. 9 local patches (2 in the Nova scheduler). Policy not reviewed.
- **Evidence:** deployment tool release notes claim support for the jump (Reported). No rehearsal or tests shown.
- **Uncertainty:** restorability, patch compatibility, policy impact, migration state, third-party stack support, platform health.
- **Options considered:** go next week (rejected for now: Recovery and Evidence gates fail). Postpone and prepare (recommended). Other options unknown.
- **Selected option:** pending the owner's decision.
- **Recovery:** none demonstrated. Required before proceeding: a restore exercise.
- **Stop conditions:** see above.
- **Verification:** see above.
- **Follow-up:** record why the date moved so it isn't read as inertia. Review which patches can be removed after the upgrade. Set an expiry date on any risk acceptance.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process. Release-specific mechanics (SLURP rules, status tools, Nova N-2 tolerance, Neutron contract behavior) should be verified against current upstream and vendor documentation for your releases.