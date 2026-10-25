**Score: 4/10**

This is a rough score based on what you've told me. I haven't seen your actual setup.

**What's working**
- **Observability:** Dashboards for every service is good coverage.
- **Documentation:** Recovery is written down, and 400 runbook pages shows a habit of documenting.
- **Track record:** Three successful RabbitMQ recoveries is real evidence that the process works.

**Why it isn't higher**
- **Key-person dependency:** All three recoveries were done by one person, and nobody else has done one. That means the documentation has never been tested by anyone but its author. A runbook the author can follow from memory doesn't show that a new reader can follow it. If your lead is on leave, asleep, or has left, you effectively have no tested recovery capability.
- **Unproven runbooks:** Documented but never run by anyone else is a weak control. The gap usually shows up as missing steps, assumed context, and stale commands.
- **Size of the wiki:** 400 pages is more likely a sign of sprawl than of maturity. Nobody has said how many are current, owned, or findable during an incident.
- **Dashboards aren't detection:** You didn't mention alerting, thresholds, on-call routing, or SLOs. Dashboards only help if someone is looking at them. Alerts are the control.
- **Nothing on rehearsal:** You didn't mention game days, failure drills, or restore tests. Three real incidents is also a small sample, and a different failure mode may not match the runbook.

**How to get to a 7 or 8**
1. Have a second engineer run the next RabbitMQ recovery from the runbook alone, with the lead watching but not helping. Fix every gap they hit.
2. Run a drill in staging at least quarterly, rotating who leads it.
3. Confirm you have alerts on queue depth, memory and disk alarms, unacked messages, and node partitions, routed to an on-call rotation.
4. Give each runbook an owner and a last-verified date. Archive or flag the ones nobody has checked in 12 months.
5. Write a short post-incident review for each of the three past recoveries, if there isn't one. Check that what the lead did matches what the runbook says.

Items 1 and 3 would move the score the most. If you can tell me about your alerting, on-call setup, and whether the recoveries had post-mortems, I can make the score more precise.