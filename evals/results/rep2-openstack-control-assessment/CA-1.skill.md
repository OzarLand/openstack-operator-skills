You're probably in restoration mode, not planning mode. The order is: understand, protect, stabilize, and only then transform. I've seen none of your platform yet, so everything below is a method and a list of what to collect. I'm not assessing anything.

## The core idea
Your question isn't "which tool?" or "which network design?". It's whether the organization can understand, intervene on, recover and evolve this cloud without depending on individuals or guesses. "People restart things when in doubt" and "the previous team left" suggest the answer is currently no. Also, "frequent incidents" and "restart when in doubt" are repeated recovery, and repeated recovery isn't stability.

## First 30 days: make the situation understandable enough to decide better

**Week 1: protect and discover (read-only first)**
1. **Rank business dependence.** Ask which business capabilities depend on this cloud and how critical each is: which tenants, which workloads, who pays, who gets paged. If nobody knows, that's your first finding.
2. **Pick one journey and walk it end to end.** VM creation is the usual choice: API, Keystone, Nova, Placement, Neutron, Glance, Cinder, RabbitMQ, Galera, storage, compute. For each step, note who owns the signal, how failure is detected, and who can recover it. Gaps usually sit at team boundaries.
3. **Inventory what exists.** All of this is read-only:
   - Release and version of every service, plus OS and kernel.
   - Deployment method and where its configs and repo live.
   - Local patches and customizations.
   - Backends (Ceph or other storage, Neutron driver).
   - RabbitMQ and Galera topology.
   - Backups, and whether a restore has ever been done.
   - Monitoring and alert ownership.
   - Certificates and their expiry dates, and Fernet key handling.
4. **Mine the incident history.** Look at the last 6–12 months of tickets and chat. Cluster the incidents by recurring dependency, not by symptom. Ask what changed before each one. Whatever repeats is your stabilization backlog.
5. **Find the remaining knowledge holders.** Include ex-team members and vendors. Capture what they know before it disappears (record sessions, write down the procedures they actually use).

**Week 1–2: guard against the "restart when in doubt" habit**
This is probably your biggest immediate risk. For RabbitMQ, Galera, Neutron agents and compute services, a blind restart can turn a degraded state into an outage or lose evidence. A minimal guardrail is:
- Before restarting any control-plane component, someone captures status and logs (read-only) and names a second person.
- A short "do not do without approval" list covers things like Galera bootstrap, queue purges, mass evacuation and DB edits.

Every guardrail needs an owner, a reason, a removal condition and a review date. Otherwise the emergency state becomes permanent.

**Weeks 2–4: assess and stabilize**
1. Rate each critical capability from Unknown to Visible, Understood, Controlled, Recoverable and Sustainable. Give it a level only where there's evidence. "We think so" means unestablished, and many capabilities sitting at Unknown or Visible is a legitimate result.
2. Run confidence tests instead of self-assessment:
   - Ask someone who didn't design the platform to explain a critical dependency.
   - Rehearse "a user can't create a VM" and see whether the answers depend on who's on shift.
   - Have a new engineer run a real procedure alone while observed.
   - Check that a restore of the Galera database is possible and has been demonstrated by someone other than the person who wrote the procedure.
3. Fix the loudest recurring incident cause first, one at a time, with verification defined before you act.
4. Turn the recovered knowledge into tested runbooks. Someone other than the author should validate each one.

## Your team's proposals (new deployment tool, networking redesign)
Don't dismiss them, but don't start them yet. Changing the deployment tool, the network and the OpenStack release at once makes failures impossible to attribute, and a platform you can't yet recover has no safety net. Before any of them:
- **Deployment tool migration:** wait until you can say what the current deployment actually does, and until the current state is reproducible. Migrating an undocumented deployment moves the unknowns instead of removing them.
- **Networking redesign:** you need a baseline of how tenant networking works today and a demonstrated recovery for it. Treat this as a major risk, since it directly affects every tenant.
- **Upgrades:** this is the one exception. Years of postponement may mean you're on an unmaintained, unpatched release, and then upgrading may itself be the stabilization. But sequence it alone. Don't bundle it with the tooling or network changes. Keep the engineers' energy by giving them the discovery, runbook and recovery-rehearsal work, which feeds all three proposals.

A useful framing for the team is "these are on the roadmap; here are the entry criteria". For example: recovery demonstrated for critical capabilities, ownership gaps closed, critical dependencies visible. That is sequencing, not resistance.

## What I need from you to do a real baseline
I won't guess any of these:
- Your OpenStack release, deployment method (Kolla-Ansible or other) and storage backend.
- Team size now, who is on call, and whether any previous-team knowledge is reachable.
- Your top 3 recurring incidents (anonymized is fine).
- Whether backups exist and have ever been restored.
- Your business criticality list, even a rough one.
- How you want to engage: I can't reach your systems from here, so you'd run the read-only commands and paste the output. Please redact passwords, tokens and `transport_url` or database connection strings first.

With those I can produce the full baseline: capability table with levels and confidence, critical risks, act-now/plan/monitor/accept decisions with owners, measures, and a restoration roadmap with explicit "control restored" criteria. I can also give you the exact read-only collection list, or a draft guardrail and "do not do without approval" list.

> Decision support only. State-changing steps above (guardrails, restart policies, any intervention) require approval by the accountable owner and should be executed under your change process.