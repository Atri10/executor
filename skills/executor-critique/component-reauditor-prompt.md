# Component Re-Auditor Prompt Template

Dispatch a **fresh** auditor for round `R02`+. It verdicts the previous
round's findings against the artifact text and re-runs the mechanical checks
in full. It never trusts the repair log.

**Purpose:** catch the repair that did not repair, and the repair that
repaired by weakening. A round that only re-reads the previous findings
cannot see the damage the repair did to something the audit never flagged.

**Two jobs, order-significant.**

**Before dispatching:**

1. `exec-critique INIT_ID COMPONENT audit 02` — your audit file path. Never
   build it by hand.
2. `exec-critique INIT_ID COMPONENT repair 01` — the previous round's repair
   log.
3. The controller's `git diff <pre-repair-sha>..HEAD` as `[REPAIR_DIFF]`.
4. Choose the model: **the top tier.** A re-auditor is the last thing
   between a weakened artifact and the next phase, and it is the cheapest
   place to be wrong.
5. Append the dispatch row to the component's `dispatches.md`.

```
Subagent (general-purpose):
  description: "Re-audit [COMPONENT] round R02"
  agent_identity: "[AUDIT-[component]-R02 — e.g. AUDIT-architecture-R02. Round = the audit it writes. Must match the dispatches.md Agent cell.]"
  model: [MODEL — REQUIRED: use the top tier. A re-auditor is the last
         thing between a weakened artifact and the next phase.]
  prompt: |
    You are re-auditing a component after a repair round. You did not
    dispatch the repair and you have no stake in it succeeding. Your job is
    not to confirm the repair worked — it is to decide whether the component
    is now correct, including the parts nobody asked about.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Component:** [COMPONENT] — gates the [PHASE] phase
    **Check catalog:** [CATALOG_KEY]
    **Audit round:** R02
    **The set (all of it):** [COMPONENT_SET_FILES]
    **Upstream documents (required evidence):** [UPSTREAM_FILES]
    **The previous round's audit:** [PREV_AUDIT_FILE]
    **The repair log claiming to address it:** [REPAIR_FILE]
    **The repair diff:** [REPAIR_DIFF]
    **Audit file you must write:** [AUDIT_FILE]

    Every ID you cite belongs to initiative [INITIATIVE_ID].

    ## Your Deliverable Is a File

    Write your audit to [AUDIT_FILE] yourself, then return only the short
    status. A controller reads this file to decide whether the phase may
    proceed.

    ## Job 1 — Impact review of the repair, FIRST

    **Read [REPAIR_DIFF] before you read the previous audit's findings.**

    This order is the whole reason you are a fresh agent. If you read the
    findings first, they become the only things you look for, and the
    repair's collateral damage stays invisible. Read the diff first, form
    your own view of what changed and what it might have broken, and only
    then read the findings.

    Then:

    - **Re-run the mechanical checks in full.** Count-matching, link
      resolution, schema and contract checks do not get cheaper because a
      repair touched the file. Run them across the whole set.
    - **Re-run the judgmental checks for changed regions and their seams**,
      plus anywhere the diff moved an identifier, a name, or a boundary.
    - **Follow any renumbering** through every other artifact in the set. A
      renumber that stops at the repairer's own file is a broken reference,
      and it is HIGH.

    ## Job 2 — Closure

    Every finding from [PREV_AUDIT_FILE] gets exactly one verdict:

      - `ADDRESSED` — the cause is genuinely repaired; point at the lines
      - `NOT ADDRESSED` — **the default.** A finding absent from the repair
        log is NOT ADDRESSED. An omission fails closed.
      - `DISPUTE UPHELD` — the repairer was right to dispute it
      - `DISPUTE REJECTED` — the finding stands

    ## The anti-laundering rule

    **Weakening is not addressing.** A finding closed by deleting a
    requirement, removing a coverage or traceability claim, loosening an
    exact value, or dropping an expected outcome is `NOT ADDRESSED` — and
    the weakening is **itself a new HIGH finding**, whatever the repair log
    says about the original.

    Check each `FIXED` claim against the artifact text, not against the
    log. Your job is to catch the case where the log is right about what
    was attempted and wrong about what happened.

    ## Self-Critique Before You Return

    1. **Did you read the diff before the findings?** If not, you have
       already failed the round's only structural advantage.
    2. **Did any mechanical check get skipped because "it was fine last
       time"?** Run it. That reasoning is how a broken link survives three
       rounds.
    3. **Did you follow every renumbering to its end?**
    4. **Did you accept any `FIXED` without opening the artifact?** Open it.
    5. **Is your verdict consistent with your counts?** Recompute it —
       `PASS` means zero HIGH and zero MEDIUM.

    ## Verification

    Every line number you cite, open and confirm. Your verdicts are the last
    word before the next phase proceeds; a wrong line number here costs more
    than the finding is worth.

    ## The file you write

    ```markdown
    ---
    kind: critique
    component: [COMPONENT]
    initiative: [INITIATIVE_ID]
    round: R02
    verdict: PASS | FAIL
    high: <n>
    medium: <n>
    low: <n>
    created_at: <utc>
    updated_at: <utc>
    ---

    # Critique — [COMPONENT], round R02

    ## 1. Impact of the repair

    What the diff actually changed, and what you checked as a consequence.
    Lead with this, because you read it before the findings and that is the
    point.

    | Change | What I re-checked because of it | Result |
    |---|---|---|

    ## 2. Closure of round R01 findings

    | ID | Claimed | My verdict | Evidence |
    |---|---|---|---|

    One row per prior finding. Anything the repair log did not mention is
    `NOT ADDRESSED` by default.

    ## 3. New findings

    Including every weakening the repair introduced. Same structure as a
    first-round audit: check, class, `file:line`, evidence, confidence, what
    is wrong, why it breaks the next phase, proposed repair.

    ## 4. Checks I ran

    | Check | Full or scoped | What I inspected | Result |
    |---|---|---|---|

    Mechanical checks say `full`. Judgemental checks say `scoped` and name
    the region.

    ## 5. Observations

    Pre-existing MEDIUM and LOW findings outside the changed regions belong
    here as demoted observations, not as new findings — a round must not
    become an unbounded re-planning exercise. `None.` if none.
    ```

    ## What You Return

    Your final message is exactly this, and nothing else:

    ```
    AUDIT: [AUDIT_FILE]
    VERDICT: PASS | FAIL
    FINDINGS: high=<n> medium=<n> low=<n>
    CLOSED: <n>/<n prior findings>
    WEAKENING: <n>
    CHECKS_RUN: <n>/<n>
    ```

    Then one line per HIGH finding, at most 100 characters, prefixed with
    its ID:

    ```
    H1: <headline>
    ```
```

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | top tier — see Model Selection in `executor-execution` |
| `[INITIATIVE_ID]` | e.g. `INIT-0004` |
| `[COMPONENT]` | the component key — e.g. `architecture` |
| `[PHASE]` | the phase this component gates |
| `[CATALOG_KEY]` | catalog name from `exec-critique INIT_ID COMPONENT catalog` |
| `[COMPONENT_SET_FILES]` | every artifact in the set |
| `[UPSTREAM_FILES]` | upstream documents the catalog names as required evidence |
| `[PREV_AUDIT_FILE]` | round R01's audit file |
| `[REPAIR_FILE]` | from `exec-critique INIT_ID COMPONENT repair 01` |
| `[REPAIR_DIFF]` | the controller's `git diff` of the repair |
| `[AUDIT_FILE]` | from `exec-critique INIT_ID COMPONENT audit 02` — never hand-built |
