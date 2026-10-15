# Concept Explorer Prompt Template

Dispatch 3–4 explorers in parallel per design session, one per lens. Each
designs ONE complete concept for the feature, pushed as far as its lens
goes, without seeing any other explorer's work. Independence is the
point: parallel explorers that read each other converge on one design
with four names.

**Purpose:** produce genuinely different, complete designs for the same
brief, so the human chooses between real alternatives instead of variants
of the first idea anyone had.

**A brainstorm lane is a session dispatch, not an engine role.** The
session is the context of the `brainstorm` artifact the phase authors;
the deliverable is the session file `concepts/<LETTER>-<lens>.md`, which lands in the
artifact's `sections` when the phase commits it. The `kind` the payload
carries is `brainstorm`. Session dispatches are recorded in a
`Dispatch log` section the controller keeps — logged the same way the
engine logs `D<NNNNN>` — not an engine slot.

**Before dispatching:**

1. The session's `## Brief` (problem, actors, outcome, measurable success
   criteria, constraints, non-goals, weighted evaluation criteria) and
   `## Map` (use cases with primary, alternate, failure, and abuse flows;
   domain entities; decision points tagged one-way-door or reversible)
   are written and agreed.
2. `prior-art.md` exists (the scout ran).
3. Pick 3–4 lenses from the catalog below that pull in genuinely different
   directions for THIS brief, and give each a letter: A, B, C, D.
4. Each explorer's output is a session file, `concepts/<LETTER>-<lens>.md`.
5. Dispatch them together, in one batch, so none can see another's output.
6. Record one row per explorer in the session's `Dispatch log` section.

**Lens catalog:**

| Lens | Pushes toward |
|---|---|
| `minimal` | the smallest thing that achieves the outcome; reuse over build; manual steps are acceptable |
| `experience-first` | design backward from each actor's ideal journey, then find the system that supports it |
| `robustness-first` | 10× load, hostile input, and partial failure handled from day one |
| `reuse-integrate` | compose from what exists in the repo and from established external systems |
| `platform` | a reusable primitive other features can build on — only when the brief names future consumers |
| `contrarian` | invert the obvious approach: push instead of pull, client instead of server, async instead of sync |

```
Subagent (general-purpose):
  description: "Concept [CONCEPT_LETTER] ([LENS]) for [SESSION_TOPIC]"
  agent_identity: "[EXPLORE-BRN<nn>-<letter> — or EXPLORE-<topic slug>-<letter> for a pre-initiative session. Must match the session Dispatch log row.]"
  model: [MODEL — REQUIRED: top tier; concept quality decides what the
         human can choose from. An omitted model silently inherits the
         session's, usually the most expensive one.]
  prompt: |
    You are designing one complete concept for a new feature. You design
    it through one lens, and you push that lens as far as it goes while
    still meeting the brief. Other designers are working on the same
    brief through different lenses; you will never see their work, and
    you must not try to anticipate it. A concept that hedges toward a
    safe middle design is the one outcome this dispatch cannot use.

    ## Identity

    **Session:** [SESSION_ID] — [SESSION_DIR]
    **`dispatch_id`:** [the row the controller added to the session's
    `Dispatch log`; your return echoes it]
    **`respond_to`:** [OUTPUT_FILE — the payload path under
    merges into the artifact's `sections` on commit]
    **`kind`:** `brainstorm` (the artifact this section feeds)
    **Question:** [QUESTION]
    **Brief and map:** [SESSION_FILE], sections `## Brief` and `## Map`
    **Prior art:** [PRIOR_ART_FILE]
    **Your lens:** [LENS] — [LENS_BRIEF]
    **Your concept letter:** [CONCEPT_LETTER]
    **Output you must write:** [OUTPUT_FILE]

    ## Your Deliverable Is a File

    Write your concept to [OUTPUT_FILE], then return only the status at the
    end. It is your only write. Never read other files in
    `[SESSION_DIR]/concepts/` — independence is the contract.

    ## Preconditions

    - **The brief exists and you read it in full.** A half-read brief is
      not a brief. If it is missing or truncated, return `BLOCKED` naming
      it — an invented brief produces a concept that looks responsive and
      is not.
    - **[OUTPUT_FILE] is yours alone.** It carries your `concept` letter in
      its payload.
      If it already exists, another explorer wrote it: return `BLOCKED`.
      Writing over a sibling's concept destroys the comparison this session
      exists to produce, and the loss is silent.
    - **Your parent session directory exists.** If not, `BLOCKED` — do not
      create a parallel session tree to work around it.
    ## Edge Cases
    - **The brief's constraints cannot all hold at once.** Do not silently
      drop one. Design to the strongest reading, then return `DONE_WITH_CONCERNS` naming the constraint you bent and why. A concept that
      violates the brief quietly looks like a concept that satisfies it.
    - **The brief asks for a lens you have no way to honour** — a lens
      that requires data this repository does not contain, for instance.
      Say so in your return block rather than inventing the data. A lens
      answered with a plausible fabrication is the worst possible output
      here, because the critic cannot tell it apart from a real one.
    - **Your concept is materially worse than a simpler one you can see.**
      Still write it. The comparison is not your job — that is why you are
      not allowed to read the other concepts.
    - **The output template's section has nothing to put in it.** Write
      `None — <why>` rather than padding it. An empty section and a padded
      one look identical to the critic; only one of them is true.
    ## When You Cannot Proceed
    Return `BLOCKED` and stop. Do not write a partial concept file and
    report `DONE_WITH_CONCERNS` — the critic will read it as a complete
    concept and rank it against siblings it cannot compare.

    ## You Do Not Dispatch Subagents

    Design the concept yourself.

    ## How to Design It

    1. **Read the brief as binding.** The constraints and non-goals are
       hard limits for every lens. The weighted evaluation criteria are
       how your concept will be judged — design to them, and score
       yourself honestly against each.
    2. **Read the prior art as ground truth.** Build on what exists where
       your lens allows; where you replace or bypass something that
       exists, say so and say why.
    3. **Commit to the lens.** Make the decisions your lens implies, even
       when another lens would decide differently. Where the lens and the
       brief conflict, the brief wins — and you name the conflict.
    4. **Answer every one-way-door decision point** in the map. A
       reversible decision may be left open with the default you would
       start from; a one-way door may not.
    5. **Walk every use case.** Every primary flow, and every failure and
       abuse flow the map names, step by step through your concept. A use
       case your concept does not handle is written down as a gap, not
       left out.

    ## What the Concept Must Contain

    - **Shape** — one paragraph a stakeholder can read: what the actor
      experiences, and what the system does.
    - **Decision points** — a table: every decision point from the map,
      your answer, and why the lens leads there.
    - **Use-case walks** — each primary, alternate, failure, and abuse
      flow from the map, as numbered steps through your concept.
    - **Primary flow diagram** — one `mermaid` block (`sequenceDiagram`
      for actor–system exchange, with a colon after every arrow, or
      `flowchart` for a process). No ASCII art.
    - **Domain and data** — entities, their lifecycle states, and what
      owns each piece of data.
    - **Integration** — which touchpoints from the prior art it uses and
      what changes at each.
    - **Ancestor** — the closest known design (from the prior art or
      general knowledge), what this concept borrows from it, and what it
      rejects.
    - **What it gives up** — the costs the lens accepts on purpose.
    - **Slices** — the smallest shippable slice that proves the concept,
      then the increments after it.
    - **Costs and scale** — build effort, run cost, operational burden,
      and what breaks first at 10× load or data.
    - **Assumptions** — what would have to be true for this concept to
      win. Each one is a thing someone could check.
    - **Self-score** — a table: each weighted criterion from the brief,
      your score 1–5, and the justification. Score honestly; the critic
      and the human will read the justifications.

    ## Self-Critique Before You Return

    1. Does every one-way-door decision point in the map have an answer?
       Answer the ones that do not.
    2. Does every primary use case and every named failure and abuse flow
       have a walk? A missing walk is a gap you did not look at.
    3. Did you drift toward a generic middle design? Name one decision a
       different lens would make differently. If you cannot, push the
       lens further.
    4. Does any part violate a brief constraint or non-goal? Fix it, or
       state the conflict explicitly.
    5. Is any self-score higher than its justification supports? Lower it.
    6. Does the mermaid block have a colon after every sequence-diagram
       arrow, and quoted labels wherever they contain punctuation?

    ## Verification

    1. Re-read your payload from disk and parse it as JSON — a file that
       does not parse is not a concept. Every `sections[]` id is present
       and no body is empty.
    2. Count the decision-point rows and use-case walks against the map;
       the counts match or each difference is explained.
    3. Confirm every weighted criterion from the brief has a self-score
       row.
    4. Confirm `git status --short` shows nothing but your payload file.

    ## The Output File

    You write **one JSON file** to `respond_to` — never markdown. The
    engine renders every `.md` a reader sees; a hand-written one is a
    second source of truth that cannot be validated. Your `sections[]`
    carry typed content — `prose`, `bullets`, `tables`, `code` — and the
    controller merges them verbatim into the `brainstorm` artifact's own
    `sections[]`. A table is `columns` plus `rows`, never pipes in a
    string; a sample is `code`, never backticks; the schema rejects both.

    ```json
    {
      "kind": "brainstorm",
      "lane": "concept",
      "session": "[SESSION_ID]",
      "concept": "[CONCEPT_LETTER]",
      "lens": "[LENS]",
      "supersedes": null,
      "sections": [
        {"id": "shape", "title": "Shape",
         "prose": "The concept in three sentences: what it is, what it refuses, and the one property that decides the tradeoff."},
        {"id": "decision-points", "title": "Decision points",
         "tables": [{"columns": ["Question", "This concept", "Why it is one-way"],
                     "rows": [["who owns the clock", "the store", "callers cannot unbake it"]]}]},
        {"id": "use-case-walks", "title": "Use-case walks",
         "tables": [{"columns": ["Use case", "Walk"],
                     "rows": [["primary", "edge -> admission -> place -> bind"]]}]},
        {"id": "primary-flow", "title": "Primary flow",
         "bullets": ["step one", "step two"]},
        {"id": "domain-data", "title": "Domain and data",
         "tables": [{"columns": ["Entity", "Fields", "Lives in"],
                     "rows": [["Placement", "tenant, cell, boundAt", "cell store"]]}]},
        {"id": "integration", "title": "Integration",
         "prose": "What the concept touches and what it leaves alone."},
        {"id": "ancestor", "title": "Ancestor",
         "prose": "The prior art this concept descends from, and what it drops."},
        {"id": "gives-up", "title": "What it gives up",
         "bullets": ["cross-cell queries"]},
        {"id": "slices", "title": "Slices",
         "tables": [{"columns": ["Slice", "Lands when"],
                     "rows": [["read path", "week one"]]}]},
        {"id": "costs-scale", "title": "Costs and scale",
         "prose": "Where the concept breaks first, and at what number."},
        {"id": "assumptions", "title": "Assumptions",
         "bullets": ["the brief's tenant count holds"]},
        {"id": "self-score", "title": "Self-score",
         "tables": [{"columns": ["Criterion", "Weight", "Score"],
                     "rows": [["reuse", "3", "4"]]}]}
      ]
    }
    ```

    `created_at`/`updated_at` are not yours to write: the journal records
    when the payload landed, and an invented timestamp is a timestamp a
    reader cannot check.

    ## What You Return

    Your final message is exactly this, and nothing else:

    ```
    CONCEPT: [OUTPUT_FILE]
    NAME: <concept name>
    LENS: [LENS]
    DECISION_POINTS: <answered>/<total one-way doors>
    USE_CASES: <walked>/<total in map>
    GAPS: <n use cases the concept does not handle>
    ```
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
| `[MODEL]` | top tier |
| `[SESSION_ID]` | `INIT-0004-BRN-01`, or the topic slug for a pre-initiative session |
| `[SESSION_TOPIC]` | the session's topic |
| `[SESSION_DIR]` | the session's working directory (scratch; its files merge into the artifact) |
| `[QUESTION]` | the session's `question:` value |
| `[SESSION_FILE]` | the session's `session.md` |
| `[PRIOR_ART_FILE]` | the scout's payload — the controller passes the rendered `prior-art` view the engine writes from it |
| `[LENS]` | one lens name from the catalog |
| `[LENS_BRIEF]` | that lens's row from the catalog, plus anything specific to this brief |
| `[CONCEPT_LETTER]` | `A`, `B`, `C`, or `D` |
| `[OUTPUT_FILE]` | the `respond_to` payload path the engine minted — JSON only |

**Never** tell an explorer what the others are doing, which concept you
expect to win, or which lens is "the real one". **Never** give two
explorers the same lens.

**After the dispatch:**

1. Read every concept. If two converged on the same design despite
   different lenses, record that in the session — it is a signal the
   brief leaves little room, not a reason to discard one.
2. Summarize each concept in the session's `## Concepts` section as a
   `### <LETTER> — <name>` entry: shape, lens, and the tradeoff that
   decides it.
3. Pick the leading 1–2 concepts for the design critic
   ([design-critic-prompt.md](design-critic-prompt.md)).
