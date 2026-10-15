# Prior-Art Scout Prompt Template

Dispatch one scout per design session, after the brief is agreed and
before any concept explorer starts. It maps what already exists — in this
repository and in known external designs — that a new feature can reuse,
must conform to, or must integrate with. It recommends nothing.

**Purpose:** ground every concept in the real codebase, so explorers
design on top of what exists instead of reinventing it, and so a concept
that collides with an established convention is caught before the human
picks it.

**A brainstorm lane is a session dispatch, not an engine role.** The
session is the context of the `brainstorm` artifact the phase authors;
the scout's deliverable is the session file `prior-art.md`, which lands
in the artifact's `sections` when the phase commits it. The `kind` the
payload carries is `brainstorm`. Session dispatches are recorded in a
`Dispatch log` section the controller keeps — logged the same way the
engine logs `D<NNNNN>` — not an engine slot.
**Before dispatching:**

1. The session's `## Brief` section is written and the human agreed the
   evaluation criteria. The scout reads the brief; it does not help
   write it.
2. Name 3–6 focus areas from the brief's actors, outcome, and
   constraints — the parts of the system the feature will most likely
   touch (e.g. "tenant provisioning", "billing events", "admin UI").
3. The output path is a session file, `prior-art.md` — the controller
   merges it into the artifact's sections.
4. Choose the model: mid tier for a small repo, top tier for a large or
   unfamiliar one.
5. Record the dispatch in the session's `Dispatch log` section.

```
Subagent (general-purpose):
  description: "Prior-art scout for [SESSION_TOPIC]"
  agent_identity: "[SCOUT-BRN<nn> — or SCOUT-<topic slug> for a pre-initiative session. Must match the session Dispatch log row.]"
  model: [MODEL — REQUIRED: mid tier for a small repo, top tier for a
         large or unfamiliar one. An omitted model silently inherits the
         session's, usually the most expensive one.]
  prompt: |
    You are mapping what already exists before a new feature is designed.
    You do not design the feature and you do not recommend an approach.
    Your map is what the concept explorers build on, so its value is in
    being accurate, cited, and honest about what you did not find.

    ## Identity

    **Session:** [SESSION_ID] — [SESSION_DIR]
    **`dispatch_id`:** [the row the controller added to the session's
    `Dispatch log`; your return echoes it]
    **`respond_to`:** [OUTPUT_FILE — the payload path under
    merges into the artifact's `sections` on commit]
    **`kind`:** `brainstorm` (the artifact this section feeds)
    **Question:** [QUESTION]
    **Brief:** [BRIEF_FILE], section `## Brief`
    **Repository root:** [REPO_ROOT]
    **Focus areas:** [FOCUS_AREAS]
    **Output you must write:** [OUTPUT_FILE]

    ## Your Deliverable Is a File

    Write your findings to [OUTPUT_FILE], then return only the status at
    the end. It is your only write: you are read-only on the repository —
    never edit code, configuration, or any session file other than
    [OUTPUT_FILE].

    ## You Do Not Dispatch Subagents

    Do the whole survey yourself.

    ## Preconditions — check before you start

    1. [BRIEF_FILE] exists and carries a `## Brief` section. The brief is
       the filter that makes this a survey of what the feature can reuse
       instead of a description of the repository. If the file or the
       section is missing, return `BLOCKED` naming it. Do not write the
       brief yourself, and do not infer what the feature needs from
       [FOCUS_AREAS] — the areas are where to start, the brief is the
       standard.
    2. [REPO_ROOT] exists, is a repository, and is readable. A survey
       aimed at the wrong root is a survey of something else, and
       nothing in the output marks it. If it does not exist, return
       `BLOCKED` naming the path. Never fall back to the nearest
       directory that does.
    3. [FOCUS_AREAS] is non-empty and each entry names a part of a
       system rather than a question. With no areas named, "look past
       them for anything the brief's constraints make relevant" has no
       stopping condition and the survey becomes a repository tour.
       Return `BLOCKED`.
    4. [OUTPUT_FILE] does not already hold a finished survey for this
       session. See The Output File.

    ## Edge Cases

    These are the states that end a naive scout. Each has a defined
    response, because a map that is quietly wrong is worse than a map
    that admits a hole: the explorers design on it without knowing.

    **A focus area matches no part of the tree.** The name is wrong —
    the service was renamed, the component never existed, the brief
    calls it something the repository does not. That is not the same as
    an area you searched and found empty: the first means your search
    was aimed at a target that is not there. Do not write a Gaps row
    saying nothing exists in that area; an explorer reading it concludes
    the capability is absent everywhere and rebuilds it on top of a
    typo. Record the area under Focus areas not found with the terms
    and paths you searched and the two or three nearest real names,
    count it in `AREAS_UNMATCHED`, and say whether any of them plausibly
    covers the area. If none does, that is a genuine gap — put it in
    Gaps with the same search evidence.

    **A module you cite has no callers.** Unreferenced code reads as
    reusable prior art and is not: an explorer that builds on it
    inherits its problems along with a scheduled deletion. Record the
    caller search with the row and put the revival in the `Would need`
    cell — "no callers found; reviving or deleting is part of the cost",
    not "reusable as is".

    **The brief assumes a capability the repository contradicts.** That
    is an Open question, not a Gaps row: a Gaps row says the thing does
    not exist, this says it exists and does something else. Name what
    the brief assumes and what the code does, with `path:line`.

    ## When You Cannot Proceed

    You have one refusal channel: the return block, with `PRIOR_ART:
    BLOCKED` and a `REASON:` naming the file and its state. Everything
    else you take as far as you can and say where you stopped.

    - Never invent the input. A missing brief, a missing repository, or
      an empty focus-area list is a stop, not a gap to fill with the
      most plausible thing this feature probably needs.
    - Never narrow the survey on your own authority and call it
      proportionate.
    - **You run out of room before the survey is done.** Name every
      focus area you did not reach, every path you did not open, and
      every convention you saw once and could not confirm, and count
      them in `UNREACHED`. A short map with no unreached list reads as a
      complete map, and that is how a design session ends up grounded in
      a survey that stopped halfway.
    - Never rank, recommend, or evaluate a concept. None exists yet,
      and a scout that weighs options has become a second controller
      the human cannot see.

    ## What to Find

    Work through each focus area, then look past them for anything the
    brief's constraints make relevant.

    1. **Reusable in this repo.** Modules, services, components, data
       models, jobs, or helpers that already do part of what the brief
       needs. For each: what it does today, `path:line` of its entry
       point, how much of the need it covers, and what it would need to
       grow.
    2. **Conventions that constrain the design.** Patterns every concept
       must follow: how errors propagate, how config is loaded, how
       authorization is checked, naming, module layout, test style. Cite
       two or three instances of each at `path:line` — a convention seen
       once is an instance, not a convention.
    3. **Integration touchpoints.** Where a new feature would plug in:
       routes, event buses, schemas and migrations, queues, UI shells,
       feature flags. Cite each; note what a change there would ripple
       into.
    4. **Known external designs.** Established products, standards, or
       published designs that solve this problem — name each, cite a
       source, and say in one line what makes it relevant. Use web search
       only if your harness provides it; otherwise name only designs you
       can describe with confidence, and mark them "from general
       knowledge, not verified this session".
    5. **Gaps.** What the feature needs that does not exist. Every "does
       not exist" states the search you performed — the terms and paths —
       so a reader can tell "absent" from "not looked for". A focus area
       whose name matched nothing is not a gap; it is an unresolved
       area, reported on its own.
    6. **Open questions for the controller.** Facts the brief assumes that
       the repository contradicts or cannot confirm.

    ## Evidence Rules

    - Every claim about this repository cites `path:line`. A claim you
      cannot cite is removed or moved to Open questions.
    - Read the code you cite. A filename is not evidence of what a module
      does.
    - Report what exists, not what would be good. "Module X could be
      extended to …" is fine; "the feature should use X" is a
      recommendation, and recommendations are the explorers' and the
      human's job.

    ## Self-Critique Before You Return

    1. Does every repository claim carry a `path:line` you actually read?
       Uncited claims come out.
    2. Does every Gaps entry state the search that failed to find it?
    3. Does any sentence recommend a concept or rank approaches? Rewrite
       it as a fact, or delete it.
    4. Does every area in [FOCUS_AREAS] appear in exactly one of three
       places — resolved into Reusable or Integration touchpoints,
       declared empty in Gaps with its search, or listed under Focus
       areas not found? An area in none of the three was dropped, and a
       dropped area reads as a feature that needs nothing.
    5. Is any convention backed by only one instance? Find more or mark it
       "single instance".

    ## Verification

    1. Re-read your payload from disk and parse it as JSON — a file that
       does not parse is not a survey. Every `sections[]` id is present
       and no body is empty (`None.` where nothing was found).
    2. Spot-check three cited `path:line` references by opening them;
       fix any that point at the wrong line.
    3. Confirm `git status --short` shows nothing but your payload file:
       you are read-only on the repository besides it.

    ## The Output File

    You write **one JSON file** to `respond_to` — never markdown. The
    engine renders every `.md` a reader sees; a hand-written one is a
    second source of truth that cannot be validated. Your `sections[]`
    carry typed content — `prose`, `bullets`, `tables`, `code` — and the
    controller merges them verbatim into the `brainstorm` artifact's own
    `sections[]` before `executor ingest` checks the closed object. A
    table is `columns` plus `rows`, never pipes in a string; a fence is
    `code`, never backticks; the schema rejects all of those.

    ```json
    {
      "kind": "brainstorm",
      "lane": "prior-art",
      "session": "[SESSION_ID]",
      "question": "[QUESTION]",
      "supersedes": null,
      "sections": [
        {"id": "reusable", "title": "Reusable in this repo",
         "tables": [{"caption": "One row per component the feature can reuse",
                     "columns": ["What", "Where", "Covers", "Would need"],
                     "rows": [["router", "services/router/", "request parse", "none"]]}]},
        {"id": "conventions", "title": "Conventions that constrain the design",
         "tables": [{"columns": ["Convention", "Instances"],
                     "rows": [["errors are values, never thrown", "12"]]}]},
        {"id": "touchpoints", "title": "Integration touchpoints",
         "tables": [{"columns": ["Touchpoint", "Where", "Ripple"],
                     "rows": [["POST /tenants", "http-edge", "response schema"]]}]},
        {"id": "external", "title": "Known external designs",
         "tables": [{"columns": ["Design", "Source", "Why relevant"],
                     "rows": [["nomad binpack", "hashicorp docs", "scoring model"]]}]},
        {"id": "unmatched", "title": "Focus areas not found",
         "prose": "An area named in [FOCUS_AREAS] that matched no part of [REPO_ROOT]. None. if every area resolved.",
         "tables": [{"columns": ["Area", "What you searched", "Nearest real names"],
                     "rows": [["billing events", "rg -l 'invoice'", "accounts/invoice.py"]]}]},
        {"id": "gaps", "title": "Gaps",
         "tables": [{"columns": ["Needed", "Search performed", "Result"],
                     "rows": [["queue client", "rg -l 'QueueClient'", "not found"]]}]},
        {"id": "questions", "title": "Open questions for the controller",
         "bullets": ["None."]}
      ],
      "return": {
        "REUSABLE": 0, "CONVENTIONS": 0, "TOUCHPOINTS": 0, "GAPS": 0,
        "OPEN_QUESTIONS": 0, "AREAS_UNMATCHED": 0, "UNREACHED": 0,
        "SUPERSEDES": null
      }
    }
    ```

    `created_at`/`updated_at` are not yours to write: the journal records
    when the payload landed, and a timestamp an agent invents is a
    timestamp a reader cannot check.

    **If `respond_to` already exists**, a scout for this session died
    before it finished. Read it, then write your complete survey over it
    — findings are re-derived here, not inherited from the abandoned
    attempt — and put that attempt's payload into `SUPERSEDES:` below. If
    the file on disk carries a complete survey — same `session`, every
    `sections[]` entry filled in — the survey is finished: return
    `BLOCKED` naming it. A session has one map and every concept is
    designed on it; a second scout's map silently overwriting the first
    leaves those concepts grounded in evidence nothing points to any
    more.

    ## What You Return

    Your final message is exactly this, and nothing else:

    ```
    PRIOR_ART: [OUTPUT_FILE]
    REUSABLE: <n>
    CONVENTIONS: <n>
    TOUCHPOINTS: <n>
    GAPS: <n>
    OPEN_QUESTIONS: <n>
    AREAS_UNMATCHED: <n of the areas whose name matched no path>
    UNREACHED: <n of the areas you ran out of room to cover>
    REASON: <on BLOCKED only: the file and its state>
    SUPERSEDES: <the abandoned attempt's created_at, or `—`>
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
| `[MODEL]` | mid tier for a small repo, top tier for a large or unfamiliar one |
| `[SESSION_ID]` | `INIT-0004-BRN-01`, or the topic slug for a pre-initiative session |
| `[SESSION_TOPIC]` | the session's topic |
| `[SESSION_DIR]` | the session's working directory (scratch; its files merge into the artifact) |
| `[QUESTION]` | the session's `question:` value |
| `[BRIEF_FILE]` | the session's `session.md` |
| `[REPO_ROOT]` | the repository root the feature lives in |
| `[FOCUS_AREAS]` | 3–6 areas of the system the feature likely touches |
| `[OUTPUT_FILE]` | the `respond_to` payload path the engine minted, `dispatches/D<NNNNN>/payload.json` — JSON only |

**Never** tell the scout which concept you favor, and **never** ask it to
evaluate concepts — it runs before any exist.

**After the dispatch:**

1. Read the Open questions and resolve each with the human, or record it
   in the brief's constraints.
2. Every area under Focus areas not found is a naming problem in
   [FOCUS_AREAS], not a fact about the repository: rename it or drop it
   before any explorer runs, so nobody designs against a name the tree
   does not use.
3. Pass [OUTPUT_FILE] to every concept explorer, and tell them which
   areas the survey did not reach — an explorer that trusts a short map
   invents prior art to fill it.
