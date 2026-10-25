# Restoration playbook (when control is already lost)

From [Book: Ch. 7], with links to [Book: Ch. 9] and [Book: Ch. 10].

## Contents

- First principle: restraint
- The sequence
- First thirty days
- Guardrails
- Exit criteria: "control restored"
- Exception: when transformation is the stabilization

## First principle: restraint

The first mistake is usually to start transforming the platform: transformation
introduces uncertainty, and a platform that is hard to understand does not
become safer because more of it changes. During restoration, significant
production changes carry a stronger burden of proof, and new complexity is
avoided unless it directly reduces immediate risk. Keep emergency containment
separate from structural remediation.

## The sequence

| Stage | Purpose |
|---|---|
| **Discover** | Establish what is known and unknown: capabilities, dependencies, owners, experts, vendors, critical workloads, recovery methods. |
| **Protect** | Stop making it worse: temporary guardrails, no uncontrolled production changes, protect critical capabilities. |
| **Assess** | Where is business exposure highest and control weakest (use the control spectrum). |
| **Stabilize** | Focus on the critical path; restore trusted operating states; remove immediate sources of instability. |
| **Recover knowledge** | Undocumented decisions, hidden dependencies, single-expert knowledge; reconstruct the history needed to operate safely (code, configs, git history, test executions, decision records [Book: Ch. 12]). |
| **Simplify** | Remove unnecessary complexity where the risk reduction justifies the change. |
| **Establish control** | Make ownership, observability, recovery and decision rights explicit. |
| **Evolve** | Only then does major transformation become the primary objective. |

## First thirty days

Practical outputs: current-state map, critical risks, immediate guardrails,
ownership gaps, recovery gaps, control roadmap. The first objective is to make
the situation understandable enough to decide better; improving the platform
comes after.

## Guardrails

In OpenStack terms, concrete guardrails include: a project's quota set to zero
for new instances; a compute service disabled so the scheduler ignores its
host; an API endpoint withdrawn from the load balancer; a change window closed
until a recovery has been rehearsed. Each guardrail needs:

| Field | Content |
|---|---|
| Guardrail | what is restricted |
| Reason | risk it contains |
| Owner | who maintains and removes it |
| Removal condition | evidence that makes it unnecessary |
| Review date | when it is reconsidered regardless |

Without an owner and a removal condition the emergency state becomes permanent
operational debt. All guardrails are state-changing and need approval.

## Exit criteria: "control restored"

Define it explicitly, e.g.: demonstrated recovery for critical capabilities;
ownership gaps closed; critical dependencies visible; recurring incidents
understood; a credible lifecycle plan. Final milestone: the organization
returns to normal change, support, recovery and governance without emergency
improvisation. Stabilization with no exit condition becomes the new
architecture.

## Exception: when transformation is the stabilization

[Book: Ch. 7, Ch. 9] Some platforms are so far behind — unmaintained releases,
unpatched vulnerabilities — that the transformation is the only available
stabilization and waiting is itself the risk. The rule is "do not stack
uncertainty", not "never move". Even then, the sequence applies to everything
around the transformation.
