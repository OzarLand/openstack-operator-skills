**Yes, rebuild it, but do it as a migration, not a flag-day wipe.** That resolves the "teams have stuff in there" objection.

**Why repairing has stopped working**
- Each fix runs against unknown state: orphaned ports, half-applied config, drift nobody documented. You can't predict what it will break, so fixes keep causing the next problem.
- Nobody can say what "correct" looks like, so you can't tell whether a repair worked.
- A test cloud that can't be trusted gives unreliable results. Failures may be the cloud's fault, and passes may be accidental. This cost is spread across every team, so it's easy to underestimate.
- Repair effort never ends, because the debt is in the state you can't see.

**Why "teams have stuff in there" is weaker than it sounds**
- Most of it is probably abandoned. After years of shared use, the real inventory is usually much smaller than the apparent one.
- Anything that can't survive a rebuild is already at risk. A test cloud with irreplaceable data in it is a latent incident.
- The people holding that objection are the ones who benefit most from a trustworthy cloud.

**A plan that addresses the concern**
1. **Inventory and announce.** Export instances, volumes, networks, floating IPs, images and projects with owners. Publish a deadline (say 4–6 weeks) and a "claim it or lose it" list. Unowned and untagged resources are default-delete.
2. **Build the new cloud in parallel.** Deploy from code (Kolla-Ansible, OpenStack-Helm or similar), with all config in git and no manual changes. Use per-team projects with quotas and mandatory owner and expiry tags.
3. **Migrate by team.** Claimants move volumes and images, or snapshot and re-import. Offer help to teams who need it, and put the heavy lifting on the teams that own the resources.
4. **Freeze the old cloud** to read-only or no new resources once the new one is usable.
5. **Archive and decommission.** Keep final snapshots of anything contested for a grace period, then retire it.
6. **Prevent a repeat.** Run periodic reapers for expired or untagged resources. Have a rule that nothing is changed outside the deployment code. Rebuild on a schedule (quarterly or annually) so a rebuild is routine.

**When I'd reverse this**
- Several teams have long-running, stateful, hard-to-reproduce workloads that really must stay, and the inventory proves it.
- You can't get the capacity to run old and new side by side.
- The problems turn out to be one or two root causes, such as a broken Neutron agent or a bad DB state, rather than general rot. A one-day diagnostic can rule this in or out.

I'd do that diagnostic first. If it finds no single cause, rebuild. If you give me access, or paste the outputs of `openstack server list --all-projects`, `openstack port list` and a list of services and agents, I can quantify how much is orphaned and draft the inventory and announcement. I can also put this into a short page to circulate to the teams if that would help.