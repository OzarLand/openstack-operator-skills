**Verdict: not ready for next week. I'd treat this as a no-go until the blockers below are cleared.** The plan has no rollback path, one hard prerequisite was skipped, and two risks are unassessed.

## Blockers

1. **Online data migrations were never run (hard blocker).**
   - SLURP skips the intermediate release's code, so the schema and data must be fully migrated on the starting release. Newer releases drop the compatibility code for unmigrated rows. The upgrade can fail outright or leave you with broken instances, flavors or allocations.
   - You've been skipping them since the last upgrade, so the backlog may span more than one release.
   - Run `nova-manage db online_data_migrations` until it reports nothing left, and check `nova-status upgrade check`. Do the same for Cinder (`cinder-manage db online_data_migrations`). Confirm Glance and Neutron are clean too (`glance-manage db check`, `neutron-db-manage current` and `check_migration`).
   - This can take a while on a large DB and may surface errors you need time to fix. It's also safe to run now, on the current release.

2. **No usable restore.**
   - A 2-year-old test by someone who left proves nothing about today's backups or procedure. The DB schema, versions and tooling have all changed since then.
   - Without a tested restore, any failed migration is a possible unrecoverable outage. The DB migrations are one-way, and there's no downgrade.
   - Before the window you need a fresh backup of all five service DBs, a restore into a scratch environment, and a timed run-through. Include config, certificates and Fernet/credential keys for Keystone.

3. **Local patches are unreviewed against the new code.**
   - The two in the Nova scheduler are the highest risk. The scheduler and placement interaction changes between releases, so they likely need a rebase or rewrite, and a bad scheduler patch breaks every boot.
   - For each of the 9 patches, decide whether it's merged upstream, still needed, or needs porting. Then rebuild the images with the patches and test them.
   - Confirm your deployment tool even carries them through the upgrade.

4. **Policy changes are unexamined.**
   - Newer releases tighten RBAC defaults (scoped tokens, new default roles, and enforcement of the new defaults where they're now on). This is a common cause of "upgrade worked but users and automation got 403s".
   - Diff your custom policy files against the new defaults. Run the new policies in staging with real user and service roles, including monitoring and automation accounts.

## Smaller gaps

- **Tool release notes aren't validation.** They say the jump is supported in general. They don't cover your patches, your config or your data. Verify you're on a SLURP release now, since only SLURP-to-SLURP is supported, and check the exact version path and any intermediate required steps.
- **No staging rehearsal is mentioned.** A full dry run on a copy of production data is the best way to catch the issues above.
- **Missing from the plan:** pre-checks (`nova-status upgrade check`), a service order, a maintenance window sized from the rehearsal, a rollback decision point, and post-upgrade validation (boot, attach volume, create network, image upload, token issue).
- Review the deprecated and removed config options for all five services.

## Suggested path

1. **This week:** run the online migrations and take and test a fresh backup and restore. These are safe and needed regardless.
2. **Next 1–2 weeks:** triage the patches, diff the policies, and rehearse the full upgrade in staging on a restored copy of production.
3. **Then:** schedule the window with a written go/no-go checklist. The migrations must be complete, the restore proven, and the rehearsal clean.

If the date is fixed, the minimum is steps 1 and the scheduler patch check. I wouldn't proceed without a proven restore.

I can turn this into a go/no-go checklist page for your team if that would help.