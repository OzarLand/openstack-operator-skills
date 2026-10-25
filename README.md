# OpenStack Operator Skills

Agent Skills that help Claude reason like an experienced production OpenStack
operator: investigate before acting, separate facts from hypotheses, weigh
business impact, insist on recovery paths and verification, and leave
disruptive decisions with the people accountable for them.

The skills turn the operating method of the book
[*OpenStack, the Day After Tomorrow — Operating Mission-Critical OpenStack Platforms*](https://github.com/soufian-zaouam/openstack-the-day-after-tomorrow)
(Soufian Zaouam, v1.2) into reusable workflows. You do not need to have read
the book to use them.

> **Status: 0.1.0 — early release.** Structurally validated and
> behaviourally tested on 28 scenarios (Sonnet, plus Haiku spot checks;
> see
> [docs/evaluation-report.md](docs/evaluation-report.md)). Not a substitute
> for engineering judgement, and never an authorization to change production.

## The skills

| Skill | Use it when you need to… |
|---|---|
| [`openstack-incident-analysis`](skills/openstack-incident-analysis/SKILL.md) | investigate a live or recent incident: VMs stuck in BUILD, RabbitMQ/Galera trouble, hosts down, evacuation decisions, RCA |
| [`openstack-change-review`](skills/openstack-change-review/SKILL.md) | decide if a planned change (upgrade step, rotation, config, network, DB intervention) is ready: gates, blast radius, rollback, stop conditions, verification |
| [`openstack-maintenance-planning`](skills/openstack-maintenance-planning/SKILL.md) | plan host patching or maintenance within real capacity and business criticality: live vs cold migration vs restart, sequencing, failure domains |
| [`openstack-operational-decisions`](skills/openstack-operational-decisions/SKILL.md) | choose between options: upgrade now or later, backport or upgrade, keep or remove a workaround, repair or rebuild, security exceptions |
| [`openstack-control-assessment`](skills/openstack-control-assessment/SKILL.md) | assess how much control you actually have over a platform, review after a team change, or plan a restoration when control is lost |
| [`openstack-automation-review`](skills/openstack-automation-review/SKILL.md) | review playbooks, scripts or auto-remediation for delegated judgement, blast radius, safeguards and maintainability |
| [`openstack-runbook-authoring`](skills/openstack-runbook-authoring/SKILL.md) | write or review runbooks with decision points, stop/escalation conditions and validation by a non-author |

Each skill works on its own; they reference each other when a task crosses
their boundaries.

## What the skills do — and do not do

They **do**:
- structure the reasoning (evidence ledger, dependency path, hypotheses with
  disproving checks, gates, trade-offs, decision rights);
- propose **read-only** diagnostics first and label every step read-only or
  state-changing;
- attach prerequisites, blast radius, verification, stop conditions, recovery
  and an approving role to every state-changing recommendation;
- list missing information instead of inventing it;
- cite the book (`[Book: Ch. 9]`) so a human can check the reasoning, and mark
  this repository's own additions (`[Addition]`).

They **do not**:
- execute anything or access your infrastructure (unless you give Claude tools
  in your own session — the skills never assume it);
- claim an action succeeded without evidence you provide;
- authorize production changes;
- replace the official OpenStack, RabbitMQ, Galera or vendor documentation —
  release-specific facts are flagged for verification.

## Install

See [docs/installation.md](docs/installation.md) for details.

**Claude Code (plugin marketplace):**

```text
/plugin marketplace add soufian-zaouam/openstack-operator-skills
/plugin install openstack-operations@openstack-operator-skills
```

**Claude Code (copy):** copy the directories under `skills/` into
`~/.claude/skills/` (personal) or `<project>/.claude/skills/` (project).

**claude.ai:** run `python3 tools/package_skills.py` and upload each
`dist/<skill>.zip` in *Settings → Capabilities/Features → Skills* (requires a
plan with code execution enabled).

**Claude API:** upload each skill directory through the Skills API
(`/v1/skills`) and use it with the code execution tool.

## Usage

Talk to Claude as you would to a colleague; the skills trigger from the
request. Examples:

- "Nobody can create VMs since 10 minutes, conductor logs show
  MessagingTimeout and one Galera node is non-Primary. What do I do?"
- "Review this change: rotate all internal TLS certificates Saturday together
  with the controller OS update."
- "We must patch 300 compute hosts for a QEMU CVE in three weeks and only have
  spare capacity for about eight hosts."
- "Upgrade now in two hops, progressively, or postpone and carry a backport?"
- "Here's our auto-evacuation script, can we put it in cron?"
- "Turn these incident notes into a runbook."

In Claude Code you can also invoke a skill explicitly, e.g.
`/openstack-incident-analysis`.

## Supported environments

| Surface | Works | Notes |
|---|---|---|
| Claude Code | yes | Tested here (CLI, `claude -p`). Skills load from `.claude/skills/`, `~/.claude/skills/` or the plugin. |
| claude.ai | expected | Same files; upload as zip. Not tested in this release. Custom skills are per user. |
| Claude API (Skills API) | expected | Requires the code execution tool. No network access in the container. Not tested in this release. |
| Agent SDK | expected | Filesystem skills as in Claude Code. Not tested in this release. |

Frontmatter uses only the portable keys (`name`, `description`, `license`,
`metadata`). The only script (`openstack-operational-decisions/scripts/weighted_score.py`)
needs Python 3 and no packages; the skill works without it.

## Repository layout

```text
skills/<name>/SKILL.md          skill instructions (< 500 lines each)
skills/<name>/references/       detailed reference loaded on demand
shared/                         canonical shared references (copied into each skill)
docs/knowledge-map.md           what the book contains, and what each skill draws from
docs/design.md                  why these skills, and how they are built
docs/installation.md            installation per surface
docs/evaluation-report.md       what was tested, how, and the results
evals/scenarios/                behavioural test scenarios (24)
evals/grader-prompt.md          rubric instructions for the model grader
evals/results/                  raw outputs and grades of recorded runs
tools/validate_skills.py        structural checks (run in CI)
tools/sync_shared.py            copy shared/ into every skill
tools/run_behavioral.py         behavioural evaluation via the Claude Code CLI
tools/package_skills.py         zip skills for claude.ai / API upload
.claude-plugin/marketplace.json Claude Code plugin marketplace manifest
```

## Contributing

Operational experience is the most valuable contribution: a scenario where a
skill gave unsafe or unhelpful advice, a missing decision point, a technical
note that has aged. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Relationship to the book and licence

The skills paraphrase and restructure the book's method; they do not
reproduce its text. The book itself remains under CC BY-NC-ND 4.0 in its own
repository. This repository is licensed under Apache-2.0 (see
[LICENSE](LICENSE) and [NOTICE](NOTICE)).

Cite the book as: Zaouam, S. (2026). *OpenStack, the Day After Tomorrow:
Operating Mission-Critical OpenStack Platforms* (v1.2).
https://github.com/soufian-zaouam/openstack-the-day-after-tomorrow

*OpenStack is a registered trademark of the OpenInfra Foundation. This project
is independent of, and not endorsed by, the OpenInfra Foundation or Anthropic.*
