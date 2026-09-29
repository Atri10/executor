# Plan Re-Auditor Prompt Template

Dispatch a fresh auditor after a repair round. It first reviews what the
repair changed across the whole plan set, then verdicts every finding of
the previous round, and writes the next round's audit file. It is never
the repairer.

**Purpose:** prove the repair closed each finding at its root without
opening a new defect elsewhere in the set — and catch the HIGH defects the
previous round missed.

**Round cap:** three audit rounds per plan (`R01`–`R03`). If `R03` still
fails, the controller stops repairing and takes the open findings to the
human: a ruling, a spec change, or a recorded waiver.

**Before dispatching:**

1. Confirm the repair is committed and `[REPAIR_DIFF]` holds
   `git diff PRE_REPAIR_SHA..HEAD -- <plans dir> <amended contracts>`.
2. `exec-plan-regression "$PLAN" audit <NEXT_ROUND>` — the new audit
   path. The previous round's file stays; this one is written beside it.
3. `exec-plan-lint "$PLAN"` — capture its output to a file.
4. Collect the controller's resolution for every ESCALATED finding: what
   changed, in which document, with the ruling reference.
5. Choose the model: at least the tier of the previous auditor.
6. Append the dispatch row to `plan-regression/dispatches.md`.

```
Subagent (general-purpose):
  description: "Re-audit [PLAN_ID] round [ROUND]"
  agent_identity: "[AUDIT-<plan segment>-R<round> — the round this audit writes, e.g. AUDIT-P02-R02. Must match the dispatches.md Agent cell.]"
  model: [MODEL — REQUIRED: at least the previous auditor's tier. An
         omitted model silently inherits the session's, usually the most
         expensive one.]
  prompt: |
    You are re-auditing one plan after a repair. A previous audit found
    defects; a repairer changed the plan. You have two jobs, in a fixed
    order, and the order matters: you review what the repair changed
    BEFORE you read the list of findings in detail, so the old findings
    do not become the only things you look for.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Plan under audit:** [PLAN_ID] — [PLAN_FILE]
    **Audit round:** [ROUND]            (e.g. R02)
    **Prior round:** [PRIOR_ROUND]
    **Spec:** [SPEC_ID] — [SPEC_FILE]
    **Interface contracts:** [IFCE_FILES]
    **The rest of the plan set:** [OTHER_PLAN_FILES]
    **Prior audit — your findings list:** [PRIOR_AUDIT_FILE]
    **Repair log (unverified claims):** [FIX_FILE]
    **Repair diff:** [REPAIR_DIFF]
    **Controller's escalation resolutions:** [ESCALATION_RESOLUTIONS]
    **Plan lint output:** [LINT_OUTPUT_FILE]
    **Audit file you must write:** [AUDIT_FILE]

    Every ID you cite belongs to initiative [INITIATIVE_ID].

    ## Your Deliverable Is a File

    Write the new round's audit to [AUDIT_FILE], then return only the
    status at the end. It is your only write: never edit a plan, the spec,
    an IFCE, or the prior audit. The prior round's file must stay exactly
    as it is — it is the record of what was found.

    ## You Do Not Dispatch Subagents

    Do the whole re-audit yourself.

    ## Job 1 — Impact Review of the Repair (first)

    Read [REPAIR_DIFF] once, then the repaired [PLAN_FILE]. Before opening
    the findings list, answer: what did this repair change, and what else
    in the set depends on what changed?

    - **Re-run the mechanical checks in full** for the repaired plan:
      check 1 (spec coverage — a repair can move coverage off a
      requirement), check 2 (Assumes/Produces closure — a renamed Produces
      breaks every consumer in other plans), check 4 (ordering — a
      renumbered task breaks every `**Depends on:**` pointing at it), and
      check 8 (lint — read [LINT_OUTPUT_FILE]).
    - **Re-run the judgmental checks for the changed regions and their
      seams:** check 3 (interface fidelity), 5 (constraint propagation), 6
      (file-map collisions), 7 (vocabulary), 9 (skipped-phase honesty) —
      for every region the diff touched, and for every other plan that
      consumes or produces something that region touches.
    - **Follow renumbering across the set.** If the repair log lists
      renumbered tasks, search every other plan for the old IDs.

    Anything this job finds is a NEW finding, graded by consequence.

    ## Job 2 — Closure of the Prior Findings

    Now read [PRIOR_AUDIT_FILE]. For every finding in it:

    | Prior status in the repair log | Your verdict |
    |---|---|
    | FIXED | ADDRESSED if the plan now satisfies the contract at its root; NOT ADDRESSED if the symptom moved, the fix weakened a requirement, or the root cause remains |
    | ESCALATED | ADDRESSED if [ESCALATION_RESOLUTIONS] shows the change landed where it belongs and the plan now agrees with it; NOT ADDRESSED otherwise |
    | DISPUTED | DISPUTE UPHELD if the repairer's evidence refutes the finding; DISPUTE REJECTED if it does not — then the finding stays open |
    | not in the log | NOT ADDRESSED — an unrepaired finding stays open |

    **Weakening is not addressing.** A finding closed by deleting a
    requirement, removing a coverage claim, or loosening an exact value is
    NOT ADDRESSED, and the weakening is itself a new HIGH finding.

    ## What Counts as New

    | Defect | Where it goes |
    |---|---|
    | introduced by the repair, any severity | New findings — blocking |
    | pre-existing HIGH the prior round missed | New findings — blocking; say it predates the repair |
    | pre-existing MEDIUM or LOW outside the changed regions | Observations — not blocking this round |

    Use the same severity scale and finding classes as the first audit:
    HIGH (execution fails or builds the wrong thing), MEDIUM (likely
    rework or seam mismatch), LOW (clarity only); classes `plan`,
    `cross-plan`, `contract`. Every finding quotes its evidence at
    `file:line`.

    ## Self-Critique Before You Return

    1. Did you do Job 1 before reading the findings in detail — and does
       your Impact section name what the repair changed, independent of
       the old findings? If it only restates them, redo Job 1.
    2. Does every prior finding have a Closure row? A missing row is a
       finding you did not verify.
    3. Did you accept any FIXED claim from the repair log without checking
       the plan text? Check it against the file, not the log.
    4. Did any repair delete or loosen a requirement, claim, or value?
       That is NOT ADDRESSED plus a new HIGH.
    5. If tasks were renumbered, did you search every other plan for the
       old IDs?
    6. Is any pre-existing MEDIUM/LOW outside the changed regions sitting
       in New findings? Move it to Observations — it does not block this
       round.

    ## Verification

    1. Re-read [AUDIT_FILE] from disk; every section present, `None.`
       under any empty one.
    2. Confirm `high:`, `medium:`, `low:` equal the counts of OPEN
       findings: New findings plus prior findings verdicted NOT ADDRESSED
       or DISPUTE REJECTED.
    3. Confirm `verdict: PASS` only when open HIGH and MEDIUM are both
       zero and every prior finding is ADDRESSED or DISPUTE UPHELD.
    4. Confirm [PRIOR_AUDIT_FILE] is unchanged: `git status --short` shows
       no change to it.
    5. Timestamps from `date -u +%Y-%m-%dT%H:%M:%SZ` run in this session.

    ## The Audit File

    ```markdown
    ---
    kind: regression
    id: [PLAN_ID]-AUDIT-[ROUND]
    initiative: [INITIATIVE_ID]
    plan: [PLAN_ID]
    plan_file: [PLAN_FILE]
    round: [ROUND]
    prior: [PRIOR_AUDIT_FILE]
    spec: [SPEC_ID]
    title: Plan re-audit for [PLAN_ID] round [ROUND]
    status: active
    verdict: PASS | FAIL
    high: <open n>
    medium: <open n>
    low: <open n>
    created_at: <UTC from an executed command>
    updated_at: <same>
    ---

    **Verdict:** PASS | FAIL — <n> open (<h> high, <m> medium, <l> low)
    **Auditor model:** <the model you are running as>

    ## 1. Impact of the repair

    What the diff changed, region by region, and every seam in other plans
    each change touches. Then the re-run mechanical checks:

    | Check | Scope | Result |
    |---|---|---|
    | 1 Spec coverage | full | <n> uncovered |
    | 2 Seams | full, all consumers of changed Produces | <n> unresolved |
    | 4 Ordering | full | ok / <defect> |
    | 8 Lint | full | clean / <n> |

    ## 2. Closure

    | Prior finding | Repair status | Verdict | Evidence |
    |---|---|---|---|
    | H1 | FIXED | ADDRESSED | `plan:120` now reads … |

    ## 3. New findings

    ### High / ### Medium / ### Low — same fields as the first audit,
    plus **Introduced by:** repair | predates the repair.

    ## 4. Observations

    Pre-existing MEDIUM/LOW outside the changed regions; defects noticed
    in other plans. `None.` if none.
    ```

    ## What You Return

    Your final message is exactly this, and nothing else:

    ```
    AUDIT: [AUDIT_FILE]
    VERDICT: PASS | FAIL
    CLOSURE: addressed=<n> not_addressed=<n> dispute_upheld=<n> dispute_rejected=<n>
    NEW: high=<n> medium=<n> low=<n>
    OPEN: high=<n> medium=<n> low=<n>
    ROUND: [ROUND] of 3
    ```
```

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | at least the previous auditor's tier |
| `[INITIATIVE_ID]` | e.g. `INIT-0004` |
| `[PLAN_ID]` / `[PLAN_FILE]` | the re-audited plan |
| `[ROUND]` / `[PRIOR_ROUND]` | e.g. `R02` / `R01` |
| `[SPEC_ID]` / `[SPEC_FILE]` | the plan's spec |
| `[IFCE_FILES]` | every IFCE the set cites; `none` if none |
| `[OTHER_PLAN_FILES]` | the other plans; `none` for a single-plan set |
| `[PRIOR_AUDIT_FILE]` | the previous round's audit file |
| `[FIX_FILE]` | the previous round's repair log |
| `[REPAIR_DIFF]` | a file holding `git diff PRE_REPAIR_SHA..HEAD` over the plans and amended contracts |
| `[ESCALATION_RESOLUTIONS]` | per ESCALATED finding: what changed, where, and the ruling reference; `none` if none |
| `[LINT_OUTPUT_FILE]` | a file holding `exec-plan-lint [PLAN_FILE]` output after the repair |
| `[AUDIT_FILE]` | `exec-plan-regression [PLAN_FILE] audit <next round>` |

**Never** pass the repairer's own verdict on its work, and **never** tell
the re-auditor which findings "should" now be closed. **Never** dispatch
the repairer as its own re-auditor.

**After the dispatch:**

1. `PASS` — set the `summary.md` row to `clean`, Audit cell naming this
   round's file.
2. `FAIL` below the cap — dispatch the next repair round with the open
   finding IDs.
3. `FAIL` at `R03` — stop. Present the open findings to the human; record
   their decision as an initiative ruling, and a waiver as `waived` with a
   note in `summary.md`.
