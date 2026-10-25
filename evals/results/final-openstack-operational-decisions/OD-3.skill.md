**Recommendation: rebuild, but as a managed migration rather than a wipe.** This is a test cloud, so the main question is whether the information in its current state is worth preserving. Mostly it isn't. Years of accumulated experiments are the thing making it untrustworthy. Your own symptom, where each fix creates the next problem, shows that repair is no longer converging on a known state.

I haven't inspected the cloud. Everything below rests on what you told me, so it's all **Reported**.

## Why repair is the weaker option

- You can't say what "fixed" looks like. Leftover ports, half-applied config and orphaned instances mean you have no baseline to repair toward.
- Every repair step is itself a state-changing action on a system nobody fully understands. The next problem is often one of those steps, not an old one.
- "Teams have stuff in there" is a claim that hasn't been checked yet. It's the only real argument for repair, so it's the thing to test first.

## What a rebuild has to include

1. **Inventory and snapshot, read-only first.** List instances, volumes, images, networks, floating IPs and projects, with owners and last activity. Back up the databases and configs as evidence, so you can still see what the old cloud looked like afterward.
2. **Owner triage with a deadline.** Send each project owner their list and ask them to claim what they need. Say that unclaimed resources will not be migrated. An unanswered claim is a decision, and it avoids debating "what if someone needs it" forever.
3. **A defined baseline and validation criteria.** Decide what "good" means before building. For example: a clean deploy from version-controlled config, a smoke test (boot a VM, attach a volume, reach it over a floating IP), and a restore test. Automated installation alone doesn't prove the result matches the baseline.
4. **Migration of the claimed resources.** Move them by image, volume export or re-creation from code. Move only what's claimed, not the old cloud's accumulated state.
5. **Guardrails against repeating this.** Give projects quotas and an owner tag. Add a resource expiry or periodic cleanup and a no-manual-config rule, so the cloud doesn't drift again. Otherwise you'll be back in the same place in a few years.

## When I'd change my answer

- **Repair is better** if the cloud is really a shared dev/staging environment that holds irreplaceable state, such as long-lived data or hand-built environments nobody can reproduce. That makes it closer to production, and the calculus flips. Even then, ask whether continued repair is reducing risk.
- **Don't rebuild yet** if you can't staff it. A rebuild with no owner or validation criteria just moves the mess. If the first gate fails, say no owner, no one who can deploy it cleanly or no backup, the first action is to create that condition.

## Decision rights

The platform team can assess the technical risk. Someone with authority over the shared environment, not the platform team alone, has to accept losing unclaimed state and set the deadline. Teams can challenge, but one named person decides.

## Gaps I'd close first

- Is this truly test-only, or do any teams treat it as pre-production?
- Is the deployment tooling and config in version control, so it can be rebuilt reproducibly?
- Is there an owner for each project, and how many resources have no owner at all?
- Release and deployment method. Check lifecycle status at releases.openstack.org before choosing the rebuild target. Building on a release near end of maintenance would repeat the problem.

## Review trigger and success check

Revisit the decision if owner triage shows a lot of irreplaceable state. The rebuild worked if, after 3 to 6 months, fewer incidents trace to cloud drift, a fresh deploy from code matches production-like behaviour, and teams can find and own their resources.

If you want, I can draft the owner-triage message and the read-only inventory checklist next.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.