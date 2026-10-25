**Recommendation: rebuild it, but do it as a managed migration, not a flag-day wipe.** Your "every fix creates the next problem" symptom is the strongest signal. It means the cloud's actual state has diverged from anything anyone can reason about, so repairs can't be verified.

**Why rebuilding wins**
- **Unknown state is the real problem.** Half-applied config and orphaned ports mean you can't predict what a change will do. Each repair is a gamble, and the cost compounds.
- **A test cloud's value is that it's reproducible.** If nobody can say how it got into its current state, it has stopped being a trustworthy test environment. Results from it are suspect too.
- **"Teams have stuff in there" is an argument about data, not about the cloud.** Test instances are almost never irreplaceable. The few things that are (images, volumes, keypairs, networks with fixed IPs, DNS or floating IP dependencies) can be inventoried and moved.

**When I'd say keep repairing**
- Someone is using it as de facto staging or for long-running state that can't be recreated.
- You have no automation for deploying it, so a rebuild would reproduce the same drift. In that case, fix the deployment tooling first, or the rebuilt cloud will rot the same way.
- A real deadline makes a rebuild window impossible. Then do a time-boxed cleanup and schedule the rebuild.

**How I'd run it**
1. **Inventory (about a week).** Export instances, volumes, images, networks, floating IPs, and security groups per project. Include owner, last activity, and size.
2. **Announce a firm date** (4–6 weeks out) with a deadline for teams to claim what they need. The default is that unclaimed resources are gone. Without a default, nobody acts.
3. **Build the new cloud declaratively** (Kolla-Ansible, OpenStack-Ansible, or whatever you use, all from git). Keep the config in version control. Have a quota and cleanup policy ready, or it will fill with leftovers again.
4. **Stand up the new cloud beside the old one if hardware allows.** Let teams migrate on their own schedule, then retire the old one. If you can't run both, rebuild in place after snapshotting claimed data.
5. **Add guardrails.** Use per-project quotas, mandatory tags with an owner and expiry, and a scheduled reaper for expired resources. This is what stops a repeat.

**The rebuild fails mostly for these reasons**
- Skipping the guardrails, so you're back here in two years.
- Letting the "claim it" step go unenforced.
- Rebuilding with the same undocumented manual tweaks. Anything you change by hand during the rebuild should go into the code.

If you share how the cloud was deployed and roughly how many projects and instances it has, I can sketch the inventory scripts or a migration plan.