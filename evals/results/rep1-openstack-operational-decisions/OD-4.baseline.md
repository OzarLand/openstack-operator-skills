**Remove it, but as a staged experiment with a rollback, not a delete.** Your team lead is right that a nightly restart across every network node is debt. The people who are scared are also right that nobody knows what it's masking. A canary removal settles both.

**Why not just delete it this week**
- Nobody understands the failure, so you can't predict what breaks. The likely symptoms are instances failing to get or renew a lease, or a new port getting an IP that dnsmasq still maps to an old MAC. These show up as tenant-facing incidents, often at 3am.
- If it fails, you'd be debugging a two-year-old problem under pressure, with no baseline.

**Why not leave it forever**
- The restart is itself a risk: a brief DHCP gap every night, and it hides any real regression.
- It will get copied into new deployments and survive upgrades unexamined.

**Plan that fits in a week**
1. **Spend a day on archaeology.** Check the cron file's history, the original ticket or chat, and the OpenStack release and dnsmasq version at the time. Many "stale lease" causes were fixed upstream, such as dnsmasq host/lease files not being updated on port delete or IP reuse, or resync after lost RabbitMQ messages. You may find the root cause was fixed in an upgrade you've already done.
2. **Build a detector before changing anything.** Write a script that compares each network's dnsmasq `leases` and `host` files against `openstack port list` (MAC to IP). It should count mismatches per node and per network. This gives you a baseline and a way to know the workaround is no longer needed.
3. **Canary it.** Disable the cron on one network node. Check that `dhcp_agents_per_network` is at least 2, so another agent covers its networks. Do this in staging first if you have one. Run it for 1–2 weeks, longer if you have lots of port churn.
4. **Set the rollback trigger up front.** For example, any mismatch that persists for more than N minutes, or any DHCP-related ticket. Rolling back is re-enabling the cron.
5. **Roll out node by node** if the canary is clean, then delete the cron and write down what you learned.

**If the canary fails**
You now have a reproducible failure and data. Replace the blunt restart with something targeted, like the detector script triggering a per-network resync, or an upgrade or config fix. That's the actual tech-debt payoff, because you've replaced a mystery with a monitored mechanism.

**For the team lead:** "Yes, we'll remove it, and we'll have it off on one node this week and fully gone in two to three, with a detector and a rollback." That addresses the debt concern and gives the cautious people a safety net, so nobody has to bet on a guess.