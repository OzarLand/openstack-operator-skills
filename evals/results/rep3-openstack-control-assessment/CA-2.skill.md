**Short answer: no.** Documentation plus two presentations will transfer what he can write down and say. It won't transfer the two things you're most likely to lose. Four weeks is enough to do much better if you change the plan this week.

I'm working only from what you've told me. I haven't seen your platform, team, tooling or documentation. Everything below is a general pattern, and the points marked as questions are gaps I can't fill.

## Why the current plan falls short

**1. Upgrades are something he does, not something he knows.**
- The hard part of an upgrade is running it through your deployment tooling. That means the order of steps, the checks he does without thinking, and the point where he stops and says "this looks wrong".
- A document can list the steps. It can't show someone what he does when the output is unexpected.
- *Test:* has anyone else ever run an upgrade step in your environment while he watched?

**2. The reasons behind the customizations are the part most likely to vanish.**
- Docs usually record what the customizations are. They rarely record why each one exists, which incident or bug caused it, and what breaks if you remove it.
- Without the reasons, the team will do one of two things. They'll leave every customization in place forever, so every upgrade gets harder. Or they'll remove one that matters and find out in production.
- This directly affects your next upgrade decision.

**3. Presentations are a weak transfer mechanism.**
- Audiences feel they understood. Nobody finds out what's missing until they have to act.
- Documentation written by the expert alone is also unvalidated. He can't see what he's leaving out, because it all seems obvious to him.

**4. A leaving engineer's time is the scarcest thing you have.**
- If "write docs and present" is added on top of his normal duties, the quality will be poor, and incidents during these four weeks will take what's left.
- Management should treat this as his main job and drop other work from his plate. That is their decision, not his.

## What I'd do instead (4 weeks)

| When | What | Why |
|---|---|---|
| This week | Decide which capabilities the business can't lose, and list who else can operate, diagnose and recover each one today. Anything with "only him" is your priority list. | Spend his limited time where losing him hurts most, not evenly across everything. |
| This week | Name a successor for each critical area, someone who will actually do the work. | A named backup who never performs real operations only documents the dependency. |
| Weeks 1–3 | **Reverse the roles.** Successors perform real operations (routine changes, an upgrade rehearsal in staging if you have one) while he watches and corrects. | This is the only way to find out what he knows that isn't written down. |
| Weeks 1–3 | **Customization register.** For each local patch or config deviation, record why it exists, what it fixes, what happens if it's removed, and whether upstream has since fixed it. Get his best recollection, even when he's unsure. | This is the highest-value document. A written reason that's 80% right is much better than none. |
| Weeks 2–3 | Have someone else walk through a realistic failure ("a user can't create a VM", "a compute node is down") and a recovery, without him prompting. | Shows what the documents don't cover. |
| Week 4 | Have someone other than the author follow the runbooks. Then close the gaps they hit. | A procedure nobody else has followed hasn't been validated. |
| Throughout | Ask what he's worried about. Which parts of the platform does he think are fragile, and which decisions has he been postponing? | Experts know their platform's weak points but rarely write them down. |
| Last days | Agree a way to reach him after he leaves (paid consultancy hours or a short retainer, if his contract allows). | Cheap insurance for the question nobody thought to ask. |

Keep the presentations, but as an addition. Record them, and use them to introduce the walkthroughs. They shouldn't be the main transfer.

## Management decisions to make

These need an owner with authority. They aren't engineering choices:
- **Postpone the next upgrade or large change** until the successors have done at least one operation themselves, or accept that risk explicitly and in writing.
- **Free up his time and the successors' time** for the four weeks.
- **Accept or fund the remaining gap.** If capabilities will still have no one who can recover them after he leaves, that is a business risk, and someone should own it. Options include hiring, a contractor, or vendor support. Choosing between them is a separate decision once you know the size of the gap.

## Questions only you can answer

- Who is left on the team, and what do they already know?
- What does your deployment tooling look like (Kolla-Ansible, another tool, or custom)? Where do upgrade procedures currently live?
- How many local patches or customizations exist, and are they tracked in one place?
- Has any recovery (database, messaging, a failed host) been exercised by someone other than him?
- Is there a staging environment where successors can practice?

If you send me the answers, I can turn this into a capability-by-capability assessment showing where control is weakest, a prioritized plan for his remaining four weeks, and a template for the customization register. I can also draft runbooks from his notes or chat logs. That's my suggestion, not something I've started.

*Decision support only. Any state-changing steps (postponing upgrades, changing responsibilities, rehearsals on live systems) require approval by the accountable owner and should be executed under your change process.*