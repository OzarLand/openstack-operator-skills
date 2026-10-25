## Summary

**Verdict: Not ready as written. Split the change, then resubmit.**

Depth: full review. This is a control-plane-wide change with no rehearsal, no meaningful rollback, and a second high-impact change stacked on top.

Top risks:
1. **The rollback doesn't work.** "Restore old certs" returns you to certificates that expire in 9 days. It is a delay, not a recovery. It also assumes the old files, keys and trust chain are intact and that every service can reload them without a restart (unknown).
2. **Two unrehearsed changes in one window.** If the cluster is unhealthy after the reboots, you can't tell whether the certificates or the patches caused it. A TLS fault and a quorum fault look similar on the bus and the database.
3. **First-ever rotation across three dependent layers** (API endpoints, RabbitMQ, Galera). Agents on every compute node connect to RabbitMQ and the APIs over TLS, so a trust or SAN mistake reaches the whole platform at once.

I assumed "Saturday" is 2026-10-31, which leaves about 3 days of margin before expiry. Please confirm the real expiry date and time. Once Saturday's window is spent, the margin shrinks to a single retry.

## Objective and four questions
- **Objective:** (1) avoid a platform-wide TLS failure when the certificates expire; (2) apply a security update.
- **Protects:** control-plane availability, which depends on the API, bus and database trusting each other.
- **Could affect:** every service, plus agents on all computes. Tenant workloads keep running if the control plane drops, but nobody can manage them.
- **Burden added:** none if you leave a rotation procedure and expiry monitoring behind. Unknown today.
- **Needed afterwards:** a documented, rehearsed rotation. Right now the knowledge is nobody's, because the last deployment was 3 years ago.

Item (1) is urgent and has a hard deadline. Item (2) has no stated deadline. "We have the window anyway" is not a reason to combine them (see the next section).

## Starting state
- **Unknown:** current platform health (Galera `wsrep_cluster_size` and status, RabbitMQ cluster and partition state, a recent clean control-plane check).
- **Unknown:** where the certificates came from (internal CA or self-signed), the CA's own expiry, whether SANs and key usage are correct, and whether the deployment tool (Kolla, OSA, etc.) manages them.
- **Unknown:** other changes scheduled for the same window.
- **Reported:** the certificates expire in 9 days and have never been rotated.

## Scope and blast radius
- API endpoints (internal, and external if "all internal" includes them), HAProxy/VIP, RabbitMQ (client and inter-node TLS), Galera (client TLS and wsrep replication TLS).
- **Not mentioned, so I'd inventory them:** libvirt/QEMU TLS, etcd, memcached, Ceph RGW or other backends, Horizon, Octavia, and any service with a custom CA bundle.
- **Trust distribution:** nova-compute, Neutron agents and Cinder on every node all need the right CA bundle. This is the usual cause of "controllers fine, computes can't connect".
- **Reboot scope:** all three controllers carry the VIP, Galera and RabbitMQ quorum. Rebooting more than one at a time breaks quorum. Whether controllers also run L3/DHCP agents is unknown. If they do, tenant networking is affected too.
- **Consumers:** every API user and automation tool, until the window ends.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | No statement of acceptable API downtime, consumers, or who has accepted the failure case. |
| Recovery | **fail** | "Restore old certs" returns to expiring certificates. It was never exercised, and the point of no return is undefined. No recovery exists for the OS update either (see Recovery). |
| Evidence | **fail** | Never rotated and no rehearsal reported. Galera replication TLS and RabbitMQ reload behaviour are unproven here. |
| Owner | unknown | No owner named for certificates, RabbitMQ or Galera. |
| Authority | unknown | Approver not named. |
| Blast radius | **fail** | Whole control plane plus all agents, with no staged scope. Controller reboots are not constrained to one at a time. |
| Mandatory requirements | pass (provisional) | Rotation is itself a security requirement. Check the crypto policy (below). |

Any failed gate means not ready. I won't soften that because of the deadline. What the deadline does is make the preparation work urgent.

## Recommended restructure
Keep the CAB request, but change what it asks for:

1. **Before Saturday (low-risk, no outage):** inventory every certificate. Check the CA's own expiry, since a 3-year-old CA may expire soon too. Check that the platform is healthy. Rehearse the full rotation in a staging or lab environment built like production. Take a restorable backup of the old certificates, keys and configs.
2. **Option to evaluate, to reduce risk:** re-issue certificates from the same CA and the same keys with new validity dates. That changes only the certificate files, with no trust or key change. It is not suitable if the CA is expiring or the keys must change. Confirm with whoever owns the CA.
3. **If a new CA is involved, use two phases.** First distribute a trust bundle containing both old and new CAs everywhere. Then swap the certificates, and remove the old CA later. This makes rollback real until the old certificates expire.
4. **Saturday: rotation only.** Do it in dependency order and one controller at a time. Do not patch.
5. **Patch and reboot in a separate window** (a later Saturday, or a weeknight if the platform tolerates it). Do the controllers one at a time, waiting for Galera sync and RabbitMQ rejoin before the next. Treat this as its own change.

Rejected option for the record: combining both in one window. The reason is that a failure can't be attributed, and rollback of one change would disturb the other.

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Certificate inventory (all services, SANs, expiry, issuer, CA expiry) | unknown | unknown |
| Rehearsal in a representative environment | unknown / not done | unknown |
| Backup of old certs, keys, configs; restore tested | unknown | unknown |
| Health baseline: Galera, RabbitMQ, Keystone token issue, VM create test | unknown | unknown |
| Reload vs restart behaviour per service, including Galera wsrep TLS requirements | unknown. **Verify for your MariaDB/Galera and RabbitMQ versions.** | unknown |
| OS update contents (does it touch openssl, erlang, mariadb, rabbitmq, kernel?) | unknown | unknown |
| Crypto policy effects of the update on 3-year-old certificates (e.g. weak signature or key-size rejection) | unknown | unknown |
| Previous kernel and package versions retained; out-of-band console access (BMC/IPMI) to all controllers | unknown | unknown |
| Monitoring for TLS handshake errors and certificate expiry | unknown | unknown |
| Consumer communication | unknown | unknown |

## Recovery
- **Certificates:**
  - *Method proposed:* "restore old certs". *Exercised:* no.
  - *What it actually gives you:* a few days at most. Recovery has to be "roll back to a working state, then retry before expiry". If the deadline has passed, rollback is impossible and you can only roll forward.
  - *Points of no return to define:* trust bundle replaced on computes, Galera restarted with the new certificates, old files overwritten.
  - *Preserve before starting:* old certs, keys, CA bundles and service configs from every node, in a place that doesn't depend on the control plane. Record the current Galera and RabbitMQ state.
- **OS update and reboot:**
  - Package downgrade or an old kernel is the nearest equivalent to a rollback. Whether that is possible depends on your distribution and repos, and it is unknown here.
  - Roll-forward is usually the realistic path.
  - Before the window, define what you do if a controller doesn't come back, and whether you can lose one controller and still run on two.
- **Galera:** if a node fails to rejoin after the reboot, the response depends on cluster state and which node was last. Do not bootstrap on instinct. The decision needs a named person and the evidence in front of them.

## Execution boundaries and stop conditions
**Boundaries:** one controller at a time. One service layer at a time (trust, then APIs, then bus, then database). Do not begin the next controller until the current one is verified healthy.

**Stop conditions (stop and decide; do not push on):**
- A handshake or verification error appears on any component, or compute agents lose connection.
- Galera cluster size or sync state differs from the baseline, or RabbitMQ reports a partition.
- Rollback is no longer credible (e.g. backup not restorable, old files overwritten).
- Monitoring can't show the effect.
- The elapsed-time budget is exceeded (set time checkpoints inside the 4 hours, with a latest go/no-go for each phase).
- The approving authority is unreachable.

Resuming after a stop is a new decision.

## Verification (defined in advance)
- Every certificate: new expiry date visible to monitoring, correct chain and SAN, checked from the client side (read-only).
- Galera: cluster size and sync state, plus a write and read test.
- RabbitMQ: cluster status, no partition, queue consumers present, agent heartbeats from all computes.
- Platform capability end to end: token issue, create a test VM, network, volume and image, and delete them.
- Compute agents: `nova-compute` and Neutron agents all up.
- Observation period: a defined period after the change before declaring success. The thresholds are yours to set from your baselines.

## Decision rights
Assessor: unknown. Capability owner: unknown. Accountable: unknown. Decision maker: unknown. Consumer communication: unknown. CAB needs real names here. The business owner should explicitly accept the failure case, which is a control-plane outage that may exceed the window.

## Gaps and questions
1. What are the exact expiry dates (including the CA's) and what issues the certificates?
2. Is there a staging or lab environment? Has anything been rehearsed?
3. How are the services deployed and configured (Kolla, Ansible, manual)? Does the tool manage certificates?
4. Which service versions: MariaDB/Galera, RabbitMQ and Erlang, OpenStack release, OS?
5. Do controllers also host network agents, Ceph monitors or the VIP/HAProxy pair?
6. What does the OS update change, and do you have out-of-band access to the controllers?
7. Who owns each component and who can authorize the outage?

(Please redact any passwords, tokens or keys before pasting configs or output.)

## Decision record (draft)
- **Change / decision:** Internal TLS certificate rotation (API, RabbitMQ, Galera). OS security update and controller reboot proposed to be separated.
- **Date:** Saturday window, 4 h (date to confirm). **Decision owner / Capability owner / Technical assessor:** unknown.

**Objective** — Avoid control-plane failure at certificate expiry; keep the platform patched.
**Current state** — Certificates 3 years old, expiring in 9 days, never rotated. Health unknown.
**Evidence** — Reported expiry only. No rehearsal or inventory shown.
**Uncertainty** — CA expiry, reload behaviour, trust distribution to computes, Galera TLS behaviour, OS update effect on crypto.
**Options considered** — (A) combined change as submitted: rejected (unattributable failures, fake rollback). (B) rotation only, with rehearsal, then patching separately: recommended. (C) same-CA, same-key re-issue as a minimal-change variant of B: evaluate.
**Trade-offs** — B needs preparation time before Saturday and a second window. A saves one window and risks both changes.
**Selected option** — Pending; recommended B, or C if the CA allows.
**Recovery** — Per component, with a defined point of no return, before expiry only. After expiry: roll forward.
**Stop conditions** — As above.
**Verification** — As above.
**Follow-up** — Document the rotation runbook. Add expiry monitoring with a long lead time. Add rotation to the maintenance calendar. Review the patching schedule after this change.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you answer the questions above, I can turn this into a CAB-ready change record. I can also publish it as a private page you can share.