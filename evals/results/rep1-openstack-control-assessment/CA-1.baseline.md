# Where to start: stabilize, learn, then change

Don't start with the deployment tool or the networking redesign. You don't yet know what the system does, so you can't judge whether a migration would improve it. Spend the first 90 days on a few things, in this order.

## Weeks 1–2: Find out what you have

1. **Inventory what's actually running.** Record the OpenStack release, the deployment method, which services are enabled, and the hypervisor and kernel versions. Also record the Ceph or storage backend, the Neutron driver (OVS or OVN, and what overlay), the DB and message queue topology, and any out-of-tree patches. Version drift and local patches decide how hard upgrades will be.
2. **Find the single points of failure.** Check Galera/MySQL, RabbitMQ, controllers, Ceph mons, the L3 agents, and the DNS and NTP sources. Confirm that backups exist and that a restore has been tested. Back up the DB and the config management state before you touch anything.
3. **Get access and credentials sorted.** Find any secrets, certs and their expiry dates, and whoever holds root on what. Expired certs are a classic surprise outage.
4. **Locate the tribal knowledge.** Talk to the people who left, if any are reachable. Ask for runbooks and a list of "things we never touch". Also read the last 6–12 months of incident tickets and chat.

## Weeks 2–4: Make the incidents legible

- **Classify the incidents.** Tag the last 20–50 by cause: RabbitMQ, DB, Neutron agents, capacity, storage, human error, or a noisy tenant. You'll probably find that two or three causes explain most of them. That list is your real roadmap.
- **Replace "restart when in doubt" with a short triage runbook.** For the top 5 failure modes, write down the symptom, how to check, the safe fix, and what not to do. Restarting RabbitMQ or an L3 agent can make things worse, so some restarts need an explicit "ask first" rule.
- **Add basic observability if it's missing.** At a minimum: API latency and error rates, RabbitMQ queue depth, DB health, agent liveness, hypervisor capacity, and Ceph health. Alerts should be few and actionable. A noisy pager reinforces the restart reflex.
- **Introduce lightweight incident hygiene.** Use one incident channel, one commander, and short blameless postmortems with action items you actually track.

## Months 2–3: Fix the top causes and de-risk upgrades

- **Fix the top recurring causes** from your classification. These are usually boring: tuning, capacity, cleanup of stale resources, or fixing a flapping component.
- **Build a staging environment.** Even a small one (3 controllers, a few computes) that mirrors your versions lets you rehearse upgrades. Without it, every upgrade is a gamble, which is probably why they've been postponed.
- **Decide the upgrade strategy from the facts.** If you're many releases behind, OpenStack supports skip-level upgrades only within limits (SLURP releases). You may need to step through releases in staging first. Also check which release you're on against its EOL status, because that determines how urgent security patching is.
- **Make the config reproducible.** Whatever the current tool is, get its repo into a state where you can see drift. Then you'll know whether it's really the problem.

## Handling the new engineers

Their enthusiasm is an asset, but pointing it at a rewrite now is risky. Rewriting the deployment tool and the network while you're still firefighting means changing two foundations at once, with no baseline. Channel it like this:

- **Give them the investigation work.** Let them own the inventory, the incident analysis, and the staging environment. That builds context and credibility.
- **Ask for a written case.** For each proposal (new deploy tool, network redesign), have them state the problem it solves, backed by incident data, plus the migration path, rollback plan, and cost. If the case is strong, it will survive that scrutiny.
- **Set a gate.** Something like: no major migration until incident rate is down, backups are tested, and a staging upgrade has succeeded. A deployment-tool migration may well turn out to be the *right way to do upgrades*, but you want to reach it deliberately, not as a reaction.
- **Keep networking changes incremental.** Redesigning the network live under 600 computes is among the riskiest things you can do. Target specific pain points first, and prototype in staging.

## Talk to your management early

You've inherited a lot of deferred maintenance. Set expectations now: stabilization comes first and upgrades are a multi-quarter project. Ask for headcount or time for the staging environment, because it's the thing that unblocks everything else.

## A rough first-90-days order

1. Backups verified, inventory done
2. Incident classification and triage runbooks
3. Monitoring and alerts cleaned up
4. Staging environment up
5. First rehearsed upgrade or patch in staging
6. Only then, evaluate the tooling and networking proposals with real data

If you tell me the OpenStack release, the current deployment tool, and the network driver, I can get more specific about upgrade paths, the usual failure modes, and what to check first. I can also write this up as a shareable plan or checklist page if you'd like to hand it to your team or management.