## Summary

**Verdict: Not ready.** I'd split the change before it goes to CAB.

**Review depth: full.** It touches every control-plane service, the message bus and the database. The certificate rotation has never been done here, and the rollback has not been shown to work.

**Top 3 risks**
1. **Two unrehearsed changes are stacked on the same nodes.** Rotating certs on RabbitMQ and Galera and rebooting all three controllers both put cluster quorum at risk. If something breaks afterwards, you can't tell whether the certs, the patch or the reboot order caused it. The OS update can also replace OpenSSL, Erlang or MariaDB packages, which changes TLS behaviour. That muddies the certificate result as well.
2. **"Restore old certs" is not a recovery plan.** The old certs expire in 9 days, so it only buys time. It also doesn't cover a changed CA or trust bundle, a half-rotated Galera or RabbitMQ cluster, or whether the old cert and key files were backed up at all.
3. **There is no second attempt before expiry.** Today is Sunday 25 Oct, so Saturday is 31 Oct. Expiry is about 3 Nov, which leaves roughly 3 days of margin if the window fails. The next Saturday window is already past expiry. This is my date arithmetic from "9 days", so please confirm the exact expiry timestamp and timezone from the certs.

## Objective and four questions
- **Objective (cert rotation):** avoid a full control-plane outage on ~3 Nov. This is mandatory and time-boxed. Platforms like this often fail hard when certs expire.
- **Objective (patching + reboot):** apply a security update. The reason given is "we have the window anyway", which is convenience, not a need. I don't know the CVE urgency, so please state it.
- **Capability protected:** API access, RPC over the bus, and database access.
- **Capability at risk:** all of the above, plus agents on every compute node (nova-compute, neutron agents) that talk TLS to RabbitMQ or the APIs.
- **Operational burden:** none of the three certificate types has ever been rotated here, so there is no known process or owner. Make this the first rotation and leave behind a repeatable runbook and expiry monitoring.

## Starting state
- **Unknown:** platform health today, Galera and RabbitMQ cluster state, and whether other changes are planned for Saturday.
- **Reported:** certs date from deployment 3 years ago and have never been rotated.
- **Unknown:** the full certificate inventory, whether one CA signs everything, and the CA's own expiry date. If the CA expires soon too, the plan changes.

## Scope and blast radius
- **Cert rotation:** the API endpoints (including load balancer/HAProxy and Horizon if they terminate TLS), RabbitMQ (inter-node and client), Galera (client and SST/IST), and every client of those. That includes agents on all compute nodes and any other service that trusts the CA.
- **Reboot of 3 controllers:** loss of Galera or RabbitMQ majority, VIP failover, and any controller-hosted services I haven't been told about. Control-plane downtime could reach consumers.
- **Running workloads:** instances should keep running, but nothing can be created, changed or migrated during an outage.
- **Unknown:** whether the controllers also host Galera and RabbitMQ (likely, please confirm), the number of compute nodes, and any consumers that depend on the APIs, such as CI pipelines or Kubernetes on OpenStack.

## Decision gates

| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | **unknown** | No accountable owner has accepted the failure case, including losing the control plane for part of the window. |
| Recovery | **fail** | "Restore old certs" has not been exercised, is time-limited, and ignores the cluster and CA states. |
| Evidence | **fail** | No rehearsal or staging test of the rotation or the patched controllers is mentioned. |
| Owner | **unknown** | No owner named for certificates, RabbitMQ or Galera. |
| Authority | **unknown** | Approver not named. |
| Blast radius | **fail** | Everything is touched at once, with no staging or batching defined. |
| Mandatory requirements | **pass** for certs, since expiry forces the work. Patching: **unknown**. | Is there a compliance deadline for the OS update? |

## Prerequisites

| Prerequisite | Status | Owner |
|---|---|---|
| Inventory of every certificate, SAN, issuer and expiry (endpoints, RabbitMQ, Galera, HAProxy, agents) | unknown | to be named |
| New certs issued, validated (SANs, chain, key usage, key size) and available before the window | unknown | to be named |
| Rehearsal in staging or a lab of the exact rotation, including RabbitMQ and Galera restart behaviour | unknown (no evidence) | to be named |
| Backup of old certs, keys and CA bundle, and restore tested | unknown | to be named |
| Galera backup that has been restored successfully; config backups | unknown | to be named |
| Cluster health baseline (wsrep status, `rabbitmqctl cluster_status`, queue types, `safe_to_bootstrap` state) | unknown | to be named |
| Monitoring that can see TLS errors, AMQP connections and expiry dates | unknown | to be named |
| Timed runbook with a step-by-step schedule for the 4 hours | unknown | to be named |
| Consumer communication | unknown | to be named |

## Recovery
- **Method today:** "restore old certs".
- **Exercised?** No evidence.
- **Why it is weak**
  - It returns you to certs that expire in 9 days, so it is a fallback for hours or days, not a recovery.
  - It only works if the old certs and keys are saved and the trust chain still validates.
  - If the CA changes, restoring means reverting the trust bundle on every node and agent too.
  - RabbitMQ and Galera need restarts to pick up new TLS settings. A half-rotated cluster can fail to form or sync, and reverting means more restarts.
- **Points of no return:** the first node of each cluster restarted with new TLS settings, and any Galera node that goes through a full SST.
- **Better design**
  - Where possible, use an overlapping trust bundle (old and new CA together) so nodes accept either cert during the transition.
  - Rotate one cluster member at a time, verify, then continue.
  - Pre-agree a stopgap, such as a short-lived emergency cert, if the rotation fails and expiry is still near.
- **Evidence to preserve:** current certs and keys, CA bundles, service configs, and cluster state output from before the change.

## Execution boundaries and stop conditions

**Recommended structure.** Order the work to reduce risk, not just to fit the window.
1. **Before Saturday, if the rehearsal passes:** rotate certs on the individual API endpoints one service at a time during business hours. They are lower risk and give early signal.
2. **Saturday window:** rotate RabbitMQ and Galera certs, one node at a time. Do **not** reboot in the same window.
3. **Next available window:** OS update and rolling controller reboots, one at a time, with health checked between nodes. The certs will already be fixed by then, so the patch gets its own rollback story. If the patch is urgent, schedule it as its own change before or after, not combined.

**Stop conditions**
- Any cluster member fails to rejoin or sync.
- AMQP or database TLS errors in service logs that you can't explain.
- API error rates above your baseline. You'll need to supply the threshold.
- Compute agents show as down and don't recover.
- No decision-maker is reachable.
- The remaining window is too short to restore the previous state safely. Fix the cut-off time in advance.

## Verification
- Every new cert's chain, SANs and expiry checked from outside and inside (`openssl s_client`), and visible in monitoring.
- Galera `wsrep_cluster_size` = 3 and status Primary. RabbitMQ shows all 3 nodes with no partitions.
- End-to-end test: create, attach and delete a VM, a volume and a port.
- All compute services and agents report up.
- No TLS handshake errors in logs, checked after an observation period you define (I won't set one for you).
- Monitoring updated so the next expiry is alerted well ahead.

## Decision rights
- **Technical assessor:** unknown.
- **Capability owner:** unknown. This is a gap given nobody has rotated certs before.
- **Accountable:** unknown.
- **Decision maker:** unknown.
- **Consumer communication:** unknown. Tenants should be told creation and changes may be unavailable during the window.

## Gaps and questions
1. Exact expiry timestamps for every certificate, and the CA's expiry.
2. Is there a staging or lab environment that mirrors production?
3. Where do Galera and RabbitMQ run? Is the cluster on the three controllers?
4. How are certs deployed (Kolla-Ansible, Puppet, manual)? That determines whether a rolling rotation is supported.
5. Is the same CA used throughout, or will it change?
6. Why must the OS update happen this window? What CVE or compliance date drives it?
7. Which workloads depend on the APIs staying up?
8. Has the OS update been tested on a controller?

## Decision record (draft)

- **Change / decision:** Internal TLS certificate rotation (APIs, RabbitMQ, Galera); OS security update and controller reboots
- **Date:** Saturday 31 Oct 2026 (window), subject to approval
- **Decision owner:** unknown
- **Capability owner:** unknown
- **Technical assessor:** unknown

**Objective:** Prevent control-plane outage when certificates expire (~3 Nov). Apply security patch (urgency unknown).

**Current state:** Certs from deployment, never rotated. Platform health and cluster state unknown.

**Evidence:** None provided beyond the expiry date and the change description.

**Uncertainty:** Certificate inventory, CA expiry, rehearsal results, cluster state, backups, restore ability, patch urgency.

**Options considered:**
- (A) Combined change in one window: rejected, because failures can't be attributed and recovery is unproven.
- (B) Certs only on Saturday, reboots in a separate window: **recommended**.
- (C) API certs earlier, RabbitMQ and Galera Saturday, patch separately: recommended if rehearsal passes.

**Trade-offs:** Splitting costs another window and approval but keeps one failure domain per change and keeps the patch from affecting the cert result.

**Selected option:** Pending CAB. Recommended B or C.

**Recovery:** Needs a rewritten plan: backed-up old certs, overlapping trust bundle, node-by-node rotation, and a pre-agreed emergency cert if the rotation fails.

**Stop conditions:** As listed above.

**Verification:** As listed above.

**Follow-up:** Certificate lifecycle runbook, expiry alerting, an owner for certificates, and a rotation schedule so this does not recur.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can turn this into a shareable page for CAB if you'd like. I can also draft the step-by-step runbook once you've answered the questions above.