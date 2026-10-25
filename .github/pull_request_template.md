## What and why

<!-- What changes, which skill(s), and the operational reason. Link the issue. -->

## Sources

- [ ] Book content is tagged `[Book: Ch. N]`, everything else `[Addition]`
- [ ] Technical facts link to upstream or vendor documentation where relevant

## Checks

- [ ] `python3 tools/sync_shared.py`
- [ ] `python3 tools/validate_skills.py` reports 0 errors
- [ ] `python3 tools/test_weighted_score.py`
- [ ] `ruff check .`

## Behavioural results (if a skill's behaviour changed)

<!-- Scenarios run, model, scores, whether the skill triggered, critical errors.
     Only results you actually ran. Write "not run" otherwise. -->
