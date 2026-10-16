# Plan Re-Auditor Prompt Template

Dispatch one fresh auditor per plan for rounds after the first. The
engine's dispatch brief names `target`, the minted `round`, and in
`context` the prior audit's findings plus the repair payload. You are
fresh: read the repair before the findings, because reading findings
first narrows you to what the first auditor looked for.

Fill every `[BRACKET]`. An unfilled bracket is a defect.

```
Subagent (general-purpose):
  description: "Re-audit plan [PLAN_ID] round [ROUND]"
  agent_identity: "AUDIT-<plan>-R<round>"
  model: [MODEL — REQUIRED: at least the prior auditor's tier.]
  prompt: |
    You are re-auditing one plan after a repair round. Verdict each prior
    finding and judge the repair's collateral across the whole plan set.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Audit target:** [PLAN_ID]
    **Round (the new audit you write):** [ROUND]
    **Dispatch:** [D<NNNNN>]
    **`respond_to`:** [absolute path of dispatches/D<NNNNN>/payload.json]

    ## Job 1 — Impact review of the repair, FIRST

    Read the repair payload first — the redrafted `tasks`/`sections` —
    and form your own view of what changed and what it might have broken
    across the set. Then re-run the mechanical checks in full: coverage
    unions, seam closure, ordering, vocabulary. A redraft that moves a
    `T<nn>` id, a `files` entry, or a seam name is tracked through every
    other plan.

    ## Job 2 — Closure

    Every prior `open` finding gets exactly one verdict in `status`:

    `fixed` (cause genuinely repaired, `evidence` pointing at the text) ·
    `open` (**the default** — an omission fails closed) ·
    `waived` (a human ruling accepted it) · `routed` (another plan's lane).

    ## The anti-laundering rule

    **Weakening is not addressing.** A finding closed by deleting a
    requirement, removing a `files`/`accepts` entry, loosening an exact
    value, or dropping an expected outcome is still `open` — and the
    weakening is itself a new `critical` finding. A redraft that only
    renames what the finding quoted is `open` plus `critical` for the
    laundering. A `T<nn>` renumber is not a fix; it is an orphaned
    finding.

    ## Edge Cases

    - **A prior finding's subject is gone** — the task or section
      deleted. Still `open`; the deletion is a new finding.
    - **The repair fixed the finding and broke a seam the prior audit
      never flagged** — a new finding at its own severity.
    - **The redraft touches only prose** — no task contract moved; every
      prior finding is `open` and the round is a no-op: say so.
    - **The repair closes a finding the prior audit never raised** —
      verdict only what the audit raised; record the mismatch in an
      `info` finding.

    ## What You Return

    ```json
    {"kind": "audit", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "target": "[PLAN_ID]", "round": [ROUND],
     "verdict": "PASS | FAIL",
     "findings": [{"id": "<prior finding id or H1>",
                   "severity": "critical | important | minor | info",
                   "claim": "…", "evidence": "§… — \"…\"",
                   "status": "fixed | open | waived | routed"}]}
    ```

    `round` echoes the minted round; `id`s echo prior finding ids where
    they answer one.
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
| `[MODEL]` | re-auditor model — at least the prior auditor's tier |
| `[INITIATIVE_ID]` / `[PLAN_ID]` | the plan under re-audit |
| `[ROUND]` | the round the engine minted |
| `[D<NNNNN>]` | the dispatch id |
