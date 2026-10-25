# Minimum change decision record

Structure from [Book: App. C]. Keep it proportional to consequence: a
low-risk routine operation needs no formal record; a high-impact production
change should leave enough for another engineer to understand the reasoning
later. Leave a field as `unknown` rather than inventing content.

```markdown
- **Change / decision:**
- **Date:**
- **Decision owner:**
- **Capability owner:**
- **Technical assessor:**

**Objective** — What business or operational outcome is required?

**Current state** — What is known about the platform before the change?

**Evidence** — What observations support the decision?

**Uncertainty** — What remains unknown?

**Options considered** — What alternatives were evaluated?

**Trade-offs** — What risk, complexity and control implications does each option introduce?

**Selected option** — What was chosen and why? Which options were rejected and why?

**Recovery** — How will the organization return to a trusted state if the change fails?

**Stop conditions** — Under what conditions will execution stop?

**Verification** — What evidence will establish that the intended outcome was achieved?

**Follow-up** — What should be documented, measured, simplified or revisited after the change?
```

Notes:
- Rejected options can be as valuable as the selected one: if an upgrade was
  postponed because recovery was insufficient, that reason must stay visible so
  the next team does not read it as inertia [Book: Ch. 13].
- If the change accepts a risk, record a review condition: risk acceptance
  should expire [Book: Ch. 13].
