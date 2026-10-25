Yes, the "delete all keys except the new primary" step is the one to drop. It would break things.

**Why not**

After a rotation the old primary becomes a secondary key. It's still needed to decrypt every token issued before the rotation. If you delete it, all outstanding tokens fail validation at once. That means API calls, long-running Heat and Nova operations, and anything holding a token, with a 401 storm. Tokens can stay valid for `[token] expiration` (1h by default). With `allow_expired_window` (default 48h), keys should be kept at least that long.

The deletion also removes the staged key (key 0). Staging is what makes rotation safe across nodes. Every node already holds the future primary, so it can validate tokens before it starts issuing them.

You also don't need to clean up. `max_active_keys` (default 3) makes `fernet_rotate` prune the oldest keys itself. With a never-rotated repo you probably have only keys 0 and 1, so there's nothing to remove.

**Safer procedure**

1. **Verify the nodes agree first.** Run `sha256sum /etc/keystone/fernet-keys/*` on all three nodes. If they differ, fix that before rotating. Divergent keys on a never-touched cluster would explain odd intermittent 401s.
2. **Back up** `/etc/keystone/fernet-keys/` on all nodes.
3. **Rotate on keystone-1:**
   `keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone`
   Keep the user and group flags so ownership and permissions stay right (keystone-owned, 0600 files).
4. **Sync to 2 and 3 immediately.** Use `rsync -a --delete` to preserve ownership and mode. `--delete` is fine here because keystone-1 now holds the authoritative set. Until the sync finishes, keystone-1 issues tokens with the new primary that the other nodes can't validate, unless they already have that key as staged key 0. If your load balancer sends traffic to all three, either do the sync fast or briefly drain keystone-1.
5. **Skip the restart.** Keystone reloads keys from the repo, so a restart isn't needed. If you restart anyway, do it as a rolling restart, one node at a time, not all three together.
6. **Verify.** Re-run the checksums, then request a token from each node and validate it against the other two.

**Other points**

- The `credential-keys` repo is separate. Don't touch it. Rotating it requires re-encrypting stored credentials (`credential_migrate`).
- If a deployment tool manages the keys (Kolla-Ansible, OpenStack-Ansible, TripleO or a similar tool), rotate through that tool. Otherwise it may overwrite your manual change.
- Schedule rotation going forward (cron on one node, with a distribution step). A first rotation after a long gap is the riskiest one.