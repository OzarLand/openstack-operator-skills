# Where to start: stabilize, understand, then change

Don't start with the deployment tool or the network redesign. You can't safely change a system you can't observe or explain, and right now people restart things because nobody knows what's actually wrong.

## Weeks 1–2: Get visibility and stop the bleeding

1. **Inventory what you actually run.** Collect:
   - OpenStack release and per-service versions
   - deployment method (and whether it can still reproduce the cloud)
   - Neutron backend (OVS or OVN), Ceph or other storage, RabbitMQ and DB topology
   - every local patch or fork
   - the hardware and firmware mix

   Expect drift between what the docs say and what's running.
2. **Check that you can recover.** Verify that DB backups exist and that a restore has actually been tested. Confirm you have the config, secrets, certs (check expiry dates), and a way to rebuild a control-plane node. If any of that is missing, fix it before anything else.
3. **Get basic observability if it's thin.** You need:
   - control-plane health: API latency and error rates, RabbitMQ queue depth, DB connections and replication, and agent heartbeats (nova-compute, neutron agents)
   - capacity: per-host CPU, RAM, and disk, plus Ceph health
   - central logs you can search by request ID
4. **Analyze the incident history.** Pull the last 6–12 months of tickets, chat, and pages, and categorize them. In OpenStack, a few causes usually dominate: RabbitMQ partitions or queue buildup, DB slow queries or stale connections, Neutron agent or L3/DHCP issues, Ceph degradation, and certificate or token expiry. Pick the top 2–3 and fix those first.
5. **Tame the restart culture.**
   - Write short runbooks for the top incident types.
   - Require that anyone who restarts something first captures logs, state, and a timestamp, and notes it in the ticket.
   - Add a blameless post-incident template.

   Restarts that "fix" things are your best clues about root causes, but only if they're recorded.
6. **Find the knowledge holes.** List what only departed people knew. Check for key-person risk in vendor contacts, support contracts, and credentials. Consider short paid support or consulting for the gaps.

## Weeks 3–8: Build the safety net for change

- **A staging environment** that mirrors prod's topology, even if it's small. This is the prerequisite for every upgrade and migration.
- **Config in version control**, with a way to detect drift between nodes.
- **A change process** with a change log, a rollback plan, and a freeze policy. It should be light, but real.
- **Define SLOs** for the API, VM boot success, and network connectivity, so you can tell whether things are getting better.
- **Capacity and lifecycle review:** hardware age, OS and kernel versions, and which security patches you've missed. Also check what's end-of-life. Postponed upgrades mean you may be several releases behind on something no longer supported.

## Upgrades

The longer they were postponed, the more this is the real risk. Plan for it as a project:

1. Find out how far behind you are. OpenStack supports sequential upgrades (and SLURP skip-level paths between certain releases), so you can't just jump.
2. Rehearse the upgrade in staging, including rollback and DB migration timing.
3. Upgrade the control plane first and computes in batches. Keep the OS and kernel upgrades separate from the OpenStack ones.
4. Do it in small, boring steps with a rollback point at each.

## The new engineers

Channel their energy, but sequence it. A new deployment tool and a network redesign are each year-long, high-risk projects, and starting both on a cloud with frequent incidents is how you create a worse outage.

- **Give them real work now.** Observability, runbooks, staging, and automating the upgrade rehearsal all move you toward their goals.
- **Ask for a short written proposal** for each idea: the problem it solves (with evidence), the migration path for the *existing* 600 computes, the rollback plan, and the cost. A deployment-tool migration usually means adopting or re-templating live nodes, so the proposal has to explain how that happens without a rebuild.
- **Treat them as decisions to make later.** Often the right answer is to upgrade with the current tool first, then evaluate a migration once you understand the system. Networking redesigns should be driven by specific measured problems (scale limits, failure domains, performance), not preference.
- **Be honest that you're still learning the system.** That's a reason to wait on decisions, and it's a credible position.

## Talk to the people around you

- **Stakeholders:** agree on a 90-day goal, such as "fewer incidents, a tested restore, and an upgrade plan." Ask what's hurting most.
- **Remaining team:** the people who stayed hold context. Find out what they've been afraid to touch and why.
- **Management:** you'll likely need headcount, staging hardware, or a support contract. Use the incident data to make that case.

## Rough sequencing

| When | Focus |
|---|---|
| Days 1–14 | Inventory, backups and restore test, cert expiry check, incident analysis |
| Weeks 3–8 | Observability, runbooks, staging, config in git |
| Months 3–6 | Fix top incident causes, rehearse and begin upgrades |
| Month 6+ | Evaluate deployment tooling and networking, with data in hand |

If you share your OpenStack release, deployment tool, and the most common incident types, I can help turn this into a more specific plan, an incident-triage template, or a draft of the proposal format for your engineers. I can also write it up as a shareable page if you want to circulate it to your team or management.