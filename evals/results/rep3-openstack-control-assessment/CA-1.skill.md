Start by making the situation understandable. Don't start by improving the platform. For the first 30 days, treat this as a control restoration. Ask whether the organization can still understand, decide, intervene, recover and evolve without depending on individuals or undocumented assumptions. Your symptoms point to no: frequent incidents, restarts "when in doubt", most of the previous team gone, and upgrades skipped for years.

I haven't seen any evidence from your platform yet. Everything below is a method, not a finding.

## Weeks 1–2: Discover and protect

**1. Find out what the business depends on.** Ask which business capabilities run on this cloud (customer-facing services, internal CI, databases, GPU work) and how critical each is. If nobody can answer, that is your first finding. A simple dependency behind a critical capability matters more than a complex component behind a trivial one.

**2. Walk one real user journey end to end, usually "create a VM".** For each hop (Keystone, Nova, Placement, Neutron, Glance, Cinder, RabbitMQ, Galera, storage, the network underlay), ask:
- Where is the signal for this hop?
- Who owns it?
- How is a failure detected, and how is it recovered?
- Which business capability is affected?

Gaps usually show up at team boundaries.

**3. Stop reflexive restarts without banning them.** A restart is a state change made without a diagnosis, and repeated recovery is not stability. Propose a lightweight rule for the control plane (RabbitMQ, Galera, APIs, nova-compute):
- Capture evidence first: logs, service state, and what changed recently.
- Name who approved the restart.
- Log it in one shared place.

Restarts also tell you where the platform is weak. Fixing a recurring one is how you start to regain control.

**4. Ask what changed.** For your last 5–10 incidents, collect the timeline and whatever changed beforehand. Recurring incidents usually have a small number of causes.

**5. Map people and knowledge.** Write down who is left, who knows what, and who has vendor or contractor contacts. Keep this about capability, not individual performance. Look for control debt: local patches, custom configs, or scripts that only one person understands and that recovery depends on. Recover knowledge from git history, configs, old tickets and chat while the people who remember are still reachable, including former team members.

## Weeks 2–4: Assess and decide

Rate each critical capability on this scale: **Unknown → Visible → Understood → Controlled → Recoverable → Sustainable**.

- Each rating needs evidence. "We think so" means the level isn't established.
- Don't compute one score. Report a profile per capability.
- Expect many entries at Unknown or Visible. That is a useful baseline.
- Recoverable means someone other than the procedure's author has demonstrated recovery within a time the business accepts. Your best test is to have a newer engineer run a real recovery procedure while an experienced one observes. Backups, Galera/RabbitMQ recovery, and a failed compute host are good candidates.

Then put each finding into one of four buckets, each with an owner:
- act now
- plan
- monitor
- consciously accept (with an expiry date)

## The upgrade and redesign pressure

Don't say no, and don't let them run it as the first step. Their case has real force: unsupported releases and unpatched CVEs are themselves a risk, and some platforms can only be stabilized by moving them forward. But a new deployment tool, a network redesign and a release upgrade together make failures impossible to attribute, and you currently can't recover reliably from the failures you already have.

- **Reframe it as sequencing.** The new engineers' energy is useful, but point it at discovery first. Have them build the dependency map, inventory configs and patches, and stand up a representative lab or staging environment. A lab is the right place to try the new deployment tool.
- **Change one major thing at a time**, and only after you can show a recovery. You need at least two things first: a demonstrated rollback or recovery path, and an inventory of what's actually deployed and patched.
- **Get a clear picture of upgrade distance.** Identify the current release and its support status. How far behind you are decides whether upgrading is the main priority or merely a gated one.
- **Redesign networking last.** It carries the largest blast radius, so it needs the most control first.

## What I need from you

These are all read-only. Redact any passwords, tokens, `transport_url`, `[database] connection` strings and `clouds.yaml` contents before pasting:
- OpenStack release, deployment tool, OS, and number of controllers, and whether it's single-site or multi-region.
- Storage and network backends (Ceph or not, OVN or OVS/ML2, and so on).
- The last 5–10 incidents: dates, symptoms, what was restarted, and whether the cause was ever found.
- Who is left on the team, and what each person is confident operating.
- What's monitored today, and who actually gets paged.
- Whether you have any tested backups, DB restore procedures, or recovery runbooks.
- The most critical workloads or tenants, and who the business owner is for each.

With that I can produce the baseline: a control-level table by capability, risks where low control meets high consequence, a measures list, and a 30/60/90-day roadmap. Any temporary guardrail, such as disabling a flaky compute host in the scheduler or a change freeze, needs an owner and a removal condition, or it becomes permanent.

Decision support only. State-changing steps above (guardrails, restart policy, recovery rehearsals) require approval by the accountable owner and should be executed under your change process.