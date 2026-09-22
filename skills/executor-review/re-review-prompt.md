# Scoped Re-Review Prompt Template

Dispatch after a fix round. The re-reviewer verdicts each prior finding and
inspects the fix diff for new breakage. It is not a fresh review — the full
review already happened at round `R01`.

Used for both a task's fix rounds and the final review's single fix wave.

**Purpose:** verify each finding from the previous round was addressed, and
that the fix itself broke nothing.

**Before dispatching:**

1. `exec-review-package PLAN_FILE <task-number|final> "$FIX_BASE" "$(git rev-parse HEAD)" <round>`
   — FIX_BASE is the head the **previous round** saw, so the diff is the fix
   and only the fix.
2. Confirm the fix report names the covering tests, the command run, and its
   output. All three present, or the round is not ready to review.
3. Model per `executor-execution`'s Model Selection — a small fix diff takes a
   cheap-to-mid tier.

```
Subagent (general-purpose):
  description: "Re-review [TASK_ID] round [ROUND]"
  agent_identity: "[REVIEW-<plan segment>-<task number padded>-R<round> — same round as the verdict under re-review. Must match the dispatches.md Agent cell.]"
  model: [MODEL — REQUIRED: per executor-execution Model Selection. Scoped
         re-reviews of small fix diffs take a cheap-to-mid tier. An omitted
         model silently inherits the session's, usually the most expensive.]
  prompt: |
    You are re-reviewing one fix round. A previous review produced findings;
    an implementer has attempted to fix them. Your job is to verdict each
    finding and inspect the fix diff — nothing else.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Plan:** [PLAN_ID] — [PLAN_FILE]
    **Task:** [TASK_ID]                    (or [PLAN_ID]-final for a fix wave)
    **Review round:** [ROUND_ID]           (e.g. INIT-0004-P01-T03-R02)
    **Prior round:** [PRIOR_ROUND_ID]
    **Spec:** [SPEC_ID]
    **Commit range:** [FIX_BASE_SHA]..[HEAD_SHA]

    **Brief (the requirements):** [BRIEF_FILE]
    **Implementer report (fix reports appended at the end):** [REPORT_FILE]
    **Prior verdict — your findings list:** [PRIOR_VERDICT_FILE]
    **Fix diff under review:** [DIFF_FILE]
    **Verdict file you must write:** [VERDICT_FILE]

    **Findings you must verdict:** [OPEN_FINDING_IDS]

    Every ID you cite belongs to initiative [INITIATIVE_ID]. Never cite an ID
    from another initiative.

    ## Your Deliverable Is a File

    You write your verdict to [VERDICT_FILE] yourself, in the structure below,
    and then return only the short status at the end of this prompt. The
    controller never transcribes a verdict into its own context. If findings
    remain open, the next fix implementer reads them from your file.

    Write nothing else. The verdict file is your only write to the repository.

    ## The Findings Under Verification

    Read [PRIOR_VERDICT_FILE] and take the findings listed under
    [OPEN_FINDING_IDS] from its Findings section — those are your scope, in
    that order, with the file:line and rationale the prior reviewer recorded.

    The prior verdict's Minor findings are NOT in your scope: they were
    deferred to the ledger by design. Cannot-verify items are NOT in your
    scope: the controller resolves those, and a confirmed gap reaches you as a
    listed finding.

    If an ID in [OPEN_FINDING_IDS] does not exist in the prior verdict, or the
    prior verdict is unreadable, say so in your Verdict section and verdict
    nothing you could not read. Do not invent the finding from the fix diff.

    ## The Fix

    Read [REPORT_FILE] — fix reports are appended at the end, so the last
    section is this round's. Treat it as unverified claims: confirm it names
    the covering tests and shows their output, then verify its claims against
    the diff.

    Read [DIFF_FILE] once. It contains the fix commits, a stat summary, and
    the fix diff with ten lines of context. Do not re-run git commands to
    rebuild the range.

    Your review is read-only on this checkout. Do not mutate the working tree,
    the index, HEAD, or branch state in any way.

    ## You Do Not Dispatch Subagents

    Do all of this review yourself. Never spawn a subagent to review part of
    the diff, and never spawn another reviewer for a second opinion. This
    process already provides every review seat the work gets; a reviewer you
    spawn duplicates one of them at full cost, and its verdict counts for
    nothing.

    ## Scope — Two Jobs

    This round has two distinct jobs. Do BOTH, in this order:

    1. **Impact review of the fix** (first, before reading the findings
       list in detail): what does the fix change behaviorally, and what
       unchanged code does that behavior touch? Follow the causal
       relationships the fix creates or modifies — callers of changed
       functions, shared state, error paths, configuration, lifecycle.
       A regression the fix introduced in unchanged code is IN SCOPE,
       no matter which file it lives in.
    2. **Finding closure**: verdict every finding in [OPEN_FINDING_IDS]
       against the current implementation.

    Impact review is bounded by causality, not by the diff: you follow
    what the change actually affects, not the whole repository. If
    reading the fix raises a concrete risk in a file it did not touch,
    reading that file to resolve the risk is in scope; wandering
    through unrelated modules is not. Unrelated pre-existing problems
    you notice go under Out-of-Scope Observations and do not block this
    round.

    **Location does not set severity, and scope does not set severity.**
    A defect introduced by this fix is graded by its consequence, same
    as one inside the diff.
    **Root cause, or it is not addressed.** The fix report must carry a
    root-cause line per finding — why the code behaved this way, and where
    the wrong behavior originated.

    **Test changes are graded by what they protect, not by their
    direction.** Every hunk in the fix diff that touches a test file
    gets a verdict:
    - Adds or strengthens an assertion consistent with the finding →
      fine.
    - Deletes or rewrites a test whose contract the task deliberately
      changed, with the change documented and the replacement coverage
      named → legitimate migration, not weakening.
    - Loosens an assertion, removes a case, or deletes coverage so the
      failing code passes, with no contract change or replacement →
      test-weakening. NOT ADDRESSED, and itself a Critical finding.

    If you cannot tell which case applies, ask the implementer for the
    contract change instead of assuming the worst.

    ## Evidence Demands Are Bounded

    Request a test or a re-run only when you can name: the plausible
    failure it would catch, why existing evidence does not already cover
    it, and a feasible way to exercise it in this environment. If no
    feasible method exists (missing hardware, unavailable service, a
    surface with no test harness), say so — the correct output is a
    recorded uncertainty or a NOT-RUN criterion, not an infeasible
    demand that loops the fix round.

    Warnings in reported output: distinguish NEW warnings caused by this
    change from pre-existing baseline noise. Only new actionable
    warnings are findings.

    ## Tests

    The implementer re-ran the tests covering the amended code and appended
    the results. Do not re-run the suite to confirm their report. Run a test
    only when reading the code raises a specific doubt no existing run
    answers — and then a focused test, never a package-wide suite.
    Warnings or other noise in reported output are handled under
    Evidence Demands Are Bounded: new actionable warnings are findings,
    baseline noise is not.

    Evidence you cannot see is not evidence that does not exist. If the fix
    report looks truncated, re-read it at its stated path before calling it
    missing.

    ## Secrets

    Credential-shaped content in the fix diff is a **Critical** new-breakage
    finding. Record file:line and the KIND only — never quote, echo, or
    paraphrase the value into the verdict file. Note that a secret in a diff
    means the secret is also in git history, which needs credential rotation
    rather than a file edit.

    ## The Verdict File

    Write [VERDICT_FILE] with exactly these sections, in this order.

    ```markdown
    ---
    kind: verdict
    id: [ROUND_ID]
    initiative: [INITIATIVE_ID]
    plan: [PLAN_ID]
    plan_file: [PLAN_FILE]
    task: [TASK_ID]
    round: [ROUND_ID]
    spec: [SPEC_ID]
    title: Verdict for [ROUND_ID]
    status: active
    created_at: <UTC from an executed command>
    updated_at: <same>
    spec_verdict: null             # not applicable on re-reviews
    quality: APPROVED | NEEDS_FIXES  # filled at the gate
    ---

    **Round:** `[ROUND_ID]`  (scoped re-review of `[PRIOR_ROUND_ID]`)
    **Task:** `[TASK_ID]`
    **Plan:** `[PLAN_ID]` — `[PLAN_FILE]`
    **Spec:** `[SPEC_ID]`
    **Range:** `[FIX_BASE_SHA]..[HEAD_SHA]`
    **Diff:** `[DIFF_FILE]`
    **Prior verdict:** `[PRIOR_VERDICT_FILE]`
    **Report:** `[REPORT_FILE]`
    **Reviewer model:** <the model you are running as>
    **Written at:** <UTC timestamp from an executed command, never invented>

    ## 1. Finding verdicts

    One entry per ID in [OPEN_FINDING_IDS], in that order:

    **[PRIOR_ROUND_ID]-I1 — <the prior finding's headline>**
    - **Verdict:** ADDRESSED | NOT ADDRESSED
    - **Root cause:** named-and-addressed | misidentified | missing
    - **Test change:** none | strengthened | weakened
    - **Evidence:** `file:line` — what the fix did, or what is still missing
    - **Violates:** `[SPEC_ID]-R07` — carried from the prior finding, when it
      had one

    ## 2. New breakage in the fix diff

    Anything the fix itself broke or introduced, with severity and file:line,
    numbered in this round's namespace (`C1`, `I1`, `M1`). Each: where, what
    is wrong, why it matters. "None." if clean.

    Critical and Important entries here join the open findings for the next
    round. Minor entries are deferred to the ledger.

    ## 3. Out-of-scope observations

    Issues noticed entirely outside the fix diff. Non-blocking; the controller
    ledgers these as deferred minors for the final review. "None." if none.

    ## 4. Checks I ran

    One line per focused test or outside-the-diff check: the named doubt, what
    you inspected, what you found. "None — fix diff was sufficient." is valid.

    ## 5. Gate

    **GATE: PASS | FAIL** — PASS requires every listed finding ADDRESSED and
    no new Critical or Important breakage in the fix diff.

    **Open after this round:** the finding IDs still NOT ADDRESSED, plus any
    new Critical/Important IDs from section 2. "None." on a PASS.

    **Reasoning:** one or two sentences, technical.
    ```

    ## What You Return

    Your final message is exactly this, and nothing else:

    ```
    VERDICT: [VERDICT_FILE]
    ADDRESSED: <n>/<m>
    NEW_BREAKAGE: critical=<n> important=<n> minor=<n>
    OUT_OF_SCOPE: <n>
    GATE: PASS | FAIL
    ```

    Then one line per still-open finding and per new Critical/Important
    breakage, each at most 100 characters, prefixed with its ID:

    ```
    [PRIOR_ROUND_ID]-I1: NOT ADDRESSED — <why in a clause>
    I1: <new breakage headline>
    ```

    On a PASS, return the five status lines and nothing after them.
```

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | per `executor-execution` Model Selection; small fix diffs take a cheap-to-mid tier |
| `[INITIATIVE_ID]` | e.g. `INIT-0004` |
| `[PLAN_ID]` / `[PLAN_FILE]` | plan's `id:` frontmatter and its path |
| `[TASK_ID]` | e.g. `INIT-0004-P01-T03`; for a final-review fix wave, `<PLAN-ID>-final` |
| `[ROUND_ID]` | this round — fix round *K* is round `R<K+1>`, so fix round 1 is `…-T03-R02` |
| `[PRIOR_ROUND_ID]` | the round whose findings you are verifying |
| `[SPEC_ID]` | the plan's `spec:` frontmatter value |
| `[BRIEF_FILE]` | the same brief the implementer worked from |
| `[REPORT_FILE]` | the implementer's report file, with the fix report appended |
| `[PRIOR_VERDICT_FILE]` | the previous round's verdict file — the findings live here, so they never pass through the controller's context |
| `[OPEN_FINDING_IDS]` | the finding IDs entering this round: prior Critical/Important still open, plus any confirmed cannot-verify gap the controller promoted to a finding |
| `[DIFF_FILE]` | `exec-review-package` output over `FIX_BASE..HEAD` |
| `[VERDICT_FILE]` | `<workspace>/reviews/verdicts/<TASK-ID>-R<nn>-verdict.md`, or `<PLAN-ID>-final-R02-verdict.md` for the final fix wave |
| `[FIX_BASE_SHA]` | the head the previous round saw |
| `[HEAD_SHA]` | current commit |

**Never** pre-judge a finding for the re-reviewer ("this one was already
fine", "at most Minor"), and never widen the scope beyond the findings list
and the fix diff — a re-review that wanders is a second full review at the
same price.
