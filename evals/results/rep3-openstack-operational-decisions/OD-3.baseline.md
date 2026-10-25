**Yes, rebuild it. But do it as a planned migration with a deadline, not a wipe.**

**Why repairing is the wrong bet**
- You can't predict what a fix will break. Years of manual changes, half-applied config, and orphaned ports mean the real state differs from what any config or documentation says. Each repair has unknown side effects, which is why every fix seems to create the next problem.
- The cost of repair never stops. You pay it on every incident, forever, and the cloud never becomes trustworthy.
- A test cloud that can't be trusted gives you misleading test results. That is a bigger cost than the downtime of a rebuild.
- "Teams have stuff in there" is mostly an inventory problem. Much of it is probably abandoned, and nobody can say which parts. That is a reason to inventory, not a reason to keep the mess.

**How to do it safely**
1. **Inventory and announce.** Export every project, instance, volume, network, floating IP, and image, with owner and last activity. Send each team their list with a firm cutover date, 4–6 weeks out.
2. **Default to "not migrated."** Teams claim what they need. Anything unclaimed by the date gets snapshotted and archived, then deleted after a grace period.
3. **Back up what matters.** Take volume snapshots and image exports. Teams should recreate instances from code where they can.
4. **Build the new cloud from code.** Use Kolla-Ansible, OpenStack-Helm, or whatever you deploy with, all in version control. Fresh deployments should be reproducible and rebuildable by anyone on the team.
5. **Run old and new side by side**, then migrate team by team. Keep the old cloud read-only for a few weeks after cutover.
6. **Add guardrails so it doesn't rot again.** Set per-project quotas, require owner and expiry tags on resources, and run an automated reaper for expired or untagged resources. Rebuild on a schedule, for example every 6–12 months, so it stays routine.

**When I'd reconsider**
- If the cloud is small and the mess is mostly orphaned resources (ports, floating IPs, stale instances) with a healthy control plane, a targeted cleanup might be enough. Check whether the problems are in the control plane (config, DB, services) or just leftover resources. Control-plane drift is what justifies a rebuild.
- If you can't staff a rebuild right now, run an interim cleanup. Do it with the same inventory and quota process, so it becomes the first step of the rebuild rather than more repair work.

**For the "keep repairing" camp:** the aim is to protect what teams actually need. A migration does that better than the status quo, because it documents what exists and makes it reproducible. Today nobody can say what's in there or whether it would survive the next fix.

I can write this up as a one-page proposal or a migration checklist to circulate to the teams. Say if you want either.