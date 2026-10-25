**Recommendation: rebuild, but not as a big-bang wipe.** Rebuild on a fixed timeline with a claim-your-stuff window, and keep the old cloud read-only until the window closes. This is an analysis for your decision owner. It isn't an authorization to delete anything.

## Decision to make
You have a shared, long-lived test cloud and a choice between repairing and rebuilding it. The objective is a test environment teams can trust, meaning results that don't depend on leftover state. The decision owner is unknown. Someone with authority over the platform and the consuming teams needs to be named (see Decision rights).

## Evidence and uncertainty
| Fact / belief | Tag | Confidence |
|---|---|---|
| Years of use by many teams, with leftover instances, ports and half-applied config | Reported | Medium. I haven't seen any inventory or output. |
| Each fix creates the next problem | Reported | Medium. It's a strong signal, but it needs a count of fixes and what they caused. |
| "Teams have stuff in there" | Reported | Low. Nobody has said what the stuff is, who owns it, or whether it can be recreated. |
| Config no longer matches any known baseline | Hypothesis | Unverified. A config diff against the deployment tool's intended state would confirm or refute it. |
| Release, size, deployment tool, backends, and whether anything production-like depends on it | Unknown | Gaps. |

## Options
| Option | Risk of doing it | Risk of not doing it |
|---|---|---|
| Keep repairing | Each fix is made on an unknown baseline. Effort goes into discovering state rather than improving anything. | The repair cycle continues. Test results stay unreliable, and the cloud stays uncontrolled. |
| Rebuild with a migration window (recommended) | Teams lose unclaimed state. Rebuild effort is real. The new cloud can drift again. | Not applicable, since this is the recommended path. |
| Immediate wipe and rebuild | Surprise data loss and lost trust. A hidden dependency, such as something a team treats as production, breaks. | Same as repairing, with no migration cost. |
| Declare it unsupported and build a second cloud in parallel | Double the capacity and double the operations. | Same as keeping it as-is, and the old cloud rots further. |

## Gates
- **Keep repairing:** fails the "recovery path / known trusted state" criterion. A baseline you can't define can't be repaired back to. What would satisfy it is a full inventory and a config diff against intended state, which is likely more work than rebuilding.
- **Immediate wipe:** fails the owner and impact gates. Nobody has accepted the loss, and affected teams haven't been told.
- **Parallel cloud:** survives the gates, but it only makes sense if capacity is cheap and you also commit to decommissioning the old cloud.

## Trade-offs
The deciding question is whether the information in the current state is worth preserving along with its uncertainty. For a test cloud, it usually isn't. Most of that state is accumulated experimentation. What's worth keeping is the few items teams can name, not the whole environment.

"Teams have stuff in there" is a reason to run a migration process, not a reason to keep the cloud as it is. Anything a team can't recreate from code or images is a separate finding, because it means that team has a backup problem.

Two conditions make the rebuild succeed or fail:
- **Define the baseline.** Write down what "known good" means: versions, config, networks, quotas, images. Check the result against that definition. Running the installer is not proof of equivalence.
- **Close the drift path.** Without that, the new cloud ends up like the old one in a year. This means changes only through the deployment tool, resource quotas, and expiry or tagging for instances and ports.

## Recommendation
1. **Preserve evidence first (read-only).** Export inventories of servers, ports, volumes, networks and floating IPs by project. Also save the current configs and the deployment tool's state. This helps with ownership questions and lets you learn which half-applied changes caused trouble.
2. **Announce a date, not a debate.** Send teams a notice with a firm cutoff and a way to claim resources. Unclaimed resources get a tag or shutdown first, which is reversible, and deletion comes only after a grace period.
3. **Migrate only claimed items.** Teams recreate what they can from code. For the rest, snapshot or back up, then restore on the new cloud.
4. **Rebuild from a written baseline.** Run acceptance tests, and keep the old cloud read-only until the window closes.
5. **Add drift controls and a named owner** before declaring it done.

**What you accept:** some teams will be inconvenienced, and a few unclaimed things will be lost. That is the price of getting a trusted environment back.

**One caveat:** if the platform runs anything production-like, or a team can show a real dependency on specific state, that item needs its own plan before the cutoff. It is not a reason to cancel the rebuild.

## Decision rights
Whoever owns the platform's budget and the consuming teams' agreement decides. The platform team assesses the technical risk. Team leads accept or contest the loss of their own state. Anyone can challenge, but one person must decide. If the platform owner can't be named, that is the first problem to solve, because it is probably part of why the cloud got into this state.

## Owner, review trigger, exit condition
- **Owner:** a named platform owner for the rebuilt cloud (unknown today).
- **Review trigger:** drift detected against the baseline, or a quarterly check.
- **Exit condition for the old cloud:** decommissioned after the grace period, with a recorded date.

## How we will know it worked
- Config matches the baseline, shown by a diff.
- Leftover resources stay near zero because expiry works.
- Fewer "fix creates the next problem" incidents over the next quarter.
- Teams can reproduce their environments from code.

## Gaps I need from you
- OpenStack release and deployment tool.
- Rough counts of instances, ports and volumes, and how many projects.
- Whether any team treats this cloud as production-like.
- Who owns the platform today.

## Decision record (draft)
- **Decision:** rebuild with a claim window.
- **Rejected alternatives:** continue repair; immediate wipe; parallel cloud.
- **Key assumption:** state is mostly disposable experimentation (unverified).
- **Reopen if:** inventory shows production-like dependencies.

> Decision support only. State-changing steps above require approval by the accountable owner and should be executed under your change process.

If you'd like this as a shareable page for the teams or the decision owner, I can publish it.