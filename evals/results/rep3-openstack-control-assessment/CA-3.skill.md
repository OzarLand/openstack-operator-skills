I can't give you one score out of 10. A single number would hide the main problem here, so I'm rating by capability instead. On what you've told me, RabbitMQ recovery sits at **Visible**, the second level on the scale (Unknown → Visible → Understood → Controlled → Recoverable → Sustainable).

Everything below is based only on your description. I haven't seen the runbook, the dashboards or any recovery history, so these are Reported facts, not Observed ones.

| What you told me | What it shows | What it doesn't show |
|---|---|---|
| Grafana dashboards for every service | Signals exist. This is the "Visible" level. | Whether anyone knows which RabbitMQ signals mean "act now" versus "normal". |
| About 400 runbook pages | There is a lot of written material. | Whether the pages have ever been used by someone other than their author. Page count is not a measure of control. |
| RabbitMQ recovery is documented | The procedure is written down. | That it's been exercised. Documented-but-never-exercised is weak evidence. |
| Lead engineer did the last three recoveries successfully | Recovery works in production, with that person doing it. That is strong evidence for the person. | That the organization can recover without them. |
| Nobody else has done one | The key gap. | |

**Why it's Visible and not higher**
- **Understood** needs at least two people who can diagnose a failure. You have one.
- **Recoverable** needs recovery demonstrated by someone other than the procedure's author. That hasn't happened.
- The three successes are good evidence about your lead engineer. They are not evidence of organizational control. Successful recoveries can also hide the risk, because they make the arrangement look safe until that person is unavailable.

If RabbitMQ is a critical dependency (for example, for VM creation), this is where low control meets high consequence. It is a single-expert recovery dependency, and it can be fixed cheaply.

**Suggested next steps**
1. **Plan:** Have a second engineer run the real recovery procedure alone, in a test environment, while the lead engineer only watches. Note every point where they get stuck or need verbal help, and fix the runbook there. That result tells you more about your control than any score.
2. **Ask now:** "If the lead engineer is unavailable next week and RabbitMQ partitions, who acts, and who decides?" If the answer is unclear, treat that as a finding.
3. **Measure:** Track the number of critical capabilities with only one person able to recover them, and the date each recovery procedure was last exercised by someone other than its author.

**What would let me rate this properly:** who owns RabbitMQ, which business capabilities depend on it, how long an outage the business will accept, whether the lead engineer wrote the runbook, and what the recovery procedure actually covers (partition, full cluster loss, or queue corruption). I'd also need the same facts for your other critical capabilities, since this rating covers only RabbitMQ recovery.