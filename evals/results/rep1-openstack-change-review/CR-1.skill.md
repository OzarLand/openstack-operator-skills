## Summary

**Verdict: Not ready.** The certificate rotation is justified and urgent, but the plan can't go to CAB in its current form.

**Review depth: full.** This change touches the control plane, the message bus and the database. It has never been rehearsed, and its recovery is not credible.

**Top 3 risks**
1. **The rollback doesn't work.** The old certs expire in 9 days. "Restore old certs" returns you to a known-bad state that fails on its own around Tuesday 3 Nov. It also doesn't say how to undo the OS update or a half-formed Galera or RabbitMQ cluster.
2. **Two unrelated changes are stacked in one window.** If RabbitMQ or Galera fails to re-form after the reboots, you can't tell whether the cause is TLS or the update. Recovery steps for one can make the other worse.
3. **This is a first-ever rotation with no rehearsal.** The CA, SANs, key ownership, trust distribution and Galera/RabbitMQ TLS behaviour are all unverified. Whoever did the original deployment may no longer be around.

## Objective and four questions
- **Objective:** avoid a control-plane outage from expired certificates (urgent, hard deadline), and apply a security update (valuable, but not deadline-bound by anything you've shown me).
- **Capability protected:** API, RPC and database availability.
- **Capability at risk:** the same things. A bad rotation causes the outage it is meant to prevent.
- **Added burden:** none, if a rotation procedure and expiry monitoring come out of it. That is a good outcome to require.
- **Operating it afterwards:** unknown. Who can renew these in 3 years?

## Starting state
- Reported: the certs were installed at deployment 3 years ago and have never been rotated.
- Unknown: current platform health, cluster state (Galera `wsrep_cluster_size`/`status`, RabbitMQ `cluster_status`), the controller OS and kernel delta, and whether any other changes are in the window.
- Saturday is 31 Oct and expiry is about 3 Nov (my calculation from "9 days"). **There is no second window.** A failed Saturday means an emergency change under the expiry deadline, so the rehearsal has to happen before Saturday.

## Scope and blast radius

| Touched | Reaches |
|---|---|
| API endpoints (internal TLS) | Every service-to-service call, plus the load balancer and health checks |
| RabbitMQ | Every nova-compute, neutron agent and other RPC client on every compute node |
| Galera | Every service database. Includes wsrep replication and SST/IST encryption, not just client connections |
| 3 controller reboots | VIP/HAProxy failover, Galera quorum, RabbitMQ quorum and API availability for the whole cloud |

Compute nodes aren't mentioned. If the CA changes or clients verify the server cert, they need the new trust bundle too.

## Decision gates

| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | There's no stated API or control-plane outage budget, and no accountable owner has accepted the failure case. |
| Recovery | **fail** | "Restore old certs" is a dead end after expiry. It also covers neither the OS update nor the cluster-state recovery. |
| Evidence | **fail** | There is no rehearsal and no staging test of the rotation. |
| Owner | unknown | No named owners for the PKI/CA, RabbitMQ or Galera. |
| Authority | unknown | No named approver. |
| Blast radius | **fail** | Everything changes at once, with no staged scope. |
| Mandatory requirements | unknown | Check whether security policy requires the update by a date. |

## Prerequisites

| Prerequisite | Status | Owner |
|---|---|---|
| Inventory of every cert: path, SAN, issuer, expiry, consumers | unknown | to assign |
| CA details: same CA or new? CA expiry? CA key available? | unknown | PKI owner |
| New certs issued and validated (SAN/hostname, key usage, chain) before the window | unknown | PKI owner |
| Rehearsal in staging or a lab that mirrors the production topology | unknown | platform team |
| Restorable backups: cert/key files, config, Galera dump or backup, RabbitMQ definitions export | unknown | to assign |
| Monitoring on cert expiry, Galera, RabbitMQ and API health | unknown | ops |
| Timed runbook that fits 4 hours with margin | unknown | assessor |

## Recovery
- **Method today:** "restore old certs". Not credible, for the reasons above.
- **What a credible path needs:**
  - Keep old and new material side by side with a trust bundle containing both CAs. That lets the new certs be pre-staged, and rolling back means reverting config, not restoring an expired cert.
  - Define the known-good state per component, and rehearse the revert.
  - Add an OS-update rollback path: a snapshot, or a decision that you roll forward only.
  - Write up Galera recovery. After rebooting controllers one at a time, know how to tell whether to bootstrap (`safe_to_bootstrap`/`grastate.dat`) before anyone touches it, and who may decide.
- **Points of no return:** none are identified yet. Candidates are a Galera node that fails to rejoin, a RabbitMQ node that has left the cluster, and kernel or package changes.
- **Evidence to preserve:** the old cert/key/config, `cluster_status` and `wsrep_*` output before and after each node, and the package list before the update.

## Execution boundaries and stop conditions
**Structure (my recommendation):**
- **Pre-stage non-disruptive work before Saturday:** issue the certs, distribute the trust bundle and rehearse.
- **Use the window for the cert rotation only,** one controller at a time and in this order: API, RabbitMQ, Galera. Verify each before the next.
- **Split the OS update and reboot out** to its own window after the certs are stable. Rebooting is also the natural moment to confirm services come up on the new certs, so schedule the update soon after (see "Options considered" below).

**Stop conditions:**
- Any node fails to rejoin its cluster, or quorum is at risk.
- TLS handshake errors persist beyond an agreed number of minutes.
- Compute services flap, or the VM-create canary fails.
- Elapsed time passes an agreed cutoff, such as 50% of the window with less than half the steps done.
- Recovery is no longer credible, or the decision-maker is unreachable.

## Verification
- **Certificates:** `openssl s_client` against each endpoint, RabbitMQ port and Galera port shows the new expiry, and monitoring shows it too.
- **Clusters:** `wsrep_cluster_size` is 3 and Synced, and `rabbitmqctl cluster_status` shows 3 nodes with no partitions.
- **Services:** all nova-compute and neutron agents are up, with no TLS errors in logs.
- **Capability, end to end:** create, then delete, a VM with a network and volume. Check token issue and validation.
- **Observation period:** the length is your call, based on your baselines.
- For a later patch window, add: kernel version on each controller, and failover tested.

## Decision rights
- **Assessor:** unknown (you or your platform lead?).
- **Capability owner:** unknown.
- **Accountable:** unknown.
- **Decision maker:** unknown.
- **Consumer communication:** unknown. Tenants should be told to expect brief API errors, and the plan should say who tells them.

## Gaps and questions
1. Are the certificates signed by an internal CA or self-signed? Does the CA also expire soon? Is its key available?
2. How are the certs deployed (Kolla-Ansible, hand-installed, other)? Please redact any secrets.
3. Do compute nodes and agents verify server certificates against a CA file?
4. Is there a staging or lab environment that mirrors production?
5. Is there a hard deadline for the OS update (CVE, policy)?
6. How many people can run this on Saturday, and who is on call?
7. What happens if Saturday fails? Is there a fallback date before 3 Nov?

## Options considered
- **A. Submitted plan (certs + patch + reboots in one window).** Rejected: it fails the recovery, evidence and blast-radius gates.
- **B. Certs only on Saturday, pre-staged and rehearsed. OS update in a later, separate window.** Recommended, subject to the open questions above.
- **C. Do the OS update and reboots first, to prove controller failover, then rotate certs.** Only viable if a window exists before 3 Nov. It gives no margin if anything fails.
- **D. Do nothing.** Not acceptable: expiry means an outage in 9 days.

## Decision record (draft)
- **Change / decision:** rotate internal TLS certs (API, RabbitMQ, Galera). OS update deferred to a separate change (pending decision).
- **Date:** Saturday window, 31 Oct. **Decision owner / Capability owner / Technical assessor:** unknown.
- **Objective:** avoid control-plane outage from certificate expiry (~3 Nov).
- **Current state:** certs from deployment, never rotated. Cluster health, CA and topology: unknown.
- **Evidence:** none yet. Rehearsal results and the cert inventory are required.
- **Uncertainty:** CA/trust model, client verification, Galera TLS behaviour, window timing.
- **Options considered:** A to D above.
- **Selected option:** pending. B is recommended.
- **Recovery:** revert to the previous config using a dual-CA trust bundle. Define the Galera/RabbitMQ re-form procedure. Must be rehearsed.
- **Stop conditions / Verification:** as above.
- **Follow-up:** expiry monitoring, a documented rotation runbook, a renewal calendar, a second person trained, and a schedule for the OS update.

**Before CAB:** revise the plan to include per-component rollback, the rehearsal result, named owners and the split into two changes. Then I can re-review it. Want me to turn the revised version into a shareable page for CAB once you have the answers?

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.