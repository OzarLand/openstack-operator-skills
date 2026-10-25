# Periodic review, organizational change review and measures

From [Book: App. D], [Book: Ch. 6], [Book: Ch. 12] and [Book: Ch. 17].

## Contents

- Periodic control review questions
- Organizational change review
- Measures by area
- Measures the platform can produce itself
- Rules for measures

## Periodic control review questions

[Book: App. D] The purpose is to find where the organization is becoming less
capable, not to generate another report.

- **Visibility.** Can we explain the important signals? Can we follow critical
  dependencies? Do we know what changed recently? Does every critical signal
  have an owner?
- **Stability.** What are our trusted operating states? Which capabilities are
  repeatedly degraded? Where is capacity limiting safe maintenance? Are we
  protecting existing workloads while changing the platform?
- **Organization.** Which capabilities depend on one person? Can new engineers
  become productive without informal knowledge? Is workload sustainable? Does
  the team retain a shared identity and purpose?
- **Governance.** Who decides during a critical incident? Who accepts business
  risk? Who owns each technical capability? Are significant decisions recorded?
- **Evolution.** How far are we from maintained upstream releases? Which local
  modifications or backports remain? What debt should be removed at the next
  lifecycle event? Is the organization ready for the next transition?
- **Security.** Which advisories affect the running series, and which fixes
  are we carrying locally? Did the last upgrade's policy changes get tested
  against our users and automation? When do our certificates and Fernet keys
  expire, and when were they last rotated? Which security exceptions are open,
  who owns them, and when are they reviewed?

Rhythm should match how fast the underlying risk changes; a major lifecycle
event justifies a deeper review [Book: Ch. 6].

## Organizational change review

[Book: Ch. 12] A major organizational change can have consequences comparable
to an architecture change: the technical state is unchanged but the ability to
operate it is not. Trigger a control review, not a redistribution of tasks.

Review each critical capability against the new team:
- Who can operate Nova? Who can diagnose Neutron? Who can recover the
  messaging layer? Who can perform the next upgrade? Who can make a disruptive
  incident decision? Who owns the business consequence?
- When staffing decreases: which capabilities are critical, which activities
  can be simplified, which work can be automated safely, which changes should
  be postponed — as an explicit risk decision.

For a departing engineer, the book's field passage [Book: Ch. 12] shows what
escapes an organized transfer: the *execution* of upgrades through the
deployment tooling, and the *reasons* behind customizations and workarounds.
Knowledge shows only when someone else performs the work while the expert can
still watch. Test transfer by demonstration: can the successor explain a
dependency, perform a routine operation, investigate a realistic symptom and
describe recovery? A named secondary who never performs real operations only
documents the dependency.

## Measures by area

[Book: Ch. 6]

| Area | Example measures |
|---|---|
| Visibility | critical capabilities covered by meaningful observability; detection time; recurring events still unexplained |
| Stability | incident recurrence; capacity margin; use of controlled degradation; how often recovery requires improvisation |
| Organization | single-expert dependencies; onboarding time; knowledge-transfer coverage; ownership gaps; workload concentration |
| Governance | significant decisions with clear owner, explicit risk acceptance and recorded reasoning |
| Recovery | share of critical capabilities with demonstrated recovery; recovery success and duration; dependencies included in recovery validation |
| Change quality | significant changes with credible recovery, explicit risk, stop conditions, post-change verification |
| Upstream alignment | number of significant local modifications; maintenance status of running series; effort to reconcile local changes per upgrade |

Leading indicators (often more valuable than incident counts): critical
capabilities with only one knowledgeable engineer; recovery procedures not
exercised recently; proportion of recurring events with documented
explanation, mitigation and owner.

## Measures the platform can produce itself

[Book: Ch. 6] Facts that do not depend on anyone's memory:
- hosts with compute service disabled, and why;
- Placement allocations for instances that no longer exist
  (`nova-manage placement audit`, read-only without `--delete`);
- instances in BUILD, ERROR or deleting for more than a day;
- age of the running series vs its status on releases.openstack.org;
- number of locally carried patches in the deployment repository;
- date of the last recovery exercise for each shared component.

## Rules for measures

[Book: Ch. 6]
- Capability, not activity (ticket counts and dashboard counts prove nothing).
- No single score; trends over absolute values.
- Every metric has a decision owner and a linked action, or it is decoration.
- Concentration of capability is measured by demonstration, not declaration.
- A control programme must show improvement in capability, not completed tasks.
