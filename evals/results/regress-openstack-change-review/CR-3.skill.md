## Summary

**Verdict: Not ready.** I would not run this next week. Three gates fail or are unknown (recovery, evidence, owner/authority), and one fact (skipped online data migrations) is a likely hard blocker.

**Review depth: full.** The change touches five core services in a production control plane. It includes schema migrations that may pass a point of no return, and recovery has not been shown to work.

**Top 3 risks**
1. **Recovery is unproven.** The last control-plane restore test was 2 years old, run by someone who has left. This is Reported, not Observed. No one on the team has demonstrated recovery. The upgrade-readiness reference says the first action may then be a recovery exercise rather than the upgrade.
2. **Online data migrations were never completed after the last upgrade.** Upstream treats `nova-manage db online_data_migrations` as a hard prerequisite of the next upgrade. Skipped migrations can make the next schema sync refuse to run, or leave data in an old format the new code doesn't expect. Cinder has the same mechanism. Neutron, Keystone and Glance have their own schema or data-migration steps. Verify these per release.
3. **Unreviewed divergence.** There are 9 local patches, 2 of them in the Nova scheduler, and the policy changes haven't been looked at. A scheduler patch that conflicts with the new code, or one made redundant by it, can break or distort placement. Policy defaults can silently change what users, automation accounts and integrations are allowed to do.

## Objective and four questions
- **Objective: unknown.** "Upgrade" isn't a problem statement. Is it support or security-maintenance status, a needed feature, or a deployment-tool constraint? The answer decides how much waiting costs. If the current release is Unmaintained or End of Life, delay is itself a risk. If not, a few weeks of preparation is cheap.
- **Capability created or protected:** unknown (see above).
- **Capability affected:** API availability, provisioning, and the identity and network control plane. Running instances should stay up if the data plane is untouched (verify for your backends).
- **Added burden:** retesting 9 patches at each future upgrade.
- **Operating it afterwards:** needs an owner and a restore capability, and neither is evidenced today.

## Starting state
- **Release versions:** unknown. "Jump one release using SLURP" is ambiguous. A SLURP hop normally skips an intermediate non-SLURP release, so please state exact from/to versions.
- **Current platform health:** unknown. I have no output showing it is stable.
- **Other changes in the same window:** unknown. Don't stack OS, deployment-tool, RabbitMQ or MariaDB changes with this one.
- **Database state:** known to be untrusted. Online migrations are incomplete since the last upgrade (Reported).

## Scope and blast radius
- **Services:** Nova (plus Placement), Neutron, Cinder, Glance and Keystone. Keystone sits under every other API.
- **Shared dependencies:** the database, RabbitMQ, and agents or computes on every host.
- **Neutron contract phase:** it needs all neutron-server instances stopped, which is a Neutron API outage. Treat it as a potential point of no return.
- **Compute fleet:** rolling the computes depends on migration headroom, which is unknown.
- **Consumers:** tenants, automation, and anything calling the APIs under the old policy. Not yet identified.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | No owner has accepted the failure case. Window and consumer impact are not stated. |
| Recovery | **fail** | Restore last tested 2 years ago by a departed engineer. No demonstrated recovery on the current team. |
| Evidence | **fail / unknown** | No staging or rehearsal run is mentioned. "Tool release notes say it supports the jump" is documentation, not a demonstrated run on this deployment. |
| Owner | unknown | No named owner per service or for recovery. |
| Authority | unknown | No named person has accepted the risk. |
| Blast radius | unknown | No batching or scope plan for computes, and no control-plane stop conditions. |
| Mandatory requirements | unknown | Security or regulatory constraints are not stated. The policy review also bears on this. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Online data migrations complete on **current** release (Nova, Cinder; check others) | **fail** (Reported never run) | unknown |
| Fresh DB and config backup, **and a restore rehearsed** | **fail** | unknown |
| Rehearsal of the full upgrade in a representative environment, with the deployment tool | unknown (none mentioned) | unknown |
| Target-release `*-status upgrade check` outputs (nova, neutron, cinder, placement) | unknown | unknown |
| Inventory of the 9 patches: origin, owner, purpose, test, still needed or applicable on target; the 2 scheduler patches first | **fail** (scheduler patches unreviewed) | unknown |
| Policy review: custom policy files, `enforce_new_defaults` / `enforce_scope` state, test with real users and automation | **fail** (not looked at) | unknown |
| Deployment tool, OS and Python, RabbitMQ, MariaDB and network/storage backends all support the jump | unknown (only tool release notes, Reported) | unknown |
| Compute migration headroom and window length | unknown | unknown |
| Monitoring able to see the new release | unknown | unknown |
| Runbook with decision points, usable by someone other than its author | unknown | unknown |

## Recovery
- **Method:** unknown. A restore from backup is the likely path, but it hasn't been exercised.
- **Exercised?** No, not in 2 years, and not by anyone still on the team.
- **Point of no return (candidates):**
  - completed schema migrations and contract phases;
  - the Neutron contract;
  - the data migrations run during the upgrade;
  - Keystone and Fernet changes.
- **Preserve before starting:** DB dumps, configs, Fernet and credential keys, policy files, a copy of the 9 patches, and pre-change service and version inventory.
- **Consequence of proceeding anyway:** if the upgrade fails after a schema step, the only way back may be an untested restore. The accountable owner would be accepting an unbounded outage. This is a fail on the recovery gate, not something a schedule can offset.

## Execution boundaries and stop conditions
To define before execution; none are stated yet.
- **Boundaries:** the order of operations, batch sizes and migration rates (your baselines, which I don't have), and a freeze on resource creation during the control-plane steps.
- **Stop conditions:**
  - a status check fails on the target release;
  - a migration errors or runs unexpectedly long;
  - an expected dependency behaves differently;
  - the compute batch exceeds approved scope;
  - monitoring can't see the effect;
  - recovery is no longer credible;
  - the decision authority is unavailable.
- Resuming after a stop is a new decision.

## Verification
Define this before the window.
- **End to end:** create, reach and delete a test VM, volume and port, plus image upload and token issuance.
- **Placement:** compare scheduler decisions against a baseline, because of the 2 scheduler patches.
- **Policy:** run the real automation accounts.
- **Dependencies:** DB, RabbitMQ and agents healthy.
- **Observation period:** the length is your decision; the new state should earn trust.

## Decision rights
- **Technical assessor:** unknown.
- **Capability owner:** unknown.
- **Accountable:** unknown.
- **Decision maker:** unknown.
- **Consumer communication:** unknown.

Name all five before the window.

## Gaps and questions
1. Exact current and target releases, and the deployment tool and its version.
2. What is driving the date? Is the current release out of maintenance?
3. Has any rehearsal been done in a representative environment?
4. What do the 9 patches do? Who wrote them? Are they in upstream target?
5. Output of `nova-manage db online_data_migrations` (read-only dry check) and the matching Cinder/other state. Check what is pending and why it was skipped.
6. Who owns recovery now?
7. Policy overrides and which automation accounts and integrations exist.
8. Do OS, Python, RabbitMQ, MariaDB and the network/storage backends support the target?
9. Capacity for compute batches.

## Suggested path (sequencing, not resistance)
1. **Now, read-only:** collect the items in Gaps 5, 7 and 8, and run the target-release status checks from a rehearsal copy.
2. **Take a fresh backup, then run the pending online data migrations on the current release** (state-changing; needs an approving owner). Fix any migration that errors on its own, before the upgrade.
3. **Run a restore rehearsal** into an isolated environment, written up so someone else can repeat it.
4. **Review the 9 patches and the policy.**
5. **Rehearse the full upgrade** with the deployment tool, then re-review. Next week is realistic only if all of this fits, and I'd expect it not to. If the current release is already Unmaintained or End of Life, the owner should weigh that risk explicitly.

## Decision record (draft)
- **Change / decision:** SLURP upgrade of Nova, Neutron, Cinder, Glance, Keystone. From/to: unknown.
- **Date:** planned next week; review verdict Not ready.
- **Decision owner / capability owner / technical assessor:** unknown.
- **Objective:** unknown.
- **Current state:** online data migrations incomplete since the last upgrade (Reported); 9 local patches (2 in the Nova scheduler); policy impact not reviewed; last restore test 2 years ago (Reported).
- **Evidence:** deployment-tool release notes claim support for the jump (Reported). No rehearsal, status checks or restore evidence.
- **Uncertainty:** patch compatibility, policy impact, migration state, recovery viability, supporting component compatibility, capacity.
- **Options considered:** (a) proceed next week, rejected: recovery gate fails; (b) postpone and prepare (recommended); (c) others unknown.
- **Trade-offs:** postponing keeps current-release exposure (depends on maintenance status); proceeding risks an outage with no demonstrated recovery.
- **Selected option:** none yet. Record that postponement is for unproven recovery, not inertia.
- **Recovery:** untested; must be rehearsed first.
- **Stop conditions / Verification:** as above, to be finalised.
- **Follow-up:** remove patches the target makes unnecessary; document the restore procedure; review this record's risk acceptance date.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.