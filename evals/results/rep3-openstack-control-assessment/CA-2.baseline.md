No, it isn't enough. Documentation and presentations capture what he thinks to write down. The most valuable knowledge here is the "why" behind customizations and the upgrade judgment calls, and people rarely know to write that down. Presentations are also one-way and can't be replayed or searched.

**What I'd add in the 4 weeks**

1. **Inventory the customizations first (week 1).** Diff your deployment against upstream: patches, forked packages, config overrides, custom Ansible/Kolla/Helm overrides, cron jobs, scripts. For each item, record what it does, why it exists, what breaks if it's removed, and whether it's still needed. Have him annotate the list. This is the highest-value artifact, and it also surfaces customizations nobody can explain.
2. **Interview him instead of asking him to write.** Someone else should drive the sessions. Walk through each item and each past upgrade ("what went wrong in the Xena→Yoga upgrade?"). Record and transcribe them. Questions from a successor get at tacit knowledge much better than a blank page.
3. **Make the successors do the work while he's still there (weeks 2–4).** Run a real or rehearsal task with him watching and not driving: an upgrade in a staging environment, a failed-node recovery, a cert rotation. Gaps show up quickly this way. Documentation nobody has tested is unreliable.
4. **Write runbooks for the dangerous and rare tasks.** These are the upgrade procedure, DB migrations, Ceph/Neutron recovery, and rollback. Include the "if you see X, it's actually Y" folklore.
5. **Capture access and tribal context.** This covers credentials and vault ownership, vendor and upstream contacts, who in the community he trusts, open bugs you're carrying workarounds for, and any pending commitments to customers.
6. **Record decision history.** Put short "why" notes in the repo next to each customization, not in a wiki that will rot.
7. **Name owners.** Assign a primary and backup for each subsystem now, so knowledge has a destination.

**Also consider**
- **Retention or a consulting arrangement.** A paid retainer for 3–6 months after he leaves, for questions and for the next upgrade, is cheap compared to the risk.
- **Reduce the load.** Use the departure to retire customizations that can't be justified, since they're pure liability.
- **Free up his time.** If he's still on pager and ticket duty, he'll have no capacity for any of this. Take that off him now.
- **Check the bus factor beyond him.** Are there others who've done an upgrade end to end? If not, that's the actual risk to fix.

**Pass/fail test:** by his last day, can someone other than him perform your next upgrade in staging from the written material alone, and explain every customization? If not, you aren't done.

I can draft the customization-inventory template, the interview question list, or a 4-week plan if you want.