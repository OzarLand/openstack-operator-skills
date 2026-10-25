**Score: 5/10**, based only on what you've told me. I haven't seen the dashboards, wiki, or runbooks.

**What's working**
- Monitoring coverage is broad. Grafana dashboards for every service means you can see problems.
- Documentation exists. Having RabbitMQ recovery written down puts you ahead of teams that rely on memory alone.
- You have a track record. Three successful recoveries show the procedure works, at least when your lead engineer runs it.

**What holds the score down**
1. **Key-person dependency.** This is the main issue. Three successes by one person is evidence that *they* can recover RabbitMQ. It isn't evidence that *the control* works. If they're on leave, asleep, or gone, you don't know what happens.
2. **The runbook is untested by anyone else.** A runbook written by, or for, the person who already knows the system often skips steps that feel obvious to them. Until someone else follows it cold, you can't tell whether it's complete.
3. **400 pages is a warning sign as well as a strength.** That's a lot to keep current and find under pressure. The questions that matter are how many were reviewed in the last year, and whether someone on call at 3am can find the right one in under a minute.
4. **Dashboards show problems but don't act on them.** I don't see alerting, paging, ownership, or thresholds tied to the dashboards. Dashboards only help if someone is looking.
5. **No evidence of practice.** Successes during real incidents are not the same as rehearsed drills. Real incidents are a poor time to find gaps.

**What would move it up**
- **To 6–7:** Have a second engineer run the RabbitMQ recovery from the runbook alone, with the lead engineer observing and not helping. Fix every gap they hit.
- **To 7–8:** Make that a recurring drill (quarterly, say) in staging, rotating who runs it. Add alerting tied to RabbitMQ health (queue depth, unacked messages, node and partition state) that pages a named owner.
- **To 8+:** Give the wiki owners and review dates, and prune or archive stale pages. Track recovery time across drills.

**Caveat:** this is a judgment from four facts. If you have paging, drills, or a second on-call person that you didn't mention, the score could be higher. If the runbook is stale or the dashboards have no alerts behind them, it could be lower.