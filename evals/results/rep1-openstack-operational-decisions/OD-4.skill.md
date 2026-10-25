# Nightly neutron-dhcp-agent restart: remove it, but as a staged experiment

**Recommendation:** The team lead is right about the direction and the fearful colleagues are right about the method. Don't delete the cron job this week, and don't leave it untouched. Spend this week making its removal safe to test. That means finding out what it masks, adding a way to detect the failure, and running a canary with a one-line rollback. Then remove it everywhere once the evidence supports that.

I haven't seen your platform, so everything below about the cause is hypothesis.

## Decision to make
- **Situation:** A nightly restart on all network nodes hides a stale-lease problem that no one fully understands.
- **Objective:** Protect tenant DHCP and IP assignment, and stop carrying an unexplained workaround.
- **Decision owner:** Unknown. It is probably the team lead for priority and the network service owner for risk acceptance.

## Evidence and uncertainty
| Fact / belief | Confidence |
|---|---|
| The cron job exists and has run for about two years | Reported |
| It prevents stale leases | Reported, never shown. It may be a cause, a correlation, or a long-dead fix. |
| Nobody knows the root cause | Reported. That is the main finding: the workaround is unexplained. |
| What "stale lease" looks like, how often it happened, and whether it ever recurred on a skipped night | **Gap** |
| Release, DHCP agents per network, whether all nodes restart at the same time | **Gap** |
| Who added the cron job, and the ticket or commit behind it | **Gap**, probably recoverable from history |

## Options
| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| A. Remove everywhere this week | The symptom returns with no detection or fallback plan. Tenants may see wrong or missing leases, possibly delayed and silent. | None immediate |
| B. Keep as is, "don't touch" | None immediate | It stays accidental architecture and will surprise the next upgrade. The nightly restart is itself a risk. Knowledge of why it exists keeps fading. |
| C. Investigate, then canary removal, then staged removal (recommended) | Takes a few weeks. One node may show the symptom during the canary. | Little |
| D. Replace it with a targeted fix or a detect-then-restart check | Adds automation around something still not understood | Moderate |

## Gates
| Option | Failed gate | What would satisfy it |
|---|---|---|
| A | **Insufficient evidence.** You can't tell whether the symptom has returned. There is no defined detection or stop condition, and the blast radius is every network node. | A detection signal, a canary scope and a rollback trigger |
| B | **No owner and no exit condition.** This is the "forgotten debt" pattern. | An owner, a review date and an exit condition |
| C | None, provided scope is limited to one node or one AZ and detection exists first | |

## Things to check this week (all read-only)
1. **Origin.** Find the config-management or Ansible history, a ticket, or the commit message behind the cron entry. Ask whoever added it, if they are still around.
2. **Restart side effects.** If every network node restarts at the same moment, DHCP HA is effectively off nightly. The post-restart resync also loads neutron-server and RabbitMQ. Whether the restart disturbs the dnsmasq processes depends on your release, so verify that.
3. **Lease and state comparison.** Compare the Neutron port and IP allocations with the dnsmasq `hosts` and `leases` files for a few networks. Do this late in the day, before the restart, when drift would be largest. This is the cheapest way to see what "stale" means in practice.
4. **Agent logs and resync.** Look for resync errors, RPC timeouts or reconnect events in the dhcp-agent logs, especially after RabbitMQ events.
5. **Upstream bugs.** Search Launchpad for your release's known dhcp-agent and dnsmasq issues. Hypotheses to test, not conclusions:
   - lost RPC messages after a messaging reconnect;
   - IP reuse after port deletion;
   - lease-file drift;
   - agent state out of sync with the server.
6. **Detection.** Write down a measurable definition of "stale lease". Examples are a check that compares expected and actual dnsmasq entries, or tenant-facing symptoms such as renewal failures. Without this, you can't tell success from silent failure.

## Staged removal (state-changing, after the checks above)
- **Canary:** Disable the cron entry on **one** network node, or one AZ, that serves non-critical networks. Leave the others running.
- **Duration:** Long enough to cover several nights and any usual churn, for example one to two weeks. Pick the period from how often the problem used to appear.
- **Stop condition:** Any stale-lease detection, tenant report or resync anomaly on the canary.
- **Rollback:** Re-enable the cron job and restart the agent on that node. This is cheap and fast. The risk is in not noticing the failure, not in the rollback.
- **Roll out:** Widen in stages, one node or AZ at a time, once the canary is clean.

## Trade-offs
Removal gains control: no unexplained job and a smaller upgrade surface. It also removes the nightly unintended outage and load. The cost is a few weeks of effort and a short monitored risk window. Keeping the job has no immediate cost, but it adds control debt: the knowledge fades and it becomes a hidden requirement. The workaround test (it is safe only while the risk it adds stays smaller than the risk it removes) can't be passed today because the risk it removes was never quantified.

## Decision rights
- **Technical assessment:** the network engineers who run the agents.
- **Capability owner and risk acceptance:** the network or platform service owner, who accepts the canary risk.
- **Decision on priority and timeline:** the team lead.

The disagreement is mostly about timing and method, not about whether to remove the job. Showing that to both sides should help.

## Owner, review trigger, exit condition
- **Owner:** Name one person. Without that, the investigation won't happen.
- **Review trigger:** The end of the canary period, or any stale-lease event.
- **Exit condition, either of these:**
  - the cron is removed on all nodes with no stale-lease signal over an agreed period; or
  - the root cause is found and fixed.
- **Fallback if the symptom returns:** Keep the cron job, but document it with an owner, a detection criterion and a review date. Alternatively replace it with a targeted detect-then-restart check. Either way it becomes intentional rather than accidental. Don't restart all nodes at once.

## How we will know it worked
- Zero stale-lease detections or tenant reports for the agreed period.
- No nightly DHCP disturbance.
- The root cause, or at least the failure mode, written up in a short runbook note.
- The workaround removed from the upgrade checklist.

## Decision record (draft)
- **Decision:** Replace the unexplained nightly restart with an investigated, staged removal.
- **Reason:** The workaround is unexplained, has real side effects, and can't safely be removed blindly.
- **Accepted risk:** A short canary window on one node or AZ.
- **Owner / review date:** To be filled in.
- **Reopen if:** A stale-lease event occurs, or a vendor or upstream fix lands.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you share your OpenStack release, the number of network nodes and DHCP agents per network, and whatever you know about the cron's history, I can narrow the hypotheses and draft the detection check.