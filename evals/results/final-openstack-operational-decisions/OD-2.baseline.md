Yes, backporting is a reasonable call. A small, self-contained security patch is the usual way to handle an unmaintained series, and doing it for the seventh time doesn't change that. A few things to check before you rely on it:

- **Size isn't the main risk.** The risk is how far the code has drifted between the series the patch targets and yours. Neutron changes a lot between releases, so a small diff can still hit different surrounding code, renamed helpers, or a different DB or RPC path. Read the fix in context instead of trusting a clean `git apply`.
- **Look for prerequisite commits.** OSSA fixes often come with follow-up commits or depend on earlier refactors. Check the advisory and the linked reviews for the full set. Also check whether the patch for the oldest branch it covers differs from the master one.
- **Check for interactions with your six local patches.** Look for overlapping files and hunks, especially if any touch the same area (API, ML2, agents, policy). Run the unit tests for the touched modules after the backport, and add a test that reproduces the vulnerability if upstream's test doesn't apply.
- **Confirm your series is affected.** The OSSA lists affected versions, and the fix may not be needed or may look different on yours.
- **Check whether upstream will take it.** Since the series is unmaintained, there may be an `unmaintained/<series>` branch where you can propose the backport. That keeps you closer to upstream and lets others review it.

You're also at the point where the carrying cost matters. With seven local security patches, each new OSSA means more rebasing work and more risk of missing something. If you aren't already planning an upgrade to a maintained series, this is a good time to put one on the roadmap.

If you can give me the OSSA number, or the tree and the patch, I can check whether it applies cleanly, whether it has dependencies, and whether it conflicts with your existing backports.