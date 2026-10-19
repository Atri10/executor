---
name: executor-planning
description: Use when `executor next` enters `planning` — a spec has passed its gate and must become implementable tasks before any code is written, or when an existing plan must be split, extended, or repaired so it can be dispatched.
---

# Planning

> **Engine.** `executor <verb>` means
> `python3 <skills-dir>/executor/scripts/executor <verb>`; the engine ships
> inside the router skill, so nothing is on `PATH`.

Turn the `spec` artifact into `plan` payloads: each carries `plan_id`,
`objective`, `tasks[]` with exact file paths, verbatim test
expectations, and `depends_on` edges, and `gates[]` naming what must
hold. Planning ends when the plan set clears regression and the human
picks at `GATE plan_regression`.

**Write for an engineer with zero context for this codebase.** Assume a
skilled developer who knows almost nothing about our toolset or problem
domain. The `goal`, `files`, and `accepts` are yours to pin down —
which files they touch, what each change must do, what tests prove it.
The HOW inside those files — local names, internal structure,
error-handling style — is the implementer's own decision inside that
contract. DRY. YAGNI. TDD. Frequent commits.

That framing is not politeness. Under `executor-execution` each task is
dispatched to a **fresh worker that reads only its own `prompt.md`** —
the task's `goal`, `accepts`, `files`, plus an identity header.
Anything you leave implicit is unavailable to the agent implementing
it — and any implementation you write out in full is a design decision
they no longer make, bugs included.

## Before You Write Anything

| Read | Why |
|---|---|
| `../executor/SKILL.md` | ID grammar, citation rule, pump contract |
| The `spec` artifact | the plan argues from it; `cites` names it |
| The `ifce` artifacts | every signature a task's contract names comes from here |
| The `adr` artifacts | a plan that reopens a decided question is a defect |
| `executor status` | the phases that passed, the artifacts cleared |

**Prerequisites.** `executor status` shows `specification` passed
(`gate_decision approved`, not waived-into-nothing). No approved spec →
stop; route to `executor-spec`. No `ifce` and the work spans components
→ stop; route to `executor-architecture`. Planning does not invent
structure.

**Brainstorm the decomposition first — required.** A decided
`brainstorm` session feeding `planning` must exist: it compared at
least three ways to split the spec into plans and tasks — by component,
by user-visible slice, by risk-first spike — and recorded the human's
pick. The session's `Handoff` section (MVP slice and increments) is
the plan set's main input. A plan that splits differently cites a new
session.

**The citation rule is absolute.** Every id in a `cites` entry begins
with this plan's own initiative. A task needing something from
`INIT-0002` states the requirement in its own words; the dependency
lives in the charter.

### Citing spec requirements and constraints

A spec's `requirements[].id` and `constraints[].id` are addressable.
Use them; never write prose like "requirement 7".

| Token | Means |
|---|---|
| `R07` inside a task's `goal`/`accepts` (the plan's `cites` names its spec) | requirement 7 of that spec |
| `C03` | global constraint 3 |

Requirement IDs are what make spec-coverage mechanical instead of
impressionistic — the `plans` audit walks them.

## Step 1 — The plan id

`executor next` mints it: `INIT-0004-P01`, `P02`, … — numbered
per-initiative. The `author` `DISPATCH`'s `entity` is the id; the
payload's `plan_id` echoes it (`wrong_plan` rejection otherwise).

## Step 2 — One plan or several

Set `more_plans: true` on the first `plan` payload when the spec covers
subsystems that can ship independently; the engine then `author`s the
next plan. **Each plan must produce working, testable software on its
own** — a plan that leaves the tree broken until its successor lands
is not a plan, it is half of one.

| Split when | Keep as one plan when |
|---|---|
| Two subsystems with a stable seam between them | Tasks share a file and interleave |
| The second half depends on operational feedback from the first | The split is only "the plan feels long" |
| Different reviewers own the halves | Neither half is independently testable |

When you split, the **first** plan carries an explicit ordering note in
`gates[]` (`"execution order: P01 before P02"`), and every later plan
carries an `Assumes` section naming exactly what it takes from its
predecessors, **with exact signatures**:

```text
Assumes — INIT-0004-P01 has landed and provides:

- placeCell(tenantId: str, weight: int) -> CellId in src/cells/placement.py
- class CellId(NamedTuple): region: str; index: int in src/cells/types.py

If either signature differs from the above when this plan starts, stop
and repair the plan — do not adapt around it.
```

Cross-plan ids are inside the same initiative, so `cites` may name
earlier plans. References to another *initiative's* plan are not.

## Step 3 — Map the files before defining tasks

This is where decomposition gets locked in. Write the file map as a
`File Map` section first; tasks fall out of it.

- Design units with clear boundaries and well-defined interfaces. **One
  clear responsibility per file.**
- You reason best about code you can hold in context at once, and edits
  are more reliable in focused files. **Prefer smaller, focused files**
  over large ones that do too much.
- **Files that change together live together.** Split by
  responsibility, not by technical layer.
- **In existing codebases, follow established patterns.** If the
  codebase uses large files, do not unilaterally restructure — but if a
  file you are modifying has grown unwieldy, including a split in the
  plan is reasonable.

Each task then produces self-contained changes that make sense
independently.

## Step 4 — Right-size the tasks

**A task is the smallest unit that carries its own test cycle and is
worth a fresh reviewer's gate.**

| Rule | Consequence |
|---|---|
| Fold setup, configuration, scaffolding, and documentation into the task whose deliverable needs them | a "set up the config" task has nothing a reviewer can reject |
| Split only where a reviewer could meaningfully reject one task while approving its neighbour | otherwise the split adds two dispatches and no signal |
| Every task ends with an independently testable deliverable | the review verdict has something to grade |

Tasks are `T01`…`Tnn` **per plan**, local ids. `P02` starts again at
`T01`; the plan id keeps them distinct — the full task id is
`INIT-0004-P01-T03`.

## Step 5 — Write the plan payload

```json
{"kind": "plan", "v": "v1", "dispatch_id": "D00012",
 "plan_id": "INIT-0004-P01", "title": "Cell router",
 "objective": "one sentence: what this builds",
 "summary": "…", "more_plans": false,
 "cites": ["INIT-0004-SPEC-01", "INIT-0004-IFCE-01"],
 "tasks": [...], "gates": [...],
 "sections": [...]}
```

### `objective` and `sections`

`objective` is the one-sentence goal. The `sections` carry the plan's
contract prose, in this order — each section as `prose` or `bullets`,
each grid as a `tables[]` entry with `columns` plus `rows`; the engine
renders the `.md`, so no payload ever carries formatting:

| Section | Contains |
|---|---|
| Global Constraints | `C01`–`Cnn` verbatim from the spec — never paraphrased |
| Interfaces | `ifce` ids + the signatures this plan touches, verbatim |
| Assumes | `P02`+ only — predecessor signatures, verbatim |
| File Map | the decomposition from step 3 |
| Dependency Map | one row per pair of tasks sharing a file or symbol |

**The leak you must close:** a worker's `prompt.md` carries only the
task's own fields — the plan's sections do not travel with it. Any
constraint a task can violate inside its own code — a version it pins,
a string it writes, a dependency it adds — is **restated inside that
task's `goal` or `accepts`**, with its id. The plan section is for the
reviewer and the audit; the duplicate in the task is for the worker
who sees nothing else.

**Interfaces are cited, never invented.** A signature that does not
exist yet is an architecture gap: stop, go back to
`executor-architecture`, get the `ifce` authored, then resume. An
invented signature is a decision made without an `adr`, discovered at
review time by two tasks that built incompatible halves of one seam.

### Dependency Map

One row per pair of tasks sharing a file or an interface — the input to
`depends_on` and the engine's file-conflict awareness:

| Producer | Consumer | Shared surface | What flows across it |
|---|---|---|---|
| T02 | T04 | `src/cells/types.py` | `CellId` NamedTuple definition |
| T03 | T05 | `placeCell()` | signature and `CellError` raise contract |

| Rule | Why |
|---|---|
| **Producer is ordered before consumer** — `depends_on` encodes it | a consumer dispatched first has nothing to import |
| One row per *pair*, not per file | the controller needs the direction, not an inventory |
| Two tasks writing the same file appear here even with no symbol shared | that is a merge conflict, and the engine serialises them |
| Close with "no pair outside this table" | it turns an omission into a falsifiable claim |

If the map shows a cycle — T04 needs T06 and T06 needs T04 — the task
boundary is wrong. Merge them or move the shared symbol into an earlier
task. The engine does not detect a cycle when the payload lands: it
walks `depends_on` when choosing work, so a cycle means no task inside it
is ever dispatchable, and the pump answers `ESCALATE` with "no
dispatchable work". That failure is diagnosable, but the fix belongs
here, before execution — the plan-auditor grades a cycle as `critical`.

### The `tasks[]` contract

Each task is `{id: "T03", title, goal, files, accepts, depends_on}` —
all required except `depends_on`:

```json
{"id": "T03", "title": "Cell placement scoring",
 "goal": "Implements R04, R05. Constraints: C01 (Python >= 3.11), C02 (mypy --strict). Scores are pure functions of the arguments — no clock, no I/O. Consumes: `CellId` from src/cells/types.py (T02). Produces: `score(cell: CellId, load: int) -> float` — returns 0.0..1.0, raises ValueError when load < 0; T05 calls this.",
 "files": ["src/cells/scoring.py", "tests/cells/test_scoring.py"],
 "accepts": ["`score(CellId(\"eu-west\", 3), 0) == 0.0`",
             "`score(…, -1)` raises ValueError",
             "pytest tests/cells/test_scoring.py -v → 2 passed, exit 0"],
 "depends_on": ["T02"]}
```

| Field | Status in the dispatch |
|---|---|
| `goal` | contract — verbatim; the requirements, constraints, and Consumes/Produces signatures the implementer builds to |
| `files` | contract — verbatim; the implementer writes only these |
| `accepts` | contract — verbatim; the acceptance criteria the `verdict` grades — the test expectations in full |
| `depends_on` | contract — `T`-local ids; the engine dispatches only when they complete |
| Implementation code inside `goal` | sketch — reference only, never authority |

**Acceptance criteria stay verbatim.** `accepts` entries are the
contract the reviewer grades — assertions with expected values, the
command and its expected output. An `accepts` entry like "works
correctly" is a `critical` audit finding.

**Implementation code is limited to seams.** Signatures, protocol and
DDL definitions, interface definitions, and short sketches of the
non-obvious branch earn their place inside `goal` — labeled as
sketches. A task whose `goal` carries a complete implementation is
over-specified: it pre-spends the implementer's design decisions,
reduces the dispatch to a transcription job, and copies the plan
author's bugs into the diff verbatim. Model selection at dispatch
routes by task complexity, not by how much code the plan already
contains. If a task seems to need its whole body written out, the
design belongs upstream (`ifce`, `adr`, or a thicker Consumes/Produces
contract) — not in the task.

**The TDD rhythm binds every task producing or changing behavior.** The
worker is briefed red-green: write the failing test → run it and see
it fail → minimal implementation → run it and see it pass → refactor →
commit. A task with genuinely no test cycle (pure configuration,
generated code) needs its reason stated in `goal` — an unstated
exception is a plan defect the audit will flag.

**`goal` names the expected failure.** The RED expectation — the exact
failure the test produces before the implementation exists — lives in
`goal` or `accepts`: `FAIL: NameError: name 'score' is not defined` is
a correct RED; `FAIL` alone is not. This is what catches fake TDD at
the source: an implementer who writes test and code together cannot
state the expected failure, because they never watched it.

**Test quality is planned, not hoped for.** Tests named in `accepts`
follow the two-principle doctrine in
[`../executor/references/test-quality.md`](../executor/references/test-quality.md):

- Expected values are **literals or hand-checked fixtures** — never
  derived by calling the function under test (a mirror assertion
  passes no matter what the code does).
- Assert **behavior, not text**.
- Keep **your code, not the framework's** under test.
- Mock only the slow or external dependency, **mirror its data
  structure completely**, and let the mock earn no assertions.
- Cover the **negative and boundary** paths the requirement names.

**Consumes/Produces inside `goal` is how a worker who sees only their
own task learns what neighbours expose.** Every Produces entry a later
task consumes appears in the Dependency Map, and vice versa.

**The Implements ids are what the reviewer grades against.** A task
implementing no requirement is scope you invented; a requirement
implemented by no task is a coverage gap the `plans` audit catches by
id, not by reading.

### `gates[]`

Named conditions the plan-level `audit`/`verdict` checks beyond the
per-task loop — "the merged diff passes `mypy --strict`", "the new
endpoint appears in the smoke path". Keep them few and checkable.

## No Placeholders

Every `goal` and `accepts` contains the actual content the engineer
needs. These are **plan failures** — never write them:

- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge
  cases"
- "Write tests" without the actual expected assertions
- "Similar to Task N" instead of restating the contract — **the worker
  may be reading tasks out of order**, and under `executor-execution`
  they read exactly one task and nothing else
- `accepts` that describe *what* to do with no checkable outcome
- Implementation code that pre-spends the implementer's design
  decisions — full file bodies, complete class implementations. Keep
  the signatures, invariants, and test expectations; drop the bodies
- References to types, functions, or methods defined in no task and in
  no `ifce`

A placeholder is not a shortcut you pay for later. It is a question
the implementer answers at 2 a.m. with the worst plausible guess,
which the reviewer then rejects, which costs one full fix round.

## Self-Critique

After the plan payload is complete, read it against the spec with
fresh eyes — an adversarial pass you run yourself, before the engine's
`audit` dispatch grades it. Redraft inline.

**1. Spec coverage.** Walk the spec's `requirements[].id` in order and
name the task that implements each. An unmapped requirement gets a
task; a task mapped to nothing gets deleted or justified.

| Requirement | Task |
|---|---|
| `R01` | T01 |
| `R04` | T03 |
| `R11` | T07 |

**2. Placeholder scan.** Search `goal`/`accepts`/`sections` for every
pattern above. Fix each hit.

**3. Type consistency.** Do the types, signatures, and property names
used in later tasks match what earlier tasks defined? `clearLayers()`
in T03 and `clearFullLayers()` in T07 is a bug — the second dispatch
fails on an import error and burns a review round.

**4. Interface fidelity.** Every signature in every Interfaces section
is character-identical to the `ifce` payload. A paraphrase is a
defect.

**5. Dependency-map completeness.** Every Produces entry another task
consumes has a row. Every shared file has a row. No cycles —
`depends_on` producers precede consumers.

**6. Citation check.** Every `cites` entry and every `R`/`C` token
resolves inside this initiative.

**7. TDD completeness.** Every task that produces or changes behavior
names the full rhythm in `goal`/`accepts`: the failing test, the
expected failure, the minimal implementation, the green run, the
refactor, the commit.

**8. Task completeness.** Every task carries `id`, `title`, `goal`,
`files`, `accepts`, `depends_on` — the schema enforces presence; you
enforce content. An `accepts` a fresh implementer cannot verify is a
`critical` finding.

**9. The fresh-implementer test.** For each task, ask: could a worker
who reads only `goal`/`files`/`accepts` — no plan, no conversation,
no spec — finish the task without asking a single question? Every
question you can imagine them asking is a missing line.

**10. Decomposition fidelity.** Does the plan set follow the split the
decided planning session chose? A plan that silently re-splits the
work discards the human's decision.

## Verification

Run these in this session, and cite their output in the gate
presentation:

1. `executor ingest` accepted every `plan` payload — schema-clean:
   task ids local, `plan_id` echoes the entity, `tasks` non-empty.
2. `executor status` — every plan row `cleared` after its `plans`-catalog
   audit, or each open finding named.
3. `executor check` — `cites` resolve; no task `depends_on` a task
   that does not exist (`dangling_ref`).
4. `executor check --secrets` — exit 0.

## Decisions Here Are ADRs

A **ruling** is a runtime concept: the controller decides something
without the human *while the run is live*, and `executor decide`
journals it. Planning is not a run.

A decision taken while planning — a structure choice, a library pick,
a boundary you moved — is an **`adr` artifact** (`executor-architecture`
owns the phase). If planning surfaces a decision the architecture
never made, that is the signal to stop planning: route back, get the
`adr`, then resume. Planning around an unmade decision buries it in a
`goal` where no reviewer will recognise it as a decision.

## Execution Handoff

The handoff has two gates in sequence: **plan regression first** (the
plan set survives an adversarial audit as a set), **then** the human
picks. Never offer execution before regression clears — a pick made on
an unaudited plan set is approval of defects nobody has read yet.

**0. Plan-set regression.** When the plan set is drafted — whether one
plan or five — `executor next` enters `plan_regression`: route to
`executor-plan-regression`. The audit/repair loop clears or escalates
each plan; then `GATE plan_regression` opens and the human decides.

(Skippable only by the human's `waived` `gate_decision` with a `note`.)

**1. The gate ends your turn.** Present `executor status` — the plans,
their audit record — and stop. The human's `gate_decision` records the
pick.

Then hand to `executor-execution`. **Once execution starts it runs to
completion without check-ins** — approval happens at phase boundaries,
not inside them. That is exactly why every defect above must be caught
here.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "The implementer can look up the signature" | They read one task. Put it in `goal`, or they invent one. |
| "Task 5 is similar to Task 3" | Dispatches are independent and out of order. Restate the contract — files, signatures, accepts. |
| "I'll add the task ids when execution starts" | `tasks[].id` is schema-required; the payload never validates without them. |
| "The dependency map is obvious from the tasks" | Obvious to you, holding all seven. `depends_on` is what the engine serialises dispatch from. |
| "The interface isn't defined yet, I'll approximate" | That is an architecture gap and an unwritten `adr`. Stop and go back. |
| "Global Constraints cover it, no need to repeat" | The plan's sections never reach the worker. Restate anything a task can violate in its `goal`. |
| "Citing requirement numbers in prose is the same thing" | `R07` is auditable; "requirement 7" drifts the moment the spec changes. |
| "One giant task is simpler to review" | A reviewer cannot reject half of it, so they approve all of it. |
| "'Add error handling' is clear enough" | It is the single most rejected step in review. Specify the raise contract in `accepts`. |
| "Writing the code in the plan prevents implementer mistakes" | It transcribes the plan author's mistakes instead — verbatim, into the diff. `goal` carries the contract; bodies are the implementer's job. |
| "I'll fix the type mismatch during execution" | It surfaces as an import error mid-dispatch and costs a full fix round. |
| "I'll start executing while the human reviews the plan" | The gate ends your turn. Work past an unmade decision is work the approval cannot cover. |
