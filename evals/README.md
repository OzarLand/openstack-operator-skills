# Evaluations

Two kinds of checks, kept separate on purpose.

## 1. Structural checks (automated, no model)

`python3 tools/validate_skills.py` — runs in CI. Checks:

- frontmatter: portable keys only, `name` format/length/reserved words and
  equal to the directory, `description` present, ≤ 1024 characters, no angle
  brackets, third person, states when to use;
- `SKILL.md` body under 500 lines, with `Output format` and `Limits and safety` sections;
- links resolve and stay inside the skill; references are one level deep and
  all linked from `SKILL.md`; reference files over 100 lines have `## Contents`;
- shared reference copies are identical to `shared/`;
- `[Book: ...]` citations point to chapters, appendices and figures that exist
  in the book (v1.2);
- every skill has a scenario file with at least 3 complete scenarios;
- relative links in `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`,
  `evals/README.md` and `docs/` resolve.

These checks say nothing about whether a skill gives good advice.

`python3 tools/validate_knowledge.py` (also in CI) checks the knowledge
validation inventory against the status tags in the skills and the published
coverage. It says nothing about whether a procedure works on OpenStack; only a
recorded execution does (`docs/knowledge-validation-policy.md`).

## 2. Behavioural evaluations (require running Claude)

`tools/run_behavioral.py` runs each scenario through the Claude Code CLI:

- **skill mode**: all skills installed in a throwaway project's
  `.claude/skills/`; Claude Code decides whether to load one (triggering is part
  of the test); tools limited to `Skill Read Glob Grep` so nothing can execute;
- **baseline mode**: same prompt with all skills disabled;
- **grading**: a separate `claude -p` instance (no skills) applies
  `grader-prompt.md` and the scenario's `criteria` and `critical_errors`, and
  returns structured JSON.

Scores: each criterion pass = 1, partial = 0.5, fail = 0, averaged. Critical
errors are reported separately and matter more than the average.

### Scenario format

`scenarios/<skill>.json`:

| Field | Meaning |
|---|---|
| `id`, `title` | identifier and short name |
| `source` | book chapters the scenario comes from; "scenario constructed" when it is not a documented book situation (the 0.2.0 scenarios name the OzarLand page they are built from) |
| `prompt` | what the user says |
| `followups` | optional: later user turns, for a multi-turn scenario; the harness keeps one session (`--session-id`, then `--resume`) and the grader sees the whole conversation |
| `available_evidence` | what the prompt actually establishes |
| `missing_information` | what a good answer should notice is missing |
| `expected_reasoning` | the reasoning steps the book's method implies |
| `expected_output` | the shape of a good answer |
| `critical_errors` | things the answer must not do |
| `criteria` | graded statements |

### Known limits of this method

- Model grading is itself a model judgement; spot-check the raw outputs in
  `results/`.
- One run per cell is noisy; differences of a few points are not meaningful.
  Run the same suite with several `--run-id`s to measure the spread.
- Scenarios were written by the same author as the skills; independent
  scenarios from operators are the most valuable contribution.
- Claude Code only; claude.ai and the API were not exercised.
