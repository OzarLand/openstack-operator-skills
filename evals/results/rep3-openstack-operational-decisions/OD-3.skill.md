# Rebuild or keep repairing the shared test cloud

**Recommendation: rebuild, but as a managed migration, not a wipe.** This rests on what you've told me. I haven't inspected the cloud, so the facts below are reported, not observed.

## Why rebuild

The deciding question is whether the information in the current state is worth preserving along with its uncertainty. For a test cloud that has run for years, most of that state is accumulated experimentation.

- **Reported:** every fix creates the next problem. That means nobody can predict the effect of a change, so the cloud is no longer in a known state. Each repair spends effort and adds more unknown state.
- **Reported:** leftover instances, ports and half-applied config changes. Half-applied config means the running cloud may no longer match what your deployment tooling would produce. You can't be sure an upgrade or redeploy will behave as expected.
- **Assumption:** there's no clean baseline to repair back to. If one exists, the case for repairing gets stronger.
- Test environments exist to give trustworthy results. A cloud with unknown drift gives you results you can't trust, and that also affects the teams using it.

"Teams have stuff in there" is a reason to plan the rebuild carefully. It isn't a reason to avoid it. Almost nobody can say what is in there, and that's the real problem.

## What would change my answer

Repair is the better choice if either of these holds:

1. **Someone is using the cloud as production.** If a team depends on it for something it can't recreate, treat that team's workloads as production. Migrate them first, or exempt them until they can move.
2. **You can't rebuild it.** If the installation isn't reproducible (no tooling, config lost, or only one person knows how), a rebuild just swaps known mess for unknown mess. In that case the first job is to make the deployment reproducible. That job is needed either way.

Most of the "keep repairing" camp probably means point 1. Ask them to name what they'd lose.

## How to do it safely

1. **Preserve evidence first (read-only).** Export configs, the instance, volume, port and network inventory with owner and project, and the current service state. This helps with root cause later and lets you answer "was my thing in there?"
2. **Inventory and claim.** Publish the list per project. Give owners a deadline to claim what they want kept, with a clear default: unclaimed resources are not migrated. Set the deadline and the default with the people who'll be affected, and get them agreed by whoever has authority over the cloud.
3. **Define the baseline and acceptance tests before you build.** Write down what "known good" means: the release, the config source of truth, and a validation suite (create a network, boot an instance, attach a volume, and so on). Automated installation alone doesn't prove the new cloud is equivalent to what you need.
4. **Build the new cloud alongside the old one if capacity allows.** Migrate claimed workloads, then retire the old one. If you don't have the capacity, announce a downtime window and take a verified backup of whatever is claimed.
5. **Add guardrails so it doesn't drift back.** Use quotas, mandatory ownership tags, an expiry or reaping policy for instances, and config changes only through the deployment tooling. Without these, the same mess returns in two years.

## Decisions and owners

- **Decision owner:** unknown. Someone with authority over the shared cloud, not the engineers alone, should accept the disruption to teams. Engineers assess the technical risk and the owner accepts the business risk.
- **Deleting the old environment is irreversible.** Don't do it until the inventory is exported, owners have signed off, and the new cloud passes the acceptance tests. Keep the old one in a stopped state for an agreed period if you can.
- **Review trigger:** if claimed workloads can't be migrated by the deadline, or acceptance tests fail, pause and reassess rather than pushing on.

## How you'll know it worked

- The new cloud passes the acceptance suite, and a second rebuild from the same tooling reproduces it.
- Config drift checks show no differences from the source of truth.
- Fewer "fix creates next problem" tickets over the following months.

## Gaps I need from you

- Which OpenStack release and deployment tool you run, and whether the deployment is reproducible.
- Whether any team treats this cloud as production.
- How much spare capacity exists to run old and new side by side.
- Who owns the cloud and can decide.

If you share those, I can turn this into a short decision record with a weighted comparison of repair, rebuild-in-place and parallel rebuild.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.