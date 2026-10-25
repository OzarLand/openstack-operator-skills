# Where to start: restore control before you transform anything

I haven't seen your systems, so this is a sequence to follow, not an assessment. Nothing below is rated or measured yet.

What you describe (frequent incidents, restart-when-in-doubt, years of postponed upgrades, previous team gone) is a **platform where control may already be lost**. The default response to that is wrong: moving to a new deployment tool and redesigning networking both add uncertainty to a system nobody fully understands. Recommended order: **Discover → Protect → Assess → Stabilize → Recover knowledge → Simplify → Establish control → Evolve.** The new engineers' proposals belong in the last step, not the first.

The exception is if the release is so old that it's unmaintained or has unpatched vulnerabilities. In that case, moving may be the only way to stabilize. Even then, the earlier steps still apply around it. The rule is not to stack uncertainty on top of an unstable platform, which isn't the same as never moving.

## First 30 days

**1. Start from the business, not the component list (week 1).**
- Find out which business capabilities depend on this cloud, who the users are, and what hurts them most when it breaks.
- If nobody can tell you how critical each workload is, that is your first finding.
- For each critical capability, trace the chain: capability → OpenStack service → technical dependency → team → who knows it → how it's recovered.

**2. Walk one real journey end to end (weeks 1–2).**
- Take VM creation, from API request to a running, reachable instance.
- At each hop, ask where the signal is, who owns it, how failure is detected, and how it's recovered.
- Gaps usually sit at team boundaries (network, storage, DB and messaging teams, or whoever is left).

**3. Mine the incident history (weeks 1–2).**
- Pull the last 6–12 months of incidents and group them by symptom, not by ticket.
- "People restart when in doubt" means restarts are masking causes. Find out which restarts actually fix things and which only appear to.
- Recurring symptoms are your best map of where the real fragility is.

**4. Put temporary guardrails on production changes (week 1, needs your approval).**
- Restart-when-in-doubt is the most dangerous habit on a control plane, especially for RabbitMQ and Galera.
- Agree a simple rule: no restarts, resets or purges of messaging or DB nodes without a second person and a quick evidence check.
- Every guardrail needs an owner, a reason, a removal condition and a review date. Otherwise the emergency state becomes permanent.

**5. Rate control per capability, with evidence (weeks 2–4).**
- Use the scale Unknown → Visible → Understood → Controlled → Recoverable → Sustainable.
- Don't produce a single score. Rate each capability separately, such as scheduling, tenant networking, volumes, auth, and control-plane DB and messaging.
- "We think so" doesn't count. Evidence means something observed in production or recovery demonstrated by someone other than whoever wrote the procedure.
- With this history, expect many capabilities at Unknown or Visible. That is a useful finding, not a failure.

**6. Test confidence rather than ask for it (weeks 2–4).**
- Ask an engineer who didn't build it to explain a critical dependency.
- Have a new engineer run a real procedure alone while someone watches.
- Ask each owner what happens if their key person is unavailable next week.
- Check whether you can restore the DB and the config from backups. Don't just check whether backups exist.

**7. Find where weak control meets high consequence.** Look for:
- Unclear ownership.
- Recovery that depends on one person.
- Critical dependencies nobody monitors.
- Changes that can't be reversed.
- Local patches and drift from upstream.
- An overloaded team.

Give each finding one outcome: **act now, plan, monitor or consciously accept**. Each needs an owner, and an accepted risk needs an expiry or review condition.

## Read-only data to gather first

Asking the team or running read-only commands will answer these:

- **Release and versions:** OpenStack release, deployment tool, OS, kernel, libvirt/QEMU, and the RabbitMQ and MariaDB/Galera versions.
- **Topology:** control-plane layout, networking backend (OVS or OVN, tunnelling), and storage backends (Ceph, Cinder drivers).
- **Local changes:** patches, forks, and config that differs from defaults.
- **Backups and recovery:** whether the DB, configs and secrets are backed up and when a restore was last tested.
- **Monitoring and alerting:** what exists and who gets paged.
- **Incident and change records:** what exists for the last year.
- **Ownership:** who is on the team now and who holds which knowledge.
- **Fleet health:** compute services, agents and cluster health (`openstack compute service list`, `openstack network agent list`, `rabbitmqctl cluster_status`, Galera `wsrep_*` status).

If you paste outputs, I'll tag what is observed and what is only reported.

## Handling the migration and networking proposals

- **Don't say no.** Say not yet, and put a condition on each. A reasonable bar is that critical capabilities have demonstrated recovery, incidents are understood, ownership is clear, and the lifecycle plan is credible.
- **Redirect the energy:** have those engineers own the discovery work, such as the dependency walk, incident clustering, a lab environment, and rehearsing a restore and an upgrade. Those tasks build the knowledge any migration needs.
- **Treat upgrades as a stabilization question, not a project.** Skipping many releases increases risk, but the answer depends on your release and state. That is a decision to make with options and exit conditions once you have the baseline.
- **Define "control restored" up front,** for example: demonstrated recovery for critical capabilities, ownership gaps closed, critical dependencies visible, recurring incidents understood, and a credible lifecycle plan. Without it, stabilization turns into the new architecture.

## Questions for you

1. Which business capabilities and workloads run on this cloud, and is there any criticality ranking?
2. What release is it, and how far behind (roughly)?
3. Who is on the team now, and who actually holds knowledge of RabbitMQ, Galera and networking?
4. What are the top two or three recurring incidents?
5. Is there a tested backup and restore for the control-plane database?

The step I'd begin with is a 30-day baseline: the current-state map, critical risks, guardrails, ownership and recovery gaps, and a control roadmap. I can build that once you share any of the above, and I can draft the guardrail table or the confidence-test plan first if you prefer.

> Decision support only. State-changing steps above (such as the restart guardrail) require approval by the accountable owner and should be executed under your change process.