## Summary

**Verdict: Not ready as written. Recommended: split it into two changes.**

**Review depth: full.** This touches every control-plane service plus the message bus and the database. It has never been done on this platform, and the rollback is untested.

**Top risks**
1. **The rollback doesn't hold.** "Restore old certs" only works until the old certs expire in 9 days. After that it restores an outage. It also has no steps, no backup evidence and no test.
2. **Two unrehearsed changes are stacked.** A first-ever rotation of API, RabbitMQ and Galera certificates is combined with a reboot of all three controllers. If something fails, you can't tell which change caused it. Galera and RabbitMQ also have to re-form their clusters after each reboot while running on brand-new certificates.
3. **Almost no margin after Saturday.** If Saturday is Oct 31, you have about 3 days before expiry (Nov 3, if "9 days" counts from today). A failed or aborted window leaves no second slot unless one is reserved now. This reading assumes today is Oct 25 and that Saturday is the next one.

The patching is the part to remove. The certificate rotation has a hard deadline, but the OS update doesn't. It only has a "we have the window anyway" argument, and that is the reason to stack changes the book says not to stack.

## Objective and four questions
- **Objective:** keep the control plane trusted and running past certificate expiry, and apply the OS security update.
- **Capability protected:** authenticated, encrypted API, bus and database traffic. If the certs expire, that is probably a total control-plane outage.
- **Capability at risk:** the same thing, during the change. API availability, RPC between services and agents, and the Galera write path.
- **Operational burden added:** none if rotation becomes a routine calendar item. If it stays a one-off, you will be back at this point in 3 years.
- **Who operates it afterwards:** unknown. Whoever did the deployment 3 years ago may no longer be here.

## Starting state
- **Unknown:** Galera and RabbitMQ health baselines, the current state of the platform, and whether other changes are scheduled that weekend.
- **Unknown:** how the certs were issued (CA, SANs, chain, key storage), the deployment tool and version, and whether the old key material still exists.
- **Observed or reported:** expiry in 9 days. Never rotated. Installed at deployment. All of this is reported, not shown.
- **Finding:** expiry monitoring didn't surface this earlier. Add it to the follow-up.

## Scope and blast radius
- **Likely touched (unconfirmed):**
  - API endpoints behind the load balancer
  - RabbitMQ, with every service and every agent on every compute connecting to it
  - Galera, and every service that uses the database
- **Possibly missed:** the endpoint list isn't complete until someone builds an inventory. Candidates are:
  - the Keystone catalog
  - the Horizon, VNC/console proxies
  - OVN/Neutron database connections
  - libvirt/live-migration TLS
  - memcached
  - Ceph RGW
  - monitoring and backup agents
  - any CA bundle copied to computes, clients or automation
- **Failure reach:** all tenants' API operations and every service-to-service call. Running VMs on computes should keep running, but nothing can be managed.
- **Reboots:** 3 of 3 controllers. This removes redundancy by design. Galera needs 2 of 3 for quorum, and RabbitMQ needs a majority if it uses quorum queues. A second node going down while the first is out means a full outage.
- **Failure domain:** the whole control plane. There is no staged scope in the plan.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | **unknown** | No statement of expected API downtime, who accepted it, or what tenants were told. |
| Recovery | **fail** | "Restore old certs" is not a procedure. It expires in 9 days. Backups of old certs and keys are unconfirmed, and there is no Galera or RabbitMQ rollback sequence. |
| Evidence | **fail** | No rehearsal or staging test stated. Never rotated before. |
| Owner | **unknown** | No named owner for certs, RabbitMQ or Galera. |
| Authority | **unknown** | Approver not named. |
| Blast radius | **fail** | One window, all certs, all controllers, no batching. |
| Mandatory requirements | **unknown** | Security policy likely requires rotation (pass in direction). Check whether the CA and key lengths still meet policy. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Complete inventory of every certificate and trust consumer | unknown | to name |
| Rehearsal in a representative environment | unknown | to name |
| New certs issued and validated before the window (chain, SANs, key match, expiry) | unknown | to name |
| Backup of old certs and keys, config, and Galera and RabbitMQ definitions, with a restore test | unknown | to name |
| Baseline: Galera `wsrep_cluster_size` and status, RabbitMQ cluster status, no partitions, API error rates | unknown | to name |
| A written procedure per service (Galera and RabbitMQ order and restart behaviour) | unknown | to name |
| Monitoring covering TLS handshake errors and certificate expiry | unknown | to name |
| Consumer communication and a freeze on tenant resource creation if needed | unknown | to name |
| Reserved second window before expiry | **missing** | CAB / owner |
| Experienced person available who has seen the deployment (the original deployer or equivalent) | unknown | to name |

## Recovery
- **Method today:** "restore old certs". It isn't exercised or documented, and it expires.
- **What a credible rollback needs:**
  - Old certs, keys and configs backed up and tested, with the restore order per service.
  - A defined point where you stop rolling back and roll forward instead (see below).
- **Point of no return** (my addition, not the book's): once the new CA or trust bundle is distributed and old trust is removed, or a Galera/RabbitMQ restart with mixed TLS settings leaves the cluster unable to re-form, "restore old certs" may no longer work. The rollback is real only until the first service is committed to new trust.
- **Because the old certs expire anyway,** the realistic recovery after the first hours is roll-forward: fix the problem on the new certs. That means the rehearsal matters more than the rollback.
- **Ask:** can the old and new CA be trusted side by side during the change? That would make rollback safer and is worth designing for.
- **Galera and RabbitMQ:** TLS settings may need a coordinated restart, and mixed settings can break cluster formation. Verify for your Galera/MariaDB and RabbitMQ versions, and check the vendor documentation.
- **Evidence to preserve before starting:** all current cert files and keys, the service configs, the Galera status snapshot, the RabbitMQ definitions export, and a database backup that has been restored somewhere.

## Execution boundaries and stop conditions
**Proposed boundaries** (adjust to your baselines):
- One service group at a time, not all certs at once. Suggested order: the lowest-blast-radius first (for example one non-critical API), then RabbitMQ, then Galera, with verification between each.
- One controller at a time for any restart. Wait for a healthy cluster state before touching the next.
- A time budget per step, and a hard decision point inside the 4 hours: "past this time, we roll back or roll forward, not continue."

**Stop conditions**
- Any service shows TLS handshake errors that are not explained within the agreed time.
- Galera cluster size drops below 3 and doesn't recover, or loses quorum.
- RabbitMQ shows a partition or lost queues.
- Agents on computes fail to reconnect.
- The monitoring needed to see these effects is unavailable.
- A person with authority isn't reachable.
- The remaining time is less than the time needed for the rollback or roll-forward you have defined.

Hitting a stop condition means restoring a known-good state first, then deciding again.

## Verification
Designed before execution, and checking the capability, not the command:
- Every endpoint presents the new cert with the new expiry (check from outside and from a compute).
- Create, list and delete a test VM, volume and network, using a test project end to end.
- Galera: cluster size, status and sync state on every node. RabbitMQ: cluster status, no partitions, queue counts normal.
- Agents on all computes are up and reconnected, with no handshake errors in logs.
- Monitoring shows the new expiry dates.
- An observation period after the change. I don't set the length. Use your own baseline.

## Decision rights
- **Technical assessor:** unknown
- **Capability owner:** unknown
- **Accountable:** unknown
- **Decision maker:** CAB or named owner (to confirm)
- **Consumer communication:** unknown

## Gaps and questions
1. What tool deployed and manages the certs (Kolla-Ansible, another, manual)? Is the process documented?
2. Is there a staging or lab environment that mirrors production?
3. Exact expiry date and time, and is Saturday really the only window?
4. How many computes are there, and will they need new CA trust?
5. Galera and RabbitMQ versions, and whether the queue type is quorum or classic.
6. Is the OS update tested? What does it change (kernel, openssl, libvirt, container runtime)? Do the controllers run services in containers or on the host?
7. How were the controllers last rebooted, and has a full controller reboot been done recently?
8. What is the customer impact policy for API downtime during the window?

## Recommended restructuring
1. **Saturday: certificates only,** with conditions: inventory done, rehearsal done, backups tested, staged order, side-by-side trust if possible, and the stop conditions above.
2. **Reserve a second window** before expiry, in case the first is stopped.
3. **Controller patching and reboot: a later, separate window,** after the new certs have been observed to survive a service restart. A controller reboot also tests that the new certs survive a cold start.
4. **Rejected option for the record:** combining both in one window, because it can't be attributed or recovered cleanly and leaves no margin.
5. If CAB insists on combining, the accountable owner would be accepting that a failure leaves them unable to tell cert problems from patch problems, with 3 days or less of margin. I wouldn't recommend that.

For the controller reboot plan (one at a time, Galera and RabbitMQ rejoin checks), the `openstack-maintenance-planning` skill can help once the cert change is settled.

## Decision record (draft)
- **Change:** rotate internal TLS certificates (API, RabbitMQ, Galera). Controller OS patching split into a separate change.
- **Date:** Saturday window (4 hours); second window to be reserved
- **Decision owner / Capability owner / Technical assessor:** unknown

**Objective:** avoid control-plane outage from cert expiry in 9 days. Apply the security update in a separate change.
**Current state:** certificates installed 3 years ago, never rotated. Platform health unknown (no evidence shown).
**Evidence:** expiry reported, not shown. No rehearsal or backup evidence provided.
**Uncertainty:** certificate inventory, tooling, trust distribution, cluster restart behaviour with TLS changes, patch contents.
**Options considered:** (a) combined change in one window; (b) cert rotation only, patching later; (c) do nothing, which means outage at expiry.
**Trade-offs:** (a) saves a window but multiplies unknowns and leaves no margin. (b) needs a second window later but keeps failures attributable. (c) is unacceptable.
**Selected option:** (b), recommended. To be confirmed by the decision maker.
**Recovery:** backup and tested restore of old certs and configs, side-by-side trust if possible, defined roll-forward after the point of no return. Not yet in place.
**Stop conditions:** as listed above.
**Verification:** as listed above.
**Follow-up:** add cert-expiry monitoring, put rotation in the maintenance calendar, document the procedure, and schedule the patch window.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I can also publish this as a shareable page for CAB if you want that. If you send the deployment tool, the versions and the staging situation, I can turn the unknowns above into a tighter checklist.