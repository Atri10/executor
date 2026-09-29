# Prior-Art Scout Prompt Template

Dispatch one scout per design session, after the brief is agreed and
before any concept explorer starts. It maps what already exists — in this
repository and in known external designs — that a new feature can reuse,
must conform to, or must integrate with. It recommends nothing.

**Purpose:** ground every concept in the real codebase, so explorers
design on top of what exists instead of reinventing it, and so a concept
that collides with an established convention is caught before the human
picks it.

**Before dispatching:**

1. The session's `## Brief` section is written and the human agreed the
   evaluation criteria. The scout reads the brief; it does not help write
   it.
2. Name 3–6 focus areas from the brief's actors, outcome, and
   constraints — the parts of the system the feature will most likely
   touch (e.g. "tenant provisioning", "billing events", "admin UI").
3. The output path is `<session dir>/prior-art.md`.
4. Choose the model: mid tier for a small repo, top tier for a large or
   unfamiliar one.
5. Append the dispatch row to `<session dir>/dispatches.md`.

```
Subagent (general-purpose):
  description: "Prior-art scout for [SESSION_TOPIC]"
  agent_identity: "[SCOUT-BRN<nn> — or SCOUT-<topic slug> for a pre-initiative session. Must match the session dispatches.md Agent cell.]"
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
       so a reader can tell "absent" from "not looked for".
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
    4. Did you cover every focus area in [FOCUS_AREAS]? An area with
       nothing found says so, with the search.
    5. Is any convention backed by only one instance? Find more or mark it
       "single instance".

    ## Verification

    1. Re-read [OUTPUT_FILE] from disk — every section below present,
       `None.` under any empty one.
    2. Spot-check three cited `path:line` references by opening them;
       fix any that point at the wrong line.
    3. Confirm `git status --short` shows [OUTPUT_FILE] as your only
       change.

    ## The Output File

    ```markdown
    ---
    kind: prior-art
    session: [SESSION_ID]
    question: [QUESTION]
    title: Prior art for [SESSION_TOPIC]
    created_at: <UTC from an executed command>
    updated_at: <same>
    ---

    **Scout model:** <the model you are running as>

    ## Reusable in this repo

    | What | Where | Covers | Would need |
    |---|---|---|---|

    ## Conventions that constrain the design

    | Convention | Instances |
    |---|---|

    ## Integration touchpoints

    | Touchpoint | Where | Ripple |
    |---|---|---|

    ## Known external designs

    | Design | Source | Why relevant |
    |---|---|---|

    ## Gaps

    | Needed | Search performed | Result |
    |---|---|---|

    ## Open questions for the controller

    Numbered. `None.` if none.
    ```

    ## What You Return

    Your final message is exactly this, and nothing else:

    ```
    PRIOR_ART: [OUTPUT_FILE]
    REUSABLE: <n>
    CONVENTIONS: <n>
    TOUCHPOINTS: <n>
    GAPS: <n>
    OPEN_QUESTIONS: <n>
    ```
```

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[MODEL]` | mid tier for a small repo, top tier for a large or unfamiliar one |
| `[SESSION_ID]` | `INIT-0004-BRN-01`, or the topic slug for a pre-initiative session |
| `[SESSION_TOPIC]` | the session directory's topic |
| `[SESSION_DIR]` | the session directory path |
| `[QUESTION]` | the session's `question:` value |
| `[BRIEF_FILE]` | the session's `session.md` |
| `[REPO_ROOT]` | the repository root the feature lives in |
| `[FOCUS_AREAS]` | 3–6 areas of the system the feature likely touches |
| `[OUTPUT_FILE]` | `<session dir>/prior-art.md` |

**Never** tell the scout which concept you favor, and **never** ask it to
evaluate concepts — it runs before any exist.

**After the dispatch:**

1. Read the Open questions and resolve each with the human, or record it
   in the brief's constraints.
2. Pass [OUTPUT_FILE] to every concept explorer.
