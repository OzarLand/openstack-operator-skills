# Decision: remove the nightly neutron-dhcp-agent restart?

**Short answer:** Both sides are half right. The lead is right that it should go, and the cautious engineers are right that nobody should delete it on faith. The call is to **remove it on evidence, not by date.** This week, make the workaround observable and run a controlled removal test. Retire it fleet-wide once the test passes. "Remove it this week" is achievable only as "start the removal process this week."

I haven't seen your environment, so everything below that depends on your platform is flagged as a gap, not assumed.

## Decision to make
- **Situation:** A nightly cron restarts neutron-dhcp-agent on all network nodes to hide a stale-lease problem. It has run for two years and the root cause is not understood.
- **Objective:** Protect instance DHCP and metadata reachability, and stop carrying an unexplained deviation.
- **Decision owner:** Unknown. I'd expect the network or platform owner, with the lead as sponsor. See Decision rights.

## Evidence and uncertainty
| Fact / belief | Tag | Confidence |
|---|---|---|
| A cron restarts the agent nightly on all network nodes | Reported | Needs a look at the crontab or config management to confirm scope |
| Without it, leases go stale | Reported | **Low.** It's a two-year-old belief and it's unclear anyone has tested it |
| Root cause is unknown | Reported | It means "we think so" is all there is |
| The release, agent config, DHCP backend and lease settings | Gap | Not provided |
| Whether the original symptom is still reproducible | Gap | The platform may have been upgraded since, and an upstream fix may exist |
| Who wrote the cron and whether they're still here | Gap | Organizational facts count as evidence |
| What the restart itself costs (resync load, missed port updates) | Gap | Verify for your release |

Fear of touching the cron is also a signal. It suggests the team has lost control of this capability: they can't say what it protects.

## Options
| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| **A. Remove everywhere this week** | If the problem is real, new or renewed instances may fail to get or renew DHCP leases on every network at once. Blast radius is the whole fleet and you have no baseline to detect it. | None immediate, but the lead's objective is met only by luck |
| **B. Keep indefinitely** | Accidental architecture. It hides a bug that upgrades may change or worsen. It will be ported blindly into new deployments. The restart itself has a cost. The cron failing silently is an unmonitored dependency. | Slow loss of control |
| **C. Instrument, then staged removal with exit criteria (recommended)** | Small, bounded, reversible. Costs engineer time. | Workaround persists a few more weeks |
| **D. Replace with a smarter mitigation** (for example, restart only when a check detects staleness) | Automates a problem you don't understand. | Same as B, with extra complexity |

## Gates
| Option | Gate failed | What would satisfy it |
|---|---|---|
| A | No credible recovery demonstration, unbounded blast radius, insufficient evidence | Fails today; C creates these conditions |
| B | No exit condition or owner | Add both; acceptable only as a temporary state |
| D | Insufficient evidence (automating an unresolved workaround) | Fails until root cause is known |

C passes if an owner is named and the restart can be reinstated within minutes. That is a manual or cron re-enable, so the recovery path is trivial.

## Recommended plan (option C)

**Step 1: Read-only, this week.** Ask whoever has access to run these and paste the output. I can't inspect your system.
- Find the cron's origin: commit history, ticket, or git blame in config management. Who added it, and what was the original symptom?
- Check the release and any DHCP agent bugs or release notes since the cron was added. A fix may already be in your series. *Verify for your release.*
- Record the DHCP agent configuration: lease duration, `dhcp_agents_per_network`, resync settings, and where dnsmasq's host and lease files live.
- Record the baseline. Over a few days, capture per-network DHCP agent state (`openstack network agent list`), dnsmasq process age, and any existing DHCP-related errors in agent logs.
- Look at what the restart itself does: a log excerpt around the cron time, and time to resync.

**Step 2: Define the failure signal (read-only, no cost).** Decide what "stale lease" looks like in measurable terms. Examples: an instance not renewing, a DHCP request unanswered, or a mismatch between Neutron port records and dnsmasq's hosts file. Build a check for it before any removal. If you can't detect the failure, you can't safely remove the mitigation.

**Step 3: Pilot (state-changing).**
- Disable the cron on **one** network node, or one agent that serves a low-criticality set of networks. Don't pick the busiest one.
- Pick a window with the on-call engineer present, and an agreed observation period. It should be longer than whatever the stale-lease timing is. That timing is itself a gap.
- Stop conditions: the failure signal fires, or any tenant-reported DHCP/metadata problem.
- Recovery: re-enable the cron and manually restart the agent. Nothing else needs to be restored. This is the key reason this is safe to try.
- Approval: the network or platform owner.

**Step 4: Widen.** Extend node by node or in thirds if the pilot is clean. Then remove the cron from config management so it doesn't come back, and keep the restart as a documented manual procedure.

**Step 5: If the pilot fails**, you've gained the first real evidence about the root cause, because the failure now appears in a place you're watching. Keep the workaround with an owner, a reason, a review trigger and an exit condition. Use the evidence to file or find the upstream bug. Treat it as a lifecycle input for your next upgrade.

## What you'd be accepting
- A few more weeks with the workaround while you gather evidence.
- A small, supervised risk on one node.
- If the pilot fails, the workaround stays.

## Decision rights
- **Technical assessment:** the network engineers (you, and whoever knows the DHCP path).
- **Accountable owner and decider on the production risk:** the person who owns tenant network availability, with the team lead sponsoring.
- The lead can set the direction ("this should not exist indefinitely"). But accepting the risk of the pilot belongs to the capability owner. Nobody should accept it informally.
- If people disagree, show them the actual disagreement: is the stale-lease problem still real? That's testable, so test it.

## Owner, review trigger, exit condition
- **Owner:** a named person for the workaround until it's removed.
- **Review trigger:** pilot complete, or the next release upgrade, whichever comes first.
- **Exit condition:** the pilot shows no stale-lease signal over the observation period, and then the fleet shows none over a defined period after removal.

## How we'll know it worked
- No increase in DHCP or metadata-related tickets or alerts after removal.
- The failure-signal check stays quiet.
- Fewer nightly agent restarts and resyncs visible in logs.
- Someone on the team can explain, in a paragraph, what the stale-lease problem was (or that it no longer exists). That written explanation counts as a deliverable.

## Draft decision record
- **Decision:** Remove the nightly neutron-dhcp-agent restart via a staged, monitored pilot, not a date-driven fleet-wide change.
- **Reason:** The workaround is unexplained, unowned and unmonitored, but its removal effect is unknown.
- **Alternatives rejected:** Remove at once (fails the blast-radius and evidence gates), keep forever (no exit condition), conditional restart automation (automates an unexplained problem).
- **Owner / approver:** To be named.
- **Review trigger / exit:** As above.

If you tell me your OpenStack release and what the original symptom looked like, I can narrow the hypotheses. If you want a one-page version for your lead, I can write that too.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.