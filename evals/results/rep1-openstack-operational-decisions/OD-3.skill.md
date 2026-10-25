# Recommendation: rebuild, but as a managed migration

I recommend rebuilding, and not waiting to be sure it's needed. This is a test cloud, so I haven't built the full weighted-scoring workup. It wouldn't change the answer.

## Decision to make
- **Situation:** A shared test cloud, years of accumulated state, and fixes that keep causing the next problem.
- **Objective:** Get back to a known, trusted environment at acceptable cost to the teams using it.
- **Decision owner:** Unknown. Someone has to be named (see Decision rights).

## Evidence and uncertainty
| Fact / belief | Confidence |
|---|---|
| Leftover instances, ports and half-applied config changes exist | Reported (you said so) |
| Each fix creates the next problem | Reported |
| Teams "have stuff in there" | Reported, and not quantified |
| Which resources are actually in use | Unknown |
| Whether the config is in code or hand-edited | Unknown |
| Whether anyone can say what the correct config is | Unknown |
| OpenStack release, size, deployment tool | Unknown |

## Why repair is the weaker option
The question that matters is whether the information in the current state is valuable enough to justify preserving its uncertainty. In a test environment the state is mostly leftover experiments. The real asset is each team's data and configuration, and that can be extracted.

"Each fix causes the next problem" suggests nobody knows the intended state. Repairing toward an unknown target has no finish line. Patching also adds more undocumented drift.

"Teams have stuff in there" is a reason to inventory first. It isn't a reason to keep the platform as it is.

## Options
| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| Keep repairing | Open-ended effort. Drift grows. Failures stay unpredictable. | The status quo continues. Teams lose trust in the cloud as a test signal. |
| Rebuild in place | Destroys state before the inventory is verified. | Same as above. |
| **Build a new cloud beside the old one, migrate what's wanted, then decommission** | Needs spare capacity. Takes longer. Teams must act. | Low. |
| Declare it unsupported and let teams self-migrate | Teams that do nothing lose their data. | Low. |

## Gates
Rebuilding in place fails the "credible recovery path" gate, because there's no way back if an owner is missed. Repairing indefinitely fails the "lacks sufficient evidence" gate, because no one can show it converges. A parallel build with a time-boxed migration passes both.

## What the rebuild requires
1. **Preserve evidence first.** Snapshot configs and the DB, and save the output of `server list --all-projects`, port, volume and network lists. These are all read-only. They also show how the config drifted.
2. **Inventory by owner.** Send each team its project's resources and ask them to claim or release them. Unclaimed resources get a deadline, then are archived and dropped.
3. **Define the baseline.** The new cloud is built entirely from version-controlled config, with validation tests (boot a VM, attach a volume, floating IP, a Heat or Terraform smoke test). Automated installation alone is not proof of equivalence.
4. **Migrate in waves.** Stateful items, such as volumes and images, should be exported or snapshotted. Disposable instances should be redeployed from team IaC where it exists.
5. **Set a hard cutover date and an archive period** for the old cloud, so it doesn't become permanent.

## What you're accepting
- Temporary capacity for two clouds.
- Some teams will discover their "stuff" was undocumented. That's a cost of rebuilding, but it's also a finding.
- Test results from the old cloud won't be comparable to the new one.

## Decision rights
- Platform team: technical assessment and the build.
- Whoever funds or owns the test cloud: accepts the cutover date and the loss of unclaimed resources.
- Team leads: confirm what they need kept.
- If nobody is accountable for the cloud, name someone first. That gap is probably part of why it ended up this way.

## Owner, review trigger, exit condition
- **Reopen the decision if** the inventory shows that most resources are actively used and can't be migrated. In that case, scope a targeted cleanup of the unused remainder instead.
- **Exit condition for the old cloud:** the cutover date plus the archive window.
- **Prevent recurrence:** quotas, resource TTLs or tagging, a change-via-code rule, and a periodic orphan sweep. Without these the new cloud will look like the old one in two years.

## How we'll know it worked
- A fresh build from code reproduces the same result.
- Validation tests pass.
- The number of "mystery" resources stays near zero at 90 days.
- Fix-causes-new-problem incidents stop.

## Gaps that would change my answer
- Release and deployment tool (Kolla-Ansible, Juju, hand-built?). This affects how reproducible the rebuild is.
- Whether any team uses the cloud for something close to production.
- Whether there's spare hardware for a parallel build. If not, a phased in-place rebuild by node pool is possible, but riskier.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process. Verify release-specific behaviour against your OpenStack version.

If you want to pass this on to the team, I can publish it as a private page.