No. Documentation plus two presentations is the usual plan, and it misses the two things you described: how upgrades are actually executed, and why each customization exists. The book that skill is based on makes the same point about departing engineers. This is a capability assessment, not a judgment of him.

## Why it isn't enough

- **Documentation captures what he remembers to write down.** Upgrade know-how is mostly in the doing: the order of steps, which warnings to ignore, what to check before moving on, what he does when something goes wrong. People rarely write that down because it no longer feels like knowledge to them.
- **Presentations transfer awareness, not ability.** After two talks, people know the topics exist. They can't run an upgrade.
- **Nothing in the plan tests it.** You'd find out the transfer failed during your next upgrade or the next outage, when he's gone.
- **Customization rationale decays fast.** The reason a patch exists is often a past incident, a vendor bug or a customer commitment. If it isn't recorded per customization, the team later can't tell which ones are safe to remove and which are load-bearing. They tend to keep all of them forever, which is expensive, or remove one and find out the hard way.

## What I'd do in the 4 weeks

**Week 1: decide what matters and start recording.**
1. List the business capabilities that depend on the platform and how critical each is. Then walk one real journey, such as creating a VM, through every dependency. Ask who can diagnose and recover each step besides him.
2. Make a customization register. For each local patch, config override or workaround, record:
   - why it exists
   - what breaks if it is removed
   - whether upstream has fixed it
   - who owns it
   - when to review it
   
   Do it in interview sessions where someone else asks the questions and writes the answers. He will be faster and more complete answering questions than writing prose.

**Weeks 2–3: transfer by doing.**
3. Have a named successor, not a spectator, perform real operations while he watches: routine deployment-tool runs, a config change, a realistic failure investigation, and a rehearsal of recovery for the shared components (database, messaging, Fernet and certificate rotation). If you have a staging or lab environment, run an upgrade rehearsal there with the successor at the keyboard. If you don't, you've found a gap, and you should note it.
4. Turn what the sessions surface into runbooks. Someone other than the author should be able to follow each one.

**Week 4: test it and record what's left.**
5. Check by demonstration. Give the successor a realistic symptom, such as "users can't create VMs", and see whether they can investigate without him. Ask an engineer who didn't build the platform to explain a critical dependency and walk through a recovery.
6. Write down what is still single-person knowledge and, for each item, decide whether to act now, plan it, monitor it, or accept the risk. Accepting should be a named owner's decision with a review date.

**Also consider:** a consulting or on-call arrangement for a few months after he leaves, and a deliberate decision to postpone non-urgent upgrades until the successor has done one with backup available. If that backup is gone, delaying the upgrade is a risk decision management should make explicitly, not drift into.

## What I'd need from you to be specific

I don't know your team size, who the successor is, how critical the platform is, your deployment tool, how many customizations there are, or whether you have a staging environment. With those, I could rate each capability on a control scale (unknown, visible, understood, controlled, recoverable, sustainable) and give you a prioritized plan. The runbook-authoring skill could also turn his interview sessions into reviewable procedures.

I can also write this up as a one-page brief for management arguing for the extra work. Tell me if you want that.