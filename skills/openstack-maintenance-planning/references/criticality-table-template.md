# Workload criticality table

In the book's patching campaign, consuming teams filled in a shared table for
their own workloads, giving what the infrastructure could not infer
[Book: Ch. 20]. This template reproduces those four inputs and adds the
technical columns the plan needs. Columns marked `[Addition]` are this
repository's additions.

| Project / workload | Instances (or tag) | Business criticality | Acceptable downtime | Recovery expectations | Deadline / blackout periods | Owner (name, contact) `[Addition]` | Technical constraint (PCI/SR-IOV/vGPU/pinned/large memory) `[Addition]` | Agreed strategy (live / cold / restart / exception) `[Addition]` |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

Guidance:

- Ask consumers to fill business columns themselves; the platform team fills
  technical constraints from instance and flavor data.
- An empty business-criticality cell is a gap, not "low". Treat unknown
  workloads conservatively and escalate to the project owner.
- Keep the table after the campaign, as a document or as metadata on instances
  and projects, so it is an input to capacity planning rather than a one-off
  [Book: Ch. 20].
