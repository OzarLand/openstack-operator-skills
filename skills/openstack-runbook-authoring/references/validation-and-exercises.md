# Validating runbooks and running exercises

From [Book: Ch. 10], [Book: Ch. 11] and [Book: Ch. 12].

## Validation by a non-author

- Documentation should be tested by someone who did not write it. If another
  engineer cannot use a recovery procedure, it is not yet operational
  knowledge [Book: Ch. 11].
- The book's field example: a new engineer executed a real procedure alone,
  with a senior engineer watching but not helping. Gaps appeared: the order of
  some steps, precautions everyone applied without thinking, which signals to
  look at first when things diverged, and why some configurations were
  exceptions. The documentation was corrected from his questions
  [Book: Ch. 11].
- Knowledge that only shows when someone else performs the work must be
  captured while the expert can still watch [Book: Ch. 12].

Checklist for the validation session `[Addition]` (structure of the book's
example):
- [ ] Executor did not write the runbook.
- [ ] Observer does not help; records every question and hesitation.
- [ ] Every question becomes a document change or an explicit "out of scope".
- [ ] Validation date and executor recorded in the runbook.

## Exercises

- Real incidents rarely follow the runbook exactly: introduce controlled
  uncertainty — a dependency unavailable, an expected signal missing, the
  primary expert absent [Book: Ch. 10].
- Rotate participants: a procedure that succeeds only when its author is
  present demonstrates the author's competence, not the organization's
  resilience [Book: Ch. 10].
- Use exercises during real maintenance or controlled sessions, to find out
  whether knowledge is usable, not to produce compliance evidence
  [Book: Ch. 11].
- End every exercise with: what did this reveal that should now be different?
  (documentation, monitoring, architecture, training, simplification)
  [Book: Ch. 10].

## Lifecycle

Documentation is operational memory only when the organization creates,
maintains, tests, uses and retires it deliberately [Book: Ch. 11]. Review by
risk: critical recovery knowledge gets stronger validation than low-impact
reference material. Retire obsolete pages: contradictory documentation
increases uncertainty during incidents [Book: Ch. 11].
