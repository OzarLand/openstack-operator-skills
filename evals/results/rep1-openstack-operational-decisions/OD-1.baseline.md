**Recommendation:** do a modified version of option 2. Put a short "make it safe" phase in front of it, then upgrade one hop at a time. I'd rule out both the single-quarter double hop and postponing.

**Why not the other two**
- **Both hops in one quarter:** you'd be changing everything at once with four people. The recovery procedure has been demonstrated once, two years ago, by someone who has left, so you don't know whether you can roll back or rebuild if a hop goes wrong. Three Nova scheduling patches that nobody understands would also be ported twice under time pressure.
- **Postpone and strip patches first:** this leaves you on an unmaintained base with an unexposed-but-untested security backport for longer. Patch removal is also easier on a newer base, where upstream may already cover some of what the patches do. And the work on the old series gets thrown away at the first hop.

**Sequence**
1. **Weeks 0–4, no upgrades:**
   - **Advisory:** work out whether the vulnerable surface is actually reachable in your deployment. Apply the backport in staging and test it. Ship it, or a config or network mitigation, as a stopgap. Treat it as a bridge, not a destination.
   - **Recovery:** rehearse a control-plane restore from backup into a scratch environment, and write the runbook with at least two people who each run it. This is the gate for everything after it. If it fails, fixing it comes before any upgrade.
   - **Patches:** triage all twelve as drop, upstreamed, or re-implement. For the three Nova ones, find out what they do, check whether upstream now covers it, and if not, move them to a supported extension point (out-of-tree filters or weighers, placement traits or aggregates). Write tests for whatever you keep.
2. **Hop one:** rehearse it end to end in staging against a copy of production state. Land it in a quarter with no other big changes. If the intermediate series is still maintained, this hop also retires the backport, because the fix arrives natively. That's a strong reason to move early. Check how long that series stays maintained, because it sets how long your stabilization window can be.
3. **Stabilize for 4–8 weeks:** run on it, finish dropping patches, and repeat the recovery drill on the new release.
4. **Hop two:** same process, next quarter.

**What would change this**
- If the advisory is remotely exploitable without authentication on an exposed API, ship the backport or mitigation within days. That doesn't change the order afterward.
- If the intermediate series goes end of maintenance within about six months, shorten the stabilization window or compress the two hops. The recovery gate and the patch triage still come first.
- If the recovery rehearsal shows the backups are unusable, that's your quarter's main project.

The biggest risk in your situation is that you can't recover, not the version gap. The plan above fixes that first, and the rest of the work rests on it.

I can write this up as a shareable plan with a dated timeline and go/no-go gates if you want.