Yes, backporting is the normal move for a series upstream has stopped maintaining. I haven't seen the OSSA or your tree, so these checks are what would make it safe:

1. **Confirm your series is actually vulnerable.** Upstream usually only tests the branches it still maintains. The code on your older series may be structured differently, or may not be affected at all.
2. **Cherry-pick from the oldest branch that got the fix, not from master.** Walking the fix back one release at a time shows you which refactors it depends on. A small diff on master can rely on helpers or behavior that don't exist on your series.
3. **Check for interaction with your 6 local backports.** If any touch the same files (the API layer, the agents, or the same DB/policy paths), a clean `git apply` doesn't prove they work together. Run the unit and functional tests for those modules, and add a regression test for the vulnerability if the upstream patch included one.
4. **Check the follow-ups.** Security fixes sometimes get a second patch for a regression or an incomplete fix. Look at the bug report and the stable branches for any after the initial commit.
5. **Check whether the fix is purely server-side.** If it changes agent behavior, RPC payloads, or needs a config change, plan the rollout order across your nodes.

The bigger issue is that this will be your 7th carried patch. The cost of each one grows, because each new backport has to be checked against the whole stack of earlier ones. If you don't already have an upgrade path to a maintained series, this is a good time to schedule one. Keep a short list of the local backports, with upstream commit IDs and the reason for each, so you can drop them when you upgrade.

If you give me the OSSA number and the tree, I can look at the actual patch and check how it applies.