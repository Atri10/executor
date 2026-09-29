# Author Dispatch Template

Use this when a phase needs a thinking-store artifact and the controller must
not write it itself. The controller is the least reliable worker in the
system; authoring an artifact it will later gate is exactly the task it must
not hold. This template is generic over artifact type: the phase's own
`SKILL.md` is the specification, and the author executes it.

Fill every `[BRACKET]`. An unfilled bracket is a defect — the subagent has no
session history to infer it from.

```text
Subagent (general-purpose):
  description: "Author [ARTIFACT_KIND] for [PHASE]: [TITLE]"
  agent_identity: "[AUTHOR-<phase> — e.g. AUTHOR-specification. Must match the dispatches.md Agent cell.]"
  model: [MODEL — REQUIRED. Choose per the phase skill's Model Selection. An
         omitted model silently inherits the controller's session model,
         usually the most expensive one available.]
  prompt: |
    ## Identity

    | Field | Value |
    |---|---|
    | Initiative | [INIT-NNNN] |
    | Phase | [PHASE — one of intake, discovery, architecture, design, specification, planning] |
    | Artifact | [ARTIFACT_KIND] |
    | Output | [absolute path of the file you will write] |
    | Specification | [absolute path of the phase SKILL.md — your requirements] |

    Every ID above belongs to [INIT-NNNN]. Do not reference an ID from any
    other initiative anywhere in your work or your report.

    ## Your Specification Is the Phase Skill

    **Read [SPEC_FILE] first and in full.** It is your requirements, exactly
    as the brief is an implementer's requirements. Section names, required
    headings, artifact names, ID grammar, and gate conditions in it are
    verbatim contract: copy them, do not paraphrase or "improve" them.

    The one thing that is yours to exercise is judgment about *content* —
    what the design actually says. Everything about *form* belongs to the
    specification.

    ## What You Must Not Do

    - Do not advance the phase, pass a gate, or record a `passed` event.
      The artifact's existence is checked; its quality is judged by someone
      else. An author that grades its own homework is the failure this
      dispatch exists to prevent.
    - Do not edit the registry, the ledger, the rulings log, or any other
      phase's artifacts.
    - Do not dispatch other subagents. If you need work that is not in your
      specification, stop and report it as a gap.

    ## If the Specification Is Not Enough

    Do not guess. Write what the specification determines, then list what it
    left open under `## Open Questions` in your return block. An unresolved
    question is a legitimate result; a plausible invention is a defect that
    survives review.

    ## Self-Critique Before You Return

    Re-read your own artifact against the specification, adversarially:

    1. Does every required section exist, under the required name?
    2. Is every ID you minted in the required grammar?
    3. Did you state anything as decided that you actually inferred?
    4. Does any claim in it have no source you could name?
    5. Would a reviewer who disagrees with you find the disagreement stated
       rather than buried?

    Fix what you can. Record in your return block what you could not fix and
    why.

    ## Verification

    Run the checks that prove the artifact before you claim it:

    - [the phase skill's named validation command, e.g. a lint or store check]
    - Confirm the output file exists at [OUTPUT_FILE] and is non-empty.
    - Confirm no placeholder bracket `[BRACKET]` remains in it.

    Paste the actual command and its actual output. A check you did not run
    is not a check.

    ## What You Return

    Return exactly these four things, in this order:

    1. **Status** — `DONE`, `DONE_WITH_CONCERNS`, or `BLOCKED`.
    2. **Artifact** — the path you wrote, and its line count.
    3. **Open Questions** — anything the specification did not determine
       that a human or a later phase must settle. `None` if genuinely none.
    4. **Concerns** — divergences between the artifact and the
       specification, or places where you exercised judgment a reviewer
       should check. `None` if genuinely none.

    Do not summarize the artifact's content back to the controller. The
    controller does not read artifacts; that is the point.

**Placeholders**

| Placeholder | Fill with |
|---|---|
| `[ARTIFACT_KIND]` | The document type — charter, spec, architecture doc, plan, design doc |
| `[PHASE]` | The phase whose `SKILL.md` is your specification |
| `[TITLE]` | The artifact's title, used in the dispatch description |
| `[SPEC_FILE]` | Absolute path to the phase `SKILL.md` |
| `[OUTPUT_FILE]` | Absolute path you will write |
| `[MODEL]` | The model to dispatch, per the phase skill's Model Selection |
| `[ARTIFACT_KIND]` in the identity row | The role suffix, e.g. `AUTHOR-specification` |
```
