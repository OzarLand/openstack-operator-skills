I won't give you a single score out of 10. A lone number would hide the one thing that matters here. What you've told me does support a rating for RabbitMQ recovery, so here is that one.

## RabbitMQ recovery: Understood at best, not Recoverable

The criteria below are from the control spectrum, which runs Unknown, Visible, Understood, Controlled, Recoverable, Sustainable.

| Evidence | What it supports | Confidence |
|---|---|---|
| Grafana dashboards for every service | **Visible**. The signals exist. I don't know if anyone has established what each alert means. | Reported |
| About 400 wiki runbook pages | Coverage. It says nothing about whether the pages are accurate or usable. | Reported |
| RabbitMQ recovery is documented | The procedure exists. | Documented but never exercised by anyone else |
| Lead engineer did the last three recoveries successfully | Recovery works in production when this person does it. | Observed in production, but only for one person |
| Nobody else has done one | Fails the **Understood** test (at least two people can diagnose a failure). Also fails the **Recoverable** test (recovery shown by someone other than the procedure's author). | Reported |

My assumption is that the lead engineer wrote or shaped the runbook. If so, the runbook has never been tested by anyone but its author. Please confirm that.

Three successful recoveries is good evidence that the lead engineer can do it. It is not evidence that the organization can. Right now, your RabbitMQ recovery is this one person's expertise with a wiki page behind it.

## Why this matters more than a score

- **Single-expert dependency is your top gap.** If the lead engineer is away, sick or gone during a broker failure, you have an untested runbook and nobody who has used it.
- **Volume is not control.** 400 pages and dashboards for every service show effort. They don't show that anyone can act on them under pressure. Teams often rate themselves higher than their evidence supports, and this pattern is a common cause.
- **Cost of a failed recovery.** RabbitMQ is the messaging layer for the control plane, assuming this is an OpenStack deployment. A bad recovery attempt can make things worse. Wrong ordering or a purge or reset at the wrong time can lose in-flight operations.

## What I can't rate yet

- Whether this is OpenStack, and which capabilities depend on RabbitMQ.
- How long a recovery took, and how long the business can tolerate.
- Whether the runbook has been reviewed or updated since the last recovery.
- Whether the other 399 pages have the same single-author pattern.
- Ownership and decision rights: who can authorize destructive steps such as purging queues or resetting nodes.

## Recommended next steps (all planning, nothing state-changing)

1. **Act now.** Pick a second engineer and have them walk through the RabbitMQ runbook with the lead engineer observing but not helping. Do this in a test or staging environment first. Record every place they get stuck or ask a question, and fix the runbook where it fails.
2. **Plan.** Have that second engineer do a full recovery in a controlled environment, then a supervised one. Only then can you claim **Recoverable**.
3. **Measure.** Track "critical capabilities with only one engineer who has recovered them" as a number you want to see fall. Repeat the exercise for your next few most critical services.

If you tell me which capabilities depend most on RabbitMQ and how many people are on the team, I can build the full per-capability assessment with owners and review dates. If the platform isn't OpenStack, tell me and I'll adjust, because this assessment method is built around it.