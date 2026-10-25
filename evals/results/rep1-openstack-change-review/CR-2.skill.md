## Summary

**Verdict: Not ready as written.** The "delete all keys except the new primary" step fails the recovery and blast-radius gates. With that step removed and a few conditions added, this becomes a small, routine change.

**Review depth:** Short-to-medium. The command set is small. But a Fernet error breaks authentication for the whole platform at once, and you've said the keys have never been rotated, so you've never tested that you can.

**Top 3 risks**
1. **Deleting the old primary invalidates every token it signed.** That includes tokens held by users and by services (Nova → Neutron/Cinder/Glance calls, long-running operations, Horizon sessions). Keystone can't validate a token once its key is gone. You'd cause an outage that the rotation was meant to prevent.
2. **The nodes may not be in sync before you start.** The safe ordering depends on keystone-2 and keystone-3 already holding the staged key. If they don't, tokens issued by keystone-1 after rotation fail on the other nodes until the rsync finishes.
3. **No rollback if the old keys are deleted and not backed up.** The deleted primary can't be recreated.

## Objective and four questions
- **Objective (assumed, please confirm):** rotate Fernet keys, as routine hygiene or a compliance item. *Assumption.* The business reason isn't stated.
- **Capability protected:** key hygiene, and proof that rotation works.
- **Capability affected:** authentication and token validation for every OpenStack service and user.
- **Added operational burden:** none, if rotation becomes scheduled and identical on all nodes. If it stays manual, you've added a recurring task.
- **Needed after the project team moves on:** an automated or documented rotation, plus key-sync monitoring.

## Starting state
- Never rotated: *Reported*. Key count, indexes, timestamps and whether the three nodes match are **unknown**. No output was shown.
- Platform stability and other changes in tonight's window: **unknown**. Don't stack this on another change.
- Deployment tool: **unknown**. If you use Kolla-Ansible, Ansible/Puppet, or a `keystone-fernet` container with its own rotation or push scripts, a manual rotation and rsync can conflict with it or be overwritten. Check this first.

## Scope and blast radius
- **Touched:** `/etc/keystone/fernet-keys/` on 3 nodes. Every API and service that authenticates through Keystone depends on it.
- **Failure mode:** platform-wide 401s. Not partial, and not limited to one tenant.
- **Possible confusing symptoms:** `keystonemiddleware` caches validated tokens in memcached. After a key deletion, some requests still succeed from cache while others fail, depending on the service and cache state.
- Also check whether you use credential keys (`/etc/keystone/credential-keys/`). That is a separate repository. Don't touch it tonight.

## Decision gates

| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | unknown | The failure case (platform-wide auth outage) isn't accepted by anyone yet |
| Recovery | **fail** (as written) | Deleting keys with no backup has no way back. Passes if keys are kept and backed up |
| Evidence | unknown | Not rehearsed. No staging test shown |
| Owner | unknown | Capability owner not named |
| Authority | unknown | Approver not named |
| Blast radius | fail (as written) | Full cut-over with key deletion and a restart on all nodes. Passes with the changes below |
| Mandatory requirements | unknown | If this is compliance-driven, the required rotation interval is unknown |

## Corrections to the plan
1. **Don't delete any keys.** A correct Fernet rotation keeps old keys as secondary keys so they can still validate existing tokens.
   - **Before rotation:** the repository holds a staged key (`0`) and a primary (the highest index). *Verify for your release.*
   - **After `fernet_rotate`:** the staged key becomes the new primary, the old primary becomes a secondary, and a new staged key (`0`) is created. You then have 3 keys, which matches the default `max_active_keys = 3`.
   - **Cleanup is automatic:** the oldest secondary is pruned on a future rotation. Don't clean up by hand.
   - **Don't rotate twice in one night.** A second rotation would prune the original primary. The retention rule is `(max_active_keys − 2) × rotation interval ≥ token lifetime + allow_expired_window`. Check your values against it.
2. **Check the nodes are in sync before you rotate** (read-only). Compare `sha256sum`, owner, mode and file names across all three nodes.
   - If they differ, fix that first. Otherwise the ordering "rotate on 1, then copy" isn't safe.
   - Nodes 2 and 3 can validate keystone-1's new primary tokens only because they already hold that key as their staged key.
3. **Copy, don't delete.** Keystone doesn't need a restart to pick up new keys in typical setups. *Verify for your release and web server.* If you do restart, do it one node at a time behind the load balancer, never all at once. This matches your plan's step order, but the restart is probably unnecessary risk.
   - **rsync details:**
     - Use `rsync -a` to preserve ownership and mode (`keystone`, `0600`/`0700`).
     - Add `--delete` only after you've confirmed the source holds the complete set.
     - Run it right after rotating, so that keystone-1 is the only node out of sync and only briefly.
4. **Take a backup first.** Archive the key directory from all 3 nodes with permissions preserved (e.g. `tar -p`) and store it off-node. A key backup is itself sensitive, so protect it accordingly.

## Prerequisites

| Prerequisite | Status | Owner |
|---|---|---|
| Deployment tooling checked for conflicts with manual rotation | unknown | Platform team |
| Keys identical on all 3 nodes before the change | unknown | Operator |
| Backup of the key directory from all nodes | unknown | Operator |
| Token lifetime, `allow_expired_window`, `max_active_keys` known | unknown | Operator |
| Monitoring for 401 rate and token validation errors | unknown | Monitoring owner |
| Rehearsal in a test or staging environment | unknown | Platform team |
| Other changes in this window | unknown | Change manager |

## Recovery
- **Method (revised plan):** restore the backed-up directory on all 3 nodes. Tokens signed with the new primary then fail, but they are recent and short-lived.
- **Exercised?** No. Never rotated, and the restore is untested.
- **Point of no return:** deleting a key that has no backup. In your current plan, that is the old primary, the moment you run the cleanup.
- **Evidence to preserve:** the key backups, pre-change `sha256sum` output, and a baseline of the 401 rate and Keystone logs.

## Execution boundaries and stop conditions
- Stop if the keys differ between nodes before starting.
- Stop if the 401 or token-validation error rate rises above the platform's baseline after the rotation or the copy. Define that baseline beforehand.
- Stop if a test token issued on one node fails validation on another.
- Stop if the deployment tool starts overwriting or re-pushing keys.
- Stop if the approver isn't reachable, or if monitoring can't see authentication errors.
- After a stop, resuming is a new decision.

## Verification
- **Read-only checks after rotation and sync:**
  - File names, owners, modes and checksums match on all 3 nodes.
  - A token issued by each node (against the node directly, not the VIP) validates on every other node.
  - A token obtained before the rotation still validates after it.
  - The load balancer returns no 401s.
- **Capability test:** a real end-to-end workflow, such as booting an instance or creating a volume, plus an existing long-lived session or service token.
- **Observation period:** at least the token lifetime plus `allow_expired_window`. Don't call it done tonight, because the new state hasn't earned trust until the oldest pre-rotation tokens have expired.

## Decision rights

| Role | Who |
|---|---|
| Technical assessor | unknown |
| Capability owner (Identity) | unknown |
| Accountable for the outcome | unknown |
| Decision maker | unknown |
| Consumer communication | unknown. Warn tenants that a brief auth disturbance is possible, with a contact |

## Gaps and questions
1. What is the deployment tool (Kolla-Ansible, Ansible, packages, containers)? Does it manage key rotation or distribution?
2. Output of `ls -l /etc/keystone/fernet-keys/` and checksums from each node. Don't paste the key contents.
3. Values of `token.expiration`, `fernet_tokens.max_active_keys` and `token.allow_expired_window`.
4. Does a staging environment exist to rehearse this in?
5. Why tonight? Compliance deadline, or just housekeeping? If it's housekeeping, a rehearsed daytime change is better.
6. Are other changes planned for tonight?

## Decision record (draft)
- **Change / decision:** Fernet key rotation on 3 Keystone nodes.
- **Date:** 2026-10-25 (planned). *Unconfirmed.*
- **Decision owner / Capability owner / Technical assessor:** unknown.
- **Objective:** rotate keys for the first time and prove that rotation works. Business reason is *unknown*.
- **Current state:** never rotated (*Reported*). Key sync across nodes is unknown.
- **Evidence:** none shown.
- **Uncertainty:** deployment tool conflicts, sync state, token lifetimes, rehearsal.
- **Options considered:** (A) the original plan, rotate then delete all but the primary. **Rejected:** it invalidates tokens issued with the old primary and leaves no recovery path. (B) Rotate, retain all keys, sync, verify. **Selected, subject to the conditions above.**
- **Recovery:** restore the key directory backup on all nodes.
- **Stop conditions:** as listed above.
- **Verification:** as listed above.
- **Follow-up:** schedule recurring rotation with identical distribution, add key-sync and 401-rate monitoring, and write a runbook after the first successful run.

**Revised plan in short:** back up and compare checksums (read-only). Then run `keystone-manage fernet_rotate` on keystone-1, rsync to 2 and 3, verify cross-node tokens, and watch for the token lifetime plus the expired window. Delete nothing and restart nothing unless you have to. If you must restart, do it one node at a time. If you share the answers to the questions above, I can turn this into a step-by-step runbook.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.