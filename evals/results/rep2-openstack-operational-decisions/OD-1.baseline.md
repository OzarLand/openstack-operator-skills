**Recommendation: a modified version of option 2, with a gate in front of it.** Don't do both hops in one quarter. Don't postpone either. Treat the backport as a short bridge, not a way to stay put.

**Why not the other two**
- **Both hops in one quarter:** This stacks the two risks you can't price, which are the untested recovery and the Nova patches nobody understands. You'd do it with four people and no proven rollback. If hop one breaks something, you have no stable point to return to or debug from.
- **Postpone and remove patches first:** Every month on the old series adds more unfixed advisories. The backport only covers this one, and each later one needs the same untested work. Patch removal is also easier on a maintained base, because upstream may have fixed or replaced what the patches work around. You'd be carrying the security risk for the whole time you spend on cleanup.

**Sequence**
1. **Weeks 0–4, de-risk (gate):**
   - **Backport:** Apply the security fix in staging, test it, and deploy it. Add network or config mitigations in the meantime if the advisory allows. This is a bridge that buys you time.
   - **Recovery drill:** Rebuild the control plane from backups in a scratch environment, covering the DB, config, secrets and certs. This is the most important item, because recovery was last shown two years ago by someone who has left. No hop starts until it passes and is written down as a runbook.
   - **Patch triage:** Sort the dozen patches into drop, upstreamed or already fixed, and must keep. For the three Nova scheduling patches, first work out what they do. Then see whether a supported extension point (custom filter or weigher, placement traits, flavor extra specs, aggregate metadata) can replace them.
2. **Quarter 1, hop one:**
   - Rehearse the upgrade repeatedly in staging with a copy of production data, then do production.
   - Land on a maintained release. That fixes the advisory properly and lets you retire the backport.
   - Rebase or retire patches as you go. Aim to carry fewer patches into hop two than into hop one.
3. **Stabilize for about one full cycle:**
   - Run it in production, close out the alerts and fix the regressions.
   - Re-run the recovery drill on the new release.
4. **Hop two:** Do the same rehearse-then-execute process, with the patch count near zero.

**Triggers that change the plan**
- If the advisory is remotely exploitable without credentials, or exploited in the wild, do the backport in week 1 and test it as hard as you can in the days you have.
- If the backport fails testing, move hop one forward. The recovery drill and the rehearsal become more urgent, not optional.
- If the Nova patches turn out to be load-bearing and can't be replaced, make them the first project of the stabilization period. Don't carry them silently through hop two.

**Staffing:** With four people, make hop one the only major project this quarter. Make sure at least two people can run the recovery drill and the upgrade, so the knowledge doesn't sit with one person again.

I don't know the advisory's severity, which release you're on, or what your deployment tooling is. The first of those could shift the timing, and the other two could change how long the rehearsals take. The overall shape holds either way: prove recovery, shrink the patches, then take one hop at a time.