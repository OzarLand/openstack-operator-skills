#!/usr/bin/env python3
"""Behavioural evaluation harness using the Claude Code CLI (`claude -p`).

For each scenario in evals/scenarios/<skill>.json this script:

1. creates a throwaway project directory,
2. in mode `skill`, installs every skill of this repository under
   .claude/skills/ so Claude Code discovers them natively (triggering is part of
   the test); in mode `baseline`, runs with all skills disabled,
3. sends the scenario prompt with `claude -p` (tools limited to read-only ones,
   so nothing can be executed),
4. records the response and which skills were invoked,
5. asks a fresh `claude -p` instance (no skills) to grade the response against
   the scenario's rubric, returning structured JSON.

Requirements: the `claude` CLI, authenticated. This costs API usage.

    python3 tools/run_behavioral.py --skill openstack-incident-analysis
    python3 tools/run_behavioral.py --skill openstack-incident-analysis --scenario IA-1 --modes skill baseline
    python3 tools/run_behavioral.py --all --modes skill

Results are written to evals/results/<run-id>/ (one .md response and one
.grade.json per scenario and mode, plus summary.json).
"""

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SCENARIOS = ROOT / "evals" / "scenarios"
RESULTS = ROOT / "evals" / "results"
GRADER_PROMPT = ROOT / "evals" / "grader-prompt.md"

# Read-only tools only: the model can load skills and read their files, but
# cannot run commands or modify anything.
ALLOWED_TOOLS = "Skill Read Glob Grep"
DISALLOWED_TOOLS = "Bash Write Edit NotebookEdit WebFetch WebSearch Agent"
RUN_TIMEOUT_S = 900  # generous: a full incident analysis can be long

GRADE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["pass", "partial", "fail"]},
                    "evidence": {"type": "string"},
                },
                "required": ["criterion", "verdict", "evidence"],
            },
        },
        "critical_errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "committed": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
                "required": ["error", "committed", "evidence"],
            },
        },
        "faithfulness_issues": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["criteria", "critical_errors", "faithfulness_issues", "summary"],
}


def run_claude(prompt, cwd, extra_args, model):
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
        "--strict-mcp-config",  # no MCP servers: the run sees only the skills
        "--allowedTools", ALLOWED_TOOLS,
        "--disallowedTools", DISALLOWED_TOOLS,
    ] + extra_args
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=RUN_TIMEOUT_S, check=False)
    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return proc, events


def parse_events(events):
    skills_invoked, files_read, final_text, model_used, structured = [], [], "", None, None
    for ev in events:
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            model_used = ev.get("model")
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                inp = block.get("input", {})
                if block.get("name") == "Skill":
                    skills_invoked.append(inp.get("skill") or inp.get("command") or json.dumps(inp))
                elif block.get("name") == "Read":
                    files_read.append(inp.get("file_path", ""))
        if ev.get("type") == "result":
            final_text = ev.get("result", "") or ""
            structured = ev.get("structured_output")
    return skills_invoked, files_read, final_text, model_used, structured


def run_scenario(skill, scenario, mode, model, outdir):
    with tempfile.TemporaryDirectory(prefix="osk-eval-") as tmp:
        tmp = Path(tmp)
        extra = []
        if mode == "skill":
            dest = tmp / ".claude" / "skills"
            dest.mkdir(parents=True)
            for d in SKILLS.iterdir():
                if (d / "SKILL.md").exists():
                    shutil.copytree(d, dest / d.name)
        else:
            extra.append("--disable-slash-commands")
        proc, events = run_claude(scenario["prompt"], tmp, extra, model)
    invoked, files_read, text, model_used, _ = parse_events(events)
    (outdir / f"{scenario['id']}.{mode}.md").write_text(text, encoding="utf-8")
    meta = {
        "skill_under_test": skill,
        "scenario": scenario["id"],
        "mode": mode,
        "model": model_used,
        "skills_invoked": invoked,
        "triggered": any(skill in s for s in invoked),
        "reference_files_read": [Path(f).name for f in files_read],
        "exit_code": proc.returncode,
        "stderr_tail": proc.stderr[-2000:],
    }
    return text, meta


def grade(scenario, response, model):
    rubric = GRADER_PROMPT.read_text(encoding="utf-8")
    payload = {k: scenario[k] for k in (
        "title", "source", "prompt", "available_evidence", "missing_information",
        "expected_reasoning", "expected_output", "critical_errors", "criteria")}
    prompt = (
        rubric
        + "\n\n## Scenario\n\n```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```\n"
        + "\n## Response to grade\n\n<response>\n" + response + "\n</response>\n"
    )
    with tempfile.TemporaryDirectory(prefix="osk-grade-") as tmp:
        extra = ["--disable-slash-commands", "--json-schema", json.dumps(GRADE_SCHEMA)]
        proc, events = run_claude(prompt, tmp, extra, model)
    _, _, text, _, structured = parse_events(events)
    if structured is None:
        try:
            structured = json.loads(text)
        except json.JSONDecodeError:
            structured = {"error": "grader did not return JSON", "raw": text[-4000:], "stderr": proc.stderr[-2000:]}
    return structured


def score(grade_json):
    if "criteria" not in grade_json:
        return None
    points = {"pass": 1.0, "partial": 0.5, "fail": 0.0}
    crit = grade_json["criteria"]
    value = sum(points.get(c["verdict"], 0) for c in crit) / max(len(crit), 1)
    committed = [e["error"] for e in grade_json.get("critical_errors", []) if e.get("committed")]
    return {"criteria_score": round(value, 3), "critical_errors_committed": committed}


def main():
    ap = argparse.ArgumentParser(description="Run behavioural evaluations with claude -p")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--skill")
    group.add_argument("--all", action="store_true")
    ap.add_argument("--scenario", action="append", help="scenario id (repeatable)")
    ap.add_argument("--modes", nargs="+", default=["skill"], choices=["skill", "baseline"])
    ap.add_argument("--model", help="model for the run under test (default: CLI default)")
    ap.add_argument("--grader-model", help="model for grading (default: CLI default)")
    ap.add_argument("--run-id", default=dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--no-grade", action="store_true")
    args = ap.parse_args()

    if shutil.which("claude") is None:
        print("the `claude` CLI is required", file=sys.stderr)
        return 2

    files = sorted(SCENARIOS.glob("*.json")) if args.all else [SCENARIOS / f"{args.skill}.json"]
    outdir = RESULTS / args.run_id
    outdir.mkdir(parents=True, exist_ok=True)
    summary_path = outdir / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else []

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        for sc in data["scenarios"]:
            if args.scenario and sc["id"] not in args.scenario:
                continue
            for mode in args.modes:
                print(f"[{sc['id']}:{mode}] running ...", flush=True)
                text, meta = run_scenario(data["skill"], sc, mode, args.model, outdir)
                if not args.no_grade:
                    g = grade(sc, text, args.grader_model)
                    (outdir / f"{sc['id']}.{mode}.grade.json").write_text(
                        json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
                    meta["score"] = score(g)
                (outdir / f"{sc['id']}.{mode}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
                summary = [s for s in summary if not (s["scenario"] == sc["id"] and s["mode"] == mode)]
                summary.append(meta)
                summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
                print(f"[{sc['id']}:{mode}] triggered={meta['triggered']} score={meta.get('score')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
