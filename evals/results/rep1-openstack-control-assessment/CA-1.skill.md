# Where to start: make the platform understandable before changing it

You've told me about symptoms (frequent incidents, restart-when-in-doubt, years of postponed upgrades, a team that has mostly left). You haven't shown me any evidence yet. All of the below is therefore **Reported**, and I can't rate any capability's control level yet. Right now nearly everything is **Unknown**, which is a normal and useful starting point.

The question to answer first is "do we still control this platform?" It comes before "which tool?" or "which network design?".

## The core stance

This looks like a restoration situation, not a transformation one. The new deployment tool and the networking redesign are both reasonable ideas. But on a platform nobody fully understands, each change adds uncertainty and makes failures harder to attribute. You'd be stacking a new tool, a new network and probably a release jump on top of unknown state.

There is one exception. If you're so far behind that you're on unmaintained, vulnerable releases, the upgrade may be the only real stabilization. Even then, the discovery and protection steps below still come first.

Tell the new engineers that sequencing is not rejection: "we'll do this once we can recover from it." Give them discovery work now, because their enthusiasm is an asset.

## First 30 days

### 1. Pick the capabilities the business depends on (week 1)
Don't start with a component inventory. Ask which business capabilities run on this cloud, how critical each is, and who the consumers are. If nobody can answer, that is your first finding.

Then trace each critical capability down to the people:
business capability → OpenStack capability (create/migrate/recover VMs, tenant connectivity, volumes, auth) → service → dependency (RabbitMQ, Galera, Ceph, network) → owning team → who knows it → how it recovers.

### 2. Walk one real journey end to end (weeks 1–2)
Take VM creation, then trace every dependency: API, scheduler/Placement, message bus, database, Neutron, storage, image service. At each step ask:
- Where is the signal?
- Who owns it?
- How would we detect a failure?
- How would we recover?

Gaps cluster at team boundaries.

### 3. Find out what the departed team knew (weeks 1–4)
This is the highest-value knowledge work. Look for:
- Repositories, configs and git history.
- Chat logs, tickets and old incident notes.
- Local patches and custom config, and who knew each one. Anything known to only one person, undocumented, and essential to recovery is **control debt**.
- Contacts: can any former team members or a vendor answer questions? Even a few hours of their time is worth a lot now.

### 4. Put guardrails on the "restart when in doubt" habit (weeks 1–2)
Restarts are the riskiest habit here, because they change state, destroy evidence and can make RabbitMQ or Galera problems worse.

- Don't ban restarts outright, since that can't hold during an incident.
- Introduce a lightweight rule: collect read-only evidence first, such as service state, the queue/cluster status, what changed recently, and logs. Then restart only with a named decision-maker.
- Write down which restarts are known-safe. Anything touching the database cluster, message bus or evacuation needs an explicit owner's decision.
- Every guardrail needs an owner, a reason, a removal condition and a review date. Otherwise it becomes permanent.

### 5. Mine the recurring incidents (weeks 2–4)
Repeated recovery is not stability. List the incidents from the last 6–12 months and group them by symptom and by dependency. The recurring ones probably point to two or three root causes. Record what changed before each one.

### 6. Rate control per capability, with evidence (week 4)
Use the scale Unknown → Visible → Understood → Controlled → Recoverable → Sustainable. A level needs evidence, and "we think so" doesn't count. "Recoverable" means someone *other than the procedure's author* has demonstrated recovery within a time the business accepts. Report this as a profile per capability, not as one score.

## Tests that tell you more than self-assessment

- **Scenario drill:** "A user can't create a VM. Who gets the alert? What evidence do we collect? Who investigates Placement or Neutron? Who may restrict the API? Who talks to the consumer?" If the answers depend on who's in the room, you've found a gap.
- Ask someone who didn't build it to explain a critical dependency.
- Ask what happens if your one expert is unavailable next week.
- Have a new engineer execute a real procedure alone, with someone observing.

## Where to put your effort

Focus on the intersection of **low control and high business consequence**. The common culprits on inherited clouds are:
- Database and message-bus recovery known to one person.
- Unmonitored or unowned critical signals.
- Changes that can't be reversed.
- Drift from upstream.
- An overloaded team (the loop is capacity shortage → concentrated expertise → more dependency → more pressure → no time to improve).

Each significant finding gets one outcome: **act now, plan, monitor, or consciously accept** (with an owner and an expiry). The last option matters: not every gap needs fixing right now, but every accepted gap needs a name on it.

## What "control restored" could mean (define it early)

For example:
- Recovery demonstrated for the critical capabilities.
- Ownership gaps closed.
- Critical dependencies visible.
- Recurring incidents understood.
- A credible lifecycle plan.

Only then does the upgrade and the redesign become the main objective. At that point the options deserve a proper decision: deployment tool, upgrade path, network design. Use the decision-structuring skill for those, with trade-offs and a rollback.

## Measures

Pick a few, each with an owner and a trend (not a target score):
- Number of critical capabilities with only one knowledgeable engineer.
- Time since each recovery procedure was last exercised.
- Number of repeat incidents per root cause.
- Restarts done without prior evidence collection.

## What I need from you to go further

I haven't invented anything about your setup. To do a real assessment, any of the following would help (all **read-only** to collect, and please redact passwords, tokens and `transport_url`/DB connection strings first):

1. **Business side:** which workloads and customers matter most.
2. **Team:** who is on the team now, who left, and who is still reachable. I won't guess ownership or recovery history.
3. **Platform facts:** the OpenStack release, deployment method, control-plane topology, storage and network backends, and rough age of the nodes.
4. **Incident history:** the last several incidents (a ticket export or even rough notes is fine).
5. **Existing artifacts:** runbooks, monitoring dashboards, and where configuration is kept (git or otherwise).

If you share some of that, I'll produce the full assessment (control-state table, risks, findings with outcomes, confidence tests, measures, and a roadmap with guardrails and exit criteria). I can also pick up the individual pieces: runbooks for the knowledge you recover, incident analysis on the recurring issues, or a structured decision on the tool and network proposals.

> Decision support only. The guardrails and any state-changing steps above (restart policy, disabling services, quotas, change freezes) require approval by the accountable owner and should be executed under your change process.