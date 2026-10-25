**My recommendation is neither "remove it this week" nor "leave it alone." Turn the removal into a controlled experiment, and have the team lead own the exit date.** The lead is right that the workaround shouldn't be permanent. But nobody understands what it protects against, so deleting it is a change with an unknown blast radius, and that fails the evidence gate. The fear is also not a reason to keep it. Two years of nightly restarts on every network node is itself a risk.

## Decision to make
- **Situation:** A nightly cron restarts `neutron-dhcp-agent` on all network nodes to hide a stale-lease symptom that nobody can explain.
- **Objective:** Stop depending on an unexplained workaround without causing a tenant-visible DHCP or connectivity outage.
- **Decision owner:** Unknown. The team lead can decide to remove it, but the platform or service owner has to accept the business risk. Please confirm who that is.

## Evidence and uncertainty
| Fact / belief | Confidence | Source |
|---|---|---|
| Cron restarts the agent nightly on all network nodes, for about 2 years | Reported | You |
| The cause of the stale leases is not understood | Reported | You |
| The restart works (symptom stays hidden) | Assumption. It is probably true, but nobody has shown what happens without it. | Inferred |
| What "stale lease" means here (dnsmasq lease file, host/addn_hosts files, wrong IP, or no reply) | Unknown | Gap |
| Release, `dhcp_agents_per_network`, and number of networks and nodes | Unknown | Gap |
| Whether the restart is a symptom-masker for something broader, such as RPC/RabbitMQ message loss or agent-DB desync | Hypothesis | Untested |
| Whether anyone has ever tried disabling it | Unknown | Ask around |

## Options
| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| A. Remove this week as asked | Unknown failure mode returns on all nodes at once. Possible VM DHCP failures or IP reuse problems. The first sign may be a tenant ticket. | None for the platform, but the debt stays hidden. |
| B. Keep as is | Low immediate risk | The workaround becomes accidental architecture. The restart can mask the real fault and could interrupt DHCP renewals during an incident. Knowledge keeps eroding. |
| C. Instrument, then canary-remove, then remove everywhere, with exit criteria | Slower. It needs some effort and a window. | Low. The workaround stays one more cycle, with a deadline. |
| D. Replace the restart with a targeted check and fix (resync or a specific dnsmasq action only when staleness is detected) | Needs the root cause first | Low |

## Gates
| Option | Failed gate | What would satisfy it |
|---|---|---|
| A | Insufficient technical evidence, unbounded blast radius (all nodes), and recovery path not demonstrated. | Evidence of what the restart actually fixes, and a canary result. |
| B | Does not fail a gate, but it fails the workaround test. Nobody can say the risk it removes outweighs the risk it adds. | An owner, a defined scope and an exit condition. |
| C | Passes if one node (or one DHCP agent per network, if redundancy exists) is chosen and an owner is named. | |
| D | Not yet available because the root cause is unknown. | It becomes the outcome of C. |

## Trade-offs
- **C keeps more options open.** It produces knowledge that exists whichever way the result goes, and it fits the rule that a workaround is safe only while the risk it adds stays smaller than the risk it removes.
- **A looks decisive but stacks uncertainty.** Removal is an experiment run on production with no instrumentation.
- **A fixed deadline protects against forgotten debt.** Without one, C turns into B.

I did not use a weighted score. The gates already separate the options, and scoring would imply more precision than the evidence supports.

## Recommendation
Choose **C**, with a firm time-box (for example, fully decided within 2–3 weeks). The lead gets a concrete removal plan this week, not the removal itself.

**This week (read-only first):**
1. Find the history. Search the cron's commit or ticket, the old incident tickets and chat, and the authors. Ask the people who are afraid what they fear specifically. *(read-only)*
2. Capture what "stale" looks like. For a few ports, compare Neutron's DB state against the dnsmasq `host` and `addn_hosts` files and the lease file in the DHCP namespace directory on the node. Check agent logs for resync errors and RPC timeouts around the nightly restart. Check RabbitMQ health for lost or unconsumed messages on the DHCP agent queues. *(read-only)*
3. Confirm the facts: release, `dhcp_agents_per_network`, whether a network's DHCP is served by more than one agent, and whether the agent or its dnsmasq processes are managed by containers or systemd. Agent restart behavior and dnsmasq survival differ by release and deployment. *(verify for your release)*
4. Define a detector for the failure, such as a script that compares the DB's port/IP list to the dnsmasq host files, and alert on drift. This is what will tell you whether the restart is needed.

**Then (state-changing, needs approval from the platform owner):**
5. Canary. Disable the cron on one node, or for a subset of networks that is covered by a second DHCP agent. Do it in a window with the detector running and an operator watching.
   - **Stop and re-enable the cron if** the detector shows drift, DHCP requests go unanswered, or tenants report address problems.
   - **Recovery:** re-enabling the cron or manually restarting the agent is quick and reversible.
6. Observe for at least several nightly cycles and across a lease-renewal period. Then extend to all nodes, or keep the workaround with a documented reason.

**Accepted risk:** the nightly restart stays for a few more weeks, and one node runs without it during the experiment.

## Decision rights
| Role | Responsible for |
|---|---|
| Network or platform engineers | Technical assessment and the detector |
| Platform owner | Accepts the business risk of the canary |
| Team lead | Sets the deadline and decides on full removal, based on the canary evidence |

Anyone can challenge the plan. If the team lead and the cautious engineers disagree on risk, record exactly where, for example whether a tenant-visible outage is plausible, instead of averaging the views.

## Owner, review trigger, exit condition
- **Owner:** one named engineer, not "the team."
- **Review trigger:** the canary result, or any incident involving the DHCP agent.
- **Exit condition:** the cron is removed, or it is replaced by a targeted fix. If the canary shows it is still needed, it is documented with purpose, scope, side effects, detection and recovery, and reviewed at the next upgrade.

## How we will know it worked
Zero drift alerts and no DHCP-related tickets over an agreed number of weeks without the cron. The root cause, or at least the failure mode, is written down. A second engineer has been able to explain it.

## Decision record (draft)
Decision: retire the nightly neutron-dhcp-agent restart via a canary plan, not an immediate removal. Reason: the cause is undocumented and the blast radius is all network nodes. Alternatives rejected: immediate removal (insufficient evidence), indefinite retention (no exit). Owner, window and abort criteria: to be filled in. Review date: the end of the time-box.

**Two quick questions that would sharpen this:** what release are you on, and what exactly did people see when it went wrong two years ago (VMs not getting addresses, duplicate IPs, or something else)?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.