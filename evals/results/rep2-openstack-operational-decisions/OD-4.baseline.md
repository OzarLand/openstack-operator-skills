**Remove it, but as a staged experiment, not a delete on Friday.** Your lead is right that the workaround should go, and the nervous people are right that nobody knows what it's hiding. A canary plus detection answers both, and it fits in a week.

**Why not just delete it**
- After two years, the cron job is probably masking a real failure, such as dnsmasq host or lease files drifting from Neutron's port state. If you remove it blind, you find out when instances stop getting or renewing addresses. That's an outage, and nobody will have a diagnosis ready.
- "Nobody fully understood it" works against keeping it too. A nightly restart of every DHCP agent is a risk in its own right. It causes brief DHCP gaps and resync load, and it can leave orphaned dnsmasq processes behind.

**Plan**

1. **Day 1: find out what it was for.** Check the cron file's history, tickets, chat and the original commit message. Note your OpenStack release and what has changed since. The underlying bug may already be fixed upstream, which would make the whole question moot.
2. **Day 1–2: add detection before changing anything.** Write a check that compares Neutron's ports (MAC and IP per network) against each network's dnsmasq `host` and `leases` files and its process state. Run it before and after the nightly restart for a few nights. If the restart changes the result, you've found the symptom. If it never does, that's strong evidence the job is dead weight.
3. **Day 2–3: canary.**
   - Disable the cron on one network node. If `dhcp_agents_per_network` is above 1, the other agents cover the same networks.
   - Leave it running everywhere else.
   - Alert on the drift check and on DHCP-related failures, such as instances that can't get a lease or can't renew.
4. **Rest of the week and the next: widen the rollout.** If the canary is clean for a few nights, including a heavy churn period, disable the cron on half the nodes, then all of them. Comment the job out rather than deleting it, so rollback takes a minute.
5. **If drift shows up:** you now have a reproducible symptom to fix at the root. In the meantime, replace the blanket nightly restart with a targeted remediation that fires only when the check fails, either a resync or a restart of that agent alone. That is still better than today.

**Telling your lead**
You are removing it, and the canary is how you do it safely. You'll have a data-backed answer inside the week, with rollback ready. That respects the "workarounds are tech debt" principle without betting production on a guess. It also means that if the cron needs to stay, or be replaced, the team will finally know why.

I can sketch the drift-check script if you tell me your OpenStack release and how the agents run (systemd or containers).