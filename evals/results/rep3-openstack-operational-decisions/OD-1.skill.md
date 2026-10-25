# Recommendation: none of the three options as framed

I'd recommend a fourth path: **create the missing conditions first, bridge the advisory with a tested backport, then do the hops one at a time.** That is roughly your option 2 with a prerequisite phase and an explicit security bridge. I haven't seen your platform, so everything below rests on what you told me.

## Evidence and uncertainty

| Fact or belief | Confidence |
|---|---|
| The series is out of maintenance and two SLURP hops behind | Reported. Verify on releases.openstack.org and with your vendor. |
| The advisory affects you, and no fix exists for your series | Reported. Confirm exploitability in your own configuration. |
| Control-plane recovery worked once, two years ago, by an engineer who has left | Demonstrated once, long ago, and the person who knows how is gone. Treat it as unproven today. |
| About 12 local patches, 3 in Nova scheduling by the departed engineer | Reported. Their behavior, tests and upstream status are unknown. |
| The backport is possible but untested | Hypothesis |
| The team has shrunk from 6 to 4 | Reported |

**Gaps:**
- Which series you run, and what your vendor or distribution supports.
- Whether the vendor or distribution will ship the fix.
- Whether the Nova patches are still needed upstream.
- Your workload criticality and how much spare capacity you have.
- Whether you have a staging environment that resembles production.

## Gates

| Option | Gate failed | What would satisfy it |
|---|---|---|
| **1. Both hops in one quarter** | Recovery path (unproven). Expertise (the Nova patches' author is gone). Stacked uncertainty (two hops, 12 patches and a smaller team). The failure blast radius is the whole control plane. | A demonstrated recovery, patch triage done, and a rehearsed first hop. At that point it's no longer option 1. |
| **2. One hop, stabilize, then the second** | Fails on the same recovery-path and Nova-patch gaps if started now. It passes once those are closed. | Same as above. |
| **3. Postpone, remove patches, carry the backport** | Mandatory security requirement: the advisory remains open and the fix is untested. It also has no end date, so the series keeps aging and the team keeps shrinking. | A tested backport, compensating controls, and a dated exit. Without those it fails. |

Option 3 also holds a real insight, which the recommendation below keeps. Local patches are the biggest unknown in any hop, and removing them is cheaper before the upgrade than during it.

## Why option 1 is the worst choice

- A failed control-plane upgrade is only survivable if you can recover, and you can't currently show that you can.
- You would be debugging a bad Nova scheduling result without knowing which of two upgrades, or which patch, caused it.
- The people available to handle that have shrunk by a third.

Your platform is already far behind. The standing-still risk is real, and postponing without an end date is the expensive outcome. But speed doesn't fix it.

## Recommended sequence

Dates are yours to set. The steps are ordered by dependency.

**Phase 0: build the conditions (weeks, not quarters)**
1. **Contain the advisory now.**
   - Check whether your vendor or distribution will ship the fix.
   - Check whether the advisory is exploitable in your configuration.
   - Apply compensating controls such as network exposure limits and disabling the affected feature if possible.
   - Name an owner and a review date. This is a security exception, so it needs an owner, a compensating control and an expiry.
2. **Test the backport in staging.**
   - Record the upstream change it derives from.
   - Record who owns it, how it is tested, and that it is removed by the first hop.
   - Treat it as a bridge. If more security backports pile up, that is a lifecycle signal, not a security one.
3. **Run a control-plane recovery exercise.**
   - Use staging or a restored copy.
   - Have someone other than the author follow a written runbook.
   - Time it and fix the gaps.
   - This one is non-negotiable, because it gates everything after it. The `openstack-control-assessment` and `openstack-runbook-authoring` skills can help.
4. **Triage the 12 patches.** For each one, record:
   - the problem it solves
   - whether upstream now fixes it
   - whether a config option replaces it
   - whether it can be dropped
   - who can read and test it

   Give the three Nova scheduling patches priority. Many may be removable at hop time rather than carried. Retire what you cheaply can now. Don't rewrite a patch you intend to drop.

**Phase 1: first hop**
5. Go/no-go gate: recovery demonstrated, backport tested, patches triaged, rehearsal done in staging.
6. Do the hop, then **stabilize for a defined period.** Define "stabilized" beforehand: no new local patches, monitoring baselines established, recovery re-run on the new release.

**Phase 2: second hop**
7. Repeat the same gate. Treat the second hop as a fresh decision, not an automatic continuation.

Doing it this way leaves you more able to do the next change at every step. That matters more than total elapsed time.

## What you're accepting

- A time-boxed window of exposure to the advisory, reduced by compensating controls and an untested-until-Phase-0 backport.
- A longer total timeline than option 1.
- Continued carrying of patches whose authors have left, until each is dropped or understood.

## Decision rights

- **Technical assessment:** the platform team, including the Nova and recovery findings.
- **Security exception:** whoever in your organization can accept the security risk. That is not the engineers.
- **Go/no-go on each hop:** a named owner with business authority, informed by the gate evidence.
- **If your engineers disagree:** show where they disagree, for example on how risky the first hop is, instead of averaging it.

## Review triggers and exit conditions

- **Security exception:** reopen it if the vendor ships a fix, if exploitation is observed, or at the date you set.
- **Backport:** removed at the first hop, no later.
- **Phase 0:** if recovery can't be demonstrated within the time you allow, escalate. That is a capacity decision, such as external help or more headcount, not a reason to proceed.
- **Whole plan:** if the team shrinks further, or either hop gate keeps failing, revisit the plan itself.

## How you'll know it worked

- Recovery can be done by someone other than the author, to a written runbook.
- Local patches are fewer than 12 and each has an owner and test.
- The platform is on a maintained series with no backports carried.
- Hop two goes more smoothly than hop one, measured by incidents and effort.

## Decision record (draft)

- **Decision:** Phase 0 first, then two separate hops. Options 1 and 3 rejected as framed.
- **Owner:** to be named.
- **Review:** at the end of Phase 0 and at each hop gate.
- **Exit:** the series is maintained and the security backport is removed.

## Checks before you rely on this

Verify the current maintenance and SLURP status at releases.openstack.org and with your vendor, because lifecycle facts change. I didn't use the weighted scoring model. The gates already separate the options, and the scores would only add false precision.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.