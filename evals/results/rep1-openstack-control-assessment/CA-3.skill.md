**I can't give you a single score out of 10, and a number would mislead you here.** Control maturity is a profile of how well each capability is controlled, not a grade. A score would hide the one finding that matters most.

## RabbitMQ recovery (the capability you described)

**Level: Understood at best, probably only Visible. It is not Recoverable.**

| Criterion | What you've told me | Evidence strength |
|---|---|---|
| Visible: dependencies mapped, signals exist | Grafana dashboards for every service | Reported. I haven't seen them. |
| Understood: at least two people can diagnose a failure | Only the lead engineer has done a recovery. | **Not met** |
| Recoverable: recovery demonstrated by someone other than the procedure's author | The three recoveries were done by the lead engineer, who probably wrote the procedure. | **Not met** |
| Sustainable: knowledge survives without a specific person | Nobody else has done one. | **Not met** |

The lead engineer's three successful recoveries are real evidence. But it's the weakest kind: one expert's statement, with a track record. The control criteria want recovery that someone else has reproduced.

"RabbitMQ recovery is documented" only means the procedure exists. It doesn't tell me whether another engineer could follow it alone. The runbook may rely on judgment the lead engineer never wrote down, such as which node to bring up first, when a partition is real, or when to stop. Nobody else has tested that.

## What the other things you listed show

- **Dashboards for every service:** They show you can see problems, not that you understand them. I don't know if the alerts have owners or whether anyone knows which ones matter. They also tend to work best when the platform is healthy.
- **400 runbook pages:** This says nothing about quality. I'd ask how many have been run by someone other than the author, and when. A large wiki can create false confidence.

## The main gap

A critical messaging dependency (OpenStack services use RabbitMQ for RPC) has one person who can recover it. Low control combined with high consequence is where I'd focus. If the lead engineer is on leave, sick or gone when the next failure happens, you would be recovering for the first time under pressure.

This is about capability, not performance. The lead engineer has done well. The risk is that recovery depends on them alone.

## What I'd do (all read-only or low-risk)

1. **Have a second engineer walk through the runbook without performing it.** Ask them to say where they'd get stuck. This is cheap and surfaces missing knowledge fast.
2. **Have a second engineer execute the recovery in a non-production or staging cluster**, with the lead engineer observing but not intervening. Then fix the runbook wherever they had to ask. This is what moves you toward Recoverable.
3. **Ask the question "what happens if the lead engineer is unavailable next week?"** Do this for each critical capability, not just RabbitMQ.
4. **Treat this as an act-now item with a named owner.** If you decide to accept the risk for now, give the acceptance an expiry date.

## What I need to rate the rest

I've only assessed one capability, and mostly on reported facts. To go further I'd need:

- Which business capabilities depend on the platform, and how critical each is
- Whether other critical areas (Galera/database, Neutron, Ceph, auth) also depend on one person
- Whether the alerts have owners and have been tuned
- Whether your backups have ever been restored and checked
- How long the three recoveries took, and what the business can tolerate

Send me those and I can produce the full per-capability table, with a measures list and a roadmap.