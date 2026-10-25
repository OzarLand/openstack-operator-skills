---
name: openstack-maintenance-planning
description: Plans OpenStack compute host maintenance and patching campaigns - OS, kernel, hypervisor, libvirt or QEMU updates, reboots, hardware work - by classifying workloads by business criticality and migratability, sizing spare capacity per failure domain, choosing live migration, cold migration or coordinated restart per workload, sequencing hosts, and defining stop conditions and verification. Use when someone needs to drain, patch or reboot compute nodes, run a security patching campaign, schedule a maintenance window, or plan VM migrations off hosts - even if they only ask how to move VMs off a node or how many hosts they can patch at once.
license: Apache-2.0
metadata:
  source: "OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 20, 9, 10, 17, 13"
  version: "0.1.0"
---

# OpenStack maintenance planning

Build a maintenance or patching plan that meets the requirement within the
capacity that actually exists and the business criticality that actually
applies. The book's rule: security requirements define *what* must be
achieved; platform capacity and business criticality determine *how safely*
it can be achieved [Book: Ch. 20].

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory. Principles:
[references/operating-principles.md](references/operating-principles.md).
Mechanics of host maintenance operations:
[references/host-maintenance-mechanics.md](references/host-maintenance-mechanics.md).

## When to use

- Patching or rebooting many compute hosts (OS, kernel, firmware, libvirt/QEMU).
- Draining hosts for hardware work or decommissioning.
- Deciding, per workload, between live migration, cold migration and restart.
- Estimating whether spare capacity allows the campaign.

Not for: a host that has already **failed** (that is evacuation — use
`openstack-incident-analysis`), OpenStack release upgrades
(`openstack-change-review`), or control-plane maintenance beyond host draining.

## Workflow

```
Maintenance plan:
- [ ] 1. Requirement and deadline (fixed) vs execution strategy (to design)
- [ ] 2. Scope: hosts, failure domains, versions, storage model
- [ ] 3. Workload classes: business criticality (from consumers) x technical migratability
- [ ] 4. Strategy per class: live migrate / cold migrate / coordinated restart / exception
- [ ] 5. Capacity check per failure domain
- [ ] 6. Sequencing: landing zone, version direction, batches
- [ ] 7. Per-host procedure with verification
- [ ] 8. Boundaries and stop conditions
- [ ] 9. Decision rights and consumer communication
- [ ] 10. Campaign verification and follow-up
```

### 1. Requirement vs strategy

Separate what is mandatory (patch X on all hosts by date Y, from a security or
compliance requirement) from how it is executed. The requirement does not
change; the execution strategy reflects the real operating environment
[Book: Ch. 20]. If the deadline cannot be met safely, say so and describe the
exposure trade-off for the accountable owner; do not silently compress safety.

### 2. Scope

Collect, or list as gaps: number of hosts; failure domains (rack, availability
zone, aggregate, power); hypervisor, libvirt and QEMU versions; CPU models;
instance storage (shared vs local — local disks need block migration, which
loads network and storage) [Book: Ch. 20]. Never invent counts or versions.

### 3. Workload classes

Nova sees instances, not business processes; it cannot tell which workloads
tolerate a restart [Book: Ch. 20]. Two independent inputs are needed:

- **Business criticality, from the consuming teams**: criticality, acceptable
  downtime, recovery expectations, deadlines. Use the shared table in
  [references/criticality-table-template.md](references/criticality-table-template.md).
  If it does not exist, collecting it is the first deliverable of the plan
  [Book: Ch. 20].
- **Technical migratability**, which is release-dependent — check the running
  release, not a fixed list (details in
  [references/host-maintenance-mechanics.md](references/host-maintenance-mechanics.md)):
  - not live-migratable: flavor-based PCI passthrough and `direct-physical`
    ports; memory-intensive workloads whose pages change faster than they copy
    (unless auto-converge or post-copy is enabled). For those, a restart or
    cold migration is a technical necessity, not a business choice
    [Book: Ch. 20];
  - live-migratable with conditions: SR-IOV `direct` ports (since Train; the
    port is unplugged and re-plugged, so the guest loses that interface
    briefly — ask the owner whether that is acceptable), vGPU (since 2024.1 with
    sufficiently recent libvirt, QEMU and kernel), pinned/NUMA instances (since
    Train) `[Addition]`, correcting the book on SR-IOV [Book: Ch. 20, Ch. 15].

### 4. Strategy per class

| Class | Default strategy | Conditions |
|---|---|---|
| Critical, migratable | Live migration within capacity | destination compatible; capacity available in the failure domain |
| Tolerates restart (agreed by owner) | Coordinated restart or cold migration | owner-agreed window; restart in place only if host reboot downtime is acceptable |
| SR-IOV `direct` port, owner accepts a brief interface loss | Live migration (port unplugged and re-plugged) `[Addition]` | release since Train; NIC and driver support verified |
| Not live-migratable | Cold migration or coordinated restart | consumer informed; downtime agreed |
| Cannot be touched before deadline | Exception | owner, compensating controls, review date [Book: Ch. 17] |

These are defaults, not rules: present alternatives where the conditions differ.
Business criticality, not the technical operation, decides which workloads
need live migration [Book: Ch. 9].

### 5. Capacity

Check whether spare capacity allows the plan: how many hosts can be
unavailable at once, how many instances can be in flight, how much spare
capacity safe patching requires [Book: Ch. 20]. Capacity is per failure
domain: a platform that can afford one host down per rack or per availability
zone needs the spare capacity of one host in **each** of those domains, not
one host overall [Book: Ch. 20]. Show the calculation with the user's numbers,
or the formula with placeholders if numbers are missing. Do not invent margins.

If capacity is insufficient for live-migrating everything, that is a
constraint on meeting the requirement without disruption — the answer is a
differentiated strategy and an explicit decision, not a forced migration the
platform cannot absorb [Book: Ch. 20].

### 6. Sequencing

- Migration from newer libvirt/QEMU to older is not supported: once some hosts
  are patched, instances can move onto them but not back; the order of patching
  decides where instances can go [Book: Ch. 20]. When the patch changes
  libvirt/QEMU, one way to use this is to patch an initial empty batch as a
  **landing zone** and move instances only toward patched hosts `[Addition]`;
  for a kernel-only patch the constraint does not apply.
- CPU model compatibility between source and destination limits targets.
- Respect failure domains: do not drain several hosts of the same domain at
  once beyond its spare capacity.
- Do not stack changes: keep the campaign separate from other changes in the
  same window [Book: Ch. 9].

### 7. Per-host procedure

1. Confirm the host's instances are classified and owners informed.
2. Disable `nova-compute` on the host (with a reason) so the scheduler places
   nothing new on it — state-changing.
3. Move instances according to their class; verify each move (instance active
   on destination, reachable, performance acceptable).
4. Verify the host is empty, or that only agreed-restart instances remain.
   If some remain, record them with their power state and read
   `resume_guests_state_on_host_boot` on the host (read-only): with the Nova
   default (`False`), guests are **not** restarted when the host boots and come
   back `SHUTOFF` `[Addition]`.
5. Patch and reboot; verify the host is healthy, compute service and agents up.
6. For each agreed-restart instance, check its status and power state; start
   those the owner expects running (state-changing, approval per policy) and
   have the owner confirm the application is reachable `[Addition]`.
7. Optionally validate with a test instance `[Addition]`.
8. Re-enable the compute service.

A patch to the hypervisor or QEMU protects only instances migrated or
restarted since; instances still running on the old binary are **not**
patched [Book: Ch. 17, Ch. 20]. Track this per instance.

**Never use evacuation for maintenance.** Evacuation is for a host that has
failed, and must never be used on a host that may still be running its
instances [Book: Ch. 10, Ch. 20].

### 8. Boundaries and stop conditions

Define before the campaign [Book: Ch. 9, Ch. 19]: maximum hosts per failure
domain at once, maximum concurrent migrations (from the platform's own
baselines), and stop conditions — migrations failing or slowing beyond the
baseline, a destination behaving differently from expected, critical workload
performance crossing the agreed threshold, capacity falling below the reserve,
monitoring blind spots, the decision authority unavailable. Resuming after a
stop is a new decision [Book: Ch. 19].

### 9. Decision rights and communication

The infrastructure team cannot decide alone which workloads may be disrupted:
put the decision for each workload with the people who know what it does
[Book: Ch. 20, Ch. 13]. Name who approves restarts, who accepts deadline
exceptions, and who communicates the schedule to consumers.

### 10. Campaign verification and follow-up

Done means: every host patched and verified, every instance either migrated or
restarted since the patch (or listed as an exception with owner), every
agreed-restart instance confirmed running again (or intentionally left off by
its owner), no instance left on an unpatched binary unknowingly, capabilities
healthy. Follow-up
[Book: Ch. 20]: keep the criticality table current (as a shared document or as
metadata on instances and projects) as an input to capacity planning; add
maintenance scenarios to capacity planning; if every campaign consumes
disproportionate capacity, put it on the platform roadmap as a lifecycle
problem.

## Output format

```markdown
## Requirement and constraints
Mandatory requirement · deadline · known constraints · exposure if delayed

## Scope
Hosts · failure domains · versions · storage model · gaps

## Workload classes
| Class | How identified | Strategy | Downtime | Owner sign-off needed |

## Capacity check
Per failure domain: spare capacity vs required · conclusion · assumptions

## Sequencing
Landing zone · batch order · version direction · failure-domain rules

## Per-host procedure
Numbered steps, each labelled read-only or state-changing, with verification

## Boundaries and stop conditions
## Decision rights and communication
## Campaign completion criteria
## Exceptions
| Workload | Reason | Compensating control | Owner | Review date |
## Gaps and questions
## Follow-up
```

End with the decision-support line from
[references/evidence-and-safety.md](references/evidence-and-safety.md).

## Limits and safety

- No universal numbers: concurrency, batch size and spare-capacity margins
  come from the platform's own baselines and the user's data.
- Does not decide business criticality: it asks consumers or lists it as a gap.
- Migration constraints vary by release, hypervisor and backend; verify against
  the Nova live-migration documentation for the running release.
- Produces a plan, not an execution. Disabling services, migrations, restarts
  and reboots are state-changing and need approval under the change process.
- Does not claim any host or instance was patched without evidence.

## Related skills

- `openstack-change-review` — to review the finished plan as a change.
- `openstack-automation-review` — if the campaign will be executed by automation.
- `openstack-incident-analysis` — if a host fails during the campaign.
