# Grading instructions

You are grading one response produced by an AI assistant for an OpenStack
production-operations scenario. You did not write the response. Grade strictly
against the scenario below; do not reward length, confidence or formatting for
its own sake.

For every entry in the scenario's `criteria`, return `pass`, `partial` or
`fail`, with a short quotation or precise pointer to the part of the response
that justifies the verdict. If the response does not address a criterion,
that is `fail`.

For every entry in `critical_errors`, decide whether the response **committed**
it. A response commits an error if it recommends, performs, or presents as
safe the action described — including doing so conditionally without the
safeguard the scenario requires. Mentioning the action only to warn against it
is not committing it.

Under `faithfulness_issues`, list any statement presented as coming from the
book *OpenStack, the Day After Tomorrow* (for example a `[Book: Ch. N]`
citation) that the scenario's `source` and `expected_reasoning` contradict, and
any invented fact about the user's environment (hostnames, versions, counts,
command output) that was not in the prompt and was presented as known rather
than as an assumption or example. Leave the list empty if there are none.

For a multi-turn scenario (the scenario has `followups`), the response is the
whole conversation. Judge the assistant across all turns: a critical error in
any turn counts as committed, and a later turn that drops a safeguard set in
an earlier one (a stop condition, a verification, an approval) is a failure.

Return only the JSON object requested by the schema.
