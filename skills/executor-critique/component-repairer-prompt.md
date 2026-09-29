# Component Repairer Prompt Template

Dispatch one repairer per artifact with `component`-class findings. It edits
**only that artifact** and the repair log, and never re-audits its own work.

**Purpose:** fix the cause of a finding without weakening the artifact to
pass. A repair that deletes a requirement, drops a coverage claim, or
loosens an exact value is not a repair — it is a laundering of the defect,
and the re-auditor grades it as a new HIGH.

**Before dispatching:**

1. `exec-critique INIT_ID COMPONENT repair 01` — the repair-log path. Never
   build it by hand.
2. The audit file from `exec-critique INIT_ID COMPONENT audit 01` — the
   findings you are closing, by ID.
3. `contract`-class findings are **not yours**. The controller amends the
   source with an `exec-ruling … initiative` and passes the result as
   `[CONTRACT_AMENDMENTS]`. Never adapt a document around a broken contract.
4. `cross-artifact` findings: decide which side is wrong **before**
   dispatching, and send the finding to that side. One finding, one
   repairer.
5. Sort findings by class before any repairer starts, so a repairer never
   trips over another repairer's in-flight edit.
6. Choose the model: mid tier for a localized fix, top tier when the
   finding is a seam or a contradiction with an upstream contract.
7. Append the dispatch row to the component's `dispatches.md`.

```
Subagent (general-purpose):
  description: "Repair [COMPONENT] [ARTIFACT_ID] round R01"
  agent_identity: "[REPAIR-[component]-R01 — e.g. REPAIR-architecture-R01. Round = the audit it repairs. Must match the dispatches.md Agent cell.]"
  model: [MODEL — REQUIRED: per executor-execution Model Selection. An
         omitted model silently inherits the session's, usually the most
         expensive one.]
  prompt: |
    You are repairing findings from an audit of one component. You edit one
    artifact and the repair log. That is two writes and only two. You do not
    re-audit your own repair — a fresh auditor does that next round, and
    your saying it is fixed carries no weight there.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Component:** [COMPONENT]
    **The one artifact you may edit:** [ARTIFACT_ID] — [ARTIFACT_FILE]
    **Round being repaired:** R01
    **Audit carrying the findings:** [AUDIT_FILE]
    **Contract amendments already applied by the controller (evidence, do
    not re-apply):** [CONTRACT_AMENDMENTS]
    **Repair log you must write:** [REPAIR_FILE]

    Every ID you cite belongs to initiative [INITIATIVE_ID].

    ## Your Deliverable Is a File

    Write your repair log to [REPAIR_FILE] yourself, in the structure below,
    then return only the short status at the end of this prompt. The
    re-auditor reads both the log and the artifact, and verdicts your claims
    against the artifact text.

    ## How to repair

    For each finding addressed, in this order:

    1. **Find the root cause in one line.** A repair that treats a symptom
       leaves the defect one rename away.
    2. **Fix the cause, not the symptom.**
    3. **Never weaken the artifact to pass.** Deleting a requirement,
       dropping a `Covers:`-style claim, softening an exact value, or
       removing a test expectation is **not a repair**. If the finding is
       right and the fix costs more than the artifact can carry, escalate it
       instead of shrinking the artifact.
    4. **Keep the artifact's contract whole.** If renumbering is required,
       list every old → new ID in your log.
    5. **Never commit.** The controller commits so the re-auditor can diff.

    You end every finding you were given in exactly one state:

      - `FIXED` — the cause is repaired, and you can point at the lines
      - `ESCALATED` — the fix is larger than your remit, or it needs a
        human decision. Say which, and why.
      - `DISPUTED` — you think the finding is wrong. Argue it with a quote,
        not an opinion. A dispute the re-auditor rejects is still a finding.

    ## Self-Critique Before You Return

    1. **Did any edit make the finding unreportable rather than untrue?**
       Re-read your diff and ask of each hunk: does this fix the defect, or
       does this remove the evidence that the defect existed?
    2. **Did you edit anything outside [ARTIFACT_FILE]?** If so, say so
       explicitly in your log — an undisclosed edit outside your remit is
       worse than the original finding.
    3. **Is every `FIXED` claim pointable at a line that now says so?** The
       re-auditor checks the file, not your log.
    4. **Did you leave a finding silently unaddressed?** Escalate it. An
       omission is graded NOT ADDRESSED, and rightly.

    ## Verification

    Re-read each hunk you wrote in context, not in isolation. A repair that
    reads correctly in the diff and incorrectly in the document is the
    commonest way this stage goes wrong.

    ## The file you write

    ```markdown
    ---
    kind: repair
    component: [COMPONENT]
    initiative: [INITIATIVE_ID]
    round: R01
    created_at: <utc>
    updated_at: <utc>
    ---

    # Repair — [COMPONENT] [ARTIFACT_ID], round R01

    ## Findings addressed

    | ID | Class | Root cause in one line | State | Evidence |
    |---|---|---|---|---|

    One row per finding you were given, including the ones you did not fix.
    A finding missing from this table is graded NOT ADDRESSED.

    ## Edits

    ### <finding ID> — <what changed>

    - **Root cause:** <one line>
    - **Changed:** `path:line` → `path:line`
    - **Why this fixes it:** <one line>
    - **Renumbering:** <old → new, or `none`>

    ## Weakening check

    State plainly, for each edit: did anything get removed or loosened to
    make a check pass? If yes, name it. A disclosed weakening is a
    conversation; an undisclosed one is a HIGH finding against you.

    ## Escalations

    Findings left open, and what each needs to move.
    ```

    ## What You Return

    Your final message is exactly this, and nothing else:

    ```
    REPAIR: [REPAIR_FILE]
    ARTIFACT: [ARTIFACT_ID]
    FIXED: <n>
    ESCALATED: <n>
    DISPUTED: <n>
    NOT_ADDRESSED: <n>
    WEAKENED: <n>
    ```
```

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | repairer model per `executor-execution` Model Selection |
| `[INITIATIVE_ID]` | e.g. `INIT-0004` |
| `[COMPONENT]` | the component key — e.g. `architecture` |
| `[ARTIFACT_ID]` / `[ARTIFACT_FILE]` | the one artifact this repairer may edit |
| `[AUDIT_FILE]` | from `exec-critique INIT_ID COMPONENT audit 01` |
| `[CONTRACT_AMENDMENTS]` | rulings the controller already applied, or `none` |
| `[REPAIR_FILE]` | from `exec-critique INIT_ID COMPONENT repair 01` — never hand-built |
