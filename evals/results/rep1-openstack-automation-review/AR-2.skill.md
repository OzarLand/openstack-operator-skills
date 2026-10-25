## Summary

**Verdict: not safe to run on prod as written.** I'd call it "not safe, redesign". Fixing the first three findings below would make it "safe with changes".

This review covers the code you pasted and nothing else. I haven't seen your inventory, the `compute` group, or how you launch the playbook. Nothing has been run or dry-run.

**What it does (Observed, from the YAML):**
- It runs on every host in `compute` at once.
- It updates all packages to the latest version, and keeps going if the update fails.
- It then reboots every host.

**Top risks:**
1. There is no `serial:` batching, so every compute host reboots at the same time.
2. Nothing drains the hosts first, so every running VM loses its host.
3. `ignore_errors: true` on the update means a failed update is followed by a reboot anyway.

## Decisions it takes

| Decision | Execution or judgement | Delegated explicitly? | Recommendation |
|---|---|---|---|
| Reboot all compute hosts, with VMs on them | Judgement. It means disrupting workloads, and Nova can't tell which ones tolerate a restart. | Not visible in the code. | Keep a human decision per workload class. The automation should prepare and execute, not decide. |
| Continue after a failed update | Judgement, and a bad one. | No. | Remove it. |
| Update `*` | Execution, but unbounded: kernel, libvirt, QEMU and whatever else is pending. | Unknown. | Pin the scope to what the change approved. |

## Findings

| # | Severity | Location | Finding | Suggested change |
|---|---|---|---|---|
| 1 | **Blocking** | `hosts: compute` (no `serial`) | The whole fleet is down at once. Capacity per failure domain is ignored, and nothing stops the run after the first problem. | Add `serial: 1`, or a count based on your spare capacity per failure domain. Add `max_fail_percentage: 0` or `any_errors_fatal: true`. |
| 2 | **Blocking** | the `reboot` task | No drain. VMs on the host stop. With Nova's default `resume_guests_state_on_host_boot=False`, they stay `SHUTOFF` after the host returns (verify for your release and deployment). | Before each host, run these (state-changing, per your change process):<br>1. Disable `nova-compute` with a reason.<br>2. Live-migrate or cold-migrate each instance according to its agreed class.<br>3. Check the host is empty, or that only owner-agreed restarts remain.<br>Only then patch and reboot. |
| 3 | **Blocking** | `ignore_errors: true` | A failed or partial update (broken repo, dependency conflict) is followed by a reboot into an inconsistent state, and the run reports success. | Remove it. Let the failure stop the host, and keep the host disabled. |
| 4 | Major | `reboot` task | No post-checks. The default reboot only waits for the host to answer, not for the services to work. | After the reboot, assert that the compute service is up, the Neutron agent is up and libvirt is running. A test instance is optional. Re-enable `nova-compute` only after the checks pass. |
| 5 | Major | whole play | No preview. If any task is changed to `command`/`shell`, `--check` will skip it. | Run `--check --diff` in staging first. Use `--limit` for the first prod host. |
| 6 | Major | `name: '*'` | Libvirt or QEMU updates change which hosts instances can move to. Migrating from newer libvirt/QEMU to older isn't supported. Patching fleet-wide at random breaks that. Also, running VMs keep the old QEMU until they're migrated or restarted. | Patch a first empty batch as a landing zone and move instances only toward patched hosts. Track per instance whether it has been moved or restarted since the patch. |
| 7 | Minor | whole play | There is no lock, no logging of what changed, no `no_log`, and no `reboot_timeout`. I can't see an owner or tests. | Add an owner, put the playbook in version control, set an explicit timeout, and keep run logs. |

## Capacity and sequencing

I can't do the capacity check, because I don't have these:
- host count
- failure domains (rack, AZ, aggregate)
- spare capacity per domain
- instance storage (shared or local)
- CPU models
- the running release

The rule is that each failure domain needs spare capacity for as many hosts as you take down at once. If the numbers don't allow live-migrating everything, the answer is a mix of live migration, cold migration and owner-agreed restarts. Don't force migrations the platform can't absorb.

## Workloads

- Business criticality has to come from the teams that own the workloads. Do you have a shared criticality table?
- Technical migratability depends on your release.
  - Flavor-based PCI passthrough and `direct-physical` ports can't be live-migrated.
  - SR-IOV `direct` ports can be since Train, but the guest briefly loses that interface.
  - vGPU can be since 2024.1 (needs recent libvirt, QEMU and kernel).
- **Never use `evacuate` for this.** It's only for failed, fenced hosts.

## Suggested shape (a proposal to test in staging first)

For each host, serially:
1. Pre-check (read-only): cluster health, spare capacity, service state.
2. Disable `nova-compute` (state-changing).
3. Drain by class (state-changing, approval from the workload owners).
4. Assert the host is empty or only agreed-restart instances remain.
5. Run `dnf update`. No `ignore_errors`.
6. Reboot.
7. Post-check: services up, instances started where the owner expects.
8. Re-enable `nova-compute`.

Stop conditions to define before the campaign:
- migrations failing or slower than your baseline
- spare capacity dropping below the reserve
- a post-check failing
- the decision owner being unreachable

Resuming after a stop is a new decision.

## Questions for you

1. How many hosts are in `compute`, and what are the failure domains and spare capacity?
2. Is instance storage shared or local? Which release are you running?
3. Is there a criticality table, and who approves restarts or deadline exceptions?
4. Is anything else in the maintenance window?
5. Does anyone besides the author know how this playbook is run?

If you want, I can draft the revised playbook for staging, and the per-class drain procedure.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.