**Short answer: backporting this one is defensible, but I wouldn't call it fine without a few checks. Adding a 7th local security backport also means the real decision is about the series, not about this patch.**

## Why the backport itself is reasonable
A security advisory whose fix exists upstream but not for your series is the standard legitimate case for a local backport. A small patch also keeps the blast radius bounded.

## Why the count matters
Six local security backports already is the warning sign: backports are turning into your lifecycle strategy. Each one has these costs:
- You alone maintain it. Upstream and your distro or vendor won't.
- It makes the next upgrade harder, because every one has to be re-evaluated, dropped or forward-ported.
- The next OSSA will probably arrive on the same unmaintained series, so this recurs.

## Checks before you commit
1. **Does your distro or vendor already ship or plan this fix for your series?** If so, take theirs. That keeps the local layer thin. (Gap: I don't know your packaging or vendor.)
2. **Is the OSSA reachable in your deployment?** Look at your Neutron backend, config and exposure. If it isn't, the urgency and the case for a local patch change. (Gap: I haven't seen the advisory or your config.)
3. **Does the patch apply cleanly to your series?** Neutron fixes often touch code that moved between releases. A clean cherry-pick isn't enough. It needs to pass the relevant unit tests, and ideally a functional test in a non-production environment.
4. **Who owns the six existing backports?** Is the person who wrote them still on the team? If not, that is a control gap that predates this decision.

## Make it a managed deviation
Record these for each backport, including this one:
- the OSSA and the upstream change it derives from
- the owner
- how it was tested
- why you chose it over upgrading
- an exit condition. The natural one is "removed when we move to a maintained series."

## The decision beyond this patch
These are what I'd put in front of whoever owns the platform:
- **Is there a dated plan to leave this series?** Without one, the backport count only grows. Each OSSA becomes a recurring tax, and unpatched advisories pile up because you have to patch everything yourselves. Check the series' status on releases.openstack.org and your vendor's supported path. (I don't know your series or its upgrade distance.)
- **Set a trigger to reopen the decision.** For example, "a 7th or 8th backport", "an OSSA with no clean backport", or a fixed date. That way the choice doesn't drift into permanence.
- **If upgrading now is too risky,** the first step may be to build the missing condition. That could be a recovery exercise or a staging environment that mirrors production.

## Recommendation
Backport it, if the vendor doesn't cover it and the OSSA applies to you. Treat that as the tactical answer. Pair it with the full backport record and a dated review of the upgrade path, so this doesn't become the strategy.

If you give me the series, the OSSA number, how you're packaged (distro, vendor or source) and what the six existing backports cover, I can turn this into a proper decision record with the options compared.

Decision support only. The backport and any rollout need approval from the accountable platform owner and should go through your change process.