No. Documentation and two presentations will capture what he knows he knows. The risk is in what he doesn't know he knows, and four weeks is enough to do much better if you change the approach.

**Why docs plus talks falls short**

- **Documentation records what happened, not why.** Runbooks and architecture diagrams don't tell you why a Nova patch exists, which upgrade step silently breaks Neutron, or which customization is load-bearing and which is cruft.
- **Presentations are one-way.** Attendees nod, then discover in month six that they can't actually do the thing.
- **The missing knowledge is tacit.** It covers how to diagnose a half-failed upgrade, what "normal" looks like, and which warnings to ignore. Nobody thinks to write that down.
- **Nobody verifies the transfer.** You won't know what's missing until something breaks.

**What I'd do in the four weeks**

1. **Inventory the customizations now (week 1).** List every patch, out-of-tree change, non-default config, custom script, and cron job. For each one, record why it exists, what breaks without it, whether it's still needed, and who to ask upstream. He can narrate this while someone else writes it up. Pull from git history, config management, and the ticket tracker so he's correcting a draft rather than starting from a blank page.
2. **Pair him with named successors (weeks 1–3).** Pick one or two people to be his shadows. They do the work with him watching, instead of watching him. Examples are a routine task, a minor upgrade in staging, and a simulated failure.
3. **Run a dry-run upgrade in staging, led by the successor (weeks 2–3).** Have the successor run the next upgrade path, or a rehearsal of it, from his docs, and have him intervene only when they're stuck. Every point where he has to step in is a documentation gap you've now found. This is the best single test of whether the transfer worked.
4. **Record him instead of only presenting.** Record screen-share walkthroughs of upgrade procedures, debugging sessions, and "here's how I'd triage this alert." Recordings capture the reasoning that prose misses. Make the presentations interactive: scenario-based, with the audience working through problems.
5. **Write an upgrade history or decision log.** For each past upgrade, note what went wrong, what the workaround was, and what to watch for next time. Also list known landmines and open technical debt.
6. **Map the external relationships.** Record who he knows in the community, vendor contacts, upstream bug reports he's tracking, and any informal arrangements.
7. **Plan for after he leaves.** Ask whether he'd take a short paid consulting arrangement or an informal "can we ping you" agreement for 3–6 months. It's cheap insurance, and many people agree. Also decide who owns each area now, so nothing is "everyone's" and therefore no one's.

**Protect his time**

He can't do this and carry a full operational load. Management should explicitly take things off his plate, or the transfer work will be the first thing dropped. Without that, the plan above won't happen.

**A reasonable bar for "done"**

- Every customization has a recorded reason and an owner.
- Someone other than him has completed an upgrade rehearsal.
- Someone other than him has handled a simulated incident.
- There's a way to reach him after he leaves.

If you tell me more about your setup (deployment tool, number of customizations, next upgrade date), I can draft the customization inventory template or a week-by-week plan.