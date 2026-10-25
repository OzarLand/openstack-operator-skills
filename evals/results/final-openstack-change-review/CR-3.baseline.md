**Verdict: not ready for next week.** Three items are real blockers, and the rest are fixable before the window but only if you start now.

## Blockers

**1. Online data migrations were never run after the last upgrade.**
- This is the most serious item. Online migrations from the last release must be complete before you jump. Nova's schema and code in the target release assume they're done, and migrations that were dropped in the interim won't run at all. The result can be failed DB sync, services that won't start, or silently stale data.
- SLURP skips the intermediate release's runtime, not its data requirements.
- Run these on the current release first, then verify with the status check:
  - `nova-manage db online_data_migrations` (loop until it reports 0 remaining), then `nova-status upgrade check`
  - `cinder-manage db online_data_migrations`
  - Check Glance and Keystone for pending data or expand/migrate steps.
  - Check Neutron with `neutron-db-manage current` and `neutron-db-manage has_offline_migrations`.
- This is probably a long run on a table-heavy DB. Do it as a standalone change, not inside the upgrade window.
- If it errors, you now have a week or more of lead time to fix it. Finding that out mid-upgrade is the failure mode to avoid.

**2. The restore has not been tested in two years.**
- Without a tested restore, a failed upgrade with a one-way DB migration means a rebuild, not a rollback.
- Take a fresh DB dump and config backup. Restore them into a scratch environment and confirm services start against them.
- Ideally, rehearse the whole upgrade on that restored copy. This also times the migrations and surfaces schema problems with your data.
- Nobody on staff has done a restore, so assume the runbook is stale.

**3. The two Nova scheduler patches haven't been ported.**
- The scheduler is one of the most actively refactored areas, so a 2-patch carry across a jump is likely to conflict or silently change behaviour.
- For each of the 9 patches, decide whether it is merged upstream, needs a rebase, or can be dropped. Rebase and test the scheduler ones first.
- Confirm you have regression tests for what those two patches do. If the behaviour is only "known by the engineer who wrote it," that's a risk to flag.
- The other 7 patches need the same triage, but the scheduler pair is the critical path.

## Significant gaps

**4. Policy changes are unreviewed.**
- Recent releases moved to secure RBAC defaults (scoped tokens, `reader` and `member` roles), and the old deprecated defaults get removed on a schedule.
- If you have custom `policy.yaml` overrides, or automation and users depending on the old admin-ish behaviour, expect 403s after the upgrade.
- Run `oslopolicy-policy-generator` and `oslopolicy-list-redundant` against old and new releases, diff the results, and check the release notes for removals.

**5. "The deployment tool says it supports the jump" is necessary, not sufficient.**
- It tells you the tool's playbooks handle the jump. It says nothing about your 9 patches, your custom config, your data state, or your policy overrides.
- Check that your tool's supported path matches your exact start and end versions and your OS/Python baseline. Also check whether it requires the online migrations to be complete first (it likely does).

## Also confirm
- Run `nova-status upgrade check` and the equivalent checks for other services on the current release.
- Take a staging dry run of the full sequence, with timing, to size the downtime window.
- Prepare the rollback decision point: at what step does rollback stop being possible, and who decides?
- Review config deprecations and removals across all five services.
- Write a post-upgrade smoke test, such as boot a VM, attach a volume, boot from an image, and authenticate with a new token.

## Suggested path
- **This week:** run the online migrations, take the backup, restore it into staging, and triage the patches.
- **Next week:** rehearse the upgrade on the restored copy and review policy diffs.
- **Following window:** do the real upgrade once the rehearsal is clean.

If the date is fixed by something outside your control, the minimum I'd accept is items 1 and 2 done and verified, plus the scheduler patches rebased and tested. Without those, I'd recommend postponing.

I can also draft a pre-upgrade checklist or runbook if that helps. If you tell me your start and target releases and your deployment tool, I can make it specific.