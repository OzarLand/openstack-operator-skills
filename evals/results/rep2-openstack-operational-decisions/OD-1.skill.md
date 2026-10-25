# Recommendation: do the hops one at a time, with a time-boxed readiness phase first

I'd choose option 2, but not start it yet. Put a readiness phase of roughly 6–10 weeks in front of it. That phase includes the backport work from option 3 and nothing else from it. I'd reject doing both hops in one quarter. I'd also reject open-ended postponement.

I don't know your series, the advisory's severity, your platform size, your deployment tool or what the patches change. Those are listed as gaps below. Check maintenance status and the supported SLURP path on releases.openstack.org and with your vendor, because lifecycle facts change.

## Evidence and uncertainty

| Fact / belief | Confidence | Note |
|---|---|---|
| The series is out of maintenance and two SLURP releases behind | Reported | Verify on releases.openstack.org |
| About a dozen local patches, three in Nova scheduling, with the author gone | Reported | Contents unknown. The three Nova patches are the highest risk, because only the author knew their intent. |
| Control-plane recovery was demonstrated once, two years ago, by the engineer who has left | Reported | Treat it as stale and unrepeatable. In practice, recovery is unproven. |
| The team went from six to four people | Reported | Change capacity is reduced. |
| The security fix exists only for maintained series, and the backport is untested | Reported | The backport is plausible but unproven. |

## Options

| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| 1. Both hops in one quarter | It stacks uncertainty: unproven recovery, orphaned Nova patches and a smaller team all hit the same change. A failed hop mid-way leaves you with no known-good state and no one who has recovered the control plane. | You stay exposed to the advisory and keep drifting. |
| 2. One hop, stabilize, then the second | Each hop is smaller and leaves you more able to do the next. It takes longer overall and still needs the preconditions below. | The same drift, over a shorter period. |
| 3. Postpone, remove patches first, carry the backport | Removing patches is real progress. But you carry an untested local security change on an unmaintained series, and the next advisory repeats the problem. | Several backports at once means the series is too old. That is a lifecycle problem, not a security one. |

## Gates

| Option | Gate it fails today | What would satisfy it |
|---|---|---|
| 1 | No credible recovery path, unbounded blast radius, and it depends on expertise you lack (the Nova patches) | It can't be satisfied within a quarter. |
| 2 | No credible recovery path, until you re-demonstrate it | A recovery exercise by current staff, plus an explanation of each Nova patch |
| 3 | Insufficient evidence for the backport, and no end date | Backport tested in staging, with a dated exit condition |

Both options 2 and 3 therefore need the same missing conditions created before anything is chosen. That is the logic behind the readiness phase.

## Readiness phase (do this first)

1. **Security.** Check whether your vendor or distribution already ships the fix for your series. Then work out whether the vulnerable surface is actually reachable. Set compensating controls and a named owner for the interim exposure.
2. **Backport.** If there's no vendor fix, record the upstream change it derives from, test it in a staging environment, and give it an owner and an exit condition. The exit condition is the first hop. Tests should include the advisory's trigger path and a Nova scheduling regression run.
3. **Recovery.** Run a control-plane recovery exercise on a staging environment, led by someone currently on the team and written up as a runbook that a different person validates. Cover database restore, message queue and API recovery. Take backups first. Until this works, no upgrade hop is ready, because you couldn't recover from a failed one.
4. **Nova patches.** Reconstruct each patch's intent, the workload that depends on it, and whether upstream now provides the behaviour. Classify each as drop, upstream or replace, or still needed. Do the same for the other nine patches, ranked by how much they complicate the upgrade.
5. **Staging.** Prove you have an environment that is faithful enough to rehearse a hop.

If the recovery exercise or the patch triage shows the team cannot carry even one hop in the next two quarters, say so and bring in outside help. That is a change in the plan, not a failure.

## Then the hops

- **Hop 1:** Remove or replace the patches that block it. Rehearse in staging, then roll out with a stop condition at each stage. Retire the backport once the hop lands.
- **Stabilization:** Run for a defined period, with exit criteria set in advance: no open upgrade-related incidents, a repeated recovery exercise, and the local patch count reduced.
- **Hop 2:** Repeat the same cycle.

The risk you accept is a longer exposure window on the backport and a longer calendar time on an old series. That is preferable to an unrecoverable failure at the control plane.

## What would change this recommendation

- If the advisory is critical and remotely exploitable, tighten the readiness phase to the backport and its compensating controls only, and stop all other work until they're done.
- If the series is so old that vendor or hardware support is ending, shorten the stabilization period but keep the hops separate.
- If the Nova patches turn out to be upstreamed or trivial, the hops get cheaper. Staying on option 2 still costs little.
- If the recovery exercise fails and the team can't fix it in the phase, escalate to management. The decision becomes how to buy capability rather than which hop order to use.

## Decision rights

Your engineers assess the technical risk. An authorized owner, such as the platform or service owner, has to accept the interim security exposure and the timeline. Someone must be named as accountable. I don't know who that is, so please fill it in.

## How we will know it worked

- The recovery runbook is validated by someone who didn't write it.
- The backport has a passing test record and a named owner.
- The local patch count goes down, and each remaining patch has a recorded reason.
- After hop 1, upgrade time and incident count are no worse than the rehearsal predicted.

If it would help, I can turn this into a decision record or a weighted comparison to share with your owners.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.