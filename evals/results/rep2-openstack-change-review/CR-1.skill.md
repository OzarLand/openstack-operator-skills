# Change review: TLS rotation plus controller patching, Saturday window

## Summary

**Verdict: Not ready** to submit as written.

**Depth:** full. This touches every control-plane endpoint, the message bus and the database. It has never been rehearsed, and the rollback is not credible. The change is also two changes bundled together.

**Top 3 risks**
1. **Rollback "restore old certs" isn't a recovery path.** The old certs expire in 9 days, so restoring them only buys a few days. It also depends on assumptions nobody has verified (see Recovery).
2. **Two independent high-risk changes in one 4-hour window.** If the cloud is unhealthy afterwards, you can't tell whether a TLS fault or a patch/reboot fault caused it. Rolling back one may not fix the other.
3. **First-ever rotation, nothing rehearsed.** No one on the team has done it, and it covers RabbitMQ and Galera, the two components where a TLS mismatch splits a cluster.

**Recommendation:** split the change. The cert rotation is the time-critical part, so it keeps the Saturday window. The OS patch and reboot move to a separate window after a stability period. Details are under Gaps.

## Objective and four questions
- **Objective:** keep the control plane trusted and available past the certificate expiry, which is **Observed/Reported as 9 days away** (you stated it, no cert output shown). An expired internal cert is a classic cause of a total control-plane outage, so the objective is valid and urgent.
- **Patching** has a separate objective: closing OS security vulnerabilities. It is not stated how severe they are or whether they are actively exploited. That determines whether it really can't wait.
- **Capability protected:** API, messaging and database trust.
- **Capability at risk:** everything that talks to Keystone, Nova, Neutron and the other APIs, RabbitMQ or Galera, which is the whole platform.
- **Operational burden:** none, as long as a rotation procedure and expiry monitoring are left behind afterwards. At present there are none.
- **Required after the delivery team moves on:** a documented, rehearsed rotation runbook and an owner. Nothing in the request provides these.

## Starting state
- **Unknown:** current platform health. I have no evidence of Galera sync state, RabbitMQ partitions or alarms.
- **Unknown:** whether other changes fall in the same window.
- **Unknown:** exact expiry dates per certificate. "9 days" is reported as a single date for all of them.
- **Derived from today's date (2026-10-25), assuming "Saturday" means the coming one:** the window is Oct 31 and expiry is about Nov 3. A failed window leaves roughly **3 days** to retry, which is thin if the rotation fails and needs rework.

## Scope and blast radius
- API endpoints, the RabbitMQ cluster and the Galera cluster. **Unknown:** whether the cert list also includes the load balancer/HAProxy, etcd/memcached TLS, and the clients (nova-compute, neutron agents and the like) on every compute node.
- **Cert rotation:** every service restarts or reloads to pick up new certs, and every client must trust the new certs. If a new CA is issued, the trust bundle must reach every controller and compute node first.
- **Patch and reboot of three controllers:** this reduces quorum for Galera and RabbitMQ while each node is down. Rebooting more than one at a time loses quorum. This is a control-plane outage risk, and running VMs are affected only indirectly.
- **Consumers:** API users and automation will see errors and reconnects. **Unknown:** whether workloads depend on control-plane availability, for example orchestration or autoscaling.

## Decision gates

| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | **Unknown** | No stated impact for the failure case. Nobody named who accepts a control-plane outage. |
| Recovery | **Fail** | "Restore old certs" has not been shown to work and is time-limited (see Recovery). The OS update has no stated rollback at all. |
| Evidence | **Fail/Unknown** | No rehearsal or staging test. Nothing says the new certs have the right SANs, key usage and chain for RabbitMQ and Galera. |
| Owner | **Unknown** | No named owners for the capabilities. |
| Authority | **Unknown** | No named approver for the risk. |
| Blast radius | **Fail** | Not bounded: all certs and all three controllers in one window, with no batching or scope limits. |
| Mandatory requirements | **Pass (Reported)** | The rotation helps, since expired certs would breach security policy. The patching also supports compliance. This is not verified. |

## Prerequisites

| Prerequisite | Status | Owner |
|---|---|---|
| Inventory of every cert (endpoint, expiry, SANs, issuing CA, deployed location) | Unknown | Unknown |
| New certs issued and validated *before* the window (chain, SANs, key usage, key/cert match) | Unknown | Unknown |
| Rehearsal in a representative environment, or at least staged production | Not done (never rotated) | Unknown |
| Backup of old certs, keys and service configs, restore tested | Unknown | Unknown |
| Galera backup that has been restored successfully | Unknown | Unknown |
| Monitoring that sees TLS handshake errors, cluster state and cert expiry | Unknown | Unknown |
| Runbook with decision points and per-step verification | Missing (only "restore old certs") | Unknown |
| Who is available during the window, including DB, messaging and network owners | Unknown | Unknown |
| Consumers notified | Unknown | Unknown |

## Recovery

**What "restore old certs" doesn't cover**
- **Time limit.** The old certs expire in 9 days. A rollback that works leaves you at the same deadline with the problem unsolved.
- **Mixed trust state.** If the rotation changes the CA, then partially-rotated clients and servers may not trust each other. Rolling back one side only can leave a split state. This needs a defined rollback order and a trust bundle that includes both old and new CAs during the transition. Only the team knows if this applies. **Verify for your deployment tool and release.**
- **Galera and RabbitMQ specifics.** Mixed TLS settings between cluster members can prevent nodes from joining or syncing. Galera state transfers (SST/IST) can also use the certs. Whether a rolling rotation is possible depends on your configuration. **Verify for your Galera and RabbitMQ versions.**
- **The old private keys and configs must still exist and be backed up.** Whether they do is Unknown.
- **Not exercised.** The rollback has never been run.

**Point of no return:** unknown. For example, if the old CA is removed from trust bundles during the window, there is no easy way back. Define the point in the runbook and make the window avoid it until verification passes.

**OS update and reboot rollback:** unknown. For example, booting the previous kernel or restoring a snapshot. Package-level downgrades are often unreliable. This needs a stated method.

**Evidence to preserve before starting:** old certs, keys and configs for every service, Galera and RabbitMQ cluster state (`wsrep_*` status, `rabbitmqctl cluster_status`), a database backup and the package list before the update.

## Execution boundaries and stop conditions
**Boundaries:** one component at a time, one controller at a time, and a verification gate between each. Suggested order for the cert window, to be confirmed by your platform's owners: trust bundle distribution first, then the messaging and database layer with a healthy-cluster check after each node, then the API endpoints, and the clients last.

**Stop conditions (stop and decide, don't push on):**
- Any node fails to rejoin Galera or RabbitMQ after a cert change.
- TLS handshake errors rise above an agreed baseline.
- Quorum is lost or at risk.
- An expected dependency behaves differently from the rehearsal.
- Monitoring can't show the effect.
- The rollback is no longer credible.
- The decision authority is unreachable.
- A fixed time check is reached without the cert phase done. This should reserve enough of the 4 hours to execute the rollback.

## Verification
Designed before the window:
- All services reconnect over TLS. There are no handshake errors in service, RabbitMQ and Galera logs.
- Galera is `Synced` on all three nodes with the correct cluster size. RabbitMQ shows all members, no partitions, and queues are healthy.
- **Capability test end to end:** authenticate, create a VM, a network and a volume, attach them, and delete them. Check from a compute node too, not only from a controller.
- Monitoring shows the new expiry dates.
- **Observation period:** agree a duration with the owners. The new state gets no trust from the old state's stability.
- For the patch, a separate set: kernel/package versions, services up after each reboot, cluster re-sync before the next node is rebooted.

## Decision rights
- **Technical assessor:** unknown.
- **Capability owner:** unknown.
- **Accountable for outcome:** unknown.
- **Decision maker:** unknown. CAB approves the process, but someone who is entitled to accept a control-plane outage must be named.
- **Consumer communication:** unknown. Someone should announce the window and the possibility of API errors.

## Gaps and questions
1. **Split the change.** Rotate certs on Saturday. Patch and reboot controllers in a separate later window, after the observation period. Bundling is justified only by "we have the window anyway", which is convenience, not risk reduction. The one exception is a security update that is actively exploited, which would be a different priority and the CAB should hear it. How severe is it?
2. **Rehearse the rotation now,** before Saturday, in staging or a lab. Because it's a first rotation, treat it as an unknown with unknown blast radius.
3. **What is the fallback if Saturday fails?** There are about 3 days left before expiry. Is there a second window or an emergency path?
4. **Does the rotation change the CA, or only the leaf certs?** This decides the transition design and the rollback.
5. **Is a rolling rotation possible for Galera and RabbitMQ,** or does it need a cluster stop? That's the difference between a quiet change and a planned outage. Verify against your versions.
6. **Rewrite the rollback** with concrete steps, order, the point of no return, who triggers it and a time limit.
7. **Name owners and approvers.** Who accepts the risk?
8. **Provide for review** (redact secrets first, never send private keys or passwords): the cert inventory with expiry dates, deployment method (Kolla-Ansible or other), versions and cluster topology, and current Galera/RabbitMQ health output.

## Decision record (draft)

- **Change / decision:** Rotate internal TLS certificates (APIs, RabbitMQ, Galera). OS security update and reboot of 3 controllers are proposed to be separate.
- **Date:** Saturday window (assumed 2026-10-31), unconfirmed.
- **Decision owner / Capability owner / Technical assessor:** unknown.

**Objective:** avoid control-plane outage from cert expiry (about 2026-11-03, reported). Separately, close OS security vulnerabilities (severity unknown).

**Current state:** certs installed at deployment 3 years ago, never rotated. Platform health unknown.

**Evidence:** Reported expiry in 9 days. No rehearsal, no backup or restore test, no monitoring evidence provided.

**Uncertainty:** CA change or leaf only, rolling feasibility on Galera/RabbitMQ, client trust, patch rollback, whether other changes share the window.

**Options considered:**
- (A) Both changes in one window: rejected for now. Not attributable on failure, and the rollback is not credible.
- (B) Cert rotation Saturday, patching later: **recommended**.
- (C) Patching first, rotation later: rejected because the expiry deadline is the hard constraint.
- (D) Staged production rotation across several windows: possible if the rehearsal shows rolling is feasible. It takes longer but lowers risk.

**Trade-offs:** (B) costs a second window and delays patching. In return it isolates failures and keeps recovery credible. The residual risk is a vulnerable OS for a limited period, which needs an owner's acceptance with a review date.

**Selected option:** pending rehearsal and owner decision.

**Recovery:** to be written (steps, order, point of no return, time limit, tested restore). Currently insufficient.

**Stop conditions:** as listed above.

**Verification:** as listed above, plus an agreed observation period.

**Follow-up:** write the rotation runbook, schedule rotation in the maintenance calendar, add expiry monitoring with warning lead time, and review the patch deferral at a fixed date.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can put this into a shareable page for the CAB pack if you want one.