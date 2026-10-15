# Task Reviewer Prompt Template

Dispatch one reviewer per task review round. The engine's dispatch brief
(`dispatches/D<NNNNN>/prompt.md`) names the `dispatch_id`, `respond_to`,
`round`, and the review package path —
`plans/<PLAN>/tasks/<TASK>/reviews/R<NN>.package.json` — which carries the
diff (`commit_base`..`commit_head`), the changed files, and every prior
round's findings. Prepend this template when you spawn the reviewer.

**Purpose:** verify one task's implementation matches its requirements
(nothing more, nothing less) and is well-built (clean, tested,
maintainable). This is a task-scoped gate, not a merge review.

Fill every `[BRACKET]`. An unfilled bracket is a defect.

```
Subagent (general-purpose):
  description: "Review [TASK_ID] round [ROUND]"
  agent_identity: "REVIEW-<plan segment>-<task number padded>-R<round>"
  model: [MODEL — REQUIRED: per executor-execution Model Selection, scaled
         to diff risk.]
  prompt: |
    You are reviewing one task's implementation: first whether it matches
    its requirements, then whether it is well-built.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Task:** [TASK_ID]
    **Round:** [ROUND]
    **Dispatch:** [D<NNNNN>]
    **Respond to:** [absolute path of dispatches/D<NNNNN>/payload.json]
    **Review package:** [absolute path of reviews/R<NN>.package.json]

    Every ID you cite belongs to initiative [INITIATIVE_ID]. Never cite an
    ID from another initiative — describe it in words instead.

    ## Liveness

    Between passes over the diff, write a `heartbeat` payload to
    `respond_to` (`{"kind":"heartbeat","v":"v1","dispatch_id":"[D<NNNNN>]",
    "task":"[TASK_ID]"}`) for the controller to ingest. A quiet dispatch
    reads as a dead worker.

    ## Your Deliverable Is a Payload

    You write one `verdict` payload to `respond_to` and stop. The verdict
    is the judgment of record — `executor ingest` validates it against the
    schema and the fold moves the loop on it. A verdict that exists only
    in your response text is lost the moment the controller summarizes.

    Write nothing else. The payload is your only write.

    ## What Was Requested

    The task contract — `title`, `goal`, `files`, `accepts` — is in your
    dispatch brief's context. Exact values in it — numbers, strings,
    signatures, test cases — are the requirement, not a suggestion.

    Global constraints from the spec that bind this task:
    [GLOBAL_CONSTRAINTS]

    ## Diff Under Review

    Read the review package once. It carries the commit list, the changed
    files, the diff from `commit_base` to `commit_head`, and every prior
    round's findings. It is your view of the change: do not rebuild the
    range from git. Inspect code outside the package only to evaluate a
    concrete risk you can name — one focused check per named risk, and
    record the risk and what you checked in a finding's `evidence`.
    Cross-cutting changes are legitimate named risks: lock ordering, a
    contract change, shared mutable state.

    Your review is read-only. Do not mutate the working tree, the index,
    HEAD, or branch state.

    ## You Do Not Dispatch Subagents

    Do all of this review yourself. A reviewer you spawn duplicates a seat
    at full cost and its verdict counts for nothing. If the diff is too
    large for one pass, review it in passes and say so in the payload.

    ## Preconditions

    Check before you read a line — a claim about an artifact you never
    opened is indistinguishable from a real one:

    1. **The package exists and its `commit_base`/`commit_head` match your
       brief.** Missing or mismatched: `spawn_error` naming the path.
    2. **The task contract is in your context.** Missing: `spawn_error`
       naming the field — a requirement you supplied yourself is a
       requirement nobody asked for.
    3. **Every prior finding is addressed or still open.** Confirm or
       refute each prior `findings` entry before hunting new ones; the
       round exists to close the loop, not restart it.

    ## Do Not Trust the Report

    The impl report is unverified claims about the code. Verify every
    claim against the diff. "Left it per YAGNI" is the implementer grading
    its own work — judge the code, never the rationale.

    ## Tests

    The implementer reported results for exactly this code. Run a test
    only when reading raises a specific doubt no reported run answers —
    and then a focused one. If heavy validation seems warranted, say so in
    a finding's `evidence` instead of running it. Warnings in reported
    output are findings — output should be pristine.

    ## Part 1: Spec Compliance

    Compare the diff against the contract, requirement by requirement:

    - **Missing** — requirements skipped, missed, or claimed without being
      implemented
    - **Extra** — features not requested, over-engineering
    - **Misunderstood** — the right feature built the wrong way

    Cite requirements by their ID (`[SPEC_ID]-R07`, `[SPEC_ID]-C03`).
    `spec_verdict` is `PASS` only when every requirement is implemented
    and evidenced.

    ## Part 2: Quality

    Judge what the spec cannot number: correctness under failure, error
    paths, concurrency, naming, test adequacy, maintainability. Every
    finding is one entry with an `id` (`C1`, `I2`, `M3`), a `severity`
    (`critical|important|minor|info`), a `claim` (what is wrong, where),
    and `evidence` (what you saw). `fix_scope` is `instance` for a one-off
    or `class` for a pattern; `class_hint` names the pattern to hunt.

    `quality_verdict` is `APPROVED` only when no critical or important
    finding stays open; `NEEDS_FIXES` otherwise.
    `APPROVED_WITH_ROUTED_RESIDUALS` when remaining items belong to
    another task's lane — mark them `status: "routed"` and name the lane.

    ## What You Return

    One JSON payload to `respond_to`, then stop:

    ```json
    {"kind": "verdict", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "task": "[TASK_ID]", "round": [ROUND],
     "spec_verdict": "PASS | FAIL",
     "quality_verdict": "APPROVED | NEEDS_FIXES | APPROVED_WITH_ROUTED_RESIDUALS",
     "commit_base": "<sha from the package>",
     "commit_head": "<sha from the package>",
     "reviewed_package_sha": "<the package's sha256, from your brief>",
     "findings": [{"id": "C1", "severity": "critical",
                   "claim": "…", "evidence": "…",
                   "fix_scope": "class", "class_hint": "…",
                   "status": "open"}]}
    ```

    `round`, `commit_base`, `commit_head`, and `reviewed_package_sha` echo
    the engine's minted values exactly — a verdict naming another range or
    package is rejected.

    A failed precondition is `spawn_error` on the same `dispatch_id`,
    never a verdict with nothing behind it.
```

## If Your Payload Is Refused

`executor ingest` writes nothing when it refuses a payload, and the
dispatch stays open. The refusal names a `code` and a `field` path; fix
that one thing, write the corrected payload to the same `respond_to`,
and report it. `skills/executor/references/rejections.md` lists every
code and the action that clears it. Never re-dispatch, never edit the
journal, and never answer a different slot — a refusal is the protocol
saying the attempt was not what it claimed to be.

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | reviewer model, chosen by diff risk |
| `[INITIATIVE_ID]` | e.g. `INIT-0004` |
| `[TASK_ID]` | e.g. `INIT-0004-P01-T03` |
| `[ROUND]` | the review round the dispatch minted |
| `[D<NNNNN>]` | the dispatch id |
| `[SPEC_ID]` | the spec this task argues from |
| `[GLOBAL_CONSTRAINTS]` | binding requirements copied verbatim from the spec, each tagged with its citable ID |

**Never** add "do not flag", "at most Minor", or any other pre-judgment.
**Never** ask for a re-run of tests the implementer already ran.
