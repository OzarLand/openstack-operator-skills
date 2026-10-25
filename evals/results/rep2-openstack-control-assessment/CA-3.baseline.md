**Score: 4/10**, based only on what you've told me.

**What counts in your favor**
- Dashboards for every service give you good detection and visibility.
- RabbitMQ recovery is documented, and it has been done successfully three times.
- A large runbook library shows you take documentation seriously.

**Why it isn't higher**
- **Key-person dependency.** This is the biggest issue. Only your lead engineer has ever done a RabbitMQ recovery. Three successes tell you one person can do it. They don't tell you the control works. If that person is on leave, asleep, or has left, your recovery capability drops to untested.
- **The documentation is unproven.** Nobody else has run the runbook. Those three recoveries may have relied on knowledge that isn't written down, and you have no way to tell. A runbook only counts once someone other than its author has followed it successfully.
- **Coverage isn't quality.** 400 wiki pages says nothing about whether they're current, tested, or findable during an incident. Without owners and review dates, a pile that size tends to go stale.
- **Dashboards show problems but don't fix them.** I didn't hear about alerting, on-call rotation, escalation paths, or recovery time targets. Those are what turn visibility into response.

**What would move the score**
1. **Have someone else run the RabbitMQ recovery** in a staging environment or game day, using only the runbook, with the lead engineer observing silently. Fix every gap they hit. This alone could take you to a 6.
2. **Add ownership and review dates** to the runbooks, and prune or flag the stale ones. Start with the critical-path services.
3. **Confirm alerting and on-call coverage** for the services that matter, and make sure more than one person can be paged for each.
4. **Set and measure recovery objectives**, such as time to recover, so a "successful" recovery has a defined meaning.

Doing the first item and showing a second person can recover would put you around 7. Regular drills across your other critical systems would get you to 8 or higher.

If you can share more about alerting, on-call, and how the runbooks are maintained, I can refine the score.