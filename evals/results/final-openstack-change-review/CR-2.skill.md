## Summary

**Verdict: Not ready as written.** The plan is fixable. If you drop the "delete" step and add the pre-checks below, it becomes **ready with conditions**.

**Depth:** Full review. A bad Fernet state breaks authentication for every service at once, and no one has ever exercised this procedure on this platform.

**Top 3 risks**
1. **The "clean up" step is the dangerous one.** On a never-rotated cluster you most likely have keys `0` (staged) and `1` (primary). After `fernet_rotate` you have `0` (new staged), `1` (old primary, now secondary) and `2` (new primary). Deleting everything except `2` removes key `1`, which signed every token currently in circulation. Every token goes invalid at once. It also deletes the staged key `0`, which rotation needs for the next cycle. *(Key-numbering semantics: verify for your release.)*
2. **Nodes may not be identical, and nobody has checked.** Rotation only works if all 3 nodes hold the same key set. The plan assumes they do (Assumption).
3. **Restart and sync mechanics are unspecified.** A restart of all 3 nodes at once is an API outage. Plain `rsync` can leave bad ownership or modes, or stale files. If Kolla-Ansible or a similar tool manages these keys, it may overwrite or fight a manual sync.

## Objective and four questions
- **Objective:** Unknown. Is this hygiene or compliance, or a suspected key exposure? It matters. If a key may be compromised, purging old keys is the goal, and the result is a deliberate, platform-wide re-authentication that the owner must accept. For routine hygiene, you should never purge.
- **Capability protected:** Token integrity and key hygiene.
- **Capability affected:** Authentication and authorization for every API, Horizon sessions, long-running operations and service-to-service calls.
- **Burden added:** Rotation must recur. `max_active_keys` and the rotation interval have to cover the maximum token lifetime. *(Verify the formula and the `allow_expired_window` behaviour for your release.)*
- **After you hand it over:** Someone must own scheduled rotation. A one-off rotation tonight leaves the same problem in a year.

## Starting state
- **Unknown:** whether the 3 nodes' key directories are identical, the number and names of the keys, `max_active_keys`, token expiration, how keys are managed, and whether the platform is currently healthy.
- **Assumption:** key sets are identical on all nodes.
- **Not established:** that this platform can rotate at all. It never has.
- Please confirm no other changes are scheduled in tonight's window.

## Scope and blast radius
- **Touched:** Keystone on 3 nodes and the load balancer. Every consumer of tokens is a dependent: all OpenStack services, Horizon, automation and CI, and third-party integrations.
- **If keys diverge or are removed:** tokens fail validation on some or all nodes. Service-to-service calls fail, and cached tokens in keystonemiddleware or memcached can delay and obscure the symptom.
- **Long-running operations** that hold a user token can fail mid-flight. Examples are image uploads, volume migrations and orchestration. Application credentials and trusts live in the database and are unaffected.
- **Do not touch `credential-keys`.** `/etc/keystone/credential-keys` is a separate repository, and credentials are encrypted with it. Losing them destroys data, not just sessions. Check that your rsync and any "delete all but one" command cannot reach that directory.

## Decision gates
| Gate | Status | Evidence or gap |
|---|---|---|
| Business impact | **fail / unknown** | The plan as written causes full re-authentication. No accountable owner has accepted that. |
| Recovery | **fail** | There is no mention of a key backup. Deleted keys are a point of no return for tokens signed with them. |
| Evidence | **unknown** | No staging rehearsal. No proof that the nodes match. |
| Owner | **unknown** | The Keystone capability owner isn't named. |
| Authority | **unknown** | The approver isn't named. |
| Blast radius | **fail** | Simultaneous restart and sync across all 3 nodes, with no staged scope. |
| Mandatory requirements | **unknown** | Depends on the driver for the rotation. |

## Prerequisites
| Prerequisite | Status | Owner |
|---|---|---|
| Archive of the key directory from all 3 nodes, with perms preserved, and a restore tested | missing | you |
| Checksums of key files compared across nodes (**read-only**) | missing | you |
| Confirm how keys are managed (Kolla/other tooling, cron, config management) | unknown | you |
| Values of `max_active_keys` and token expiration in `keystone.conf` (**read-only**) | unknown | you |
| Rehearsal in staging | unknown | you |
| Monitoring on token issue and validate failures (401s) | unknown | you |
| Window clear of long-running operations | unknown | capability owner |

## Recovery
- **Method:** Restore the archived key directory to all nodes, with the same ownership and modes.
- **Exercised?** Unknown. It needs a rehearsal.
- **Point of no return:** Deleting keys is the only irreversible step, and the backup makes it reversible. Without a backup, the tokens signed by deleted keys are gone for good. They can be reissued but not recovered.
- **Preserve before starting:** The key directory from each node, the output of `ls -l` with modes, and the output of `keystone.conf` `[fernet_tokens]` and `[token]`.

## Execution boundaries and stop conditions
**Corrected sequence** (steps labelled):
1. **read-only:** `sha256sum` the key files on all 3 nodes and compare. Stop if they differ. Fix that first.
2. **state-changing:** back up the key directory on each node (`tar` with perms) and verify the archive.
3. **state-changing:** on keystone-1, run `keystone-manage fernet_rotate` (as the keystone user). Prefer taking the node out of the load balancer first, or rotate in a copy and sync. The staged key `0` already exists on every node, so nodes 2 and 3 can already decrypt the new primary as long as the key sets were identical.
4. **state-changing:** sync keys to nodes 2 and 3 as an exact mirror of node 1. Make sure ownership is `keystone:keystone`, files are mode `0600`, and the directory is `0700`. Don't use `--delete` unless you've confirmed what it removes. **Do not delete old keys.** Key `1` stays as a secondary.
5. **read-only:** compare checksums across all 3 nodes again.
6. **Restart is probably not needed.** Keystone reads the key repository. *(Verify for your release and deployment.)* If one is needed, restart **one node at a time** behind the load balancer, and verify between nodes.

**Stop conditions:** node key sets differ before you start, an archive can't be verified, checksums differ after sync, or a rise in 401s or failures validating tokens.

## Verification
- Issue a token on each node (via the node directly) and validate it on each of the other two. That's all 3×3 combinations.
- Check that a token issued before the rotation still validates after.
- Run an end-to-end action, for example creating a VM or volume.
- Watch 401 rates and the Keystone logs during an observation period you pick from your own baselines.
- Confirm all 3 nodes have identical key lists.

## Decision rights
- **Technical assessor:** you or the Keystone engineer.
- **Capability owner and accountable role:** unknown.
- **Decision maker:** unknown. Any deliberate invalidation of existing tokens needs explicit acceptance from them.
- **Consumer communication:** unknown. Tell users and automation owners about the window.

## Gaps and questions
1. Why rotate: hygiene or suspected exposure?
2. How are keys managed on this platform (Kolla-Ansible, manual, config management)? Is there a cron or automation that would conflict?
3. How many keys are there now, and what are `max_active_keys` and the token lifetime?
4. Is there a staging environment?
5. What long-running jobs run overnight?

## Decision record (draft)
- **Change:** Rotate Fernet keys on 3 Keystone nodes.
- **Date:** 2026-10-25 (proposed).
- **Decision owner / Capability owner / Assessor:** unknown / unknown / you.
- **Objective:** unknown. See gap 1.
- **Current state:** Never rotated. Key parity is unverified.
- **Uncertainty:** Parity, management tooling and whether restart is needed.
- **Options considered:** (A) the original plan, with deletion. Rejected unless the purpose is deliberate invalidation. (B) rotate and sync, keep old keys, rolling restart only if needed. Recommended.
- **Recovery:** Restore the archived key directory to all nodes.
- **Stop conditions / Verification:** as above.
- **Follow-up:** Schedule recurring rotation and document it. Rotation interval × `max_active_keys` must outlast the longest token lifetime. Remove the "delete old keys" habit from the runbook.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.