---
name: executor
description: Use when a request arrives and it is unclear whether it needs an initiative, when starting or resuming any Executor initiative, or when deciding which executor phase skill applies next.
---

# The Executor

A body of work gets one **Initiative**. The initiative owns a folder, an ID
namespace, and every document produced about it — charter, research,
architecture, decisions, interfaces, design, spec, risks, verification,
plans. Execution artifacts for those plans live in a separate store, keyed
by the same IDs.

Nothing floats. Every document, every task, every review, every ruling
carries an ID that names the initiative it belongs to, and no document
cites an ID from a different initiative.

## When to Use

Route here when work is substantial enough to survive a session: a new
subsystem, a migration, a feature spanning multiple components, a
rearchitecture. The Executor scales down (a small initiative has a charter,
a spec, one plan) but it does not scale to zero.

**Do NOT use for:** a typo, a one-line fix, a question, a spike whose output
is an answer rather than code. Those need no initiative. Creating one for
trivial work is the primary failure mode of this system — the ceremony
becomes the work.

**The gate:** if you cannot name a deliverable that outlives this session,
there is no initiative. Answer the question and stop.

## The `executor` command

Every skill in this library writes `executor <verb>` as shorthand. The
engine ships **inside this skill**, at `scripts/lib/executor/`, so nothing
is installed on `PATH` and no `PYTHONPATH` is set. Spell the command from
the skill's own directory — the directory containing this `SKILL.md`:

```bash
python3 <skill-base-dir>/scripts/executor next
```

`<skill-base-dir>` is that directory, not the project you are working in:
the launcher resolves its engine relative to itself, so it runs correctly
from any working directory. Where the filesystem kept the exec bit, the
bare `<skill-base-dir>/scripts/executor next` works too; `python3` is the
portable spelling and the one to use when a shell is unsure. Requires
Python 3.11+; the engine is standard library only, so there is nothing to
install, no virtualenv, and no dependency to resolve.

If the launcher reports the bundled engine missing, the skill was copied
incompletely — reinstall it rather than editing its contents. Do not fall
back to `python3 -m executor` from a clone: a clone's engine and the
skill's engine are different versions as soon as either moves, and the
store records which one wrote it.

## Session Opening Ritual — run before ANY work, every session

Before your first substantive action in any session touching an Executor
initiative, execute this ritual. It is not optional and it is not skippable
because you "already know" the state — session memory is not state.

```bash
git branch --show-current && git rev-parse HEAD && git status --short
```

Then read, in this order:

1. `executor status` — the gate card: which initiative exists, its phase,
   phase state, counts, and any halt.
2. `executor doctor` — open dispatches and the policy in force, so you
   know what the engine will do next.
3. `executor check` — journal refold, chain, liveness, layout. A problem
   found here is repaired before new work, not after.

Only then state, in one line: which initiative you are in, which phase it
is in, and what the last recorded event was. If you cannot state all
three, you are not ready to work. **Precedence, absolute:** the journal
beats memory — if `executor status` says `planning` and you recall a
passed gate, the journal wins; work from the record, not the recollection.

## Hard Rules — these bind regardless of which phase skill is loaded

**1. You never write implementation code outside `executor-execution`'s task
dispatch, and you never write it inline.** In discovery, architecture, spec,
and planning you write documents — no project scaffolding, no source files,
no `mkdir` for code, no "quick fix while I'm here". A probe whose output is a
measurement is evidence; label it throwaway in the document that cites it.
The only phases that touch production code are `executor-execution` (through
dispatched implementers) and `executor-verification` (through running checks).
If you catch yourself opening a source file to edit it in any other phase —
stop. That is the primary failure mode of weaker models running this system.

**2. A gate means END YOUR TURN.** "Present and stop" means: your message
ends after presenting the artifact. No follow-up work, no "while you review
that, I'll…", no next-phase preparation. The next message after a gate
presentation is the human's answer, not your continued work. Silence is not
approval — nothing acquires consent by aging.

**3. Never guess when you can read, never reason when the engine answers.**
Store paths, IDs, and phases come from the engine and its CLI (`executor
next`, `executor status`, `executor check`). Hand-built paths and invented
IDs are defects even when they look right — `executor check` enforces the
naming grammar on every file in both stores and reports anything else.

**4. One phase at a time, declared.** Every message you send names which
phase you are working in. If your work has silently drifted into a different
phase's territory (discovery producing architecture, planning writing
requirements), stop and either re-route or record the phase transition
properly.

**5. During execution, you are a pump, not a planner.** `executor next`
decides what is legal next; you carry it out. You do not read artifacts to
work out what should happen, you do not choose the order, and you do not
hold state between turns. If you find yourself reasoning about what the run
"should" do next, that reasoning belongs to the engine or to a dispatched
worker — see The Pump Contract below.

## The Pump Contract

Execution has one loop, and it is mechanical:

1. Run `executor next`.
2. Read the single action it emits, as JSON.
3. Do exactly that thing.
4. Go back to 1.

That is the whole of your job during a run. Every action carries a `resume`
manifest: the journal is the state, and a cold controller re-grounds from
`executor status` and `executor check` instead of memory. The controller is
the least reliable worker in this system — it dies, compacts, drifts, and
is under pressure at exactly the moment a judgment call matters — so the
design assumes it will try to be clever and takes away the opportunity.

A **DISPATCH** action carries everything the worker needs: `dispatch_id`,
`entity`, `schema`, `role`, `context`, and `respond_to` — the path of the
payload file the worker writes and you feed to `executor ingest`. The
worker answers the dispatch; the engine decides whether the answer is
accepted. A poll that changes nothing emits the same action again without
writing anything new: repeated `executor next` is free.

### The decision table

| `executor next` emits | You do |
|---|---|
| `PHASE-ENTER <phase>` | The phase changed. Route to the owning skill — you do not author anything |
| `DISPATCH` | Spawn the named `role` on its prompt template with `entity`, `context`, `respond_to`. A `DISPATCH` re-emitted with the same `dispatch_id` is the same open dispatch, not a new one |
| `GATE <phase>` | Present `executor status` (the gate card) to the human. They answer with `executor decide` — a `gate_decision` payload. Under an autonomy mode of `gate`/`allow` a structural phase's gate clears itself as `by: "auto"`; pick phases and handoff never do |
| `ASK <topic>` | Relay the question to the human; their answer goes in as a `ruling` via `executor decide`, or answers a blocked task's `needs_context` verbatim |
| `MERGE <plan>` | Run the plan's merge step the skill prescribes, then ingest the `merge` payload with the resulting head |
| `ESCALATE` | A bound was hit: too many fix rounds, a dead or silent dispatch, conflicting ownership. Present the escalation; do not improvise a fourth round |
| `HALT` | The run is stopped. `halt` was journaled; only a human `resume` payload via `executor decide` unlatches it |
| `DONE` | The run is finished. Report and stop |

**What "subagent-driven" means here, precisely.** Every step is either a
dispatch or an ingest — never you doing the work:

- A **dispatch** is intellectual work: authoring, auditing, implementing,
  reviewing, answering evidence. It goes to a named role (`author`,
  `repair`, `impl`, `review`, `fix`, `evidence`) with a registered prompt
  template, and its output is a payload someone else will judge.
- An **ingest** is a transition: the payload lands in the journal, the fold
  updates, and the next `executor next` decides again. `executor ingest`
  is for worker payloads; `executor decide` is for the human-only kinds —
  `gate_decision`, `ruling`, `resume` — which the CLI stamps `actor: human`
  so a worker cannot claim them.

A refused payload writes nothing, and every refusal names a code and a
field path. [references/rejections.md](references/rejections.md) is the
authoritative list: what each code means, and the action that clears it.
Fix the named thing and re-ingest — never re-author the journal, never
substitute a payload that happens to pass, and never ask the engine to
accept it.

The test: *would a subagent reading only its prompt know more than you do
right now?* If yes, dispatch. If the prompt would just be a transcript of
the payload you are about to ingest, ingest it.

### What the pump never does

- **Never authors.** Charter, spec, architecture, plan, report, verdict —
  every one is a dispatch. An artifact the controller wrote is an artifact
  nobody reviewed.
- **Never judges.** Pass or fail is a `verdict` payload; merged or not is
  a `merge` payload the engine checks. Your opinion of the diff is not
  state.
- **Never improvises a transition.** If the emitted action has no row in
  the table above, you have found a gap in the engine. Record it as a
  `concern` in a report and stop; do not approximate the missing
  behaviour.
- **Never absorbs a dead worker's work.** A silent dispatch is abandoned
  past `deadline_s` and redispatched by the engine with the same context.
  Taking over the task yourself deletes the audit trail and is the single
  most damaging thing a pump can do.
- **Never answers a human-only kind.** `gate_decision`, `ruling` and
  `resume` are refused by `executor ingest` as `unauthorized`; only
  `executor decide` writes them, as `actor: human`. You may recommend a
  waiver of an open finding; you may never grant one, and a waiver the
  human did not state is not a waiver.

### Autonomous mode

An initiative may run unattended for the phases whose autonomy the human
permits. The policy is a JSON map of phase to mode at
`.executor/<INIT>/meta/autonomy.json`, read or written through
`executor autonomy`:

```text
executor autonomy                       # the policy in force, every phase
executor autonomy execution allow       # a structural gate may clear itself
```

`deny` never clears unattended — it is the default for every phase. Under
`gate` or `allow` a **structural** phase's gate clears itself and the
journal records `gate_decision` with `by: "auto"`. The pick-class phases —
design and specification, where a human chooses between options — and
handoff, the human's sign-off on the run, never clear automatically,
whatever the file says.

The policy fails closed. A missing or malformed file, an unlisted phase,
or a mode spelled anything else all read as `deny`; `executor autonomy`
refuses an unknown phase or mode outright, so a typo can never widen a
phase. Widening a phase mid-run is a decision for the human, not for you.

An automatic pass is journaled as `by: "auto"`, never as a human decision.
Keep it that way: the difference between "a person looked at this" and
"the policy cleared this" is the difference a reader needs six weeks
later.

### When the human interrupts

If the human says something mid-run, do not interpret it and carry on.
Write it as a payload through `executor decide`:

- They answer a question you asked — the answer is a `ruling`, optionally
  scoped `for_task`/`for_plan` with `question` quoting what was asked.
- They say something you did not ask about — a `ruling` recording their
  words verbatim.
- They are stopping the run — a `halt` payload latches: `executor next`
  emits `HALT` and no dispatch until the human sends a `resume`. While
  halted, `ruling` and `resume` are the only payloads ingest still
  accepts.

Their words go in verbatim. A paraphrase in a ruling is a ruling nobody
can check against what was actually said.

## Drift Recovery — when you notice you violated a rule

Violations compound: an inline edit becomes an unrecorded decision, becomes
an unreviewed change, becomes a spec that argues from nothing. The recovery
procedure is fixed:

1. **Stop the violating action immediately.** Do not finish the edit, the
   scaffold, or the batch you were mid-way through.
2. **Assess exposure.** Did the violation produce files, commits, or
   side effects? List them.
3. **Repair to the record, not to silence.** Anything created gets either
   reverted (`git checkout -- <paths>` for uncommitted edits, or explicitly
   marked throwaway) or properly recorded (a ruling, an ADR, a phase-log
   note). An unrecorded violation discovered later by a reviewer costs a
   full round; recorded, it costs one line.
4. **Re-run the Session Opening Ritual** before continuing — your model of
   the state was wrong when you drifted; re-ground before acting on it.
5. **Continue the correct phase.** Do not restart the whole initiative; the
   record exists precisely so a detour does not become a rewrite.

## Invocation

The root router is available as the `executor` skill:

```text
/skill:executor
```

Use the phase-specific skill when the initiative already has a gate-passing
artifact:

```text
/skill:executor-initiative
/skill:executor-discovery
/skill:executor-architecture
/skill:executor-spec
/skill:executor-planning
/skill:executor-plan-regression
/skill:executor-execution
/skill:executor-review
/skill:executor-verification
/skill:executor-handoff
/skill:executor-brainstorm
```

An explicit `/skill:<name>` call loads the skill immediately in runtimes
that support it. Normal requests also route by the frontmatter description;
say "start an initiative" for intake or "execute plan INIT-0004-P01" for a
plan already approved.

The engine is a command, not a skill. It ships inside this skill's
`scripts/` directory; the `executor <verb>` spelling throughout this
library means `python3 <skill-base-dir>/scripts/executor <verb>` as
described under [The `executor` command](#the-executor-command).

## The Two Stores

```mermaid
flowchart LR
    subgraph THINK["docs/executor/ - tracked"]
        C["Charter"] --> R["Research, Options"]
        R --> A["Architecture, ADRs, Interfaces"]
        A --> D["Design"]
        D --> S["Spec"]
        S --> P["Plans"]
    end
    subgraph EXEC[".executor/ - git-ignored by default"]
        L["Ledger, Rulings"]
        B["Briefs"]
        RP["Reports"]
        V["Diffs, Verdicts"]
    end
    P -->|"each task dispatch"| B
    B --> RP
    RP --> V
    V --> L
```

**`docs/executor/` — the thinking record.** Git-tracked. Survives clones and
CI. Holds what the work IS and why: charter, research, architecture,
decisions, interfaces, design, spec, risks, verification strategy, plans,
and brainstorming sessions. A reader who clones the repo gets the complete
reasoning.

**`.executor/` — the execution record.** Git-ignored by default via a
self-writing `.gitignore`, and **safe to commit** if the user chooses:
task briefs, implementer reports, review diffs, review verdicts, the
progress ledger, rulings, dispatch log. Holds what HAPPENED during
execution. Never deleted when a plan completes — the reasoning inside it is
the point.

The split is durability-of-audience, not durability-of-value. Thinking
artifacts are for anyone who ever touches the code. Execution artifacts are
for whoever needs to know how this specific run went. Both are kept.

## The ID Namespace

One initiative, one namespace. IDs are structural, not decorative.

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
`ARTIFACT_SEGMENTS` in `scripts/lib/executor/paths.py` defines them, and an ID
carrying any other segment is a `pattern` rejection. Sequence within a
kind is per-initiative and starts at `01`.

Items *inside* a payload are addressable too: a spec's requirements as
`-R<2-digit>` and its global constraints as `-C<2-digit>`, hanging off
the spec's own ID, and a document's sections by their `sections[].id`.

Addressable requirements are what let a review finding name the exact
contract it violates instead of gesturing at the spec, and what lets a
plan task declare precisely which requirements it discharges.

### The citation rule (hard)

**A payload MUST NOT cite an ID belonging to a different initiative.**

Inside `INIT-0004`, every reference — `cites: ["INIT-0004-SPEC-01"]`,
`implements: INIT-0004-ARCH-02` — names an ID from `INIT-0004`. This is
what makes an initiative readable on its own: open the folder, and every
pointer resolves inside it.

Cross-initiative relationships exist only at the initiative level,
declared in the **charter's** `cites` — the charter payload is the only
one permitted to carry another initiative's IDs. The handoff index
(generated when the initiative finishes) mirrors them as prose.

```yaml
cites: ["INIT-0002-CHTR-01"]   # the charter this initiative needs first
```

The `cites` list is the entire cross-initiative vocabulary. Supersession
is recorded on both sides: the replacement's charter `cites` its
predecessor, and the predecessor's charter `cites` its replacement. A
one-sided link leaves a reader who finds the old initiative first with
no way forward.

A task, spec, or ADR that needs something from another initiative does not
cite it. It states the requirement in its own words and, if the dependency
is real, the initiative declares it. Chasing an ID across initiative
boundaries is how a document registry turns into a graph nobody can read.

**Why it matters:** an initiative must be archivable. When `INIT-0002`
finishes and is filed away, nothing inside `INIT-0004` breaks, because
nothing inside `INIT-0004` ever pointed at `INIT-0002`'s internals.

### Allocation

Allocate an ID by listing the target directory immediately before writing.
Never invent a number, never reuse one.

Two agents allocating at once can collide. On collision, do not overwrite:
take the next free number, write your file, and note the race in a ruling.
Preserve both documents — this is the same rule `.local/` uses, for the
same reason.

## Phases

An initiative moves through phases. Each phase has an owning sub-skill, an
output, and a gate that must pass before the next phase starts.

| Phase | Skill | Output | Gate |
|---|---|---|---|
| Intake | `executor-initiative` | Initiative folder, charter | Human approves the charter's problem statement and success criteria |
| Discovery | `executor-discovery` | Research, options comparison, the feature's design session | Human picks an approach |
| Architecture | `executor-architecture` | Architecture, ADRs, interfaces | Human approves the structure |
| Design | `executor-architecture` | Component designs | Human approves, or waives for simple initiatives |
| Specification | `executor-spec` | Spec, risks, verification strategy | Entry: a decided brainstorm session feeding specification. Exit: human reviews the written spec |
| Planning | `executor-planning` | One or more plans with in-depth tasks | Entry: a decided decomposition session feeding planning. Exit: plan set drafted and linted |
| Plan regression | `executor-plan-regression` | Plan-set audit reports, repairs, gate summary | Every plan clean or human-waived; human then picks an execution mode |
| Execution | `executor-execution` | Commits, reports, ledger | Every task reviewed and complete |
| Review | `executor-review` | Verdicts, findings, rulings | Final whole-branch review clean |
| Verification | `executor-verification` | Evidence of working software | Every claim backed by observed output |
| Handoff | `executor-handoff` | Merged branch, updated indexes | Initiative marked complete |

**Phases compress, they never vanish.** A small initiative can produce a
charter and a spec in one exchange and skip discovery entirely — but
skipping is a stated decision recorded in the charter, not an omission. The
`skipped_phases` field exists so a reader knows the difference between "we
considered alternatives and picked one" and "nobody looked."

## The Approval Gate

**Do NOT write code, scaffold a project, or take any implementation action
until the human has approved the intent for the current phase.**

The artifact scales with the work — a small initiative's architecture
section is three sentences. The approval never scales. Every phase gate in
the table above is a real stop.

**A real stop means your turn ends.** The gate presentation is the last
thing in your message. If you find yourself continuing to work after writing
"please review" — planning the next phase, pre-reading documents, drafting
the next artifact — you have not stopped. A gate crossed without approval
invalidates everything downstream of it: a spec written against unapproved
architecture gets rewritten, a plan built on an unapproved spec argues from
nothing.

Executing a plan is different: once the human approves the plan set — after
plan regression has cleared it — and picks an execution mode,
`executor-execution` runs to completion without check-ins. Approval happens
at phase boundaries, not inside them.

**Recovery when a gate was crossed without approval:** name it plainly to
the human ("I crossed the discovery gate without your pick — here is what I
did meanwhile, and here is the decision you still own"), and treat nothing
produced past the gate as approved. Do not quietly pretend the approval
happened.

```mermaid
flowchart TB
    BR["Brainstorm, design session"] -->|"adopted at intake"| I
    I["Intake, charter"] --> DI["Discovery, research, options"]
    DI -->|"design session"| BRD["Brainstorm, decided"]
    BRD --> AR["Architecture, ADRs, interfaces"]
    AR --> DE["Design, components"]
    DE --> SP["Specification, spec, risks, verification"]
    BRD -->|"feeds specification"| SP
    SP --> BRP["Brainstorm, decomposition decided"]
    BRP -->|"feeds planning"| PL["Planning, plans, tasks"]
    PL --> RG["Plan regression, plan-set audit"]
    RG --> EX["Execution, dispatch loop"]
    RG -->|"findings"| PL
    EX --> RV["Review, verdicts, rulings"]
    RV --> VF["Verification, evidence"]
    VF --> HO["Handoff, merge, archive"]
    RV -->|"findings"| EX
    VF -->|"gap found"| EX
```

**Every phase critiques and verifies its own output before its gate.**
Each phase skill carries a `## Self-Critique` section — an adversarial
pass over the artifacts it just wrote — and a `## Verification` section —
the commands that prove them, run in this session with their output
cited. A gate claimed before both ran is not claimed. Every subagent a
phase dispatches is briefed from its dedicated prompt template in the
[dispatch registry](references/layout.md#dispatch-registry), and each
template carries the same two sections for the agent's own output.

## Routing

| You need to… | Skill |
|---|---|
| Start a body of work, allocate an initiative | `executor-initiative` |
| Design a new feature or use case from a rough idea | `executor-brainstorm` (before any initiative exists, or at discovery) |
| Decide one open design question, or how a spec splits into plans | `executor-brainstorm` (decision mode) |
| Understand the problem, compare approaches | `executor-discovery` |
| Decide structure, record a decision, define interfaces | `executor-architecture` |
| Write the requirements contract | `executor-spec` |
| Turn a spec into tasks | `executor-planning` |
| Audit the plan set before executing it | `executor-plan-regression` |
| Run the plan with subagents | `executor-execution` |
| Review a task, a fix round, or a branch | `executor-review` |
| Prove the work actually works | `executor-verification` |
| Merge, archive, and close out | `executor-handoff` |

Read the contract references before writing anything into either store:

- [references/layout.md](references/layout.md) — exact directory structure
- [references/rejections.md](references/rejections.md) — every refusal code, its field, and the action that clears it
- [references/branches.md](references/branches.md) — the branch model: naming, fork rules, merge gates, edge cases
- [references/frontmatter.md](references/frontmatter.md) — the payload identity contract
- [references/indexes.md](references/indexes.md) — index formats and maintenance
- [references/safety.md](references/safety.md) — secret hygiene, required because `.executor/` may be committed

## Decisions: rule, ask, or stop

Inside a phase, a running Executor does not wait on a human — but it does
not silently decide everything either. Every decision class has exactly one
handling; picking the wrong tier is how rulings go unlogged and questions
go unasked.

| Decision class | Handling |
|---|---|
| Mechanical, contract-derived, or reversible | Decide, journal a `ruling` payload through `executor decide`, keep going. A ruling is written the moment it is made — `for_task`/`for_plan` when it binds one task or plan, unscoped when it binds the initiative. |
| Decision-class | **Ask on the spot, block only the affected lane.** Use your harness's interactive ask affordance (structured question tool if one exists, else a message that ends your turn). The question is recorded in the `ruling` payload's `question` field; other tasks keep moving. |
| The four stops | End the phase/run for human intervention. |

**Decision-class means the answer is not yours to derive:** a conflict
between two contracts that each have authority (IFCE vs SPEC, plan vs
spec); a scope cut — dropping a requirement, shrinking a plan, deferring
non-polish work; an irreversible choice the contracts leave open; product
or UX judgment the spec does not settle. Everything else — including
"which of two legal shapes to build" — is a ruling, not a question. When
unsure whether a decision is a ruling or a question, ask once; a question
that turns out to be a ruling costs one message, a ruling that should
have been a question costs a rework loop.

**The four stops** (unchanged): an irreversible or destructive operation;
a security-sensitive action; a side effect outside this worktree that
norms say you ask about first (a merge, a push to a shared branch, a
publish); a defect so deep that every path forward is a guess.

Between phases, every gate is a human-approval stop — the gates and the
decision-class lane are the only places the workflow waits on the human,
and both write their answers into the record.

## Secret Hygiene

`.executor/` is git-ignored by default, but the user may commit it. Write
every file in both stores as though it will be public.

Never write credentials, API keys, tokens, cookies, private keys, connection
strings, or personal data into any Executor artifact. Diffs and reports are
the live risk: an implementer pasting a `.env` into a report, or a review
package capturing a secret a task added. Record a redacted existence
statement and a safe path instead.

See [references/safety.md](references/safety.md) for the required scan
before any handoff, and what to do when a secret has already landed.

## A Session That Follows the Rules — worked example

The right shape of a session, condensed. Every rule above appears here in
its natural place; if your session does not look like this, find the rule
you skipped.

```text
[Session opens on "continue the cells initiative"]

$ git branch --show-current; git rev-parse HEAD; git status --short
feature/cell-router  a91e502  clean

$ executor status
INITIATIVE INIT-0004 - cells
phase: planning (gate_pending)
events: 96 | artifacts: 9 | tasks: 7
-> GATE planning: awaiting a human decision

Me: "INIT-0004 is at the planning gate: plan P01 (7 tasks) is drafted and
linted clean. Two execution modes: 1) subagent-driven — a fresh
implementer per task with independent review per diff; 2) inline —
faster, no independent review. Which?"

[TURN ENDS. No pre-dispatching, no reading ahead into executor-execution,
 no work in this message beyond the question.]

Human: "Subagent."

[They answer through the human-only channel — a ruling recording the
 mode, then a gate_decision approving the planning gate:]
$ executor decide ruling.json    # {"kind":"ruling","v":"v1","decision":"subagent mode","why":"independent review","for_plan":"INIT-0004-P01"}
$ executor decide gate.json      # {"kind":"gate_decision","v":"v1","phase":"planning","decision":"approved","by":"human"}

$ executor next
{"action": "PHASE-ENTER", "phase": "execution", ...}
[Routes to executor-execution and follows ITS skill from here.]
```

Note what did **not** happen: no inline implementation during planning, no
gate crossed in the same message that presented it, no invented state when
the journal disagreed with memory, no phase transition without the engine.
The whole discipline is: ground first, work one phase, end turns at gates,
record through `executor decide` and `executor next`.

## Self-Critique

Before routing, and again before claiming any gate, run this against what
you are about to do:

1. **Is this the right phase?** Name the phase from `executor status`,
   not from memory. A plan written while the journal says specification
   is work past a gate nobody passed.
2. **Is the next entry gated?** Specification and planning need a decided
   brainstorm session feeding them. If none exists, the route is
   `executor-brainstorm`, not the phase skill.
3. **Did the phase skill's own Self-Critique and Verification run** — and
   is their output in this session, not recalled from an earlier one?
4. **Is every subagent about to be dispatched briefed from its registered
   prompt template**, every placeholder filled, and its model named?
5. **Is anything in the message past the gate?** A gate presentation ends
   the turn; work after it is unapproved.

## Verification

Run these at the start of every session and before every gate:

1. `git branch --show-current; git rev-parse HEAD; git status --short` —
   the repository state the session starts from.
2. `executor status` and `executor doctor` — phase, open dispatches and
   the policy in force, from the journal not memory.
3. `executor check` — the store is consistent; a finding is repaired
   before new work, not after.
4. Before any handoff: `executor check --secrets` — exit 0.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "This is small, skip the initiative" | Correct — if it produces no lasting deliverable. If it does, it gets an initiative with three short documents. |
| "I'll cite the other initiative's ADR, it's right there" | That coupling is what makes registries unreadable. State the requirement in your own words; declare the dependency at initiative level. |
| "The workspace is scratch, I'll delete it when done" | The execution record is the point. Nothing deletes it. |
| "I'll allocate the ID later" | IDs allocated retroactively collide and get invented. List, then write. |
| "The ledger has the ruling, that's enough" | Unrecorded is undecided. A ruling lands in the journal the moment it is made — `executor decide`, not a note to self. |
| "No secrets in this one, skipping the scan" | The scan is cheap and the failure is unrecoverable once pushed. Run it. |
| "Phases are overhead, I'll write the plan directly" | A plan with no spec argues from nothing. If discovery and architecture are genuinely unnecessary, record them as skipped and say why. |
| "I already read the indexes earlier this session" | Session memory is not state. The ritual runs every session; compaction and interruptions make stale confidence expensive. |
| "The next step is obvious, I'll start it while they review" | A gate ends your turn. Work produced past an unpassed gate is work the approval cannot cover. |
| "It's just a small inline edit to unblock the document" | Inline execution in a document phase is the primary drift failure. Record what blocks you instead, or rule on it if a plan is running. |
| "I drifted, but the work is good, I'll keep it quietly" | An unrecorded violation is a defect discovered by a reviewer later. Run Drift Recovery: stop, assess, repair to the record, re-ground. |
