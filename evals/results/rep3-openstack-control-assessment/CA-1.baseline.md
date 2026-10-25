# Where to start

Spend the first 60 to 90 days on stability and knowledge. Don't migrate the deployment tool or redesign networking yet. Both are reasonable goals, but changing the tooling and the network while you can't yet explain the incidents is how you create bigger ones.

## Weeks 1–2: Find out what you actually have
- **Inventory.** List the OpenStack release and every service, which are customized or patched, the hypervisors and kernels, the storage backend (Ceph?), the network backend (OVS or OVN, VLAN or VXLAN, any SDN or hardware dependencies), and the DB and message bus topology.
- **Find the deployment source of truth.** Work out how the cloud was deployed (kolla-ansible, TripleO, OSA, hand-rolled, or a mix), where that code lives, and whether it matches what's running. Configuration drift on a cloud this age is likely.
- **Secure access and backups.** Confirm you have the credentials, the CA and certificate expiry dates, and the license and support contracts. Verify that DB backups exist and that a restore has been tested. If you do only one thing in week one, make it that.
- **Read the incident history.** Pull the last 6 to 12 months of tickets, chat logs and postmortems, and categorize them by root cause. Expect a few causes to account for most of the pain, such as RabbitMQ partitions, DB connection exhaustion, Neutron agents, Ceph slow ops, or full disks and expiring certs.
- **Interview the people.** Talk to the remaining engineers, to the largest tenants and to anyone who left, if they're reachable. The tribal knowledge lives there.

## Weeks 2–6: Stop the bleeding
- **Make "restart when in doubt" safe, then rarer.**
  - Write short runbooks for the top 5 recurring incidents. Each should say what to check before restarting, what to capture (logs, `rabbitmqctl` state, DB processlist), and what a restart will and won't fix.
  - Restarting isn't wrong by itself, but restarts with no evidence mean you never learn the root cause. Add a rule that you capture state first.
- **Observability baseline.** You need the following before anything else changes:
  - API latency and error rates per service.
  - RabbitMQ queue depths.
  - DB connections and slow queries.
  - Agent heartbeats.
  - Nova and Ceph capacity.
  - Certificate expiry.
  - A synthetic canary that boots a VM end to end every few minutes.
- **Incident process.** Name an incident commander, write a blameless postmortem for every incident, and keep a change log. Make changes visible, because mystery changes cause many of these incidents.
- **Capacity and blast radius.** Check how full compute, storage and IPs are, and which single points of failure exist (controllers, a single network node, one Ceph pool).

## Weeks 6–12: Build the safety net for change
- **Build a staging or lab environment** that resembles production, even at small scale. Without one, you can't responsibly upgrade or migrate anything.
- **Rehearse the upgrade.** Upgrades postponed for years mean you're likely multiple releases behind. OpenStack's supported path is generally one release at a time, or a skip-level (SLURP) path where available.
  - Check your release's EOL status and any open CVEs. That may force the timeline.
  - Do a dry run in staging, with a rollback plan and DB backups.
- **Decide on the deployment tool with evidence.** Evaluate it against the incident data:
  - If drift and manual changes are causing incidents, a migration may be justified.
  - If the existing tool works and is merely unfashionable, the better move may be to adopt it properly: get it under version control and CI, and test it.
  - A tool migration on a live cloud is often as risky as an upgrade. Don't combine them.

## Handling the new engineers
Their instincts may be right, but the order matters. Channel the energy by:
- Giving them a design-doc process: problem, evidence from incidents, options, rollback plan.
- Assigning them a staging environment, the runbooks or the observability work now. This builds their system knowledge, which they'll need to design anything good.
- Telling them plainly that the network redesign and tool migration are candidates for next year, gated on stability metrics (for example, incident count down by X% and a successful staging upgrade).

## Suggested sequencing
1. Backups and restore tested.
2. Observability and incident process.
3. Staging environment.
4. Upgrade path (needed for security and support).
5. Deployment tooling consolidation, as the tool that carries the upgrades.
6. Networking changes, last. They are the riskiest, hardest to roll back and affect every tenant.

## Two things to do early
- **Set expectations upward.** Tell your management now that the first quarter is about stabilization and learning, and agree on a few metrics (incident count, MTTR, time since last tested restore, release lag).
- **Look after the team.** If the on-call load is heavy, protect people from burnout. Write down what you learn as you go, so you don't become the next single point of failure.

If you tell me the OpenStack release, the deployment tool and the storage and network backends, I can make this much more specific. I can also turn it into a shareable plan page for your team or management.