**Do one hop, stabilize, then the second, but front-load two prerequisites. I'd reject the other two options.**

**Why not both hops in one quarter.** With four people, an untested recovery path and three unowned scheduler patches, you'd stack the two biggest unknowns on the same people at the same time. If a hop goes wrong, you'd have no proven way back and nobody who understands the Nova patches. A rollback plan you've never exercised isn't a plan.

**Why not postpone while carrying the backport.** This option keeps you on an unmaintained series, with the advisory fix as a hand-made patch nobody upstream has tested. It also adds a thirteenth local patch and an open-ended delay. Removing patches is worth doing, but as part of the upgrade work, not as a reason to stay exposed.

**Sequence**

1. **Weeks 0–2: contain the advisory now.** Check whether the first hop's target series already contains the fix. If it does, the hop is your real remediation, so schedule it as soon as the prerequisites are done. In the meantime, use compensating controls: restrict network exposure of the affected API, disable the vulnerable feature if possible, and add monitoring. Build the backport and test it in staging only if you can't meet that timeline.
2. **Weeks 0–6: prerequisites, in parallel.**
   - **Recovery drill.** Restore the control plane (DB, message queue, configs) from backups into a staging environment, time it, and write it down as a runbook. Have someone other than the departed engineer run it. This is a hard gate for hop 1.
   - **Patch triage.** Sort all twelve patches into drop, upstreamed or replaced, or port. For the three Nova scheduling patches, first ask whether a custom filter or weigher, or a placement-based approach, can replace them. If so, write that replacement as an out-of-tree plugin with tests. If not, port the patch and write the tests and documentation the original lacks. Name an owner for each.
   - **Staging.** Build a staging environment that's close enough to production to rehearse the upgrade.
3. **Hop 1.** Rehearse it in staging at least twice, including a rollback. Then upgrade production and hold for a stabilization period of a few weeks, with no feature work.
4. **Hop 2.** This should be easier. By then the patch count is down and the runbook has been proven twice.

**Triggers to revisit**
- If the recovery drill fails or takes much longer than your tolerance, fix that before anything else, even above the advisory work. Unrecoverable is worse than vulnerable-but-contained.
- If the advisory is remotely exploitable and unauthenticated, and containment isn't credible, move the backport earlier and accept the extra patch.
- If staffing drops again, or the Nova patches can't be replaced or understood, consider paid support or a contractor for hop 1 rather than compressing the schedule.

I'm assuming each hop is a SLURP-to-SLURP upgrade, which is the supported path, so there are no intermediate releases to cross. I'm also assuming staging is feasible. If either assumption is wrong, the plan changes.