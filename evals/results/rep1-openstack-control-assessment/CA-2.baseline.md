No, it isn't enough. Documentation and two presentations capture what he knows he knows. The risk is what he knows without realizing it: why a customization exists, which upgrade step bit you in a past release, and which alert is noise and which isn't. That kind of knowledge rarely comes out in a document or a talk. It comes out when someone else tries to do the work and asks him questions.

**Why those two don't cover it**
- **Docs describe what, not why.** The "why" behind customizations is mostly incident history and trade-offs he's long forgotten he made.
- **Presentations are one-way.** Audiences nod, then discover the gaps later, when he's gone.
- **Nothing tests whether the knowledge transferred.** You won't find out until the next upgrade or outage.

**What I'd add in the 4 weeks**
1. **Inventory the customizations first (week 1).** List every patch, override, custom config, out-of-tree plugin and cron job. Have him write one line for each: why it exists, what breaks if it's removed, and whether it's still needed. Do this before any other writing, because it sets the scope for everything else.
2. **Make a successor shadow him, then reverse the roles.** Name a primary and a backup owner now. For the first two weeks they watch him work. For the last two, they do the work and he watches and corrects.
3. **Run a real upgrade rehearsal.** Do a dry-run upgrade or a major change in staging, driven by the successors from his runbook. Every place they get stuck is a gap in the docs. This is the best test of whether the transfer worked.
4. **Record him.** Screen-record him doing the real tasks while he talks through his reasoning: upgrade steps, debugging a failed instance build, a Ceph/Neutron/Nova issue. A 20-minute recording often beats 20 pages of prose.
5. **Capture the tribal knowledge.** Run a few "what would you do if…" sessions on failure scenarios. Put the history in the repo as decision records, with commit messages and links to the original tickets and incidents.
6. **Collect the access and the contacts.** That means credentials and vault ownership, vendor and upstream contacts, and any cron jobs or scripts on his own machines. Missing handoffs here are common and painful.
7. **Keep a door open after he leaves.** Ask whether he'd take a paid consulting retainer or an "ask me questions" arrangement for 3 to 6 months. It's cheap insurance, and his answer may shape how much you need to capture now.

**Reduce his other work.** Four weeks of documentation on top of a full workload won't happen. Management should explicitly free up a large share of his time, or the plan will quietly become "whatever he gets to."

**Likely outcome.** Even done well, you'll recover maybe 70–80% of it. Plan for a rough first upgrade cycle, and consider shrinking the customization footprint now, since every unexplained customization is a liability.

If it would help, I can draft a week-by-week handoff plan, or the customization-inventory template, to take to management.