# The Executor

An initiative-scoped workflow system for coding agents. You describe a
major idea; the engine takes it through intake, discovery, architecture,
design, specification, planning, plan regression, execution, review, and
verification — with a strict per-initiative ID namespace, separated
thinking and execution stores, and schema-enforced contracts at every
state transition.

**Nothing floats.** Every document, task, review, verdict, and ruling
carries an ID that names the initiative it belongs to. One initiative
owns one folder, one namespace, and every payload produced about it.

**Nothing is enforced by hope.** Where a workflow could silently drift — a
verdict about a different diff than the one under review, a task completed
without review, a gate cleared by a controller that decided to be helpful —
the engine refuses it, in code, before it lands. Contracts enforced by
prose are hopes; contracts enforced by schemas and a fold are contracts.

Works with any agent that can read skill files from a directory — Claude
Code, Codex, [omp](https://github.com/Atri10/omp), or anything similar. The
skills are markdown; the engine is Python 3.11+, dependency-free, and runs
on macOS, Linux, and Windows.

## In sixty seconds

```text
$ npx skills add Atri10/executor                 # skills into your harness
$ export PYTHONPATH=/path/to/executor/engine     # the engine on the path

$ python3 -m executor new "Tenant isolation cells"
{
  "created": "INIT-0001",
  "title": "Tenant isolation cells",
  "store": ".../.executor/INIT-0001",
  "docs": ".../docs/executor/INIT-0001"
}

$ python3 -m executor next
{"action":"PHASE-ENTER","initiative":"INIT-0001","phase":"intake", ...}

$ python3 -m executor status
INITIATIVE INIT-0001 - Tenant isolation cells
phase: intake (in_progress)
events: 3 | artifacts: 0 | tasks: 0
```

The loop is always the same: **`next` gives you one typed action, you do
that one thing, and the engine decides again.** `next` also returns a
`resume` block — phase, phase state, last event, open slots, task counts —
so every action is self-describing for whoever or whatever picks it up,
and nothing depends on remembering where the run was.

## Install

One line, any of 20+ agents (Claude Code, Codex, Cursor, Copilot, Gemini
CLI, OpenCode, Amp, Goose, and more) — [`skills`](https://github.com/vercel-labs/skills)
discovers every skill in the repo and wires them into your harness:

```bash
npx skills add Atri10/executor
```

Or clone and copy `skills/` into whatever directory your agent loads from,
and put `engine/` on your `PYTHONPATH`:

```bash
git clone git@github.com:Atri10/executor.git
cp -R executor/skills/* <your-agents-skills-dir>/
export PYTHONPATH=<clone>/engine
```

Pin to a release tag instead of `main` for stability:

```bash
git clone --branch v2.0.0 git@github.com:Atri10/executor.git
```

There are no dependencies to install: the engine is the standard library,
and its own test suite needs nothing but Python (plus `coverage` if you
want the branch report — `pip install -r requirements-dev.txt`).

### One-paste install for any LLM agent

Paste this into your agent — Claude Code, Cursor, Aider, Codex, omp, or any
other harness. It discovers the right directories itself and verifies the
install:

```text
Install The Executor skill library and engine for me:

1. Clone https://github.com/Atri10/executor.git into a temp directory
2. Find my agent's skills directory. Candidates, in order — use the first
   that exists, or ask me if none do:
   - ~/.omp/agent/skills/            (omp)
   - ~/.claude/skills/               (Claude Code)
   - ~/.cursor/skills/               (Cursor)
   - .claude/skills/                 (repo-local Claude Code)
   - as my harness documents
3. Copy every directory from the clone's skills/ folder into that skills
   directory (each is one skill: skills/executor, skills/executor-spec, ...).
   Tell me the PYTHONPATH line that points at the clone's engine/ directory,
   and add it to my shell profile if I confirm.
4. Verify: run PYTHONPATH=<clone>/engine python3 -m executor --version
   (prints 2.0.0), then PYTHONPATH=<clone>/engine python3 -m executor
   --help (lists the command surface). Also confirm every copied
   skills/<name>/ directory contains a SKILL.md — count the directories,
   not a remembered number: the skill set grows, and a stale count fails
   an install that is actually fine.
5. Tell me which directory you installed into, and how to invoke the
   router in my harness (usually /skill:executor or just asking for
   "the executor").

Do not modify any file inside the clone or the skills directory other
than the copy operation itself.
```

Then invoke the root router:

```text
/skill:executor
```

or say *"start an initiative"* — normal requests route by each skill's
description.

## How a run is driven

One loop, and the controller holds no judgment: run `executor next`, read
the single typed action it emits, do that, go back. Every arrow below is
either an engine decision or a dispatched subagent.

```mermaid
flowchart TD
    start(["executor next"]) --> enter{"PHASE-ENTER phase"}
    enter --> author["DISPATCH author"]
    author --> artifact["payload written to respond_to"]
    artifact --> ingest["executor ingest"]
    ingest --> audit["DISPATCH audit"]
    audit -->|"findings open"| repair["DISPATCH repair"]
    repair --> audit
    audit -->|"clean"| gate{"GATE phase"}
    gate -->|"human decides"| decide["executor decide — gate_decision"]
    gate -->|"autonomy allows"| auto["gate clears by: auto"]
    auto --> next["next phase"]
    decide --> next
    next --> start
    start -->|"every phase resolved"| done(["DONE"])
```

### What each action asks of you

| Action | The engine is asking | You must not |
|---|---|---|
| `PHASE-ENTER` | route to the named phase skill | start work before the gate that follows it |
| `DISPATCH` | run the named subagent on the prompt it rendered | shorten, pre-judge, or answer the payload yourself |
| `GATE` | collect a human decision | pass it because the work "looks done" |
| `ASK` | answer a blocked worker's question with a `ruling` | answer it with your own guess |
| `ESCALATE` | adjudicate what the cap says cannot continue | push another round to avoid the ruling |
| `MERGE` | perform the plan merge it describes | reorder or edit the named heads |
| `DONE` | report to the human | claim "complete" while a criterion is unanswered |
| `HALT` | stop | continue quietly |

### The phase order

```mermaid
flowchart LR
    I["intake"] --> D["discovery"]
    D --> A["architecture"]
    A --> G["design"]
    G --> S["specification"]
    S --> P["planning"]
    P --> PR["plan-regression"]
    PR --> E["execution"]
    E --> R["review"]
    R --> V["verification"]
    V --> H["handoff"]

    classDef gated fill:#1f3a5f,stroke:#4a90d9,color:#fff
    classDef critic fill:#3d2f1f,stroke:#d9a04a,color:#fff
    class I,D,A,G,S,P,E,V,H gated
    class PR,R critic
```

Every authoring phase carries a critique gate after it; the two critique
phases (plan regression and review) audit the others. Phases compress —
a small initiative may author a charter and a spec in one exchange — but
skipping one is a stated human `ruling`, never an omission.

### The task loop inside execution

A task's result reaches the fold only through a review round. A worker
that stops is escalated through a fixed ladder before anyone is replaced.

```mermaid
flowchart TD
    step(["executor next"]) --> act{"action"}
    act -->|"DISPATCH impl"| disp["spawn impl on the rendered prompt"]
    disp --> worker[("worker writes its report payload")]
    worker -->|"needs_context"| ask["ASK — a human ruling answers"]
    worker -->|"spawn_error"| pending["task reverts to pending, re-dispatch"]
    worker -->|"BLOCKED"| esc["ESCALATE — adjudicate"]
    ask --> step
    pending --> step
    esc --> step
    worker -->|"reported"| rev["DISPATCH review — engine mints R<NN> package"]
    rev --> rep{"verdict open critical/important?"}
    rep -->|"clean"| merge["task complete — MERGE when the plan is ready"]
    rep -->|"open under cap"| fix["DISPATCH fix — fix-package minted"]
    fix --> rev2["DISPATCH review — new round, prior findings in context"]
    rev2 --> rep
    rep -->|"open at cap"| brk["ESCALATE — adjudicate every open finding"]
    act -->|"MERGE"| mg["ingest the merge payload — merge_sha verified"]
    mg --> step
    act -->|"DONE"| fin(["plan complete"])
```

### The task state machine

The fold owns task state; a worker cannot write it. These are the only
transitions, and each is triggered by a payload the engine accepts.

```mermaid
stateDiagram-v2
    [*] --> pending: the plan payload lands
    pending --> dispatched: DISPATCH impl
    dispatched --> reported: a report payload, result DONE/PARTIAL
    dispatched --> blocked: a report payload, result BLOCKED
    dispatched --> prior_state: a spawn_error event, or the next poll abandons it
    prior_state --> dispatched: the task is re-dispatched
    blocked --> prior_state: a human ruling answers the question
    reported --> complete: a verdict with no open critical/important
    reported --> fix_needed: a verdict with findings inside the cap
    fix_needed --> dispatched: DISPATCH fix, a new round
    fix_needed --> complete: a later verdict is clean
    fix_needed --> escalate: the round cap is reached
    escalate --> [*]: every open finding is adjudicated by ruling
    complete --> [*]
```

Two details the fold pins and a worker cannot alter: a lost dispatch
(spawn error, or silence past the deadline) returns the task to
**`prior_state`** — the state it was in when it was dispatched, so a fix
round resumes as a fix round, not as new work; and a ruling does the same,
so a question raised during review resumes review rather than
implementation. `needs_context` is that waiting state, and it is entered
only by a question payload.

## The skills, and when each one loads

| Skill | Loads when | It owns |
|---|---|---|
| `executor` | always — the router and contract | the pump, the ID namespace, the two stores, secret hygiene |
| `executor-initiative` | `PHASE-ENTER intake`, or a request to classify work | classify / spike / initiative / attach, the charter |
| `executor-discovery` | the discovery phase | options comparison, brainstorm sessions |
| `executor-architecture` | architecture and design | `arch`, `adr`, `ifce`, `design` artifacts |
| `executor-spec` | the specification phase | `spec`, `risk`, `vrfy` artifacts |
| `executor-planning` | `GATE specification` passed | the `plan` payload: tasks, sections, dependencies |
| `executor-plan-regression` | `PHASE-ENTER planning` is done | the plan-set audit, repair, re-audit — gates execution |
| `executor-execution` | `PHASE-ENTER plan-regression` passed | task dispatches, reports, fix rounds, the merge |
| `executor-review` | a task reports, or the plan is ready to merge | `verdict` payloads, findings, the whole-branch audit |
| `executor-verification` | execution and review are finished | `evidence` payloads per `vrfy` criterion |
| `executor-handoff` | `PHASE-ENTER verification` passed | the rulings report, docs export, the human's decision |
| `executor-critique` | any critique gate | per-component audit, repair, re-audit |
| `executor-brainstorm` | a brainstorm artifact is needed | recorded divergent ideation |

## Feature highlights

### The journal is the state, and the fold is its only reader

Every accepted payload is one JSON line in
`.executor/INIT-NNNN/journal/events.v1.jsonl`, hash-chained (`prev_sha`,
`line_sha`) — `executor check` recomputes the chain and refuses a store
that was edited by hand. Views (`views/progress.md`, `views/dispatches.md`,
`views/summary.md`, `views/graph.json`, the rendered `.md` beside each
committed payload) are derived projections; `state.json` is a cache the
engine detects and refolds when stale. A dispatch is single-use and
answered exactly once: `slot.json` records the minting event, `prompt.md`
is the worker's brief, and `payload.json` is the `respond_to` path
`executor ingest` validates against the `kind`'s schema.

### Every payload is a closed, typed document

`engine/executor/schemas.py` defines each `kind` as a closed object with
anchored patterns: exact ID shapes, back-references tying a task ID to its
plan, numeric bounds pinned by a literal table, and rejections that name
the field, the expected type, and the observed value. A plan cannot cite a
task that does not exist; a verdict cannot name a round the engine did not
mint; a verdict about another diff is `round_mismatch`, not a numbering
slip.

### A payload is data; the engine writes every document

Sections carry four typed shapes — `prose`, `bullets`, `tables`
(`columns` plus `rows`), and `code` — and no string in a payload may carry
markdown syntax. A pipe table, a code fence, or a heading inside a string
is rejected as `notMatch`; a table row whose cell count differs from its
columns is `row_width`; a whitespace-only value is `nonBlank`;
`sections[].id` must be unique, because a reviewer cites it.
`engine._render_doc` is the only writer of document markdown.

```json
{"kind": "spec", "v": "v1", "dispatch_id": "D00112",
 "id": "INIT-0004-SPEC-01", "title": "Cell placement",
 "summary": "A tenant is placed in exactly one cell, deterministically.",
 "sections": [
   {"id": "determinism", "title": "Determinism",
    "prose": "The same inputs name the same cell, on every node.",
    "tables": [{"caption": "What the invariant forbids",
                "columns": ["Input", "Permitted", "Forbidden"],
                "rows": [["region, sizeClass", "any known pair", "an unknown region"]]}]}],
 "requirements": [
   {"id": "R01", "requirement": "placement is deterministic",
    "observable": "two calls with identical inputs return the same cell",
    "cites": ["INIT-0004-ARCH-01"]}],
 "constraints": [], "risks": [], "cites": ["INIT-0004-ARCH-01"]}
```

Every refusal the engine can emit — 37 of them — is listed in
`skills/executor/references/rejections.md` with its field and the action
that clears it, and `engine/tests/test_docs_agreement.py` walks the
engine's raise sites against that list so a new rejection cannot ship
undocumented.

### Plans are audited as a set, not one at a time

Per-plan review reads one payload; the defects that actually ship live
*between* payloads. `executor-plan-regression` reads the whole set against
the spec, the interface artifacts, and each other — coverage, seam closure,
ordering, constraint propagation, file ownership. Execution cannot start
until every plan is clean or the human has waived a finding by `ruling`.

### Reviewers see the package, not a paraphrase

When a task reports, the engine mints `reviews/R<NN>.package.json`:
`commit_base`, `commit_head`, the diff, and every prior finding. The
reviewer's `verdict` payload echoes `round`, `commit_base`, `commit_head`,
and `reviewed_package_sha`; a mismatch is rejected. Two verdicts are
mandatory — `spec_verdict` (PASS/FAIL against the contract) and
`quality_verdict` (APPROVED/NEEDS_FIXES/APPROVED_WITH_ROUTED_RESIDUALS) —
and findings carry `severity`, `claim`, and `evidence` quoting `path:line`.

### A fix loop with a breaker

Findings are severity-graded: `critical`/`important` enter the fix loop,
`minor` stays `open` for the final audit, `info` is recorded. Each round
is a `fix` dispatch plus a scoped re-review; near the cap the dispatch goes
to a fresh implementer one tier up (the cap is the `max_fix_rounds`
tunable, default 5, bounds 1–50). At the cap, `ESCALATE` requires
adjudicating every open finding — parked with a journaled `ruling`, never
silently dropped.

### Evidence is capability-aware, not ceremony

The implementer contract asks for the **strongest feasible evidence** for
every behavior change: a watched failing test where a harness exists, a
named alternative instrument where it does not, and an explicit
NOT-RUN/UNAVAILABLE record where nothing feasible exists. The verification
phase turns the `vrfy` criteria into `evidence` payloads with observed
output, and `executor status` counts every criterion as proven, failed,
unavailable, or unanswered — a criterion nobody ran is unproven however
obviously it "must" work.

### Upstream drift has a seat

No reviewer ever gets only the diff. The critique catalogs make the
`arch`, `ifce`, and `design` artifacts required inputs of the
implementation critique, and the final reviewer takes them as required
inputs with an architecture-conformance check: where the spec and the
architecture disagree, that is a finding, and the diff alone cannot say
which side is wrong.

### Unattended runs, fail-closed

An initiative declares which phase gates a human agreed to let go
unattended — `executor autonomy`, one JSON map of phase to mode:

```text
executor autonomy                        # the policy in force, every phase
executor autonomy execution allow        # a structural gate may clear itself
```

`deny` is the default for every phase, and every ambiguity resolves to it:
a missing or malformed file, an unlisted phase, a mode spelled wrong. The
pick-class phases (`design`, `specification`), where a human chooses
between options, and handoff never clear automatically whatever the file
says. An auto-cleared gate is journaled as `by: "auto"`, visibly distinct
from a human `passed`.

### The controller carries no weight

The controller is the least reliable worker in the system — it dies,
compacts, drifts, and is under pressure at exactly the moment a judgment
call matters — so the design assumes it will get clever and takes away the
opportunity. It never authors (every artifact is a dispatch), never judges
(every verdict is a payload), never passes a gate (only `executor decide`
writes `gate_decision`, stamped `actor: human`, so a worker cannot approve
its own work), and never improvises a transition (an action with no row in
the decision table is an engine gap to record, not to approximate).

## How the engine is put together

### The CLI is the whole surface

```text
executor new "<title>"                     scaffold INIT-NNNN
executor next [INIT]                       one typed action + its prompt
executor ingest <path.json|-> [INIT]        a worker payload: validate → fold → render
executor decide <path.json|-> [INIT]        a human decision: gate_decision, ruling, resume
executor status [INIT]                     the gate card
executor check [INIT] [--secrets]           chain, dangling edges, liveness, layout; or scan
executor doctor [INIT]                     check + open dispatches + policy in force
executor graph [INIT] [--format json|mermaid]
executor migrate [INIT] [--dry-run]        reports the store version verdict; never edits
executor autonomy [INIT] [<phase> <allow|gate|deny>]
```

Exit codes: `0` ok · `1` a check found problems · `2` usage or engine
error. Every write goes through `create_initiative`, `ingest`, or
`emit_next`; there is no command that edits the journal directly.

### Module map

```mermaid
flowchart LR
    CLI["cli.py — the command surface"] --> ENGINE["engine.py — emit_next, ingest, check"]
    CLI --> VIEWS["views.py — status card, render"]
    ENGINE --> SCHEMAS["schemas.py — closed, typed payload contracts"]
    ENGINE --> PATHS["paths.py — the single path authority"]
    ENGINE --> STORE["store.py — journal, chain, lock, initiative lookup"]
    ENGINE --> POLICY["policy.py — autonomy, tunables, project config"]
    STORE --> FS[("filesystem")]
```

`paths.py` is the one path authority: ~40 named `*_file`/`*_dir`
functions, and `classify(rel, store)` parses any path back into
`(store, kind, ids)` — so `executor check` can audit every file in both
stores against the naming grammar and flag drift rather than assume it.

### Versioned, and honest about skew

Each store records the engine version that wrote it in `meta.json`. When a
newer engine opens an older store, commands report the mismatch and say
what `executor migrate` would report — `migrate` never edits the store
itself. A reader of an old journal gets the old fold, not a guess.

### The merge contract

`emit_next` mints `MERGE` as a real slot: the action names the plan, its
branch head, and the `respond_to` path for a `merge` payload. Ingest
verifies the named `merge_sha` exists in the repository, descends from the
plan's head, and binds to the dispatch that answered it. A merge claim
about a commit that does not exist is a rejection, not a plausible-sounding
summary.

## The Two Stores

```mermaid
flowchart LR
    subgraph THINK["docs/executor/ - tracked"]
        C["charter, options, brainstorm payloads"] --> A["arch, adr, ifce, design"]
        A --> S["spec, risk, vrfy"]
        S --> P["plan payloads + rendered .md"]
    end
    subgraph EXEC[".executor/ - git-ignored by default"]
        J["journal/events.v1.jsonl — the truth"]
        D["dispatches/D<NNNNN>/ — slot, prompt, payload"]
        R["reviews/, fixes/"]
        V["views/ — derived projections"]
        PR["plan-regression audits and repairs"]
    end
    P -->|"each task dispatch"| D
    D --> J
    J --> V
```

- **`docs/executor/`** — the thinking record, committed by
  `executor handoff`: the payloads and their rendered markdown, per
  initiative, per artifact, plus the exported journal snapshot. A reader
  who clones the repo gets the complete reasoning.
- **`.executor/`** — the execution record: the journal, the dispatch
  slots, the review packages, the fix packages, and the run views.
  Git-ignored by default, safe to commit if you choose; never deleted —
  the reasoning is the point.

The split is durability-of-audience, not durability-of-value.
`.executor/` resolves from the main repository root, so **removing a
worktree cannot destroy the execution record.**

## The ID Namespace

```text
INIT-0004                      the initiative
INIT-0004-CHTR-01              its charter
INIT-0004-OPTS-01              an options comparison
INIT-0004-BRN-01               a brainstorm session
INIT-0004-ARCH-01              an architecture document
INIT-0004-ADR-03               a decision record
INIT-0004-IFCE-01              an interface/contract document
INIT-0004-DSGN-02              a component design
INIT-0004-SPEC-01              a specification
INIT-0004-SPEC-01-R07          requirement 7 inside that spec
INIT-0004-SPEC-01-C03          global constraint 3 inside that spec
INIT-0004-RISK-01              a risk register / pre-mortem
INIT-0004-VRFY-01              a verification strategy
INIT-0004-P01                  a plan
INIT-0004-P01-T03              task 3 of that plan
D00112                         the dispatch minted at journal seq 112
R2                             review round 2 (an integer, paired with its task)
```

**Grammar:** `INIT-<4-digit>` then `-<KIND>-<2-digit>`, plans as
`-P<2-digit>`, tasks as `-T<2-digit>`, dispatches as `D<5-digit>`
(seq-derived), review rounds as an integer `round` field paired with the
task ID. The kind segments are `CHTR`, `OPTS`, `BRN`, `ARCH`, `ADR`,
`IFCE`, `DSGN`, `SPEC`, `RISK`, `VRFY` — the closed set
`ARTIFACT_SEGMENTS` in `engine/executor/paths.py` defines them, and an ID
carrying any other segment is a `pattern` rejection. Sequence within a
kind is per-initiative and starts at `01`.

**A payload must not cite another initiative's ID.** Cross-initiative
relationships exist in exactly one place: the charter's `cites`. Everything
else states the requirement in its own words, so an initiative stays
archivable — open the folder and every pointer resolves inside it.

## Where things live

```mermaid
flowchart TD
    R["repository root"] --> E["engine/ — the engine, stdlib only"]
    R --> S["skills/ — one directory per skill"]
    R --> SC["scripts/ — run_tests.py, mutate.py, validators"]
    R --> CI[".github/workflows/ — the gates"]
    R --> DOC["docs/executor/ — the committed record of each initiative"]
    E --> ET["engine/tests/ — the suite"]
```

| Path | What it is |
|---|---|
| `engine/executor/` | the engine: `cli.py`, `engine.py`, `schemas.py`, `paths.py`, `store.py`, `views.py`, `policy.py` |
| `engine/tests/` | the suite (717 tests), plus the tree-walking contract tests |
| `skills/executor/` | the router skill, its prompt templates, and the references |
| `skills/executor-*/` | one directory per phase skill |
| `scripts/run_tests.py` | the test runner; enforces the branch-coverage floor |
| `scripts/mutate.py` | mutation testing; the allow list records equivalent survivors |
| `scripts/validate_skills.py` | the skill contract: registry, references, payload shapes |
| `scripts/lint-prompt-injection.py` | blocks override directives and concealment in skill text |
| `docs/executor/` | the committed thinking record, exported by handoff |
| `.executor/` | the run store — journal, dispatches, views (git-ignored) |

## Testing and CI

The engine's suite is Python and runs anywhere Python runs:

```bash
python3 scripts/run_tests.py              # full suite, 100% branch coverage gate
python3 scripts/run_tests.py --no-cover   # no coverage accounting
python3 scripts/run_tests.py -k dispatch  # by name fragment
```

Coverage is branch coverage with `fail_under = 100` in `pyproject.toml`: a
line the tests touch but do not branch is not covered. Adequacy is audited
by mutation testing — `scripts/mutate.py` mutates the AST of the engine
modules and fails if a mutant survives without a recorded reason in
`scripts/mutation-allow.json`.

CI (`.github/workflows/ci.yml`) runs Python-only gates: the suite under a
pinned coverage floor, the skill contract validator, the prompt-injection
lint, and a secret scan.

## Safety

`.executor/` may be committed, so everything in both stores is written as
though it will be public. Credentials, tokens, and personal data never go
into any payload — a redacted existence statement and a safe shape
instead. `executor check --secrets` scans both stores and reports
file:line and the rule, never the value; reviewers treat credential-shaped
content in any diff as a `critical` finding, and a secret that reached a
diff is rotation, not a file edit. `skills/executor/references/safety.md`
carries the policy.

## Project docs

| Doc | Purpose |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to change skills, references, and the engine |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Participation standards and enforcement |
| [SECURITY.md](SECURITY.md) | Reporting vulnerabilities and how artifact secret-hygiene works |
| [CHANGELOG.md](CHANGELOG.md) | Notable changes, newest first |

This README is the project's single design document: the protocol, the
reasoning behind each invariant, and the flows that drive it all live here.

## License

[MIT](LICENSE)
