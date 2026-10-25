# Control spectrum and assessment worksheet

From [Book: Ch. 5] and [Book: App. B].

## Contents

- Levels and criteria
- Evidence confidence
- What common claims must mean
- Assessment worksheet (per critical capability)

## Levels and criteria

The author's criteria, written so that two engineers rating the same
capability arrive at the same answer [Book: Ch. 5].

| Level | Criterion |
|---|---|
| **Unknown** | Nobody can say with confidence which services and dependencies the capability involves, or who owns them. |
| **Visible** | Dependencies are mapped and the main signals exist, but their meaning is not established: an alert fires without anyone knowing whether it matters. |
| **Understood** | The organization can explain normal and degraded behaviour, and at least two people can diagnose a failure of the capability. |
| **Controlled** | Changes to the capability follow a known path with stop conditions and verification; ownership and decision rights are explicit. |
| **Recoverable** | Recovery has been demonstrated, by someone other than the author of the procedure, within a time the business finds acceptable. |
| **Sustainable** | Recovery and change have been demonstrated more than once, over time and after team changes, and the knowledge survives without a specific person. |

A capability sits at the highest level whose criterion **and all lower
criteria** are met with evidence (this combining rule is an `[Addition]`).

## Evidence confidence

[Book: Ch. 5] The book gives pairwise comparisons (observed in production is
stronger than documented but never exercised; demonstrated is stronger than an
untested procedure; independently reproduced is stronger than one expert's
statement). The single ordering below is this repository's synthesis of those
pairs `[Addition]`. From stronger to weaker:

1. Observed in production.
2. Demonstrated in a controlled environment.
3. Independently reproduced by someone other than the original expert.
4. Documented but never exercised.
5. Statement from a single expert.

The exact scale matters less than making confidence visible so assumptions
are not silently treated as facts.

## What common claims must mean

[Book: Ch. 5]
- "RabbitMQ can be recovered" → the procedure is documented, understood and
  has been demonstrated.
- "We have rollback" → there is a credible path and a known-good state to
  return to.
- "We have backups" → they have been restored into a test environment and
  compared with the running platform; for service databases, all at one point
  in time and reconciled [Book: Ch. 10].

## Assessment worksheet

[Book: App. B] One per critical capability. If the answer is "we think so",
the control level is not yet established.

| Question | Evidence |
|---|---|
| What business capability depends on it? | |
| Which OpenStack services participate? | |
| Which external dependencies participate? | |
| Who owns the capability? | |
| Who operates it? | |
| Who can diagnose it? | |
| Who can recover it? | |
| Is recovery demonstrated? When, by whom? | |
| What signals indicate degradation? | |
| What changes commonly affect it? | |
| What customizations affect it? | |
| What upstream divergence exists? | |
| What single-expert dependency exists? | |
| What is the current control level (Unknown → Sustainable)? | |
| What is the most important control gap? | |
| What should be done now? | |
| What can wait, and until when? | |
