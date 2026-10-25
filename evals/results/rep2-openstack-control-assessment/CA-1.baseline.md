# Where to start: stabilize, observe, then change

**Don't migrate tooling or redesign networking yet.** Your first job is to make the cloud understandable and stop self-inflicted damage. Both proposals are reasonable later, but doing either on a system you can't observe or reproduce is how you get a worse outage than the ones you have now.

## Weeks 1–2: learn what you actually have

1. **Inventory the truth, not the docs.**
   - Record the OpenStack release and per-service versions.
   - Record the OS and kernel on each node class.
   - Record how it was deployed, and whether the tool's inventory and config still match reality.
   - Record every out-of-tree patch and local config override.
   - Find the bus-factor items: DB and RabbitMQ topology, Ceph or other storage, certificates and their expiries, credentials, and who holds the keys.
2. **Check backups and recovery before anything else.** Confirm you have a recent DB backup, config backups, and a restore you've actually tested. This is the safety net for everything after it.
3. **Mine the incident history.** Pull the last 6–12 months of tickets, chat and pages, then categorize them. In clouds like this, most incidents come from a few causes, such as RabbitMQ partitions and queue buildup, DB connection or slow-query issues, Neutron agents and L3/DHCP, stuck Nova or Cinder states, full disks, and expired certs. Fix the top 2–3 categories first.
4. **Talk to the people who left.** Ask for an hour each if they're reachable. Ask what breaks, what they never touch, and what they restart and why.

## Weeks 2–6: stop the bleeding

- **Replace "restart when in doubt" with a short runbook.** For each recurring symptom, write the diagnosis steps, what's safe to restart and in what order, and what to capture first (logs, `rabbitmqctl` state, agent status). Restarts destroy evidence, so even a one-page runbook per top-5 failure helps.
- **Monitoring and alerting.** Cover control-plane service health, RabbitMQ queue depth, DB, API latency and error rates, agent heartbeats, capacity, and cert expiry. Alert on symptoms users feel, not on every metric. Centralize logs if they aren't already.
- **Blameless postmortems for every incident,** with a standing action-item list. This also shows the team you're replacing folklore with learning.
- **Change control.** Set a lightweight rule: no changes to production without a ticket, a rollback plan, and a second pair of eyes. Config in git, with no hand edits on nodes.
- **Build a staging environment.** Even a small virtualized one on the same release and deployment method is enough. It's the prerequisite for upgrades and for any tooling change.

## Months 2–6: upgrades

Years of postponement means you're probably several releases behind, and possibly on an unsupported one. That's a security risk, but it's also a hazard to rush.

- Find out how far behind you are. Use SLURP releases and skip-level upgrade paths where supported to cut the number of hops.
- Rehearse the full upgrade in staging, including DB migrations timed against a copy of production data.
- Upgrade control plane first, then computes in rolling batches. Keep a rollback plan, and know your point of no return.
- Check whether your current deployment tool can do the upgrade. That's the real input to the tool-migration question.

## Handling the new engineers

Their instincts aren't wrong, so channel them rather than blocking them:

- **Deployment tool migration:** ask for a written evaluation. What problem does it solve (reproducibility, upgrades, drift)? What does migration cost on a live 600-node cloud? Is there an in-place adoption path? Often the answer is to keep the current tool until the upgrade is done, or to pilot the new one in staging only.
- **Networking redesign:** ask for specifics on what's broken or limiting today (data from incidents, not preference). Networking changes are the hardest to do live. Make it a design doc and a staging experiment, not a project yet.
- Give them real work now: monitoring, staging, runbooks, incident analysis. Those are prerequisites for their projects and build the knowledge they'll need.

## Sequencing summary

| Phase | Focus |
|---|---|
| 0–2 wks | Inventory, backups verified, incident data, talk to ex-team |
| 2–6 wks | Monitoring, runbooks, change control, postmortems, staging started |
| 2–6 mo | Upgrade rehearsal and execution |
| 6 mo+ | Tooling and networking proposals, judged against measured pain |

Also set expectations upward early. Incident volume may not drop for a couple of months, and you should tell your management that the first deliverable is visibility.

If it helps, I can turn this into a shareable page (for example, a 30/60/90-day plan) for your team or management. If you tell me your release, deployment tool and the top recurring incidents, I can make the advice much more specific.