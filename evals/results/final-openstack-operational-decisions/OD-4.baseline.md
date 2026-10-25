**Remove it, but as a staged experiment with a way to detect failure, not a "delete and hope" change.** Your lead is right that a workaround nobody understands is debt. The cautious people are right that deleting it blind turns the debt into an outage. You can do both this week.

**Why you can't just leave it**
- The nightly restart is itself a risk. Every network node loses DHCP at the same moment, and it hides whatever the real fault is.
- If the underlying bug drifts, the cron may stop covering it, and nobody will know.

**Why you can't just delete it**
- Nobody knows what it prevents. If it prevents tenant VMs failing to renew or get leases, the failure shows up as confusing tenant tickets days later.

**Plan for this week**

1. **Day 1: find the history.** Check the cron's commit or ticket, the Puppet/Ansible repo, old chat, and the original on-call notes. Check which Neutron and dnsmasq versions were running when it was added. The bug may already be fixed by an upgrade.
2. **Day 1–2: record what the restart fixes.** Just before the restart, run a read-only check on each node. For each `qdhcp-*` namespace, compare the dnsmasq `host`, `leases` and `opts` files against the ports and IPs in the Neutron DB. Log the drift and the agent's RPC/RabbitMQ errors. Also record how many dnsmasq processes are running versus how many networks the agent hosts. This shows what "stale lease" means in practice, and it may show the cause (lost RPC messages, orphaned dnsmasq, a missed port-delete event).
3. **Day 2–3: canary.** Disable the cron on one node, ideally one that serves networks with low-risk tenants. Keep the drift check running and alert on it. Define rollback criteria up front, such as any drift lasting more than N hours or any failed lease renewal. Rollback means re-enabling the cron.
4. **Day 4–5: widen.** If the canary stays clean for several days, disable the cron on the other nodes one at a time. If drift appears, you now have evidence to find the root cause. Likely candidates are the RPC reliability settings, `resync_interval`, `dhcp_lease_duration`, or a known dnsmasq or Neutron bug.
5. **Replace, don't just remove.** The best end state is the drift check alerting, with a restart only when drift is detected. That is a documented remediation, not an unexplained nightly ritual. If drift never appears, delete the check too.

**What to tell the lead:** "We'll remove it, and the canary starts [date]. We'll stop restarting everything blindly, and if the underlying issue still exists we'll have the evidence to fix it properly." That meets their goal and gives the nervous people a rollback path.

**If the lead insists on removal everywhere tonight:** push back on the method, not the goal. A staged rollout over a few days costs almost nothing, while a fleet-wide DHCP failure costs far more.

If you can share the cron's history or a sample of the agent logs, I can help work out what the drift check should compare.