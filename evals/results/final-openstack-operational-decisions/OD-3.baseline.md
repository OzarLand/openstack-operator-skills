**Yes, rebuild it. But build the new cloud next to the old one and migrate teams over. Don't wipe it in place.**

**Why repairing has stopped working**
- Each fix is applied to state nobody fully understands, so it creates the next problem. That pattern means the drift has outgrown what you can reason about.
- A test cloud is only useful if it behaves like a clean, known environment. Years of half-applied config changes mean results from it are partly artifacts of the cloud itself.
- "Teams have stuff in there" is an argument about migration cost, not about whether the cloud is healthy. Most of that stuff is probably abandoned. Instances and ports nobody has touched in a year usually belong to people who have left or moved teams.

**How I'd run it**
1. **Inventory first.** Export all instances, volumes, ports, floating IPs, networks and projects, with owner and last-activity data. Tag anything without an owner.
2. **Make teams claim their resources.** Set a deadline, for example 4–6 weeks. Anything unclaimed gets snapshotted and archived, and is then not carried over.
3. **Define the new cloud as code** (Kolla-Ansible, OpenStack-Helm, Terraform or similar), so a rebuild is repeatable and config drift shows up in review. Without this you'll be back in the same state in two years.
4. **Run both clouds in parallel.** Teams recreate their environments on the new one, ideally from their own templates. Where they can't, migrate with snapshots or Glance images.
5. **Decommission the old cloud on a published date.** Keep a final snapshot or backup for a grace period.
6. **Add guardrails to the new one.** Per-project quotas, a mandatory owner tag, automatic expiry or reaping of idle resources, and a periodic reconcile of config against the code.

**What would change my answer**
- If you can't get the hardware or capacity to run two clouds side by side, the rebuild gets harder. You could migrate in waves on the same hardware, but that is riskier.
- If some teams have stateful, hard-to-recreate workloads, handle those individually, with a dedicated migration path and an owner.
- If the underlying problem is the control plane (database corruption, a stuck Neutron or Nova state) rather than leftover resources, a cleanup campaign might be enough. Ask yourselves honestly whether cleanup would fix it or whether the config drift is the real issue. From what you describe, it sounds like drift.

For the stakeholders who want to keep repairing, I'd frame it this way. The question isn't whether to throw teams' work away. It's whether you want to keep paying a growing, unpredictable cost for each fix, or pay a bounded one-time cost with a deadline.

I haven't seen the cloud itself. If you can share inventory output or the failure history, I can help size the migration or draft the announcement. I can also put this into a shareable one-pager if you need to make the case to others.