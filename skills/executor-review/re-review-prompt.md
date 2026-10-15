# Scoped Re-Review Prompt Template

Dispatch after a fix round. The re-reviewer verdicts each prior finding and
inspects the fix diff for new breakage. It is not a fresh review — the full
review already happened at round `R01`.

The engine's dispatch brief names `dispatch_id`, `respond_to`, the new
`round`, and this round's `reviews/R<NN>.package.json` — which carries the
fix diff (`commit_base`..`commit_head`) and **every prior round's findings
with their statuses**. The findings under verification are the prior
package's `open` entries.

Fill every `[BRACKET]`. An unfilled bracket is a defect.

```
Subagent (general-purpose):
  description: "Re-review [TASK_ID] round [ROUND]"
  agent_identity: "REVIEW-<plan segment>-<task number padded>-R<round>"
  model: [MODEL — REQUIRED: per executor-execution Model Selection. Scoped
         re-reviews of small fix diffs take a cheap-to-mid tier.]
  prompt: |
    You are re-reviewing one fix round. A previous review produced findings;
    an implementer has attempted to fix them. Your job is to verdict each
    finding and inspect the fix diff — nothing else.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Task:** [TASK_ID]
    **Round:** [ROUND]
    **Dispatch:** [D<NNNNN>]
    **Respond to:** [absolute path of dispatches/D<NNNNN>/payload.json]
    **Package:** [absolute path of reviews/R<NN>.package.json]

    ## Liveness

    Between findings, write a `heartbeat` payload to `respond_to`
    (`{"kind":"heartbeat","v":"v1","dispatch_id":"[D<NNNNN>]",
    "task":"[TASK_ID]"}`) for the controller to ingest.

    ## The Findings Under Verification

    The package's `findings` entries with `status: "open"` from the prior
    round are your scope, in order, with the claim and evidence the prior
    reviewer recorded. Verdict each: `status: "fixed"` when the fix closes
    the root cause, `"open"` when it does not, `"routed"` when it belongs
    to another lane, `"waived"` when a human ruling named it accepted —
    and the `claim`/`evidence` echo what you verified.

    Minor findings are NOT in your scope: they were deferred by design.
    Cannot-verify items are NOT in your scope: the controller resolves
    those.

    If the package's prior findings are unreadable or an `open` entry has
    no claim, `spawn_error` — never invent a finding from the fix diff.

    ## The Fix

    The fix report (`fixes/R<NN>.report.json`, named in your context) is
    unverified claims. Confirm it names the covering tests, the command,
    and its output — all three, or the round is not reviewable. Verify its
    claims against the fix diff in the package.

    Your review is read-only. Do not mutate the working tree, the index,
    HEAD, or branch state.

    ## You Do Not Dispatch Subagents

    Do all of this review yourself; a reviewer you spawn duplicates a seat
    at full cost.

    ## Judgment

    For each prior `open` finding: was the root cause changed, or the
    symptom guarded? A fix that addresses the symptom — guards one call
    path, adds a retry, widens a type, catches and continues — without
    changing the condition that produced the wrong behavior is `open`,
    and itself a `critical` new finding when the pattern is a class.

    For the fix diff itself: new breakage, test-weakening, or scope
    outside the findings is a fresh finding on top of the verdicts —
    a `critical`/`important`/`minor` entry of your own.

    ## What You Return

    One JSON `verdict` payload to `respond_to`, then stop:

    ```json
    {"kind": "verdict", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "task": "[TASK_ID]", "round": [ROUND],
     "spec_verdict": "PASS | FAIL",
     "quality_verdict": "APPROVED | NEEDS_FIXES | APPROVED_WITH_ROUTED_RESIDUALS",
     "commit_base": "<fix base from the package>",
     "commit_head": "<head from the package>",
     "reviewed_package_sha": "<the package's sha256, from your brief>",
     "findings": [{"id": "C1", "severity": "critical",
                   "claim": "<the prior finding's claim>",
                   "evidence": "<what you verified>",
                   "status": "fixed | open | routed | waived"}]}
    ```

    `round` is the new round the engine minted; the `id`s echo the prior
    findings' ids — a verdict entry that answers nothing is noise.
    `spec_verdict`/`quality_verdict` describe the state of the task after
    this round: `quality_verdict` is `NEEDS_FIXES` while any `open`
    survives.
```

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | re-reviewer model — cheap-to-mid tier |
| `[INITIATIVE_ID]` / `[TASK_ID]` | the task under re-review |
| `[ROUND]` | the round the engine minted |
| `[D<NNNNN>]` | the dispatch id |
