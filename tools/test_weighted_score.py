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
        "Immediate": {"value": 5, "control": 4, "transition_risk": 1,
                      "complexity": 3, "lifecycle": 5, "readiness": 2},
        "Progressive": {"value": 4, "control": 4, "transition_risk": 3,
                        "complexity": 3, "lifecycle": 4, "readiness": 3},
        "Postpone": {"value": 2, "control": 3, "transition_risk": 4,
                     "complexity": 4, "lifecycle": 1, "readiness": 4},
    },
}
EXPECTED_LINES = ["Progressive                    3.60", "Immediate                      3.45",
                  "Postpone                       2.95",
                  # the book: a recovery exercise moving transition risk 1 -> 2 flips the ranking
                  "Immediate.transition_risk +1 (1->2)"]


# (input, expected exit code, text expected in stdout+stderr)
EDGE_CASES = [
    ([1, 2], 1, "top level must be an object"),
    ({"weights": {"a": "0.5", "b": 0.5}, "options": {"x": {"a": 3, "b": 3}}}, 1, "must be a number >= 0"),
    ({"weights": {"a": 1.5, "b": -0.5}, "options": {"x": {"a": 1, "b": 5}}}, 1, "must be a number >= 0"),
    ({"weights": {"a": 0.5, "b": 0.5}, "options": {"x": {"a": True, "b": 3}}}, 1, "outside 1..5"),
    ({"weights": {"a": 0.5, "b": 0.5, "z": 0},
      "options": {"x": {"a": 3, "b": 3, "z": 3}, "y": {"a": 3, "b": 3, "z": 3}}}, 0, "tied"),
]


def run(data):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f)
    out = subprocess.run([sys.executable, str(SCRIPT), f.name], capture_output=True, text=True, check=False)
    Path(f.name).unlink()
    return out


def main():
    out = run(EXAMPLE)
    missing = [line for line in EXPECTED_LINES if line not in out.stdout]
    if out.returncode != 0 or missing:
        print(out.stdout, out.stderr)
        print(f"FAIL: missing {missing}")
        return 1
    for data, code, text in EDGE_CASES:
        out = run(data)
        if out.returncode != code or text not in out.stdout + out.stderr or "Traceback" in out.stderr:
            print(out.stdout, out.stderr)
            print(f"FAIL: edge case {data!r}: expected exit {code} and {text!r}")
            return 1
    print("OK: weighted_score.py reproduces the Ch. 18 example and handles edge cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
