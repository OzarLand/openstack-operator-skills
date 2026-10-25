#!/usr/bin/env python3
"""Check that weighted_score.py reproduces the book's worked example (Ch. 18)."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "openstack-operational-decisions" / "scripts" / "weighted_score.py"

EXAMPLE = {
    "weights": {"value": 0.25, "control": 0.25, "transition_risk": 0.20,
                "complexity": 0.10, "lifecycle": 0.10, "readiness": 0.10},
    "options": {
        "Immediate": {"value": 5, "control": 4, "transition_risk": 1, "complexity": 3, "lifecycle": 5, "readiness": 2},
        "Progressive": {"value": 4, "control": 4, "transition_risk": 3, "complexity": 3, "lifecycle": 4, "readiness": 3},
        "Postpone": {"value": 2, "control": 3, "transition_risk": 4, "complexity": 4, "lifecycle": 1, "readiness": 4},
    },
}
EXPECTED_LINES = ["Progressive                    3.60", "Immediate                      3.45",
                  "Postpone                       2.95",
                  # the book: a recovery exercise moving transition risk 1 -> 2 flips the ranking
                  "Immediate.transition_risk +1 (1->2)"]


def main():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(EXAMPLE, f)
    out = subprocess.run([sys.executable, str(SCRIPT), f.name], capture_output=True, text=True)
    Path(f.name).unlink()
    missing = [line for line in EXPECTED_LINES if line not in out.stdout]
    if out.returncode != 0 or missing:
        print(out.stdout, out.stderr)
        print(f"FAIL: missing {missing}")
        return 1
    print("OK: weighted_score.py reproduces the Ch. 18 example")
    return 0


if __name__ == "__main__":
    sys.exit(main())
