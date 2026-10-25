Yes, there's one serious problem. The "delete all keys except the new primary" step will break your cloud.

**Why deleting the other keys is dangerous**

Fernet tokens are validated against every key in the repository, not only the primary. After `fernet_rotate` you have:

- `0`: the staged key (the future primary)
- `N`: the new primary
- the old primary, still needed to decrypt every token issued before tonight

If you delete everything except the new primary, every existing token becomes invalid immediately. That includes user sessions, service tokens, and long-running operations. Services that cache tokens, such as Nova, Neutron, and Heat, will start getting 401s. Trusts and application credentials will also fail until they re-authenticate. Cleanup removes the staged key as well, which breaks the next rotation.

Your keys have never been rotated, so right now you probably have just `0` and `1`. After rotation you'll have `0`, `1`, and `2`, and all three should stay in place.

**What the rotation should look like**

1. **Back up first.** On each node, run `tar czf` on `/etc/keystone/fernet-keys/`, keeping the ownership and permissions.
2. **Check the current state.** Run `ls -l /etc/keystone/fernet-keys/` on all three nodes, and confirm they match. If they have drifted apart, you'd be spreading a bad state.
3. **Rotate on keystone-1.** Run `keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone`. This promotes the staged key to primary and creates a new staged key `0`.
4. **Sync the whole directory to nodes 2 and 3.** Keep ownership as `keystone` and mode `600` on the files and `700` on the directory. Use `rsync -a --delete` so stale files don't linger. If you want to avoid running as root, `keystone-manage fernet_rotate` is safe to run only on one node.
5. **Restart or reload.** Strictly speaking, Keystone re-reads the key repository on each token operation, so a restart often isn't needed. Under Apache/mod_wsgi, a graceful reload is enough if you want to be safe. Do nodes one at a time behind the load balancer.
6. **Verify.** Request a token from each node. Then validate a token issued before the rotation against each node.

**Cleanup**

Don't clean up tonight. Old keys are removed by the next rotation, once `max_active_keys` (default 3) is exceeded. If you want to cap the number of keys, set `[fernet_tokens] max_active_keys` in `keystone.conf`. It must be at least 3.

**For later**

- Don't let the nodes rotate independently. Pick one node as the source of truth and sync from it.
- Keep `max_active_keys` times your rotation interval above your token expiration (`[token] expiration`, default 1 hour). If you run daily rotations with 3 keys, this is fine.
- Automate with a cron job or Ansible, or with a Kubernetes secret if you're on that.
- Treat the keys as secrets. Don't store them in git or ship them over unencrypted channels.

If you give me the output of `ls -l` for the key directory, I can check the exact state before you start.