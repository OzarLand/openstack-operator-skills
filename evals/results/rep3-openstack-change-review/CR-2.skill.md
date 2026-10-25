## Summary

**Verdict: Not ready.** Step 2 ("delete all keys except the new primary") fails the recovery gate and would likely cause a platform-wide authentication outage. The rest of the plan is fixable.

**Review depth:** Full. Keystone sits under every OpenStack API, and the plan contains an irreversible step. The platform has also never rotated its keys, so nobody has shown that rotation works here.

**Top 3 risks:**
1. **The "clean up" step invalidates live tokens.** With only the new primary, every token signed by the old keys fails validation at once. That includes tokens held by services, long-running automation, Horizon sessions and in-flight operations.
2. **The key set can differ between nodes.** An rsync that fails partway, or a restart that happens before it completes, leaves nodes with different key sets. Tokens issued on one node then fail on another, which looks like intermittent 401s.
3. **The plan has no verification and no recovery.** Once the old keys are deleted, rollback means restoring them from a backup. The plan doesn't mention a backup.

## What's missing, in order of severity

**1. Don't delete the old keys.** Fernet rotation is designed to keep old keys.
- `fernet_rotate` promotes the staged key (index 0) to primary and creates a new staged key. It also adds a new key file and keeps the previous primary.
- Old keys are needed to **decrypt** tokens issued before the rotation, until those tokens expire.
- `keystone-manage fernet_rotate` also removes the oldest keys itself once the count exceeds `max_active_keys`. Cleanup is built in, so you don't need to do it by hand.
- If you want to remove old keys, wait until the longest-lived token issued before the rotation has expired. Check `[token] expiration` and `[token] allow_expired_window` in your config. Then let later rotations prune them, or remove them deliberately.

*Evidence class: Reported, from the plan. Your actual `token.expiration` and `max_active_keys` are unknown, so please send them (redact anything sensitive).*

**2. A first rotation after "never rotated" has one subtle trap.**
- Before the change, keystone-1's repository probably holds just keys `0` (staged) and `1` (primary). Confirm that with `ls -l /etc/keystone/fernet-keys/`; that is a read-only check.
- After rotating, the staging key `0` becomes primary `2`, and a new `0` is created. Every node needs the new staged key **before** any node starts issuing tokens with the new primary. Otherwise a node receiving a token signed with the new primary can't decrypt it.
- The safer order is: rotate on keystone-1, distribute to the other nodes, and only then rely on the new primary. The usual practice is to run the rotation on one node and push the full key set everywhere. On keystone-1 itself, keep traffic away until it's synced, or accept that its tokens are briefly unverifiable elsewhere.

**3. Distribution needs to be safe, not just "rsync".**
- Use `rsync` with `--delete` only if you intentionally want a mirror, and only after you've decided what the set should be. Better to avoid `--delete` here, given point 1.
- Preserve ownership and permissions: owner `keystone`, mode `0600` on keys, `0700` on the directory. Use `rsync -a` and then check.
- Check how your keys are normally distributed today (Kolla-Ansible, config management, a sync cron job). If another mechanism **overwrites** `/etc/keystone/fernet-keys/` on a schedule, your manual rsync will be overwritten or will diverge. **Unknown, so please confirm.**
- If you deploy with Kolla-Ansible, the keystone-fernet container usually handles rotation and sync (via `keystone-fernet` and SSH/rsync between nodes). Doing it by hand underneath that can clash with it. **Unknown.**

**4. Restarting Keystone isn't normally required.** Keystone re-reads the key repository when validating tokens. Restarting all three at once causes an avoidable API blip. If you do restart, do it one node at a time behind the load balancer, and check each node before the next.

**5. Backup before you start.** Copy `/etc/keystone/fernet-keys/` from all three nodes, preserving permissions, and keep the copies off the node. Also compare the three key sets today. If they already differ, that's a finding to fix first.

**6. Verification isn't in the plan.** Design it before you begin:
- Compare key file names and checksums across all three nodes (read-only). Don't print key contents.
- From **each** node, issue a token and validate it against **each** other node. A 3×3 matrix catches the divergence problem directly.
- Check that an existing token issued **before** the rotation still validates.
- Run an end-to-end capability check, such as a Nova or Neutron list call from a service-role token.
- Watch for a rise in 401s in the Keystone and HAProxy logs, and for service-to-service auth failures.
- Define an observation period using your own baselines.

**7. Nobody has shown that your platform can rotate.** Rotate in a lab or staging environment first, using the same distribution mechanism. If there's no environment like that, that is a risk to state. It doesn't have to block the change, but whoever approves it should know.

## Decision gates

| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | **unknown** | No statement that the owner accepts the failure case (a platform-wide 401 outage). |
| Recovery | **fail** | Deleting old keys is the point of no return. No backup or restore is mentioned. |
| Evidence | **unknown** | No rehearsal described. Token lifetime and `max_active_keys` not provided. |
| Owner | **unknown** | No capability owner named. |
| Authority | **unknown** | No approver named. |
| Blast radius | **fail** | One-shot change to all three nodes, with no staged scope. |
| Mandatory requirements | **unknown** | Check whether any policy mandates a rotation interval or a change window. |

## Revised plan (draft for your review)

1. **Read-only:** list the key repository on all three nodes. Compare file names and checksums. Record `token.expiration`, `allow_expired_window` and `max_active_keys`. Identify how keys are normally distributed.
2. **State-changing, low risk:** take a permission-preserving backup of the key directory from each node, off-node.
3. **Read-only:** run a baseline token issue/validate matrix across the three nodes. Record the 401 rate.
4. **State-changing:** on keystone-1, run `keystone-manage fernet_rotate` (as the `keystone` user, with the same `--keystone-user` and `--keystone-group` settings you use today).
5. **State-changing:** sync the full key set to keystone-2 and keystone-3. Use `rsync -a` without `--delete`, then fix and check ownership and modes.
6. **Read-only:** compare checksums across all nodes. Rerun the token matrix. Validate a token issued before the rotation.
7. **Restart only if you've found a reason to.** If so, go one node at a time.
8. **Observe** for at least the longest token lifetime plus margin. Keep the old keys throughout.
9. **Later, separately:** old keys age out through subsequent rotations (or a deliberate, separately approved cleanup after the token lifetime has passed).

**Stop conditions:**
- Key sets differ across nodes after sync.
- Any cross-node validation fails.
- 401s rise above your baseline.
- A pre-rotation token no longer validates.
- The approver isn't reachable.

On a stop, don't delete anything. Restore the backed-up key set to every node, the same way for all three.

## Decision rights
- **Assessor:** you or your Keystone engineer.
- **Capability owner, accountable owner and decider:** unknown, so please name them.
- **Consumer communication:** unknown. Tell API consumers and automation owners about the window, since a mistake produces 401s.

## Gaps and questions
1. How are keys distributed today (Kolla, Ansible, cron, manual)?
2. What are `token.expiration`, `allow_expired_window` and `max_active_keys`?
3. Do all three nodes currently hold identical key sets?
4. Is there a staging environment you can rehearse in?
5. Who approves this, and does a change window exist?
6. Is this the only change planned for tonight? Don't stack changes.
7. Which release are you on? Details of rotation and pruning vary, so check the upstream docs for your release.

## Decision record (draft)
- **Change:** First-ever Keystone Fernet key rotation across 3 nodes
- **Date:** tonight (2026-10-25), **not approved**
- **Decision owner / capability owner:** unknown
- **Technical assessor:** unknown
- **Objective:** Begin regular key rotation so a leaked or aged key stops being usable. Reported, not shown.
- **Current state:** Never rotated (reported). Key-set consistency across nodes is unknown.
- **Uncertainty:** Distribution mechanism, token lifetime, rotation rehearsal, the 401 baseline.
- **Options considered:** (a) Original plan with immediate deletion of old keys: rejected, because it invalidates live tokens and removes the recovery path. (b) Rotate, sync and retain old keys, with pruning later: preferred.
- **Recovery:** Restore the backed-up key set to all nodes. Valid only if the backup is taken and tested.
- **Stop conditions:** As above.
- **Verification:** The token matrix, a pre-rotation token check and a 401 watch.
- **Follow-up:** Schedule recurring rotation, automate and monitor it, and document the procedure as a runbook.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

I haven't touched any system. I can turn the revised plan into a runbook with exact commands once you've answered the questions above.