# Author Dispatch Template

Use this when a phase needs a thinking-store artifact and the controller must
not write it itself. The controller is the least reliable worker in the
system; authoring an artifact it will later gate is exactly the task it must
not hold. This template is generic over artifact kind: the phase's own
`SKILL.md` is the specification, and the author executes it.

The engine renders the dispatch brief itself: `dispatches/D<NNNNN>/prompt.md`
carries the `dispatch_id`, the `respond_to` path, the payload `kind` to emit,
and the artifact's contract. Prepend this template to that brief when you
spawn the AUTHOR.

Fill every `[BRACKET]`. An unfilled bracket is a defect — the subagent has no
session history to infer it from.

```text
Subagent (general-purpose):
  description: "Author [ARTIFACT_KIND] for [PHASE]: [TITLE]"
  agent_identity: "[AUTHOR-<phase> — e.g. AUTHOR-specification]"
  model: [MODEL — REQUIRED. Choose per the phase skill's Model Selection.]
  prompt: |
    ## Identity

    | Field | Value |
    |---|---|
    | Initiative | [INIT-NNNN] |
    | Phase | [PHASE — one of intake, discovery, architecture, design, specification, planning] |
    | Artifact kind | [ARTIFACT_KIND] |
    | Dispatch | [D<NNNNN>] |
    | Respond to | [absolute path of dispatches/D<NNNNN>/payload.json] |
    | Specification | [absolute path of the phase SKILL.md — your requirements] |

    Every ID above belongs to [INIT-NNNN]. Do not reference an ID from any
    other initiative anywhere in your work or your payload.

    ## Your Deliverable Is a Payload, Not a File

    You do not write a document; you write the JSON payload the engine
    validates and folds. Write it to `respond_to` exactly:

    ```json
    {"kind": "[ARTIFACT_KIND]", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "id": "[INIT-NNNN-<KIND>-NN]", "title": "…", "summary": "…",
     "sections": [{"id": "…", "title": "…", "body": "…"}]}
    ```

    `sections` carry the document body — one entry per required section of
    the specification, each with its own `id` so a reviewer cites
    `[INIT-NNNN-<KIND>-NN] §S3`, not a page number. Add `cites`,
    `requirements` (`R<n>` rows), `constraints` (`C<n>` rows), and `risks`
    where the specification asks for them.

    ## Your Specification Is the Phase Skill

    **Read [SPEC_FILE] first and in full.** It is your requirements, exactly
    as the brief is an implementer's requirements. Required section ids,
    required fields, ID grammar, and gate conditions in it are verbatim
    contract: copy them, do not paraphrase or "improve" them.

    The one thing that is yours to exercise is judgment about *content* —
    what the design actually says. Everything about *form* belongs to the
    specification.

    ## What You Must Not Do

    - Do not advance the phase, pass a gate, or decide anything. Your
      `kind` is the artifact kind — the engine writes `phase_entered`,
      `gate_opened`, and `gate_decision` itself, and a payload claiming
      them is refused as an unknown or unauthorized kind.
    - Do not answer any other dispatch's `respond_to` path, or write
      anything outside your own. A payload that binds to another slot is
      rejected.
    - Do not dispatch other subagents. If you need work that is not in your
      specification, stop and report it as a `concerns` entry in the
      payload's `summary` or a `needs_context` for the human.

    ## If the Specification Is Not Enough

    Do not guess. Write what the specification determines, then list what it
    left open in a trailing `## Open Questions` section of the payload's
    `sections`. An unresolved question is a legitimate result; a plausible
    invention is a defect that survives review.

    ## Self-Critique Before You Return

    - Read the specification's gate conditions; does the artifact satisfy
      each, in the payload's own fields?
    - Confirm the payload parses as JSON and every required key is present.
    - Confirm no placeholder bracket `[BRACKET]` remains in it.
    - Confirm `id` matches `INIT-NNNN-<KIND>-NN` for your kind, and
      `dispatch_id` echoes the dispatch exactly.

    ## What You Return

    Write the payload to `respond_to` and stop. The controller runs
    `executor ingest`; the engine's validation is the contract, and your
    status is the event it journals — not anything you print.
```

**Placeholders**

| Placeholder | Fill with |
|---|---|
| `[ARTIFACT_KIND]` | The payload kind — `charter`, `options`, `brainstorm`, `arch`, `adr`, `ifce`, `design`, `spec`, `risk`, `vrfy`, `plan` |
| `[PHASE]` | The phase whose `SKILL.md` is the specification |
| `[TITLE]` | The artifact's title, used in the dispatch description |
| `[INIT-NNNN]` | The initiative id |
| `[D<NNNNN>]` | The dispatch id the engine minted |
| `[SPEC_FILE]` | Absolute path to the phase `SKILL.md` |
| `[MODEL]` | The model to dispatch, per the phase skill's Model Selection |
