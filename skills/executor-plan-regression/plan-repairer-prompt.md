# Plan Repairer Prompt Template

Dispatch one repairer per plan after a failed audit round. It redrafts
**only that plan** — a new `plan` payload — and never grades its own work.
`contract`-class findings are amended at their source by the controller
and passed in `context`; never adapt the plan around a broken contract.

Round cap: at most `max_audit_rounds` audit rounds per plan. A repairer at
the last round reports what it could not close concretely enough for a
human to settle.

Fill every `[BRACKET]`. An unfilled bracket is a defect.

```
Subagent (general-purpose):
  description: "Repair plan [PLAN_ID] round [ROUND]"
  agent_identity: "REPAIR-<plan>-R<round>"
  model: [MODEL — REQUIRED: mid tier for localized fixes, top tier for
         seams and contract contradictions.]
  prompt: |
    You are repairing findings from a plan audit. You write one redrafted
    `plan` payload — the whole plan, repaired — to `respond_to`. That is
    your only write.

    ## Identity

    **Initiative:** [INITIATIVE_ID]
    **Plan you redraft:** [PLAN_ID]
    **Round being answered:** [ROUND]
    **Dispatch:** [D<NNNNN>]
    **Respond to:** [absolute path of dispatches/D<NNNNN>/payload.json]
    **Findings assigned to you:** the `open` `plan`/`cross-plan` findings
    in your context
    **Contract amendments already applied (evidence, not yours):** the
    `routed` findings in your context

    ## Scope

    The assigned `open` findings are your scope. You write the whole plan:
    the un-finding'd `sections` carry over unchanged — a repair is a
    redraft, not a rewrite.

    ## How to repair

    - **Fix the cause.** A `Consumes` nothing produces is not closed by
      deleting the `Consumes` — it is closed by producing it, or by
      naming the producer that already exists. `class` findings are
      patterns: fix every instance `class_hint` names.
    - **Never weaken to pass.** Dropping a requirement, loosening an
      `accepts` criterion, or deleting a `files` entry that should stay
      is laundering — the re-auditor grades it `critical`.
    - **Task ids are stable.** `INIT-NNNN-PNN-TNN` ids are how dispatches
      and verdicts address the work — renumbering a task to hide a
      finding orphans its record.

    ## Edge Cases

    - **A finding's evidence names a different plan** — do not touch it:
      record it in `summary`-adjacent `sections` text; the controller
      routes.
    - **A `contract` finding assigned anyway** — `routed`, never repaired.
    - **A defect no assigned finding covers** — record it in `risks` or a
      `concerns` section with `§<section>` and the quote; the next audit
      owns it.

    ## What You Return

    ```json
    {"kind": "plan", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "id": "[PLAN_ID]", "plan_id": "[PLAN_ID]",
     "title": "…", "summary": "…", "objective": "…",
     "sections": [{"id": "S1", "title": "…", "prose": "…",
                   "bullets": ["…"],
                   "tables": [{"columns": ["…"], "rows": [["…"]]}],
                   "code": [{"lang": "…", "source": "…"}]}],
     "tasks": [{"id": "T03", "title": "…", "goal": "…",
                "files": ["…"], "accepts": ["…"],
                "depends_on": ["T01"]}],
     "more_plans": false}
    ```

    A section is data, not markdown: `prose`, `bullets`, `tables`
    (`columns` plus `rows`), and `code`, with the engine rendering the
    `.md`. A pipe table or a fence inside a string is a schema rejection.

    `id`/`plan_id` echo the target exactly; task `id`s are the short
    `T<nn>` the fold prefixes into `INIT-NNNN-PNN-TNN` — renumbering one
    orphans its dispatch record. `depends_on` names short task ids;
    `consumes`/`provides` carry the seam vocabulary the auditor's check 2
    resolves. `more_plans` says whether later plans follow — flipping it
    silently reshapes the phase.

    The journal's `repairs/R<NN>` records the round; your payload is the
    new truth the re-auditor grades.
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
| `[MODEL]` | repairer model, scaled to finding class |
| `[INITIATIVE_ID]` / `[PLAN_ID]` | the plan under repair |
| `[ROUND]` | the round the engine minted |
| `[D<NNNNN>]` | the dispatch id |
