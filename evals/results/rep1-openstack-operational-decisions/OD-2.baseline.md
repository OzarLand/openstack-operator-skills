Yes, backporting is the right call. For an unmaintained series, a local backport is the standard way to handle an OSSA. Some checks matter more than the patch being small:

1. **Check that you're affected.** Upstream's OSSA only lists versions it assessed, and an EOL series usually isn't one of them. Read the vulnerable code path on your branch to confirm it exists and is exploitable. Older code sometimes lacks the vulnerable path, and sometimes has a variant the upstream fix doesn't cover.
2. **Check for a missing prerequisite.** A small patch can depend on refactors or earlier fixes your series doesn't have. If the cherry-pick conflicts, understand why before resolving it. A clean conflict resolution that silently changes behavior is the main risk with old branches.
3. **Check for overlap with your 6 existing backports.** If any touch the same files or the same area (API validation, policy, the DB layer, agents), apply the new patch on top of them and rerun their tests as well.
4. **Check whether the fix spans repos.** Some Neutron OSSAs also change neutron-lib, a plugin or driver, or a policy default. If so, backport those too or you'll only have part of the fix.
5. **Test it.**
   - Include the upstream regression test, adapted to your series.
   - Run the unit tests for the touched modules.
   - Run any functional tests you can.
   - Try the exploit scenario from the advisory before and after the patch.
6. **Record provenance.** Keep the upstream commit ID, the OSSA/CVE number and a note on any adaptations. Carry the patches as a clean ordered series (a git branch or quilt), not as edits to the tree. That makes a seventh backport as easy to audit as the first.

On the bigger picture, a seventh backport on an unmaintained series is not a problem in itself. But each one adds to the cost of diverging from upstream. It's worth putting a date on your upgrade path, or on adopting a vendor-maintained series. Backporting means you've taken on the job of triaging every future advisory for this branch yourself.

If you share the OSSA number and the patch, I can check whether it applies cleanly to your tree and whether it interacts with your existing backports.