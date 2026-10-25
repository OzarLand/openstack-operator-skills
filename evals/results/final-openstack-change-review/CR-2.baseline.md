Yes, one step in your plan would cause an outage. The rest is fine but can be made safer.

**Don't delete all keys except the new primary.**
- Fernet tokens are encrypted with the primary key and decrypted by any key in the repo. Tokens and Keystone-issued credentials already out in the wild are still valid, and their keys are the ones you'd be deleting.
- Deleting everything else invalidates every outstanding token at once. Services, Nova and Cinder calls, Horizon sessions and long-running operations all start failing auth until they re-authenticate.
- It also deletes the staged key (`0`). The staged key is what makes the next rotation safe, because every node already has the key that is about to become primary.

`fernet_rotate` already prunes. It keeps `[fernet_tokens] max_active_keys` keys (default 3) and drops the oldest. Since you've never rotated, you probably have keys `0` and `1`. After the rotate you'd have `0` (new staged), `1` (secondary) and `2` (primary). That is the correct end state, so don't delete anything.

**Other things to adjust:**
1. **Verify the nodes match before you start.** Compare `sha256sum /etc/keystone/fernet-keys/*` across all three nodes. If they differ, fix that first.
2. **Rotate only after the nodes are in sync, then push the result right away.**
   - Because staged key `0` is already on every node, nodes 2 and 3 can decrypt tokens signed by the new primary even before the sync completes. That only holds if step 1 is true.
   - Don't let the nodes sit out of sync for long.
3. **Take a backup first.** Run `cp -a /etc/keystone/fernet-keys /root/fernet-keys.bak-$(date +%F)` on each node.
4. **Preserve ownership and permissions when you rsync.**
   - Use `rsync -a --delete` (or `-aP`). The keys need to be owned by `keystone` and mode 0600 (dir 0700).
   - On SELinux hosts, check the context afterwards.
5. **Restart may not be needed, and the service name may differ.**
   - Keystone re-reads the key repo on token operations, so a restart usually isn't required.
   - If you do restart, Keystone typically runs under Apache/httpd or uwsgi. A reload of that is gentler than a hard restart, and you should do it one node at a time behind the load balancer.
6. **Check whether your deployment tool owns this.** If you use kolla-ansible, OpenStack-Ansible, a Juju charm or similar, use its rotation mechanism. Otherwise it may overwrite your manual changes on the next run.
7. **Verify afterwards.**
   - Issue a token from each node and validate it against the others. For example, run `openstack token issue` while pointing at each node, then validate with `curl` against the other nodes.
   - Check the Keystone logs for `InvalidToken` or "Could not find Fernet key" errors.
8. **Schedule regular rotation.**
   - Rotation needs to happen more often than your token lifetime allows keys to expire. With `max_active_keys=3`, rotating every few days to weekly is common.
   - Automate it with a cron job or your deployment tooling.
   - Rotating faster than token expiry times `(max_active_keys - 2)` will invalidate live tokens.

Revised plan: back up, check the nodes match, run `fernet_rotate` on keystone-1, rsync `-a --delete` to 2 and 3, reload the web server node by node, then validate tokens across nodes. Skip the cleanup step.