Yes, one step will hurt you: **don't delete everything except the new primary.**

**Why not**
- After `fernet_rotate`, the repository holds the staged key (`0`), the new primary (highest index), and the previous primary as a secondary.
- Tokens already issued were signed with the old primary, which is now a secondary. Deleting it invalidates every outstanding token. Users and services get 401s and long-running operations fail mid-flight.
- Keystone already prunes old keys for you. Rotation deletes the oldest secondaries beyond `[fernet_tokens] max_active_keys` (default 3).
- If you want to clean up manually, delete only secondaries older than your longest token lifetime. That's `[token] expiration` (default 1h), plus any window for long-lived tokens. Never delete the staged key (`0`) or the primary.

**Other things to add**
1. **Back up first.** Run `tar czf` on `/etc/keystone/fernet-keys` on all 3 nodes.
2. **Check the nodes match before rotating.** Compare `sha256sum /etc/keystone/fernet-keys/*` on all 3. If they differ, fix that first. Otherwise node-1 can issue tokens with a key the others don't have.
3. **Sync fast, and don't use `--delete` carelessly.** After rotating on node-1, the other nodes can already validate its new tokens, because the new primary was their staged key. Still, sync right away. Use `rsync -a --delete` only if node-1 is the source of truth, and preserve ownership and permissions (`keystone:keystone`, dir `0700`, files `0600`). Use `-a` and run as root or the keystone user.
4. **Restart is probably unnecessary.** Keystone re-reads the key repository on each token operation. A restart of httpd/apache just causes avoidable blips. If you do restart, do it one node at a time behind the load balancer.
5. **Check your deployment tool.** If this is kolla-ansible, OpenStack-Ansible, charms, or similar, it manages the keys itself. A manual rotation may be overwritten, or may diverge from its distribution mechanism. Use the tool's own rotation (e.g. kolla's `keystone_fernet` cron/rotate scripts) instead.
6. **Verify afterwards.**
   - Run `ls /etc/keystone/fernet-keys` on each node. You should see `0`, N (primary), and N-1.
   - Run `openstack token issue` against each node. Validate a token issued by node-1 on nodes 2 and 3, and the reverse.
   - Confirm a token issued before the rotation still validates.
7. **Automate it.** Rotate periodically (e.g. weekly) and set `max_active_keys` so that (rotation interval × (`max_active_keys` − 2)) exceeds your max token lifetime. Otherwise you'll be doing this by hand again.

**Revised plan**
1. Back up and compare checksums on all nodes.
2. On keystone-1, run `keystone-manage fernet_rotate --keystone-user keystone --keystone-group keystone`.
3. Rsync to keystone-2 and keystone-3 immediately.
4. Verify as above.
5. Skip the manual cleanup. Let `max_active_keys` handle it.