No. Documentation and two presentations will capture what he *knows he knows*. The risk is the rest: the reasoning behind decisions, the failure modes he handles by reflex, and the things he'd never think to write down. Four weeks is tight, but you can do much better than the default plan.

**Why docs and talks fall short**
- Docs describe the system as it is. They rarely say why it's that way, or what breaks if you change it. That is the hard part of "why half our customizations exist."
- Presentations are one-way. Nobody knows what to ask until they're in the incident.
- Nobody has proven the docs work. Untested runbooks are usually missing a step that "everyone knows."
- Tacit knowledge, such as which alert is noise, which node is fragile, and which vendor contact actually helps, doesn't come out when someone is asked to write documentation.

**What I'd add, in priority order**

1. **Inventory the customizations first (week 1).** List every patch, out-of-tree change, non-default config, and workaround. For each one, record why it exists, which bug, ticket or incident drove it, what happens if it's removed, and whether it's still needed. Have him narrate it while someone else drives and takes notes. Talking is faster and more complete than writing. Check the git history and tickets alongside, because they'll jog his memory.

2. **Make successors do the work with him watching (weeks 2–3).** Have the people who will inherit this perform a real task, ideally a minor upgrade, a node add or a cert rotation, using only the docs, with him observing and not helping unless they're stuck. Every time they stall is a doc gap. Fix it on the spot. This is the single highest-value activity.

3. **Record the upgrade history.** Do a retrospective on each past upgrade: what went wrong, what you'd do differently, the order of operations, rollback points, and the gotchas specific to your deployment. Also capture a clear upgrade plan for the next release, written by him.

4. **Record sessions, don't just present.** Record screen-share walkthroughs of real operations and of troubleshooting. Replace one of the two presentations with a "game day": he injects or describes realistic failures (a Galera split, a stuck Neutron agent, RabbitMQ partition, Ceph degradation) and the team diagnoses while he coaches.

5. **Name owners and a second person for each area.** Map which areas (compute, networking, storage, identity, upgrades, monitoring) have only one person who understands them. Assign a primary and backup now, while he can still review their understanding.

6. **Do the "ask me anything" sweep.** Have the team and adjacent teams submit questions for him in a shared doc during weeks 1–3. Also ask him directly: "What would you worry about if you were staying? What are you most afraid will break?" That list is your risk register.

7. **Arrange post-departure access.** Negotiate a paid or informal consulting arrangement or an agreed-upon "call me for emergencies" window for 3–6 months. It costs little compared to a single bad outage, and it's best raised now, while the relationship is good.

**Logistics that matter**
- Protect his time. Reduce his operational load so he isn't doing KT in the margins. Otherwise it won't happen.
- Assign a scribe or technical writer to work with him. Senior engineers are usually poor, slow documenters but good at explaining aloud.
- Set a handoff checkpoint at week 3 where successors demonstrate competence, leaving week 4 to close gaps.
- Store everything in one searchable place, linked to the code and tickets.

**Longer-term reality check:** even with all this, you'll lose some knowledge. Two things reduce the long-term risk: reducing the number of customizations (every one you can upstream or remove is one less thing to explain), and considering support from a vendor or an OpenStack-specialist firm if the team is thin.

I can draft the customization inventory template, a week-by-week KT plan, or the question list for the sweep, if that would help.