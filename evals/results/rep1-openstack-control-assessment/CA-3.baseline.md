**Score: 4/10**

You have good visibility and documentation. Your recovery capability depends on one person.

**What's working**
- **Observability (strong):** Grafana dashboards for every service means you can see problems.
- **Documentation (decent):** RabbitMQ recovery is written down, and the wiki is large.
- **Track record:** Three successful recoveries show the procedure works, at least when your lead runs it.

**What holds the score down**
- **Key-person dependency:** Nobody but your lead engineer has done a RabbitMQ recovery. If they're on leave, asleep, or gone, you have a documented procedure that no one has tried to follow. Three successes by one person show that person is good. They don't show the control is mature.
- **Untested documentation:** You don't know whether the runbook works for anyone else. Runbooks written by the expert who performs the task often skip steps that person does from habit. Only a second person following it cold will show those gaps.
- **Wiki size:** 400 runbook pages is a count, not a quality measure. At that size you should ask how many are current, who owns them, and whether responders can find the right one at 3am.
- **Unknowns:** You didn't mention alerting, paging and escalation, drills, or post-incident reviews. Dashboards show problems only when someone is looking at them. If these exist, the score goes up.

**What would move you to 7 or 8**
1. Have a different engineer run a RabbitMQ recovery in staging, using only the runbook, with your lead observing and not helping. Fix every gap they hit.
2. Repeat that with a third person, then add it to the on-call rotation's onboarding.
3. Assign an owner and a review date to each critical runbook, and audit the 400 pages to find the ones that matter.
4. Make sure alerts page someone before anyone has to check a dashboard.
5. Run recovery drills on a schedule, for example quarterly.

Step 1 alone is worth about two points. It turns a single-person capability into a documented, repeatable one.