**Verdict: not ready for next week.** I'd move the date. Several of the gaps below are individually blocking, and the missing restore test means you have no rollback.

## Blockers

1. **`nova-manage db online_data_migrations` was never run after the last upgrade.**
   - SLURP skips the intermediate release's code, so any data migration the old release left pending has no code to run it. It can fail the DB sync or leave services refusing to start. Nova checks for this explicitly.
   - Run `nova-status upgrade check` now, then the online migrations on the current release until they report nothing left. Do the same for the other services:
     - Cinder: `cinder-manage db online_data_migrations`.
     - Glance and Keystone: `db expand`, `migrate` and `contract` state.
     - Neutron: `neutron-db-manage` heads.
   - These can take hours on a big DB and may surface errors you've been carrying silently. Run them well before the window.

2. **There is no tested rollback.**
   - OpenStack DB migrations are forward-only, so rollback means restoring the control-plane DB and configs. That procedure was last tested two years ago by someone who left, so assume it doesn't work.
   - Before the upgrade, take a fresh backup, restore it into an isolated environment, and boot the services against it. This also gives you a realistic DB for the rehearsal in item 5.
   - Write down who decides to roll back, and by when, so the decision isn't made mid-incident.

3. **Nine local patches, two of them in the Nova scheduler.**
   - You need to know for each patch whether it was merged upstream, can be dropped, applies cleanly, or needs porting. Scheduler internals (placement-driven allocation, filters and weighers) change a lot across releases.
   - Check whether any patch touches DB models or adds a migration, since that affects the upgrade path.
   - Each patch needs a functional test that proves its behaviour still holds. Nothing should be rebased for the first time during the change window.

4. **Policy changes haven't been reviewed.**
   - Recent releases have been moving towards secure RBAC defaults (scoped tokens, `reader`/`member`/`manager` roles, service role). Any custom `policy.yaml` overrides can silently stop doing what you expect, in either direction: users locked out, or access wider than intended.
   - Run `oslopolicy-list-redundant` and `oslopolicy-policy-generator` on old and new releases, diff them against your overrides, and test with real user roles. Keystone role assignments may also need changes, so check this across all five services.

5. **The deployment tool's release notes aren't validation.**
   - "Supports the jump" doesn't cover your config, your patches, or your DB state.
   - Confirm your current release is a valid SLURP starting point. If your last upgrade landed on a non-SLURP release, the jump isn't supported as planned.
   - Do a full rehearsal in staging on a restored copy of the prod DB, with your patches applied. Time it, so the window length is based on a measurement.

## Suggested order

1. Run the online migrations and the `upgrade check` tools in prod, which is low risk.
2. Do the backup and restore test, which also yields the rehearsal environment.
3. Port and test the local patches, starting with the scheduler ones.
4. Do the policy diff and test it.
5. Do the full rehearsal and write the runbook, including rollback.
6. Then pick a date. Realistically that's several weeks out, not days.

## Go/no-go gates for any new date
- All online migrations report complete, and every `upgrade check` is clean.
- A restore has been proven within the last few weeks, with a measured RTO.
- Every local patch is accounted for and tested on the target release.
- A policy diff has been reviewed, with test results for each affected role.
- The rehearsal succeeded end to end on prod-like data.

I haven't seen your environment, so this is based only on the facts you listed. If you share the patch list, current and target release names, and the deployment tool, I can make the checks more specific. I can also turn this into a shareable checklist page if you want one for the team.