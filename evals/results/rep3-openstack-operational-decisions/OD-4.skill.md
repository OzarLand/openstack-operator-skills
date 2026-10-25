## Decision to make

**Situation:** A nightly cron restarts `neutron-dhcp-agent` on every network node. It has run for two years to mask a stale-lease problem nobody fully understands. The new team lead wants it gone this week because workarounds are tech debt. Others are afraid to touch it.

**Objective:** Instances keep getting correct DHCP leases and metadata, and the platform is no longer dependent on a mystery job.

**Decision owner:** Unknown. Someone has to own the network service and accept the risk.

## Recommendation

**Don't remove it this week, and don't leave it forever either.** Keep the cron temporarily, and turn "remove it" into a short, evidence-driven project with a date. Both camps are partly right.

- The lead is right that an unexplained, undocumented, platform-wide workaround is debt. Without an exit condition it becomes accidental architecture.
- The cautious people are right that "we don't understand it" is not a reason to delete it. It is a reason to understand it first. Deleting it on a deadline and finding out in production is the worst way to learn what it does.

The skill's workaround test applies: a workaround is safe only while the risk it adds is smaller than the risk it removes. Nobody has measured either side yet. Measuring both is the first task.

## Evidence and uncertainty

| Fact / belief | Confidence | Source |
|---|---|---|
| The cron exists and restarts the agent nightly on all network nodes | Reported | Your message |
| It compensates for a stale-lease problem | Reported (one historical explanation) | Your message |
| Nobody fully understands the root cause | Reported | Your message |
| What breaks without it, and how fast | **Unknown** | Never tested |
| Whether the original cause still applies (release, config, dnsmasq version) | **Unknown** | Not established |
| Who wrote the cron and whether they are still here | **Unknown** | Gap |
| Whether the restart itself causes side effects (brief DHCP/metadata gaps, dnsmasq respawn, lease file handling) | **Unknown** | Verify for your release and deployment tool |

## Options

| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| A. Remove this week, as requested | Stale leases return across all networks at once. The failure is likely to be intermittent and slow, so it shows up as new instances without addresses, duplicate or stale-IP conflicts, or metadata failures. The blast radius is every tenant network, with an unknown recovery path and no proof it's safe. | Debt lingers. The restart may cause small nightly side effects. The fear grows. |
| B. Keep as is, indefinitely | Permanent dependence on an unknown. It will get carried into upgrades, and the people who remember will leave. | Same as A's "not doing it" risks, with no end date. |
| **C. Keep temporarily, and investigate and remove in a staged way (recommended)** | Costs some engineering time. The cron stays for a few more weeks. | Low. This is the current state plus a plan. |
| D. Replace the cron with something smarter, such as detecting stale leases and restarting only when needed | Automates an unresolved workaround and adds more code nobody understands. | Same as B. |

## Gates

| Option | Failed gate | What would satisfy it |
|---|---|---|
| A (remove this week, all nodes) | Insufficient technical evidence. Unbounded blast radius, because it applies to all network nodes at once. No demonstrated recovery path. | Evidence of what the restart fixes, a test on one node, and a defined rollback (re-enable the cron) with detection criteria. |
| B (keep indefinitely) | No exit condition, no owner. | Name an owner and set a review date. |
| D (smarter automation) | Problem not understood. | Root cause first. |
| C | None | — |

## Trade-offs (surviving option C)

- **Gains:** No new production risk. You keep service stability while you learn. Removal happens on evidence rather than on opinion or fear.
- **Costs:** The debt lasts a few more weeks, which is a small price. Someone needs to spend real time on it.
- **Next transition:** Do this before your next upgrade. A workaround for an unknown cause is the kind of thing that breaks when the release changes. Include it in upgrade planning.

## Suggested plan (read-only first)

**Step 1: Document it (read-only, a day or two).**
- Find the cron's author, commit, ticket or chat history. Check whether the original incident was written up.
- Record the cron's schedule, exact commands, and which nodes it runs on.
- Check whether the agent restart has side effects (brief DHCP gaps, dnsmasq respawn), as a step toward explaining the symptom.

**Step 2: Reconstruct the symptom (read-only).** On a network node, near the end of the 24-hour cycle and before the cron fires, compare:
- The DHCP agent's view of leases and ports, the dnsmasq `host`/`leases` files per network namespace, and the Neutron DB port/IP allocations.
- Agent logs, such as the DHCP agent and dnsmasq, for the pre-restart window.
- How many networks per agent, since scale matters.
- Whether this reproduces on a test node.

Redact credentials from any logs or configs you share. This should show whether the problem still exists and what "stale" actually means: stale dnsmasq host entries, stale lease files, or agent/DB drift.

**Step 3: Check the environment (read-only).**
- Compare the version and upstream bug history for your release. Verify against your release and deployment tool, because this behaviour changes between releases. The cause may already be fixed upstream or by a patch level you've since deployed.
- Look at `dhcp_agents_per_network`, `dhcp_lease_duration`, and whether the DHCP agent runs HA.

**Step 4: Controlled trial (state-changing; needs owner approval).**
- Pick one network node, ideally one with less critical tenants, or a staging environment if you have a faithful one.
- Disable the cron on that node only, for a defined window (for example 3 to 7 days), while watching.
- Detection criteria: instances failing to get leases, duplicate/stale entries in the leases or hosts files, metadata failures, agent log errors.
- Stop condition: any of those appear, or the agent is observed degrading. Rollback is to re-enable the cron and restart the agent. That rollback is cheap and fast, which is why a staged trial is acceptable and an all-nodes removal isn't.
- Do it away from changes and maintenance windows so you can attribute causes.

**Step 5: Decide from the evidence.**
- If nothing breaks after a full cycle, extend to other nodes in stages, then remove the cron and record why.
- If it does break, you now have a reproducible failure to debug properly. File the bug, fix or patch it, and keep the cron with a documented purpose and an exit condition tied to that fix.

## Decision rights

- **Technical assessment:** whoever owns Neutron and the network nodes.
- **Accountable owner for accepting the risk:** a named person, for example the platform owner or the team lead with the network service owner. The team lead can reasonably decide to make this a priority, but removing a safeguard from production is a risk acceptance, so it should be recorded rather than done by default.
- **Challenge:** everyone, including the people who are afraid. Their concern is evidence about organizational risk, not just timidity.

## Owner, review trigger, exit condition

- **Owner:** assign one engineer now.
- **Reason it exists:** to prevent stale leases (unproven, to be validated).
- **Review trigger:** a fixed review date (suggest within weeks, not quarters), plus any upgrade planning or a change to the network node set.
- **Exit condition:** the node-by-node trial shows no stale-lease symptoms for at least one full observation window, or a root-cause fix is deployed and verified. Until then, the cron is documented and justified rather than forgotten.

## How we'll know it worked

- The root cause is documented and written down.
- The cron is gone, or has a documented permanent reason.
- No increase in DHCP-related tickets or failed instance boots in the weeks after removal.
- Someone besides the original author can explain why the cron existed.

## What to tell the team lead

> "I agree it should go. But right now we don't know what it protects against, and removing it from all nodes at once is an unbounded change with no evidence. Give us a few days to document and reproduce the issue, then a staged one-node trial with an easy rollback. That gets it removed on evidence rather than on a bet."

That is a plan the lead can put a date on, and it addresses the fear without giving it a veto.

## Decision record (draft)

- **Decision:** Retain the nightly DHCP agent restart temporarily. Investigate root cause and trial staged removal.
- **Owner:** to be named.
- **Reason:** unproven stale-lease protection; removal evidence missing.
- **Accepted risk:** continued low-grade debt and any current side effects of the restart.
- **Review date:** to be set, short.
- **Exit condition:** as above.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I didn't have access to your systems, so the open questions in the evidence table are gaps to close. If you can share redacted agent logs, the cron entry, and your OpenStack release and deployment method, I can help work out what the stale-lease symptom is.