# Decision-type playbooks

Book-derived questions and defaults for recurring decision types. Each
playbook feeds steps 4–9 of the workflow in SKILL.md.

## Contents

- Upgrade strategy (now / progressive / postpone)
- Local backport vs upgrade
- Technical debt: keep, reduce, remove, schedule
- Workarounds: retain or end
- Repair vs rebuild
- Security exceptions
- Automate or not
- Vendor and expert dependence

## Upgrade strategy

Sources: [Book: Ch. 14, Ch. 18, Ch. 9].

- Facts to establish (verify on releases.openstack.org and with the vendor):
  maintenance status of the running series, whether it is a SLURP release, how
  many SLURP hops to a maintained series, the vendor's supported path.
- Readiness evidence: local modifications, demonstrated recovery (by whom,
  when), test coverage, documentation, capacity, ownership, consumer and
  monitoring readiness.
- The standing-still risk is real: unmaintained series, unpatched advisories,
  growing divergence. The book allows that a platform far enough behind may
  have no stabilization other than the upgrade itself [Book: Ch. 9].
- Prefer the sequence that leaves the organization more able to perform the
  next transition; if transition risk is driven by missing recovery capability,
  the first action may be a recovery exercise [Book: Ch. 18].
- Delaying an upgrade until the organization can carry it can be right; delaying
  it again once the organization can no longer afford to is not [Book: Concl.].

## Local backport vs upgrade

Sources: [Book: Ch. 14, Ch. 17].

A backport can be reasonable when: a known defect affects a stable release,
the fix exists in a newer release, the defect's impact is bounded, and the
upgrade carries significant risk this quarter. Most legitimate case: a
security advisory whose fix exists upstream but not for the running series.

Minimum record for a backport:
- upstream issue addressed;
- upstream change it derives from;
- why the full upgrade was not chosen;
- owner of the local modification;
- how it is tested;
- when it will be reconsidered (exit condition — usually the next upgrade).

Check first whether the distribution or vendor already ships (or will soon
ship) the fix for the running series [Book: Ch. 14, Ch. 17].

Warning signs: backports becoming the lifecycle strategy; several security
backports carried at once (the series is too old — a lifecycle decision, not a
security one). An upstream stable backport is maintained by the community; a
vendor's by the vendor; a local one by you. Know which of the three layers
(upstream, distribution, local) each change lives in, and keep the local layer
thin.

## Technical debt

Source: [Book: Ch. 15] decision table.

| Situation | Operational consequence | Typical decision |
|---|---|---|
| Low business impact, well understood, no significant lifecycle impact | Limited exposure | Keep and document |
| Moderate impact, stable workaround, recurring operational effort | Consumes capacity | Plan simplification |
| Critical capability, recovery depends on one person | High organizational risk | Prioritize removal or redundancy |
| Customization complicates OpenStack upgrades | Increased lifecycle risk | Remove or replace during a planned event |
| Workaround is currently safer than a large production change | Immediate removal may increase risk | Keep temporarily with an exit condition |
| Debt repeatedly causes incidents | Direct loss of control | Treat as a priority risk |
| No remaining justification | Complexity without value | Remove |

Questions: what capability depends on it, how critical, who can operate and
recover it, what happens if it fails, does it make changes or upgrades harder,
how much effort does it consume. Prioritize by control improvement per unit of
capacity. Classify complexity as still required / justified but improvable /
no longer justified (the strongest candidate, often protected by fear)
[Book: Ch. 3]. After removal, verify the expected benefit occurred.

## Workarounds

Source: [Book: Ch. 15].

A workaround needs: purpose, owner, known scope, known side effects, detection
criteria, recovery method, exit condition. It is safe only while the risk it
introduces remains smaller than the risk it removes. Repetition is evidence:
frequency, effort and side effects feed the remediation decision. Watch for
accidental architecture (manual step → script → deployment logic → assumed
requirement). Intentional retention is legitimate; accidental permanence is
not. Include known workarounds in upgrade planning.

## Repair vs rebuild

Source: [Book: Ch. 10] (field passage on a shared test environment).

- Question: is the information in the current state valuable enough to justify
  preserving its uncertainty?
- Criterion: which option gives the highest probability of returning to a
  known, trusted state with acceptable business impact?
- Test environments: state is mostly accumulated experimentation; rebuilding
  is often right.
- Production: state is business continuity and cannot be discarded; still ask
  whether continued repair reduces risk when each fix creates the next problem.
- A rebuild needs a defined baseline, validation criteria and proof of
  equivalence — automated installation alone is not enough. Preserve evidence
  before either path.

## Security exceptions

Sources: [Book: Ch. 17, Ch. 20].

When a patch, rotation or upgrade cannot be done now: owner, compensating
controls, review condition. The requirement defines what must be achieved;
capacity and criticality define how safely. Security exposure is a control gap
reviewed with the same owners and exit conditions as other gaps. Recurring
difficulty meeting security requirements is a lifecycle problem for the roadmap.

## Automate or not

Source: [Book: Ch. 16] (the "execution before judgement" position is the
author's own and not shared by every engineering culture).

- Will automating make the platform easier and safer **for this organization**
  to operate?
- Is the underlying problem understood? Automating an unresolved workaround
  makes it happen faster and at scale.
- Execution vs judgement: decisions needing business context, uncertain
  diagnosis or risk acceptance stay with humans unless explicitly delegated.
- Semi-automation (prepare, collect evidence, propose; human decides) is often
  better. Low-frequency, highly contextual operations may stay manual.
- Automation is production software: owner, version control, tests, docs,
  observability, recovery path.
- For code review of the automation itself, use `openstack-automation-review`.

## Vendor and expert dependence

Sources: [Book: Ch. 2, Ch. 12, Ch. 14].

- Which operations can the organization perform without opening a ticket, which
  not, and is the second list shrinking?
- Does each escalation return an explanation the team can reuse?
- Does each external engagement leave the organization more capable after the
  expert has gone?
- A vendor that is the only party able to explain the platform's behaviour is a
  control gap.
