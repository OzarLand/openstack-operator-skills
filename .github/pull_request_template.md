## What and why

<!-- What changes, which skill(s), and the operational reason. Link the issue. -->

## Sources

- [ ] Book content is tagged `[Book: Ch. N]`, everything else `[Addition]`
- [ ] Technical facts link to upstream or vendor documentation where relevant

## Validation (see docs/knowledge-validation-policy.md)

- [ ] Every new or changed procedure or technical claim has a status tag and an
      entry in `validation/inventory.yaml`
- [ ] Validated statuses cite a recorded execution (environment, release,
      deployment method, backends, date, steps run and not run); nothing raised
      without new evidence
- [ ] Changed steps of a validated procedure are set to `NEEDS-REVALIDATION`

## Checks

- [ ] `python3 tools/sync_shared.py`
- [ ] `python3 tools/validate_skills.py` reports 0 errors
- [ ] `python3 tools/test_weighted_score.py`
- [ ] `python3 tools/validate_knowledge.py`
- [ ] `ruff check .`

## Behavioural results (if a skill's behaviour changed)

<!-- Scenarios run, model, scores, whether the skill triggered, critical errors.
     Only results you actually ran. Write "not run" otherwise. -->
