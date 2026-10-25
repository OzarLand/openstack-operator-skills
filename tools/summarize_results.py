#!/usr/bin/env python3
"""Aggregate behavioural results (evals/results/<run-id>/summary.json) into Markdown.

    python3 tools/summarize_results.py final-*        # run-id glob(s)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evals" / "results"


def main(patterns):
    rows = []
    for pattern in patterns or ["*"]:
        for summary in sorted(RESULTS.glob(f"{pattern}/summary.json")):
            for m in json.loads(summary.read_text()):
                m["run"] = summary.parent.name
                rows.append(m)
    if not rows:
        print("no results found")
        return 1

    print("| Scenario | Mode | Model | Skill(s) invoked | Criteria score | Critical errors committed |")
    print("|---|---|---|---|---:|---|")
    for m in sorted(rows, key=lambda r: (r["scenario"], r["mode"])):
        sc = m.get("score") or {}
        crit = "; ".join(sc.get("critical_errors_committed", [])) or "none"
        invoked = ", ".join(m.get("skills_invoked") or []) or "—"
        value = f"{sc['criteria_score']:.2f}" if "criteria_score" in sc else "n/a"
        print(f"| {m['scenario']} | {m['mode']} | {m.get('model')} | {invoked} | {value} | {crit} |")

    print("\n| Mode | Runs | Mean criteria score | Runs with ≥1 critical error | Expected skill triggered |")
    print("|---|---:|---:|---:|---:|")
    for mode in ("skill", "baseline"):
        sel = [m for m in rows if m["mode"] == mode and m.get("score")]
        if not sel:
            continue
        mean = sum(m["score"]["criteria_score"] for m in sel) / len(sel)
        crit = sum(1 for m in sel if m["score"]["critical_errors_committed"])
        trig = sum(1 for m in sel if m.get("triggered"))
        trig_txt = f"{trig}/{len(sel)}" if mode == "skill" else "n/a"
        print(f"| {mode} | {len(sel)} | {mean:.2f} | {crit} | {trig_txt} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
