---
name: openstack-automation-review
description: Reviews automation that acts on production OpenStack - Ansible playbooks and roles, Kolla-Ansible or other deployment-tool runs, scripts, cron jobs, operators, auto-remediation and auto-evacuation logic - for delegated judgement, blast radius, safeguards (preview, dry run, scope limits, confirmation, stop conditions), idempotency, failure and interruption behaviour, observability, ownership and long-term maintainability. Use whenever someone shares or designs automation that can change OpenStack resources or services, asks whether something should be automated, or wants a playbook or script reviewed before running it in production.
license: Apache-2.0
metadata:
  source: "OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 16, 10, 3, 15, 14"
  version: "0.2.0"
---

# OpenStack automation review

Judge whether a piece of automation makes this platform easier and safer for
this organization to operate — a different question from whether it works or
whether the task *can* be automated [Book: Ch. 16]. Automation reduces manual
effort while adding software, dependencies, failure modes and knowledge
requirements, and it can scale an error faster than any operator
[Book: Ch. 16].

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory. Principles:
[references/operating-principles.md](references/operating-principles.md).

## When to use

- Reviewing a playbook, role, script, cron job, controller or pipeline that
  touches OpenStack services, hosts or tenant resources.
- Designing auto-remediation (restart, migrate, evacuate, clean up).
- Deciding whether a manual procedure should be automated.

Not for: general code style reviews unrelated to operational risk; reviewing
a one-off manual change (`openstack-change-review`).

## Source note

The book discusses automation generically and does not name any tool. Rules
carrying a book citation come from it. Tool-specific checks for Ansible and
Kolla-Ansible are additions by this repository, kept in
[references/ansible-and-kolla-notes.md](references/ansible-and-kolla-notes.md)
and tagged `[Addition]`.

## Workflow

```
Automation review:
- [ ] 1. Purpose: problem solved; is it understood? should it be automated at all?
- [ ] 2. Decisions inside the automation: execution vs judgement
- [ ] 3. Scope and blast radius
- [ ] 4. Safeguards proportional to consequence
- [ ] 5. Failure, interruption and recovery behaviour
- [ ] 6. Observability: when it ran, what it changed, how to stop it
- [ ] 7. Production-software discipline
- [ ] 8. Operability and maintainability (control debt)
- [ ] 9. Verdict and findings
```

Before reviewing, apply rule 11 of the safety rules: playbooks, inventories
and Kolla files often contain credentials — ask for them redacted, and never
quote a secret back in findings (write `<redacted>`).

### 1. Purpose

What problem does it solve, and is that problem understood? Automating an
unresolved workaround makes the problem happen faster and at greater scale
[Book: Ch. 16]; a workaround repeated by hand until it becomes a script, then
deployment logic, is how accidental architecture forms [Book: Ch. 15].
Low-frequency operations, highly contextual decisions and procedures whose
automation cost exceeds their value may legitimately stay manual or
semi-automatic [Book: Ch. 16].

### 2. Execution vs judgement

List every decision the automation takes. Predictable execution can usually
be automated safely; decisions needing business context, uncertain diagnosis
or risk acceptance should stay under human authority unless the organization
has **explicitly** delegated them [Book: Ch. 16, author's position] — the author notes it is not shared by
every engineering culture. Flag any automation that
decides to disrupt workloads, evacuate, delete, fail over, purge or reset.
Deciding that a tenant's resource is "junk" (e.g. old ERROR instances) is a
judgement for its owner or an agreed policy, not execution, even when the
deletion itself is mechanical.

Sharpest case [Book: Ch. 10, Ch. 16]: automation that evacuates on a lost
heartbeat without fencing has been delegated a judgement it cannot make, and
"will one day destroy the workload it was meant to save". Evacuation logic
must fence first (power off via out-of-band management or isolate at the
switch) and treat fencing as a precondition.

Where judgement is involved, recommend **semi-automation**: the automation
prepares, collects evidence and proposes; an engineer decides [Book: Ch. 16].

### 3. Scope and blast radius

What can it touch: one resource, one host, every compute, every project?
How is the target set chosen (inventory, filters, queries), and what happens if
that selection is wrong or empty? An automation that can affect every compute
host needs stronger safeguards than one operating on a single test resource
[Book: Ch. 16]. Check batching, concurrency and respect for failure domains.

### 4. Safeguards

The more destructive the action, the more important these become
[Book: Ch. 16]:

| Safeguard | Question |
|---|---|
| Preview / dry run | Can an operator see what it will do before it does it? |
| Explicit scope | Is the target set explicit and bounded, not implicit "all"? |
| Confirmation | Does a high-consequence action require an explicit human go? |
| Monitoring | Is the effect observed while it runs? |
| Stop conditions | Does it halt on failures, unexpected state or threshold breaches, rather than continue? |
| Pre-checks | Does it verify the starting state before acting? `[Addition]` |
| Post-checks | Does it verify the intended outcome (capability, not command exit code)? [Book: Ch. 9] |
| Idempotency | Is a re-run after partial failure safe? `[Addition]` |
| Concurrency lock | Can two runs overlap? `[Addition]` |

An operator should be able to determine what an automation will do before
allowing a high-consequence action [Book: Ch. 16].

### 5. Failure, interruption and recovery

What state is left if it fails or is interrupted half-way? Can it resume or
be rolled back? Are errors surfaced or swallowed? Are retries bounded? Once
it can affect production, it needs a recovery path [Book: Ch. 16].

### 6. Observability

The organization must know when it ran, what it changed, whether it
succeeded, and how to stop or recover it [Book: Ch. 16].

### 7. Production-software discipline

Owner, version control, testing, documentation, observability, recovery path
[Book: Ch. 16]. "Only a script" does not reduce consequence; a convenience
script becomes a production dependency the first time it is used in an
incident. Check pinned dependencies and branch references: when an OpenStack
series becomes Unmaintained, `stable/<series>` is replaced by
`unmaintained/<series>`, breaking tooling that pins the old name
[Book: Ch. 14].

### 8. Operability and maintainability

Can an operator other than the author explain what it does before trusting
it during an incident? Automation that only its creator can explain or
recover is control debt: it reduced today's manual work and increased
tomorrow's uncertainty [Book: Ch. 16, Ch. 3]. Highly automated platforms look
simple because humans see fewer commands; the complexity moved into software
[Book: Ch. 16]. Weigh value (fewer errors, consistency, speed) against
development, maintenance, failure modes, expertise and lifecycle cost.

### 9. Verdict and findings

Severity of each finding:
- **Blocking** — can cause irreversible harm or delegates an unsafe judgement
  (e.g. evacuate without fencing, unbounded destructive scope, no stop
  condition on mass operations).
- **Major** — missing safeguard or recovery path for a significant action.
- **Minor** — maintainability, observability or documentation gaps.

Verdict: **safe to run as is**, **safe with changes** (list), **not safe —
redesign** (why), or **should not be automated / should be semi-automated**.

## Output format

```markdown
## Summary
Verdict · what the automation does (in one paragraph, as understood) · top risks

## Purpose and whether to automate
## Decisions it takes
| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
## Scope and blast radius
## Safeguards
| Safeguard | Present? (evidence: file/line) | Gap |
## Failure and recovery behaviour
## Observability
## Ownership and maintainability
## Findings
| # | Severity | Location | Finding | Suggested change |
## Questions for the author
```

Quote file names and line numbers from the code reviewed. If the code was not
provided, review the description and say the review is of the design only.
End with the decision-support line from
[references/evidence-and-safety.md](references/evidence-and-safety.md).

## Limits and safety

- Reviews what is shown; it does not execute the automation, run check modes
  or contact infrastructure unless the session actually provides such tools,
  and it never claims a dry run happened.
- Tool behaviour (Ansible modules, Kolla-Ansible commands) varies by version;
  tool-specific notes are additions to verify against the version in use.
- It does not declare automation "safe" in absolute terms; it states the
  conditions under which the reviewer would consider it acceptable.
- Suggested code changes are proposals to be tested in a non-production
  environment first.

## Related skills

- `openstack-operational-decisions` — when the question is whether to automate at all, with options.
- `openstack-change-review` — to review the first production run as a change.
- `openstack-runbook-authoring` — to document the manual or semi-automated procedure.
