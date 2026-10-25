## Recommendation

None of the three options as framed. Do option 2, one hop and then stabilize and the second hop, but only after a 6–10 week preparation phase that creates the conditions the upgrade currently fails on. Carry a tested security backport during that phase.

Doing both hops in one quarter fails the gates. Postponing to remove patches first mostly delays the problem.

Decision support only. Several facts below are unknown to me, so treat the recommendation as conditional on closing them.

## Evidence and uncertainty

| Fact / belief | Tag | Confidence |
|---|---|---|
| Series is out of maintenance and two SLURP releases behind | Reported | Verify on releases.openstack.org and with your vendor, including whether SLURP-to-SLURP skip-level is supported for your deployment tool |
| About a dozen local patches, three in Nova scheduling, author gone | Reported | The Nova patches have no owner. I haven't seen the patches, so I don't know whether they are upstreamed, need a port, or are still needed at all. |
| Control-plane recovery was demonstrated once, two years ago, by the person who left | Reported | Weak. It is stale, was run by one person, and was run on a different team, topology and possibly release. Treat recovery as unproven. |
| Team shrank from six to four | Reported | Strong, and it reduces change capacity |
| Advisory fix exists only for maintained series | Reported | Check the advisory text for your exposure and whether any config mitigation exists |
| Backport is possible but untested | Reported | Not demonstrated |
| Whether hop 1 lands on a maintained series | Unknown | Decisive for the choice (see below) |

## Options

| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| 1. Both hops in one quarter | Two control-plane upgrades by four people. Recovery is unproven, so a failed hop has no credible rollback. Three Nova patches nobody understands, and API, DB and scheduler behaviour changes all land at once. Uncertainty is stacked. | Longest exposure to the advisory is avoided only if it succeeds. |
| 2. One hop, stabilize, then the second | Still a control-plane upgrade, but with a smaller blast radius, a learning cycle and a second window to fix mistakes. | Platform stays unmaintained longer than in option 1, and the backport has to be carried through the stabilization period. |
| 3. Postpone, remove patches first, carry the backport | Removing patches from an old series is itself an untested production change, and the Nova scheduling patches change placement behaviour. The backport becomes the lifecycle strategy. The gap widens while the team stays small. | The series gets older and the upgrade harder, and a second advisory would mean a second untested backport. |

## Gates

| Option | Failed gate | What would satisfy it |
|---|---|---|
| 1 | No credible recovery path, since recovery is demonstrated only by someone who left. Depends on expertise you can't obtain (Nova patches). Stacked uncertainty. | A recovery exercise passed by current staff. Each Nova patch dispositioned. Even then, two hops in a quarter with four people stays marginal. |
| 2 | Not yet satisfied: recovery, patch ownership, backport evidence | The preparation phase below |
| 3 | Partially fails "depends on expertise" for the Nova patches. Fails the lifecycle-trend test if the postponement is open-ended. | A hard end date and an exit condition |

If hop 1 lands on another unmaintained series, option 2 doesn't resolve the advisory and the backport has to be carried through both hops. In that case, plan the two hops as one programme with a stabilization gate between them, and shorten the stabilization period.

## Recommended sequence

1. **Backport the fix (weeks 0–4).** Treat it as a bounded, time-limited control, not a strategy.
   - Record the upstream change it derives from, the owner, how it is tested, and the exit condition (the upgrade that lands on a maintained series).
   - Test it in a staging environment that mirrors production as closely as you can.
   - Define compensating controls for the interim: exposure reduction, API filtering and monitoring for the advisory's attack path.
   - Apply it in production only after staging passes, through your change process.
2. **Recovery exercise (weeks 2–8).** Have the current four restore the control plane from backup into an isolated environment: database, message bus, Fernet and credential keys, and service config.
   - Write the runbook as you go, and have someone other than the author validate it.
   - This is the gate that unlocks any upgrade.
3. **Patch triage (weeks 1–4).** For each of the dozen patches, record the purpose, whether it is upstream in a later release, whether it is still needed, and who owns it.
   - The three Nova scheduling patches get priority: capture what behaviour they change (placement and weighers, for example) and write a test that proves it.
   - Don't remove patches from the running series unless the removal is trivial and verified. Most should be dropped or rebased during the upgrade, when you have a staging path.
4. **Staging rehearsal of hop 1** with the Nova behaviour tests, using the restored control plane from step 2. This is the first real upgrade evidence.
5. **Hop 1 in production**, followed by stabilization of 4–8 weeks. During this period, do no other platform change. Remove the backport if hop 1 lands on a maintained series, then run hop 2 with the same rehearsal.

## What you accept

- A bounded period of exposure to the advisory, mitigated by the backport and compensating controls.
- A longer path than "both hops now".
- A one-time cost of the recovery exercise and patch triage that doesn't count as upgrade progress.

## Decision rights

- **Technical assessment:** the platform team, including the Nova triage and the backport test results.
- **Risk acceptance for the advisory exposure and the timeline:** a business or security owner with authority, not the platform team alone. Name this person now.
- **Go/no-go on each hop:** the same owner, based on the recovery exercise result and staging rehearsal.

## Review triggers and exit conditions

- **Backport:** reopen if the advisory is exploited in the wild, if the staging test fails, or if a second advisory needs a backport. A second backport means the series is too old to carry and the schedule must compress. It expires at the first hop that lands on a maintained series.
- **Recovery exercise:** if it fails, fixing recovery becomes the only priority until it passes.
- **Nova patches:** if a patch can't be explained or tested, escalate to a decision on whether to drop it, accepting the scheduling change.
- **Whole plan:** reconsider if the team drops below four or a hard deadline moves.

## How we will know it worked

- The recovery runbook has been executed and validated by someone who didn't write it.
- Every local patch has an owner, a status and a test.
- Hop 1 is rehearsed in staging before production.
- After hop 1, the series is maintained and the backport is gone.
- The number of local patches goes down, not up.

## Facts to verify before committing

- Maintenance status and SLURP path of your series (releases.openstack.org, your vendor).
- Whether hop 1's target series is maintained.
- The advisory's exposure for your deployment.
- Your upgrade tool's skip-level support.
- The topology and backup state needed for the recovery exercise.

I can draft the minimum decision record (App. C fields) or the backport record next if you want. Once you pick an option, the first production change should go through `openstack-change-review`.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.