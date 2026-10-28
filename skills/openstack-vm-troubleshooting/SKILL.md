---
name: openstack-vm-troubleshooting
description: Diagnoses problems with individual OpenStack instances, volumes and ports - stuck states (BUILD, deleting, resize, snapshot), boot and scheduling failures (No valid host, Exceeded maximum number of retries, boot from volume), instances with no IP, no metadata or unreachable, port binding failures, security groups, MTU, volumes stuck attaching, detaching or deleting, stale attachments, instances shut off by the OOM killer, and compute-host events seen from the instances - by locating the failing step of the operation, discriminating causes with read-only checks, and gating each fix by its risk and its validation status. Use when an operator reports that one or several instances, volumes or ports misbehave, asks how to read the Nova, Neutron, Cinder or libvirt logs for one resource, or asks whether a reset-state, delete, heal or cleanup command is safe to run.
license: Apache-2.0
metadata:
  source: "OzarLand openstack-vm-runbooks (lab evidence on OpenStack 2026.1 with Kolla-Ansible), with the method of OpenStack, the Day After Tomorrow (Soufian Zaouam), v1.2 - Ch. 5, 8, 9, 10"
  version: "0.2.0"
---

# OpenStack VM troubleshooting

Take one misbehaving instance, volume or port from its symptom to a verified
fix, without making its records drift further from reality. The method:
find the step of the operation that failed, read the evidence where that step
ran, tell the possible causes apart with read-only checks, and only then pick
the least invasive fix whose risk and validation status the operator accepts.

Read [references/evidence-and-safety.md](references/evidence-and-safety.md)
before the first response; its rules are mandatory, in particular rule 12 on
validation status. Principles:
[references/operating-principles.md](references/operating-principles.md).

## When to use

- An instance stuck in a state, in `ERROR`, `SHUTOFF` on its own, unreachable,
  without an address or metadata, or failing to build, resize, migrate,
  snapshot or delete.
- A volume stuck in `creating`, `attaching`, `detaching`, `deleting`, an
  attachment left behind, an extend the guest does not see.
- "Is it safe to run `reset-state` / `server delete` / `placement heal` on this?"
- Reading the logs for one request, instance, port or volume.

Not for, hand over instead:

| Situation | Use |
|---|---|
| Failures are platform-wide (every build or API call fails, `MessagingTimeout` everywhere, several computes down), or RabbitMQ, Galera, HAProxy or Keystone are implicated | `openstack-incident-analysis` |
| A compute host is unreachable and someone proposes to evacuate | `openstack-incident-analysis` (fence first) |
| Planned work on a host (patching, reboot, drain) | `openstack-maintenance-planning` |
| The fix is a configuration change through Kolla-Ansible | `openstack-kolla-ansible-operations`, then `openstack-change-review` |

If the scope is unclear, the first question is whether **other** instances
or volumes, on other hosts and in other projects, show the same symptom. One
resource is this skill; everything at once is an incident.

## What to ask for first

Ask only for what the next step needs. A good first set:

1. The resource ID and what was being done (create, delete, resize, migrate,
   attach, extend, snapshot), and when.
2. `openstack server show <id>` (or `volume show`, `port show`) as the user
   sees it: `status`, `OS-EXT-STS:task_state`, `OS-EXT-STS:power_state`,
   `fault`, host. These fields are read-only and separate the record from the
   symptom.
3. Scope: one resource, one compute, one project, or more.
4. Release, deployment method (Kolla-Ansible or other), network backend
   (ML2/OVS or OVN) and storage backend, if the answer depends on them.

Ask for credentials to be redacted from anything pasted (rule 11).

## Workflow

```
VM troubleshooting:
- [ ] 1. Resource, operation, current record (status, task_state, power_state, fault)
- [ ] 2. Scope: one resource, one host, or platform-wide (hand over if wide)
- [ ] 3. Path of the operation; the step that failed and the host where it ran
- [ ] 4. Matching symptom in the router; read-only checks to discriminate causes
- [ ] 5. Record versus reality: what Nova, Neutron, Cinder, Placement and the hypervisor each say
- [ ] 6. Fix options, least invasive first, with risk class and validation status
- [ ] 7. Verification of the resource and of what it depends on
```

### 1–2. Record and scope

Separate what the user observed (it is unreachable) from the record (Nova says
`ACTIVE`) and from the operation's own error (`fault`). A record that says
`ACTIVE` while the instance is frozen or unreachable is common: Nova reports
what it last knew [Book: Ch. 10]. Treat each as a separate piece of evidence.

### 3. Path of the operation

An API-level error is often a summary. "No valid host was found" and
"Exceeded maximum number of retries" name the scheduler's outcome; the real
error is in the logs of the computes that tried. "Binding failed for port" is
a Neutron answer to a Nova request. Follow the operation through the services
it traverses [Book: Ch. 5] and find the request ID (`req-...`) to follow it
across logs [Book: Ch. 8]; how is in
[references/logs-and-tracing.md](references/logs-and-tracing.md).

### 4. Symptom router

Pick the closest row, then work through that section's checks before
considering any fix.

| The operator sees | Reference, section |
|---|---|
| `BUILD`, then `ERROR` after about 5 minutes; port `DOWN` | [instance-lifecycle.md](references/instance-lifecycle.md), *Stuck in BUILD waiting for vif-plugged* |
| `ERROR` with "Exceeded maximum number of retries" | [scheduling-and-boot.md](references/scheduling-and-boot.md), *Exceeded maximum number of retries* |
| "No valid host was found" while computes have room | [scheduling-and-boot.md](references/scheduling-and-boot.md), *No valid host with free capacity* |
| "Flavor's disk is too small for requested image" | [scheduling-and-boot.md](references/scheduling-and-boot.md), *Image larger than the flavor disk* |
| Boot from volume ends in `ERROR` or boots nothing | [scheduling-and-boot.md](references/scheduling-and-boot.md), *Boot from volume fails* |
| A compute shows `disabled` or `down`; nova-compute refuses to start after a rename or reinstall | [scheduling-and-boot.md](references/scheduling-and-boot.md), *Compute disabled, forced down, renamed* |
| Placement usage does not match the instances; resource provider delete returns 409 | [scheduling-and-boot.md](references/scheduling-and-boot.md), *Placement allocations out of sync* |
| Stuck in `deleting`, or `ERROR` after a delete | [instance-lifecycle.md](references/instance-lifecycle.md), *Stuck in deleting* |
| `VERIFY_RESIZE` forever, stuck in `RESIZE`, `ERROR` after resize | [instance-lifecycle.md](references/instance-lifecycle.md), *Resize or cold migration not finished* |
| Snapshot stays in `image_uploading` | [instance-lifecycle.md](references/instance-lifecycle.md), *Snapshot never finishes* |
| `SHUTOFF` by itself, "shutdown by itself" in Nova | [instance-lifecycle.md](references/instance-lifecycle.md), *Shut off by the host OOM killer* |
| Instance frozen while `ACTIVE`, compute disk full | [instance-lifecycle.md](references/instance-lifecycle.md), *Compute disk full* |
| Guest does not boot (kernel panic, fstab) or locked out | [instance-lifecycle.md](references/instance-lifecycle.md), *Rescue mode* |
| Console does not open or says "invalid or has expired" | [instance-lifecycle.md](references/instance-lifecycle.md), *Console not available* |
| Many stale records: BUILD/ERROR/deleting leftovers, orphan ports, phantom allocations | [instance-lifecycle.md](references/instance-lifecycle.md), *Stale records* |
| `ACTIVE` but never got an IP address | [instance-networking.md](references/instance-networking.md), *No IP address* |
| Address, but no SSH key, default hostname | [instance-networking.md](references/instance-networking.md), *No metadata* |
| Reachable from inside its network, not from outside | [instance-networking.md](references/instance-networking.md), *Unreachable from outside* |
| "Binding failed for port" | [instance-networking.md](references/instance-networking.md), *Port binding failed* |
| A security group rule has no effect | [instance-networking.md](references/instance-networking.md), *Security group rules not applied* |
| Every instance on one compute lost the network, Nova still says `ACTIVE` | [instance-networking.md](references/instance-networking.md), *ovs-vswitchd down* |
| Ping works, large transfers stall | [instance-networking.md](references/instance-networking.md), *Tunnel MTU mismatch* |
| L3 agent dead, router not moved | [instance-networking.md](references/instance-networking.md), *Router on a dead L3 agent* |
| Volume stuck in `creating` or `error` after create | [volumes.md](references/volumes.md), *Stuck in creating* |
| Volume stuck in `attaching`, `reserved` or `detaching` | [volumes.md](references/volumes.md), *Stuck attaching or detaching* |
| Volume `in-use` for an instance that is gone or was evacuated | [volumes.md](references/volumes.md), *Stale attachment* |
| Volume stuck in `deleting` or `error_deleting` | [volumes.md](references/volumes.md), *Stuck in deleting* |
| Volume extended, guest still sees the old size | [volumes.md](references/volumes.md), *Extend while attached* |
| nova-compute `down`, instances still running, or SSH refused | [compute-host-events.md](references/compute-host-events.md), *nova-compute down, host alive* |
| After a compute reboot, instances `SHUTOFF` or without network | [compute-host-events.md](references/compute-host-events.md), *After a compute reboot* |
| Need to restart `nova_libvirt` or the OVS agent on a compute | [compute-host-events.md](references/compute-host-events.md), *Restarts that keep instances running* |
| Live migration runs long, then is aborted | [compute-host-events.md](references/compute-host-events.md), *Live migration never completes* |
| CPU steal on pinned instances | [compute-host-events.md](references/compute-host-events.md), *CPU steal on pinned instances* |
| One compute's logs do not line up in time | [compute-host-events.md](references/compute-host-events.md), *Clock skew* |

No row fits: follow the operation's path (step 3) and the logs; say that no
documented pattern matched, so every conclusion is a hypothesis.

### 5. Record versus reality

Before any fix, compare what each layer says about the same resource: Nova
(`server show`), the hypervisor (`virsh list --all` on the compute, in the
`nova_libvirt` container on Kolla-Ansible), Neutron (port `status`,
`binding:host_id`, `binding:vif_type`), Cinder (volume status and
attachments), Placement (allocations for the instance). Repairs fail when they
correct one record to match another record instead of reality
[Book: Ch. 10]. The tools that change records, and what each changes, are
listed in [references/instance-lifecycle.md](references/instance-lifecycle.md),
*Stale records*.

### 6. Fix options

For each option give: the cause it addresses, risk class, preconditions, what
is lost or affected, the undo if one exists, verification, the approver, and
its validation tag with the scope the tag states. Order:

1. No change: wait, or retry the user operation, when the evidence says a
   transient cause has cleared.
2. Fix the cause (start the dead agent, free the disk, correct the flavor or
   image), then retry the operation.
3. Change records with the project's own tools (`reset-state`, attachment
   delete, `placement heal_allocations`), once reality is established.
4. Direct database edits: only with a backup, one record at a time, verified
   after, approved as a change [Book: Ch. 10]. Never the first option.

Rules that hold whatever the symptom:

- **`reset-state` changes a record, not the resource.** Setting an instance
  or volume back to `active`/`available` does not detach, stop, free or clean
  anything; use it only after the real state is known, to let a following
  operation run. [Addition]
- **Find the real error before retrying.** Retrying a build that failed on
  every compute repeats the failure and fills logs and records. [Addition]
- **A restart is a change.** Restarting `nova-compute`, `nova_libvirt` or the
  OVS agent kept instances running on the lab (see
  [references/compute-host-events.md](references/compute-host-events.md) for
  the exact scope), but it is still state-changing, and other agents (DHCP,
  L3, metadata, OVN controllers) have their own effects.
- **Deleting is not cleaning up.** Before deleting an instance, volume,
  port or allocation that looks orphaned, establish who owns it and whether
  it holds data. Deletion is irreversible.
- **A host that looks dead is not proof.** Evacuation needs the host fenced
  first [Book: Ch. 10]; hand over to `openstack-incident-analysis`.
- **One host first.** When the same fix applies to several computes, apply it
  to one, verify with a test operation there, then continue. [Addition]

### 7. Verification

The fix is verified when every layer agrees and the user-level capability is
back: the instance reaches the expected state and is reachable or usable;
the volume is attached once to the right instance, or detached everywhere;
Placement allocations match the instance's host; nothing new appears in the
logs at `ERROR`. When the symptom hit new resources (no IP, no metadata,
failed builds or attaches), verify with a **new** one created after the fix,
not only with the one that failed; when a resource moved or was detached,
check that nothing of it remains on the old host (domain, iSCSI session,
port binding). Each reference section lists its own checks. [Addition]

## Output format

Scale the answer to the problem: one instance with a documented cause needs a
short answer. Keep the structure:

```markdown
## Resource and scope
Resource, operation, record (status / task_state / power_state / fault), scope, versions if relevant

## Evidence
| # | Class | Statement | Source |

## Where it failed
The step of the operation and the host where it ran, or what is needed to find it

## Likely causes
| Cause | Supports | Would rule it out | Read-only check |

## Next checks (read-only)
1. Command — where it runs — what each result means

## Fix options (not yet authorized)
For each: cause · risk class · preconditions · what is lost · undo · verification · approver · validation status and its scope

## Verification
What each layer must show afterwards

## Gaps
```

End any answer containing state-changing steps with the decision-support line
from [references/evidence-and-safety.md](references/evidence-and-safety.md).

## Limits and safety

- Knows only what the user shows or session tools return; never claims to have
  inspected a platform.
- Lab evidence in the references comes from OpenStack 2026.1 deployed with
  Kolla-Ansible, mostly ML2/OVS with local instance disks; much of it says
  which steps were not run. Container names and log paths are Kolla-Ansible
  ones unless stated. Other releases, deployment tools, OVN, Ceph and
  production scale need their own verification.
- Destructive steps (deleting resources or attachments, database edits,
  removing allocations) require a named human owner; the skill never
  authorizes them.

## Related skills

- `openstack-incident-analysis`: platform-wide symptoms, shared components, host failure and evacuation.
- `openstack-maintenance-planning`: moving instances off a host for planned work.
- `openstack-runbook-authoring`: turning a resolved case into a runbook.
- `openstack-kolla-ansible-operations`: configuration changes and container operations on Kolla-Ansible.
