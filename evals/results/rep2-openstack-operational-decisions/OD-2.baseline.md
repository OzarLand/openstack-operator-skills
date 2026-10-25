Yes, that's the normal approach. When upstream has stopped maintaining a series, carrying a minimal backport yourself is the practical option, and a small patch is the best case for it. Before you ship it, check these:

- **Confirm you're affected.** OSSAs usually list only the supported series, so the advisory may not mention yours. Check that the vulnerable code path exists in your tree, and reproduce the issue if you can.
- **Take the fix from the oldest branch that still has it.** Cherry-pick from the oldest upstream stable branch carrying the fix, not from master. It will be closest to your code and usually applies with the least rework.
- **Look for companion and follow-up patches.** Some OSSAs ship with a related hardening change. Others get a regression fix a few weeks later. Check the bug report and the stable branches' git log for both.
- **Look for conflicts with your six local backports.** If they touch the same files or functions, the cherry-pick may apply cleanly but still behave differently. Run the unit tests for the touched area, add a regression test for the vulnerability, and run a functional check on a test deployment.
- **Avoid pulling in schema or API changes.** If the fix needs a DB migration or an RPC/API version bump, the backport is no longer small. Weigh that cost before going ahead.
- **Keep the patches tracked.** Record the OSSA/CVE number, the upstream commit hashes, and what you changed from the original in the patch header. That makes the seven patches easier to rebase or drop when you move to a maintained series.

Seven security patches on an EOL series is also a sign that an upgrade is worth scheduling. Each new OSSA will cost more to backport as the code drifts.

If you give me the tree, or the OSSA number and your series, I can check where the vulnerable code is and how the upstream patch applies.