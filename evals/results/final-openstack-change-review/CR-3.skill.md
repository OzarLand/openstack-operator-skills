## Summary

**Verdict: Not ready.** The upgrade shouldn't start next week as planned. Three gates fail or are unknown (recovery, evidence, and the state of the database migrations), and none of them can be closed in a week unless the scope shrinks.

**Review depth:** Full. This is a multi-service control-plane upgrade across five services with a schema point of no return and no recently demonstrated recovery. The cost of being wrong is high, so I used the heaviest depth.

**Top 3 risks:**
1. **Unproven recovery.** Nobody currently on the team has restored the control plane. The last test was 2 years ago, run by someone who left. If the database migration fails midway, you have no demonstrated way back.
2. **Skipped `online_data_migrations`.** You never ran `nova-manage db online_data_migrations` after the last upgrade. Upstream treats this as a hard prerequisite for the next upgrade. The schema sync may refuse to run, or you may find a data problem in the middle of the window.
3. **Unassessed carried changes and policy.** The 9 local patches (2 in the Nova scheduler) haven't been checked against the target release. Policy changes haven't been looked at, and the secure-RBAC defaults can silently remove permissions that users, automation and integrations rely on.

## Objective and four questions

- **Objective:** Unknown. "Upgrade five services by one SLURP jump" describes an action, not the problem it solves. I'd need to know what is driving it: the end of maintenance for your current series, a security fix, a feature, or avoiding a larger jump later. This matters because it decides whether waiting is the bigger risk.
- **Capability protected or created:** unknown (see above).
- **Capability affected:** compute scheduling, networking, volumes, images and authentication. In practice that is every API and every tenant workflow.
- **Operational burden added:** unknown. Removing local patches could reduce it. Carrying 9 of them forward would add to it.
- **Operating it afterwards:** unknown. This depends on who owns the platform after the restore-test engineer left.

## Starting state

- **Reported:** the last upgrade left the online data migrations incomplete, so the starting state is not clean.
- **Unknown:** current platform health, monitoring baselines, and whether other changes are planned for the same window. Please confirm nothing else is scheduled.
- **Unknown:** the current and target releases, and their maintenance status.
- **Not established:** that the current state is trusted. An unfinished migration from the last upgrade means it isn't.

## Scope and blast radius

- **Touched:** Keystone (all authentication), Nova (scheduling, with 2 local patches), Neutron (networking), Cinder (volumes), Glance (images). The database, the message bus, Placement and the compute-node agents are touched as well.
- **Failure domain:** the whole region's control plane. Running instances normally keep running through a control-plane failure, but you lose the ability to create, change or recover anything.
- **Consumers:** all tenants and any automation using the APIs. This includes policy-sensitive integrations.
- **Neutron contract phase:** it requires every neutron-server to be stopped, so treat it as a control-plane outage window and a possible point of no return.
- **Upgrading all five at once** makes the blast radius larger than it needs to be. Keystone and the others can be sequenced.

## Decision gates

| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | No statement of acceptable downtime or failure impact from an accountable owner. |
| Recovery | **fail** | Reported: last restore test was 2 years ago, by someone who left. Nobody on the team has demonstrated it. |
| Evidence | **fail** | Reported only: the tool's release notes claim the jump is supported. The plan hasn't been run in a representative environment, and nothing shows the 9 patches work on the target release. |
| Owner | unknown | No owner named for the platform or for each service. |
| Authority | unknown | Nobody named as able to accept the consequences. |
| Blast radius | fail | Five services in one window, with no batching or scope limits stated. |
| Mandatory requirements | unknown | Security and regulatory requirements haven't been checked against the policy changes. |

## Prerequisites

| Prerequisite | Status | Owner |
|---|---|---|
| Complete `nova-manage db online_data_migrations` and confirm it reports nothing left | **Not done** | unknown |
| Run `nova-status`, `neutron-status`, `cinder-status` and `placement-status upgrade check` | unknown | unknown |
| Full upgrade rehearsal in a representative environment, including the deployment tool | unknown (none mentioned) | unknown |
| Restore test of the database and message bus, run by someone currently on the team | **Not done** | unknown |
| Review of each of the 9 patches against the target release (2 in the scheduler) | **Not done** | unknown |
| Policy review: `enforce_new_defaults` and `enforce_scope`, plus any local policy overrides, tested with real users and automation | **Not done** | unknown |
| Confirm the OS, Python, RabbitMQ, MariaDB, networking backend and storage backend all support the jump | unknown | unknown |
| Migration headroom for compute batches, and window length | unknown | unknown |
| Written runbook usable by someone other than its author | unknown | unknown |

**On the deployment tool.** Its release notes say it supports the jump. That is a **Reported** claim from the vendor's documentation. It is useful, but SLURP only covers the OpenStack services themselves. The tool's support doesn't tell you whether your configuration, your patches or your environment work. Also check which tool and version you run, since support can depend on both.

**On "jumping one release with SLURP".** SLURP supports upgrades between consecutive SLURP releases, and adjacent ones. Please confirm the current and target releases really are consecutive SLURP releases. If you are more than one SLURP behind, you'd need to hop through each intermediate one. Verify this against the current upstream release documentation.

## Recovery

- **Method:** unknown. I assume a database and message-bus restore plus a redeploy of the previous release, but the plan doesn't say.
- **Exercised?** No, not recently, and not by anyone currently on the team.
- **Point of no return:** unknown, but likely at the completed database schema migrations, and at the Neutron contract phase (it needs all neutron-servers stopped). After either, going back means restoring from backup, which is the step nobody has tested.
- **Evidence to preserve before starting:**
  - Database backups for all five services, and proof they restore.
  - Current configuration and policy files.
  - Copies of the 9 patches and the exact versions they apply to.
  - Current service, agent and migration state.

The recovery gate fails unless the accountable owner explicitly accepts the consequence of having no tested path back. I'd advise against accepting it for a control-plane upgrade.

## Execution boundaries and stop conditions

The plan has none that I can see. Suggested conditions, with thresholds for you to set from your own baselines:
- A status check or dry run reports a problem that wasn't expected.
- Any migration fails, or a service won't start after its migration.
- Rollback is no longer credible, for example a backup turns out to be unrestorable.
- A dependency (the bus, the database, or a patched scheduler) behaves differently from the rehearsal.
- Monitoring can't see the effect of a step.
- The person with authority to decide is unreachable.
- Time already spent is not a reason to continue. Resuming after a stop is a new decision.

Suggested boundaries: upgrade in stages rather than all five at once (for example Keystone first, then the others), and upgrade compute nodes in batches. Batch sizes depend on your capacity, which I don't have.

## Verification

Define these before the window:
- End-to-end checks: create and delete an instance, a volume, an image and a network, and authenticate through Keystone as a real tenant and as automation.
- Scheduler behavior checked against what the 2 scheduler patches were meant to do.
- Policy checks: key users and automation accounts still hold the permissions they need.
- Service, agent and Placement health, plus confirmation that online data migrations are complete.
- An observation period before declaring success. The length should come from your own baselines.

## Decision rights

- **Technical assessor:** unknown
- **Capability owner:** unknown
- **Accountable:** unknown
- **Decision maker:** unknown
- **Consumer communication:** unknown. Someone needs to tell tenants what to expect, such as suspended resource creation during the window.

## Gaps and questions

1. What is driving the upgrade, and what is the cost of waiting a month or two?
2. What are the exact current and target releases?
3. What does the deployment tool's support claim cover, and is it for your tool version?
4. Why were the online data migrations skipped? Are other things from the last upgrade also incomplete?
5. What do the 9 patches do? Are they upstreamed, replaceable, or still needed in the target?
6. Is there a staging environment that matches production?
7. Who is the accountable owner and the decision maker?
8. Are other changes scheduled in the same window?

## Recommended path

This is sequencing, not resistance. I'd suggest this order, with the dates set by your team:

1. **Stabilise the starting state.** Run `nova-manage db online_data_migrations` (state-changing, so do it under your change process and take a backup first). Check the `*-status upgrade check` tools (read-only).
2. **Run a restore exercise** with a current team member, ideally with a second person observing and writing the runbook. Do this before the upgrade, not alongside it.
3. **Assess the 9 patches and the policy changes.**
4. **Rehearse the full upgrade** in a representative environment, including the deployment tool.
5. **Then decide** on a date, with named owners and stop conditions.

If the date is fixed by something external, such as end of maintenance, tell me. That changes the weighing, but it doesn't remove the failed gates. It only shows what the accountable owner would be accepting.

## Decision record (draft)

- **Change / decision:** Upgrade Nova, Neutron, Cinder, Glance and Keystone by one SLURP release
- **Date:** unknown
- **Decision owner / Capability owner / Technical assessor:** unknown

**Objective** — unknown.

**Current state** — Online data migrations from the previous upgrade not run (reported). 9 local patches, 2 in the Nova scheduler (reported). Policy changes not reviewed (reported). Last control-plane restore test 2 years ago, by a departed engineer (reported).

**Evidence** — Deployment tool release notes say the jump is supported (reported, not verified).

**Uncertainty** — Recovery, patch compatibility, policy impact, migration state, dependency support, capacity.

**Options considered** — Proceed next week; postpone until the prerequisites are met; stage by service. Only the first is currently proposed.

**Trade-offs** — Proceeding next week saves time but takes on a database point of no return with no tested restore. Postponing costs a delay, but closes the main gaps.

**Selected option** — None yet. The recommendation is to postpone and prepare, and to record that reason so it isn't read as inertia.

**Recovery** — No demonstrated path.

**Stop conditions** — See above; to be agreed.

**Verification** — See above; to be agreed.

**Follow-up** — Review which local patches can be removed after the upgrade. Write the runbook. Re-run the restore test regularly with more than one person involved.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.