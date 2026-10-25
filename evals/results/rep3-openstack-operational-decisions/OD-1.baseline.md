**Recommendation: do the second option, one hop, then stabilize, then the second hop. Put a short prerequisite phase in front of it, and treat the security backport as a time-boxed bridge.** I wouldn't pick any of the three as written.

**Why not both hops in one quarter.** The team has four people, no recovery that has been proven since the engineer left, and three scheduling patches nobody understands. Two hops compound all of that. If hop 1 goes badly mid-flight, you'd have no tested way back and no spare capacity to debug. An upgrade is the moment you most need a working control-plane restore.

**Why not postpone and strip patches first.** Open-ended postponement is the worst of the three. The series stays unmaintained and the backport is untested. Every further upstream release also makes the eventual jump harder and the patch rebases more painful. Patch removal is worth doing, but as part of the prerequisites, not as a reason to wait.

**Sequence**

1. **Weeks 0–3: the advisory.** Apply the backport in staging and run your normal API and scheduling test suite against it. Deploy it, and add compensating controls in parallel: restrict exposure of the affected endpoint, and filter at the proxy or API gateway if the advisory allows. This is a bridge, not a destination. Its expiry is the moment hop 1 lands.
2. **Weeks 0–6, in parallel: re-prove control-plane recovery.** Run a real restore drill in staging: database, config, and secrets. Write it down so it doesn't live in one person's head. This is the gate for all upgrade work. If you can't restore, don't upgrade.
3. **Weeks 3–8: patch triage.** Sort the dozen patches into drop (already upstream or obsolete), replace, and carry. Spend your time on the three Nova scheduling patches. Understand what each one does and why it was written. Then see whether an upstream feature, a custom filter or weigher, or placement traits and aggregates can replace it. If one must be carried, write a test that pins its behavior. Unexplained scheduling patches are your biggest hidden risk in an upgrade.
4. **Quarter 2: hop 1.** Run it in staging first. Hop 1 should land on a series that is still maintained, so it removes the need for the backport.
5. **Stabilize for one to two months.** Rehearse the restore again against the new release, and clear the fallout.
6. **Then hop 2.** By then the patch set should be small, and the team should have done the process once.

**Staffing.** With four people, assign one named owner each for the restore runbook and the Nova patches. This is key-person risk again, so make sure each has a second person who has done it too.

**What would change my answer**
- If the advisory is remotely exploitable on an exposed API and the compensating controls can't contain it, move the backport ahead of everything else, even untested. Test it as fast as you can, but don't wait for a perfect test.
- If the restore drill fails badly, the schedule becomes "fix recovery first" and the upgrade slips. That's still better than finding out mid-hop.
- If the hop 1 target is itself close to end of maintenance, or the hops can't be separated, revisit whether to go to the final target in a single pass.
- If triage shows most patches can be dropped, the one-quarter plan gets more realistic, but only after the restore drill passes.