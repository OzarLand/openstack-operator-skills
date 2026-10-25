## Summary

**Verdict: Not ready.** Do not run the upgrade next week. The recovery gate fails, and the evidence gate and the prerequisites for the Nova upgrade are unproven or failing. I don't expect all of that to close in a week.

**Depth:** full review. This is a multi-service, control-plane upgrade of production with schema migrations, so it has a large blast radius and parts of it can't be undone.

**Top 3 risks:**
1. **No demonstrated recovery.** The last control-plane restore test was 2 years ago, and the engineer who ran it has left. A failed schema migration or contract phase would have no proven way back.
2. **Skipped `online_data_migrations`.** The upstream notes say skipped migrations make the next schema sync refuse to run. You may fail partway through the upgrade, after services are already stopped.
3. **Untested carried divergence.** Nine local patches, two of them in the Nova scheduler, have not been tested against the target release. Policy changes are also unreviewed.

I'm treating "one SLURP jump" as the plan, as you described it.

## Objective and four questions
**Observed:** nothing beyond your message. The business reason for upgrading next week (a deadline, end of maintenance for the current series, a security driver) is **unknown**. The review depends on it, because if the current series is about to lose maintenance, waiting has a cost.
- **Capability created or protected:** unknown. Presumably a maintained release.
- **Capability that could be affected:** every API and the VM lifecycle. Scheduling is affected through the 2 patched scheduler paths.
- **Operational burden added:** unknown.
- **Needed afterwards:** the team has lost its only known restore expert, so ownership after the change is unclear.

## Starting state
Not trusted. Evidence:
- **Reported:** `online_data_migrations` were never run after the last upgrade, so the database is in a half-finished state.
- **Reported:** recovery was last demonstrated 2 years ago by someone who has left.
- **Unknown:**
  - Current platform health.
  - Whether other changes are scheduled in the same window.
  - Which release you are on and which you are targeting.
  - The OS, Python, RabbitMQ and MariaDB versions.

## Scope and blast radius
- **Services:** Nova, Neutron, Cinder, Glance and Keystone, which is the whole control plane.
- **Keystone** is a dependency of every other service and of every consumer's authentication.
- **Nova** is upgraded together with Placement, and its computes are touched in batches.
- **Neutron** has an expand/contract schema, and the contract phase needs every neutron-server stopped. That is a Neutron API outage and a potential point of no return.
- **Policy:** changed defaults can silently remove permissions from users, automation and integrations.
- **Consumers:** tenants and any automation that calls the APIs. Number and criticality are unknown.
- **Failure domains and batching:** unknown.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | **Unknown** | There is no stated outage tolerance and no accountable owner who has accepted the failure case. |
| Recovery | **Fail** | The last restore test was 2 years ago and its author has left. A restore cannot be assumed to work today. |
| Evidence | **Fail** | There are no test results. The only support cited is the release notes ("supports the jump"), which is documentation, not a demonstration. |
| Owner | **Unknown** | No named owner is given for the capabilities or for recovery. |
| Authority | **Unknown** | Not stated. |
| Blast radius | **Unknown** | No batch plan, no scope limits and no capacity figures were provided. |
| Mandatory requirements | **Unknown** | Not stated. |

Any failed gate means "not ready: improve the condition first." That applies here regardless of the date.

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Upgrade rehearsed in a representative environment, including the deployment tool | **Unknown, likely missing.** Nothing shown. | unknown |
| Backups taken **and restored** | **Fail.** Restore not exercised for 2 years. | unknown |
| `nova-manage db online_data_migrations` completed | **Fail.** Never run since the last upgrade. | unknown |
| `*-status upgrade check` run with **target** release code | **Unknown** | unknown |
| 9 local patches triaged | **Fail.** 2 of them are in the Nova scheduler. | unknown |
| Policy review (RBAC defaults, overrides) | **Fail.** Not looked at. | unknown |
| Whole stack supports the jump (OS, Python, RabbitMQ, MariaDB, network and storage backends) | **Unknown** | unknown |
| Capacity for batching computes | **Unknown** | unknown |
| Runbook with decision points | **Unknown** | unknown |
| Monitoring works on the new release | **Unknown** | unknown |

### Points on your specific facts

**1. "The deployment tool's release notes say it supports the jump."**
- SLURP is a promise about OpenStack services only.
- The release notes don't tell you the OS, Python, RabbitMQ, MariaDB, or network and storage backends support the same jump.
- They don't tell you your own patches, config and policy overrides survive it. I'd count this as **Reported** and untested, not as evidence.
- Verify against the tool's current docs for your exact versions.

**2. `online_data_migrations` never run.**
- This is the most concrete blocker.
- Upstream, completing them is a hard prerequisite of the next upgrade.
- You need to run them now, on the current release, and confirm they report nothing left to migrate. This is `state-changing`: it runs in the production database, so it needs a current backup and an approver.
- Start it well before the window.
- It may reveal data problems that you want to find in a week of calm, not mid-window. How long it takes depends on your data volume, which is unknown.
- Some of what it does can't be reversed afterwards. Treat it as part of the change, with its own recovery path.

**3. The 9 local patches.** For each one, record these:
- What it fixes.
- Who owns it.
- Whether the target release already includes it.
- Whether it still applies cleanly.
- Whether it touches the DB schema, RPC versions or APIs.

The 2 scheduler patches are the most dangerous. Placement and scheduling behaviour is the hardest to see failing: nothing errors, but instances land in the wrong place or fail to schedule. They need a functional test with representative flavours, aggregates and host counts. Whether the 9 patches are all carried in your build, and how, is unknown.

**4. Restore not tested for 2 years.**
- Since nobody currently on the team has done it, the first action should be a recovery exercise, not the upgrade.
- Restore the database and the message bus configuration into an isolated environment, and time it.
- Write the procedure down so that someone other than its author can follow it.
- Also check what a restore would lose: the data written between backup and failure.

**5. Policy changes not reviewed.**
- The secure-default RBAC work changed defaults and added `enforce_new_defaults` and `enforce_scope`, with old defaults being removed over several releases.
- Which of those apply depends on which release you are on and which you are going to, so check the release notes of every release you cross, including the intermediate one you skip.
- Test with real users, service accounts and automation (CI, billing, monitoring, Terraform and similar).
- Any locally overridden policy file is a carried divergence, like a backport.
- A permission regression here looks like an outage to consumers while every service is healthy.

## Recovery
- **Method:** unknown. A full control-plane restore is the only way back once schema migrations complete, because OpenStack database migrations are generally one-way. Verify for your release.
- **Exercised?** No, not within 2 years and not by anyone present.
- **Points of no return** (candidates):
  - Completed schema migrations.
  - The Neutron contract phase.
  - `online_data_migrations` on the new release.
  - Compute nodes already running new code, with VMs now having new-release state.
- **After the point of no return:** recovery means roll-forward, or restore plus an accepted loss of everything written since the backup. Neither has been demonstrated.
- **Evidence to preserve before starting:**
  - A database dump and the config for all five services.
  - Deployment tool inventory and variables, with secrets kept out of any ticket or record.
  - A listing of instances, ports, volumes and images for comparison.
  - The output of the status checks.

If you proceed anyway, the accountable owner would be accepting that a failure may have no tested way back and that the outage lasts as long as an improvised restore takes. That is a decision for them to make explicitly, in writing. It doesn't change this verdict.

## Execution boundaries and stop conditions
**Boundaries still to be defined (unknown):** batch size, compute headroom, API freeze scope and the maintenance window. I won't invent numbers. Use your own baselines.

**Stop conditions to agree beforehand:**
- Any `*-status upgrade check` with the target code reports a failure.
- `online_data_migrations` doesn't finish clean.
- A service behaves differently from the rehearsal.
- Monitoring can't show the new state.
- Recovery is no longer credible (for example, a backup fails verification).
- The decision authority isn't reachable.
- A canary workload degrades past an agreed threshold.

Time already spent is no reason to continue. Resuming after a stop is a new decision.

## Verification
Define this before execution:
- **End to end:** boot a VM, attach a volume, create an image, authenticate with each persona and automation account, and do a network create, floating IP and connectivity test.
- **Dependencies:** services healthy, no queue build-up, Placement resource counts match the pre-change listing.
- **Scheduler:** a defined set of placement scenarios for the 2 patched paths gives the same results as before.
- **Policy:** the permission matrix of roles against actions matches expectations.
- **Observation period:** the new state earns trust and doesn't inherit the old one's. The length is for you to set.

## Decision rights
- **Assessor:** unknown.
- **Capability owner:** unknown.
- **Accountable:** unknown.
- **Decision maker:** unknown.
- **Consumer communication:** unknown. Name who tells tenants what to expect.

## Gaps and questions
1. What is driving next week? Is there a hard deadline (end of maintenance, a security issue)?
2. Which release are you on and which are you targeting? Do both sit on the SLURP path?
3. What are your OS, Python, RabbitMQ and MariaDB versions? Does the deployment tool document support for those?
4. Is there a staging or lab environment that resembles production?
5. How big is the database, and what are your backup method, frequency and last verified restore?
6. What does each of the 9 patches do? Which are in the target release already?
7. How many compute nodes and tenants, and how much headroom?
8. Is the current platform healthy? What else is scheduled in the window?
9. Who are the owners and approvers?

## What would close the gaps
In order, and each step has its own approver:
1. **Now (`read-only`):** run the `*-status upgrade check` commands to see current state. They only reflect the current release unless run with target code.
2. **`state-changing`, with approval:** run `online_data_migrations` to completion on the current release and confirm.
3. **Restore exercise** in an isolated environment, written up as a runbook someone else can follow. Have a second person execute it.
4. **Patch triage** of all 9, with a scheduler test.
5. **Policy review** and tests against real accounts.
6. **Full rehearsal** in a representative environment with your deployment tool.
7. **Set a new date** based on how long 1–6 actually take.

## Decision record (draft)
- **Change / decision:** upgrade Nova, Neutron, Cinder, Glance and Keystone via SLURP
- **Date:** unknown
- **Decision owner / Capability owner / Technical assessor:** unknown
- **Objective:** unknown (see question 1)
- **Current state:** `online_data_migrations` not run since the last upgrade; 9 local patches (2 in Nova scheduler); policy not reviewed; restore last tested 2 years ago by an engineer who has left (all reported, none observed)
- **Evidence:** deployment tool release notes state the jump is supported (reported; does not cover patches, policy or the rest of the stack)
- **Uncertainty:** restorability, patch compatibility, policy impact, stack support, health, capacity
- **Options considered:** (a) proceed next week; (b) postpone and close the prerequisites first
- **Selected option:** recommended **(b)**. Rejected (a) because the recovery and evidence gates fail. This is sequencing, not resistance. Keep this reason visible so the next team doesn't read the postponement as inertia.
- **Recovery:** none demonstrated
- **Stop conditions / Verification:** as listed above, to be confirmed
- **Follow-up:** review which patches can be dropped after the upgrade; review any accepted risk by a set date

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process. Release-specific mechanics here come from the skill's reference notes and should be verified against current upstream and vendor documentation.