**I can't give you a score out of 10. A single number would mislead you here, and the evidence you've given covers only part of the picture.** Maturity is better reported per capability, with the evidence behind each rating. Below is what your facts support.

## Scope and method
- This rates one capability, RabbitMQ and the messaging control plane, from four statements you made. I haven't inspected any system.
- I haven't assessed anything else, such as Galera, Nova, Neutron or Ceph. You didn't mention them, so they are Unknown.

## Control level: RabbitMQ recovery

| Your statement | What it shows | Confidence |
|---|---|---|
| Grafana dashboards for every service | Visibility exists. I can't tell whether anyone knows what a degraded signal means, or whether the dashboards still work when RabbitMQ is unhealthy. | Reported |
| About 400 runbook pages | Volume, not quality. I don't know whether they are current, tested or read. | Reported |
| RabbitMQ recovery is documented | Documented but never exercised by anyone other than its author. | Weak |
| Lead engineer did the last three recoveries successfully | This is real production evidence, but it all comes from one person. | Strong, but a single expert |
| Nobody else has done one | Recovery is not independently reproduced. | Decisive negative |

**Rating: Visible, possibly Understood.**
- **Understood** needs at least two people who can diagnose a failure. I have no evidence of a second person.
- **Recoverable** requires recovery demonstrated by someone other than the procedure's author. Your own statement rules that out for now.
- **Controlled** and **Sustainable** are not established.

Three successes is good news, but it doesn't mean you have control. It means one person has control. If that person is on leave, ill or gone when RabbitMQ fails, your recovery capability is whatever the wiki can do for a stranger, and that has never been tested.

## Main risk
RabbitMQ sits under most OpenStack control-plane operations: scheduling, creating VMs, and agent heartbeats. A failure is high-consequence, and your recovery depends on one person. That makes this your most important gap. The wiki and dashboards feel like control, but they haven't been shown to work without the lead engineer.

## Findings and decisions

| Finding | Outcome | Owner |
|---|---|---|
| Recovery depends on one engineer | **Act now** | Unassigned (you need to name one) |
| Runbook never executed by a second person | **Act now** | Unassigned |
| 400 pages, with no evidence of currency or testing | **Plan** | Unassigned |
| Dashboards: unclear whether they work during a RabbitMQ failure | **Plan** | Unassigned |

None of these should be accepted as risks without a named owner and a review date.

## Confidence tests I'd run
1. **Observed walkthrough:** a second engineer follows the RabbitMQ runbook in a test or staging environment while the lead engineer watches and stays silent unless there's a safety issue. Where they get stuck is where the runbook is incomplete.
2. **Absence test:** ask the owner what happens if the lead engineer is unreachable next week. If the answer is "we'd wait" or "we'd try the wiki", that's your current control level.
3. **Alert test:** pick one RabbitMQ alert and ask a non-expert what it means and what they'd do first.
4. **Degraded-state check:** confirm the dashboards stay readable when RabbitMQ is down. If they depend on the same message bus, they may not.

Any step beyond reading the runbook (restarting nodes, resetting the cluster, purging queues) is state-changing. It needs a named approver, and you shouldn't do it on production as a drill.

## Measures to track (trends, not targets)
- Number of critical capabilities with only one engineer able to recover them. Today RabbitMQ is at 1.
- Months since each recovery runbook was last run by someone other than its author.
- Runbooks changed or reviewed in the last 12 months, as a share of the 400.

## Gaps in this assessment
I don't know your answers on:
- Criticality of the workloads that depend on RabbitMQ.
- Who owns the capability, and whether the team has an on-call rotation.
- Your acceptable recovery time.
- RabbitMQ topology (clustering and queue types) and version.
- The state of Galera, Ceph and the other services.
- Backup restore testing.
- Local patches or drift from upstream.

If you tell me which OpenStack services you run and who is on the team, I can extend this to a fuller per-capability profile. If you want a first step, I can draft the observed-walkthrough test for RabbitMQ.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.