#!/usr/bin/env python3
"""Check that tools/validate_knowledge.py catches the faults it is meant to catch.

Each case copies the repository to a temporary directory, injects one fault
and expects the validator to fail with a recognisable message; the clean copy
must pass.

    python3 tools/test_validate_knowledge.py
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY = ["skills", "validation", "docs", "tools", "README.md", "CONTRIBUTING.md"]


def run(root):
    proc = subprocess.run([sys.executable, str(root / "tools" / "validate_knowledge.py")],
                          capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout + proc.stderr


def first_tag(root):
    for path in sorted((root / "skills").glob("*/references/*.md")):
        m = re.search(r"\[LAB-VALIDATED: ([A-Z]{2}-[A-Z0-9]+-\d{2})\]", path.read_text(encoding="utf-8"))
        if m:
            return path, m
    raise SystemExit("no LAB-VALIDATED tag found")


def sub(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def case_status_mismatch(root):
    path, m = first_tag(root)
    sub(path, m.group(0), f"[DOCUMENTED-UNVERIFIED: {m.group(1)}]")
    return "disagrees with inventory status"


def case_unknown_id(root):
    path, m = first_tag(root)
    sub(path, m.group(0), m.group(0) + " [LAB-VALIDATED: ZZ-NONE-99]")
    return "unknown inventory id"


def case_malformed_tag(root):
    path, m = first_tag(root)
    sub(path, m.group(0), m.group(0) + " [LAB-VALIDTED: ZZ-NONE-99]")
    return "malformed validation tag"


def case_missing_evidence(root):
    inv = root / "validation" / "inventory.yaml"
    sub(inv, "  status: LAB-VALIDATED\n", "  status: LAB-VALIDATED\n  validation_removed: true\n")
    text = inv.read_text(encoding="utf-8")
    pattern = r"(validation_removed: true\n(?:.*\n)*?)  validation:\n(?:    .*\n|      .*\n)+"
    text = re.sub(pattern, r"\1", text, count=1)
    inv.write_text(text.replace("  validation_removed: true\n", "", 1), encoding="utf-8")
    return "requires a 'validation' record"


def case_stale_coverage(root):
    sub(root / "README.md", "items in scope", "items in scope (edited by hand)")
    return "coverage is stale"


def case_no_undergoing(root):
    sub(root / "README.md", "undergoing validation", "being worked on")
    return "undergoing validation"


def case_full_claim(root):
    path = root / "skills" / "openstack-vm-troubleshooting" / "SKILL.md"
    sub(path, "## Limits and safety\n", "## Limits and safety\n\n- This skill is fully validated.\n")
    return "claims repository-wide validation"


CASES = [case_status_mismatch, case_unknown_id, case_malformed_tag, case_missing_evidence,
         case_stale_coverage, case_no_undergoing, case_full_claim]


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "clean"
        base.mkdir()
        for name in COPY:
            src = ROOT / name
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, base / name)
        code, out = run(base)
        if code != 0:
            print(f"FAIL clean copy does not pass:\n{out}")
            return 1
        print("ok   clean copy passes")
        for case in CASES:
            work = Path(tmp) / case.__name__
            shutil.copytree(base, work)
            expected = case(work)
            code, out = run(work)
            if code != 0 and expected in out:
                print(f"ok   {case.__name__}")
            else:
                failures += 1
                print(f"FAIL {case.__name__}: exit {code}, expected '{expected}' in output:\n{out[-800:]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
