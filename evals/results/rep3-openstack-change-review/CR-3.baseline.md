**Verdict: not ready for next week.** Four of your facts are blockers, and the deployment tool's release notes don't cover any of them. I haven't seen the plan document, so this review rests only on the facts you gave me.

## Blockers

1. **`nova-manage db online_data_migrations` was never run after the last upgrade.**
   - Newer releases assume those migrations are already complete. Skip-level makes this worse, because code that handled unmigrated data in the intermediate release is never deployed.
   - Expect `nova-status upgrade check` to fail, or the schema sync or services to break on leftover rows.
   - Fix this on the current release, before touching anything else. Run it until it reports nothing left to migrate.
   - Do the same for Cinder (`cinder-manage db online_data_migrations`).
   - Check Glance's and Keystone's expand/migrate/contract state, since those use a different mechanism.
   - Because it was skipped once, the backlog may be large or hit old data oddities. Time it against a copy of the production DB.

2. **The restore has not been tested in two years, and the person who did it has left.**
   - OpenStack DB migrations are effectively one-way, so rollback means restoring the databases. An untested restore means you have no rollback.
   - Take fresh backups of all five service DBs, plus configs and Fernet/credential keys for Keystone.
   - Restore them into a scratch environment, time it, and write down the steps. Define a point-of-no-return and a rollback decision owner.

3. **Nine local patches, two in the Nova scheduler.**
   - The scheduler changes a lot between releases (placement and filter behavior, deprecations), so those two are the highest risk.
   - Inventory each patch: what it does, whether upstream now covers it, and whether it touches DB models or migrations. Any patch that touches DB models or migrations needs particular care.
   - Rebase all nine onto the target release and run unit tests and a scheduling smoke test. Decide for each patch whether to drop it, upstream it, or carry it.

4. **Policy changes haven't been reviewed.**
   - Defaults have been shifting toward scoped, role-based rules (secure RBAC) across these projects, and a custom policy file can silently stop matching or start denying.
   - Diff your overrides against the target release's generated defaults (`oslopolicy-sample-generator` / `oslopolicy-policy-generator`). Read the "upgrade notes" for all five services.
   - Test as a normal user, an admin, a reader and a service account, because policy failures often show up only there.

## Other things to confirm

- **SLURP itself.** Both your current and target releases must be SLURP releases. Even then, the intermediate release's schema migrations still run in sequence. The tool saying it "supports the jump" says nothing about your patches, config or data. Treat that as a claim to verify.
- **Rehearsal.** There's no mention of a full dry run on a staging copy of production data with the patched code. This is the single most valuable step.
- **Prerequisites.** Check OS, Python, database and RabbitMQ version requirements for the target release.
- **Compute nodes.** Decide how you'll handle them (rolling, version pins/upgrade levels) and what the VM impact is.
- **Order and window.** Confirm the service order and downtime window, and assign a go/no-go owner.

## Suggested gates for a go decision

1. Online data migrations are complete on all services, and `nova-status upgrade check` is clean.
2. A restore has been performed from a recent backup, timed, and documented.
3. All nine patches are rebased and tested, with the two scheduler patches verified under realistic load.
4. The policy diff is reviewed and role-based tests pass.
5. A full rehearsal has succeeded on a copy of production data, including a rollback exercise.

If you can finish 1 and 2 this week and start 3 to 5 in parallel, a slip of one to two weeks is probably realistic. Going next week without them means you'd find these problems during the outage, with no tested way back.

If you share the plan document, the patch list or the policy overrides, I can review them in more detail.