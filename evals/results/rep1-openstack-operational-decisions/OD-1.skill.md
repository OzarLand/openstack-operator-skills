# Recommendation: none of the three options as written

Do a gated version of option 2. Before any hop, fix the missing conditions that make the other options unsafe. The security backport is the only part that can't wait.

## Decision to make
- **Situation:** unmaintained series, two SLURP hops from a maintained one, and a security advisory with no upstream fix for your series.
- **Objective:** get back to a maintained series without losing the ability to recover the control plane, with a team of four.
- **Decision owner:** unknown. See "Decision rights".

## Evidence and uncertainty
| Fact / belief | Confidence |
|---|---|
| Series left maintenance and is two SLURP releases behind | Reported. Verify on releases.openstack.org and with your vendor. |
| About 12 local patches, 3 in Nova scheduling, author gone | Reported. What the patches do is unknown to me. |
| Control-plane recovery worked once, two years ago, by the engineer who has left | Demonstrated once, two years ago. It is stale and nobody on the current team has repeated it. |
| Team shrank from six to four | Reported |
| Security fix exists only for maintained series | Reported |
| Backport is possible | Hypothesis. Untested. |

Gaps I won't guess at:
- the actual release and your vendor or distribution
- what the Nova patches change
- whether the advisory is exploitable in your network exposure
- whether your vendor already ships the fix
- your test environment fidelity

## Options and gates
| Option | Main risk of doing it | Gate result |
|---|---|---|
| **1. Both hops in one quarter** | Stacks uncertainty: two upgrades, 12 patches and an unproven recovery path, with four people. | **Fails** on recovery path, expertise and blast radius. |
| **2. Hop, stabilize, hop** | Still needs the security gap closed and the patches understood first. | **Passes if** the conditions below are created. |
| **3. Postpone, remove patches, carry backport** | Makes the old series a lifecycle strategy. Each new advisory means another untested local backport. Patch removal is done on a base you're leaving. | **Passes only time-boxed.** Open-ended postponement is the standing-still risk. |
| Keep as is | Known exploitable advisory, no fix path. | Fails the security gate. |

The gates fail because conditions are missing, so the first action is to create them. The upstream guidance is that a platform far enough behind may have no stabilization other than the upgrade itself. You are at or near that point, so postponing again is not neutral.

## What I'd do

**Phase 0: about 6–8 weeks, no hop yet.**
1. **Close the security gap as a time-boxed exception.**
   - First check whether your vendor or distribution already ships the fix. That would be the best outcome.
   - Otherwise, backport it in staging, test it, and record it: upstream change, owner, test method, exit condition.
   - Add compensating controls (restrict exposure of the affected API or service) if the advisory allows.
   - Exit condition: the backport is dropped when hop 1 lands.
   - A second backport on this series would be the signal that postponing has become the problem.
2. **Run a control-plane recovery exercise** on a production-like environment with the four people who are still here. Do this before touching the lifecycle.
   - Write the result up as a runbook that someone other than the author validates.
   - This is your largest hidden risk, and both upgrade hops depend on it.
3. **Triage the 12 patches.** Sort each one into drop, replace with an upstream feature, or rewrite.
   - Do the three Nova scheduling patches first. Work out what behavior they provide.
   - Check whether the target releases offer an equivalent through upstream config, filters or weighers, or a plugin.
   - Don't spend effort polishing patches on the old base. Understand them and test them, and remove them where the upgrade makes them unnecessary.

**Phase 1: hop 1** when the phase 0 gates are met.
- Stabilize afterward for a defined period with exit criteria: monitoring clean, recovery re-demonstrated on the new release, backport gone.
- Don't announce a date for hop 2 until those criteria are met.

**Phase 2: hop 2.** Plan it as a second, independent change.

## Why this ordering
- It avoids stacking uncertainty. Option 1 combines an untested recovery path, patches nobody understands, and two upgrades.
- Option 2 alone doesn't fix the advisory or the missing expertise. Option 3 alone leaves you further behind each month.
- Phase 0 makes each later step reversible or recoverable, and it leaves the team more able to perform the next change.

## What flips the recommendation
- **The recovery exercise fails.** Fixing recovery becomes the project, and no hop starts until it works.
- **The Nova patches turn out to be business-critical and can't be reproduced.** Hop 1 slips. The decision then moves to whether to keep the behavior at all.
- **Your vendor ships the fix.** Skip the local backport.
- **A second advisory lands before hop 1.** Accelerate hop 1. Don't accumulate backports.
- **The team drops below four.** Stop and reassess scope. Consider paid external help, with a requirement that it leaves documentation and trained staff behind.

## Decision rights
- **Technical assessment:** your platform lead and the people running the exercise.
- **Security exposure window:** the business or service owner and security owner accept it, with a named expiry date.
- **Sequencing and capacity:** the engineering manager or equivalent decides.

If your engineers disagree on how risky the transition is, record where they disagree and don't average it.

## Owner, review triggers, exit
- **Backport:** one named owner. It is removed at hop 1.
- **Reopen the decision when** any of these happens: the recovery exercise result, a new advisory, a team change, or phase 0 slipping past the planned window.

## How we'll know it worked
- Recovery was re-demonstrated by current staff.
- Each of the 12 patches has a disposition.
- The security fix is tested and has an expiry date.
- After each hop, upgrade effort and incidents are compared with the baseline.

Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process. Before any step, run it through `openstack-change-review`.

If you tell me the actual release, vendor, and what the three Nova patches do, I can tighten the plan. I can also write this up as a decision record or a shareable page for your owners.