Backporting this one is defensible, but "it's a small patch" isn't the reason to do it. The seventh local security backport on an unmaintained series suggests you're making a lifecycle decision without calling it one.

**Why the patch size doesn't settle it**
- Your cost isn't the diff. It's the testing, the ownership, the re-application at every rebase, and the fact that nobody upstream will look at it again.
- Six local backports already means this series is too old to stay on through patching. The backports are now the lifecycle strategy, and the upgrade decision is being made by default each time one lands.
- I'm assuming your six are real security fixes you maintain yourselves. I haven't seen them, the OSSA, or your series, so I can't judge the patch itself.

**Check before you write anything**
1. **Does your distro or vendor already ship the fix for your series?** If so, take theirs. That keeps the local layer thin.
2. **Is Neutron exposed to untrusted tenants or networks?** Read the OSSA's affected-versions, severity and preconditions against your deployment. It might not apply, or a config change might mitigate it. That would mean no patch at all and a documented exception instead.
3. **Does the fix apply cleanly to your series?** Neutron fixes often touch code that changed between releases. "Small" upstream can mean a hand-adapted patch with a real regression risk in the control plane.

**If you proceed, treat it as a bounded deviation.** Record these for it, and ideally for the other six too:
- the OSSA, the upstream change it derives from, and why you're not upgrading
- a named owner, who also needs to be someone who isn't about to leave
- how you test it, with at least a functional run in a non-production environment
- a rollback path, such as the previous package or image kept available
- an exit condition. Usually that is "removed at the next upgrade", which needs a date or a trigger, not just the words.

**Bring the bigger decision to whoever owns the platform.** I'd frame it as "backport vs upgrade", with a trigger. For example: the next OSSA you'd have to backport locally, or a fixed date, forces the upgrade decision. Facts to gather first:
- how far the series is from a maintained one, and whether a SLURP path exists (check releases.openstack.org and your vendor)
- what upgrade readiness you actually have: recovery exercised, local patches inventoried, test coverage

If you tell me the series, your distribution or deployment tool, and the OSSA number, I can work through the vendor-fix check and a short decision record. I can also lay out a fuller backport-vs-upgrade comparison.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.