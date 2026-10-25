# Weighted decision model

From [Book: App. A] and [Book: Ch. 18]. The author's own model; weights are
illustrative and should change with context.

## Contents

- Dimensions and baseline weights
- Scoring rules
- Adjusting weights
- Questions the model must force
- Worked example from the book
- Script: weighted_score.py

## Dimensions and baseline weights

| Dimension | Baseline weight | 5 means |
|---|---|---|
| Business value or risk reduction | 25 % | largest value / risk reduction |
| Control improvement | 25 % | largest gain in the organization's control |
| Transition risk | 20 % | **lowest** transition risk |
| Operational complexity | 10 % | **lowest** added complexity |
| Lifecycle and upstream alignment | 10 % | closest to maintained upstream |
| Organizational readiness | 10 % | team most ready to execute and operate it |

## Scoring rules

- Score each option 1–5 on every dimension; 5 is always the preferable end.
- Option score = Σ (score × weight); results lie between 1 and 5.
- Every score needs a one-line justification that cites evidence. A score
  resting on an assumption is marked as such.
- Only options that passed every gate are scored.

## Adjusting weights

[Book: App. A] A security-driven decision may weight risk reduction more; an
unstable platform may weight transition risk and control improvement more; a
team in transition may weight readiness more. State any change and its reason.

## Questions the model must force

[Book: App. A, Ch. 18]
- Why is the transition risk a 1 rather than a 3? What evidence supports it?
- What evidence supports the readiness score?
- Which assumption is most uncertain?
- What event would change the ranking?
- Is there a non-negotiable constraint that rejects an option regardless of score?
- Where do the participants' scores differ? (Disagreement made visible is the
  model's main value.)

## Worked example from the book

[Book: Ch. 18] Platform: series out of maintenance, two SLURP releases behind;
about a dozen local patches, three in Nova scheduling written by an engineer
who left; control-plane recovery demonstrated once, two years ago, by that same
engineer; team shrank from six to four; a security advisory affects the series,
upstream fix only for maintained series, backport possible but untested.

Postponement passes the security gate only because a tested backport is
credible; without it, it would be rejected before scoring.

| Dimension (weight) | Immediate (both hops in a quarter) | Progressive (one hop, stabilize, second hop) | Postpone (reduce debt first) |
|---|:-:|:-:|:-:|
| Business value or risk reduction (25 %) | 5 | 4 | 2 |
| Control improvement (25 %) | 4 | 4 | 3 |
| Transition risk (20 %) | 1 | 3 | 4 |
| Operational complexity (10 %) | 3 | 3 | 4 |
| Lifecycle and upstream alignment (10 %) | 5 | 4 | 1 |
| Organizational readiness (10 %) | 2 | 3 | 4 |
| **Weighted score** | **3.45** | **3.60** | **2.95** |

Reading, per the book: the gap between immediate and progressive is within the
uncertainty of the scores. The immediate option's transition-risk score of 1
rests on one fact — recovery not demonstrated by anyone still on the team. A
successful recovery exercise would move it to 2 or 3 and flip the ranking. So
the model's real output is the first action: **a recovery exercise, not an
upgrade.** Postponement scores highest on readiness — the honest signal that
the team is the constraint.

## Script: weighted_score.py

Optional, for deterministic arithmetic and sensitivity analysis. Requires
Python 3 only (no packages). Input is JSON:

```json
{
  "weights": {"value": 0.25, "control": 0.25, "transition_risk": 0.20,
              "complexity": 0.10, "lifecycle": 0.10, "readiness": 0.10},
  "options": {
    "Immediate":   {"value": 5, "control": 4, "transition_risk": 1, "complexity": 3, "lifecycle": 5, "readiness": 2},
    "Progressive": {"value": 4, "control": 4, "transition_risk": 3, "complexity": 3, "lifecycle": 4, "readiness": 3}
  }
}
```

Run: `python3 scripts/weighted_score.py options.json`

Output: score per option, ranking, and for each pair of adjacent options the
smallest single-score changes (±1 or ±2) that would flip their order. If the
script cannot run in the environment, do the arithmetic by hand and show it.
