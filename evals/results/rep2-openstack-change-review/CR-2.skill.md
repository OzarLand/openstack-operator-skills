## Summary

**Verdict: Not ready as written.** The "delete all keys except the new primary" step should come out of tonight's plan. The rest is fixable with prep work.

**Review depth:** medium. Fernet rotation is routine and reversible if done the standard way. The cleanup step makes it irreversible, and a mistake breaks authentication for the whole platform at once. Every service validates tokens through Keystone.

**Top 3 risks**
1. **Deleting old keys invalidates every live token.** This is the point of no return. Tokens signed with a removed key fail validation everywhere. That includes tokens held by long-running operations, such as image uploads, heat stacks, and nova-compute or cinder calls that reuse a user token, and tokens held by logged-in Horizon sessions. The default token lifetime and `allow_expired_window` set how long old keys must stay. Verify both in your `keystone.conf`.
2. **Deleting the staged key (`0`) removes the mechanism that makes rotation safe.** `fernet_rotate` promotes the old staged key to primary, keeps the old primary as a secondary (decrypt-only), and creates a new staged key `0`. It prunes surplus keys itself, down to `max_active_keys`. A manual cleanup duplicates that and leaves nodes with different key sets while the rsync is in flight.
3. **There is no tested recovery path.** The platform has never rotated, so nobody has shown that distribution, ownership and verification work. Deleted keys can't be regenerated. Recovery would depend entirely on a backup of the key directory, and that backup isn't in the plan.

## Objective and four questions
- **Objective (Reported):** rotate never-rotated Fernet keys. I assume the driver is security hygiene or compliance; please confirm.
- **Capability protected:** credential hygiene, meaning a bounded exposure window for keys.
- **Capability at risk:** all API authentication and token validation, platform-wide.
- **Operational burden:** this is a one-off. A single manual rotation tonight leaves you exactly as exposed in six months. The real objective is a repeatable rotation, so plan the schedule and automation as follow-up.

## Starting state
- **Unknown:** whether the 3 nodes currently hold identical key sets. Never-rotated platforms often have drift, a missed node, or a stale copy.
- **Unknown:** whether another mechanism already touches the keys. In Kolla-Ansible, a cron job and `fernet-push.sh` can distribute keys. A config-management run could also overwrite your rsync.
- **Unknown:** whether any other change or incident is in tonight's window.

## Scope and blast radius
- **Touched:** Keystone on 3 nodes, and indirectly every API service and every consumer that authenticates.
- **Failure mode:** a bad key state causes 401s across the platform, or intermittent 401s depending on which node the load balancer picks. Intermittent failures are the hardest to diagnose.
- **Not touched:** running VMs' data plane. Control-plane operations are what break.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | The acceptable-failure statement hasn't been given by the capability owner. |
| Recovery | **fail** | No key backup in the plan, and the cleanup step destroys the keys needed to roll back. |
| Evidence | unknown | Not rehearsed. Key sync state across the nodes is unknown. |
| Owner | unknown | Keystone owner isn't named. |
| Authority | unknown | Approver isn't named. |
| Blast radius | fail | All 3 nodes are changed with no staged scope or per-node verification. |
| Mandatory requirements | unknown | Depends on the driver for the rotation. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Identical keys on all 3 nodes, with checksums compared (read-only) | unknown | you |
| Backup of the key directory from every node, stored off-node | missing | you |
| `token.expiration`, `allow_expired_window`, `max_active_keys` read from the config | unknown | you |
| Deployment tool identified (Kolla, Ansible, manual) and its own rotation or distribution jobs found | unknown | you |
| Rehearsal in a non-production environment | unknown | you |
| Test credentials for token issue and validation against each node directly | missing | you |
| Monitoring on Keystone 401 and 5xx rates | unknown | you |

## Recovery
- **Method:** restore the key backup to all 3 nodes, then verify. This only works if the backup exists and nothing else changed.
- **Exercised?** No.
- **Point of no return:** deleting the old keys. After that, tokens signed with them are unrecoverable, and the only fix is for users and services to re-authenticate.
- **Evidence to preserve:** a tarball of `/etc/keystone/fernet-keys/` from each node (with permissions), checksums of the files, and the current `keystone.conf` token settings.

## Suggested revised plan
Steps are labelled `read-only` or `state-changing`. Verify the details against your release and deployment tool.

1. **read-only:** On each node, list the keys and checksum them (`ls -l` and `sha256sum`), and confirm owner, group and mode. Confirm the three sets are identical.
2. **state-changing:** Back up the key directory on each node, off-node, with permissions preserved.
3. **read-only:** Confirm which user the keys must belong to (usually `keystone:keystone`, mode `0600`/`0700`) and which jobs could rewrite them.
4. **state-changing:** On keystone-1, run `keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone`. Without those flags, running as root can leave keys owned by root, which Keystone can't read. Don't delete anything. Rotation prunes keys beyond `max_active_keys` itself.
5. **state-changing:** Sync the whole directory to nodes 2 and 3 right away, keeping ownership and modes. Use `rsync -a --delete` so the sets match exactly.
6. **Verify on each node, directly and not just through the load balancer:** issue a token, validate it on every other node, and watch for 401s. Then check a real service flow, for example `openstack server list`, and an image or volume operation.
7. **Restart:** Keystone normally reads the key repository on demand, so a restart may not be needed. Verify for your release. If you do restart, do it one node at a time, behind the load balancer, with a check between each. Don't restart all three together.
8. **Observe** for at least the max token lifetime plus `allow_expired_window` before considering old keys for removal. Leaving them in place costs nothing.

If the keys were out of sync in step 1, stop and fix that first. Rotating on top of drift makes it worse.

## Execution boundaries and stop conditions
Stop if any of these happen:
- The key sets differ across nodes before you start.
- Any node returns 401 or 5xx for a token issued on another node.
- Ownership or modes on a node differ from the others.
- The Keystone error rate rises above your baseline.
- You can't get the key backup restored on a test node.
- The approver or Keystone owner isn't reachable.

Resuming after a stop is a new decision.

## Verification
- A token issued on each node validates on all 3.
- Real service calls succeed (Nova, Glance, Cinder, Neutron).
- Keystone logs show no `Could not recognize Fernet token` or fernet decrypt errors.
- Monitoring shows steady 401 and latency rates through the observation period.

## Decision rights
- **Assessor:** you.
- **Capability owner, accountable owner and decision maker:** all unknown. Name them before tonight.
- **Consumer communication:** unknown. Tell API consumers a brief auth blip is possible, and name who sends that message.

## Gaps and questions
1. Is this Kolla-Ansible, another tool, or manual? Is any job already rotating or syncing keys?
2. What are `token.expiration`, `allow_expired_window` and `max_active_keys`?
3. Are the key sets identical across nodes today?
4. Why the "delete all but the new primary" step? If something specific prompted it (a suspected key leak, say), that changes the plan. A leak calls for more urgent, different handling, and the rest of this review no longer fits.
5. Who approves, and what else is happening in the window?

## Decision record (draft)
- **Change:** Fernet key rotation, 3 Keystone nodes. **Date:** 2026-10-25 (proposed). **Decision owner / capability owner / assessor:** unknown / unknown / you.
- **Objective:** rotate keys that have never been rotated (driver unconfirmed).
- **Current state:** key sets and deployment mechanism unknown.
- **Evidence:** none shown yet.
- **Uncertainty:** key drift, token settings, other jobs, rehearsal.
- **Options considered:** (a) as proposed, with manual cleanup, **rejected** because it removes recovery; (b) standard rotation with no deletion and a backup, **recommended**; (c) postpone until a rehearsal is done, which is valid if the prerequisites above can't be closed tonight.
- **Recovery:** restore the backed-up key directories on all nodes.
- **Stop conditions / Verification:** as above.
- **Follow-up:** schedule recurring rotation and keep it automated and monitored. Document the procedure as a runbook. Record the point of no return explicitly.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.