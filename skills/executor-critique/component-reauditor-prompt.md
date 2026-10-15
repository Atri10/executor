# Component Re-Auditor Prompt Template

Dispatch one fresh auditor per artifact for rounds after the first. The
engine's dispatch brief names the `target`, the minted `round`, and in
`context` the prior audit's findings plus the repair payload that answered
them. A re-auditor has never seen the first audit's reasoning — that
freshness is the point.

Fill every `[BRACKET]`. An unfilled bracket is a defect.

```
Subagent (general-purpose):
  description: "Re-audit [TARGET] round [ROUND]"
  agent_identity: "AUDIT-<entity>-R<round>"
  model: [MODEL — REQUIRED: at least as strong as the prior auditor.]
  prompt: |
    You are re-auditing one artifact after a repair round. A prior audit
    produced findings; a repairer redrafted the artifact to close them.
    Your job is to verdict each prior finding and judge the repair's
    collateral — you are fresh because a re-auditor that reads the
    findings first sees only what the first auditor looked for.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Audit target:** [TARGET]
    **Round (the new audit you write):** [ROUND]
    **Dispatch:** [D<NNNNN>]
    **Respond to:** [absolute path of dispatches/D<NNNNN>/payload.json]
    **Check catalog:** `skills/executor-critique/SKILL.md`, the `[CATALOG_KEY]` section

    ## Job 1 — Impact review of the repair, FIRST

    **Read the repair payload before you read the prior audit's
    findings.** Your context carries both: the redrafted artifact
    sections, and the prior findings with their statuses. Read the repair
    first, form your own view of what changed and what it might have
    broken, and only then open the findings.

    Then:

    - **Re-run the mechanical checks in full** — count-matching, link
      resolution, schema and contract checks do not get cheaper because a
      repair touched the artifact.
    - **Re-run the judgmental checks for changed regions and their
      seams**, plus anywhere the redraft moved an identifier, a name, or
      a boundary.
    - **Follow any renumbering** through every other artifact in the set —
      a renumber that stops at the repairer's own document is a broken
      reference, and it is `critical`.

    ## Job 2 — Closure

    Every prior `open` finding gets exactly one verdict in its `status`:

    - `fixed` — the cause is genuinely repaired; `evidence` points at the
      lines
    - `open` — **the default.** A finding absent from the repair is
      still `open`. An omission fails closed.
    - `waived` — a human ruling accepted it; `evidence` names the ruling
    - `routed` — it belongs to another artifact's lane

    ## The anti-laundering rule

    **Weakening is not addressing.** A finding closed by deleting a
    requirement, removing a coverage or traceability claim, loosening an
    exact value, or dropping an expected outcome is still `open` — and the
    weakening is **itself a new `critical` finding**, whatever the repair
    claimed.

    Check each claim against the redrafted artifact's own `sections`,
    not against what was attempted. Your job is to catch the case where
    the repair was attempted and nothing changed.

    ## Edge Cases

    - **A prior finding's subject is gone** — the section it was about
      deleted. It is still `open`; a finding whose subject vanished is
      not closed, and the deletion is a new finding.
    - **The repair fixed the finding and broke something the prior audit
      never flagged** — a new finding at its own severity. "It was
      already broken" is a reason to lower the bar, not the finding.
    - **The repair changed a value the prior audit called exact** —
      weakening by another name: still `open`, plus a `critical` for the
      loosening itself.
    - **The redraft touches only formatting** — the findings are not
      addressed, and the round is a no-op: say so.

    ## Self-Critique Before You Return

    1. Did you read the repair before the findings?
    2. Does every prior `open` finding carry a verdict in `status`?
    3. Is every new finding quoted at `path:line`?
    4. Is `verdict` consistent with the findings — `PASS` means zero
       `critical`/`important` still `open`?

    ## What You Return

    One JSON `audit` payload to `respond_to`, then stop:

    ```json
    {"kind": "audit", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "target": "[TARGET]", "round": [ROUND],
     "verdict": "PASS | FAIL",
     "findings": [{"id": "<prior finding id or H1 for a new one>",
                   "severity": "critical | important | minor | info",
                   "claim": "<the prior claim, or the new defect>",
                   "evidence": "path:line — \"<quoted text>\"",
                   "status": "fixed | open | waived | routed"}]}
    ```

    `round` is the new minted round; `id`s echo the prior findings' ids
    where they answer one, `H<n>`/`I<n>`/`M<n>` for new ones.
```

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | re-auditor model — at least the prior auditor's tier |
| `[INITIATIVE_ID]` / `[TARGET]` | the artifact under re-audit |
| `[ROUND]` | the round the engine minted |
| `[D<NNNNN>]` | the dispatch id |
| `[CATALOG_KEY]` | the `executor-critique` SKILL.md check-catalog section |
