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

## Session Opening Ritual — run before ANY work, every session

Before your first substantive action in any session touching an Executor
initiative, execute this ritual. It is not optional and it is not skippable
because you "already know" the state — session memory is not state.

```bash
git branch --show-current && git rev-parse HEAD && git status --short
```

Then read, in this order:

1. `docs/executor/INDEX.md` — which initiatives exist, their status and phase.
2. The active initiative's `INDEX.md` — its phase log: where work actually
   stopped, and which phases are skipped versus never done.
3. Any `.executor/INDEX.md` — which plans ran and where their workspaces are.

Only then state, in one line: which initiative you are in, which phase it is
in, and what the last recorded event was. If you cannot state all three, you
are not ready to work. **Precedence, absolute:** current repository state
beats stored records — if the phase log says `planning passed` and there is
no plan file, the code wins; write a correction, do not proceed on the
stale record.

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

**3. Never guess when you can read, never read when a script answers.**
Store paths, IDs, and phases come from the scripts (`exec-initiative`,
`exec-id`, `exec-workspace`). Hand-built paths and invented IDs are defects
even when they look right.

**4. One phase at a time, declared.** Every message you send names which
phase you are working in. If your work has silently drifted into a different
phase's territory (discovery producing architecture, planning writing
requirements), stop and either re-route or record the phase transition
properly.

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
/skill:executor-execution
/skill:executor-review
/skill:executor-verification
/skill:executor-handoff
```

An explicit `/skill:<name>` call loads the skill immediately in runtimes
that support it. Normal requests also route by the frontmatter description;
say "start an initiative" for intake or "execute plan INIT-0004-P01" for a
plan already approved.

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
INIT-0004-RSCH-02              a research note
INIT-0004-OPTS-01              an options comparison
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
INIT-0004-P01-T03-R02          review round 2 of that task
```

**Grammar:** `INIT-<4-digit>` then `-<TYPE>-<2-digit>`, plans as
`-P<2-digit>`, tasks as `-T<2-digit>`, review rounds as `-R<2-digit>`.
Sequence within a type is per-initiative and starts at `01`.

Items *inside* a document are addressable too: a spec's requirements as
`-R<2-digit>` and its global constraints as `-C<2-digit>`, hanging off the
spec's own ID. A requirement token and a review-round token never collide,
because a round always carries a `-T<2-digit>` segment before its `-R`
(`…-P01-T03-R02`) while a requirement hangs directly off `…-SPEC-01-`.

Addressable requirements are what let a review finding name the exact
contract it violates instead of gesturing at the spec, and what lets a plan
task declare precisely which requirements it discharges.

### The citation rule (hard)

**A document MUST NOT cite an ID belonging to a different initiative.**

Inside `INIT-0004`, every reference — `spec: INIT-0004-SPEC-01`,
`implements: INIT-0004-ARCH-02` — names an ID from `INIT-0004`. This is
what makes an initiative readable on its own: open the folder, and every
pointer resolves inside it.

Cross-initiative relationships exist only at the initiative level, declared
in the **charter's** frontmatter. Every Executor document carries
frontmatter; the charter is the only one permitted to carry these four
relationship fields. The initiative `INDEX.md` — which has no frontmatter —
mirrors them in its Dependencies section as prose:

```yaml
depends_on: [INIT-0002]            # this initiative needs that one first
supersedes_initiative: null        # this replaces that one wholesale
superseded_by_initiative: null     # set on the replaced initiative's charter
related: [INIT-0007]               # informational only
```

These four fields are the entire cross-initiative vocabulary. Supersession
is recorded on both sides: the replacement names its predecessor in
`supersedes_initiative`, the predecessor names its replacement in
`superseded_by_initiative`. A one-sided link leaves a reader who finds the
old initiative first with no way forward.

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
take the next free number, write your file, and note the race in the
initiative's `INDEX.md`. Preserve both documents — this is the same rule
`.local/` uses, for the same reason.

## Phases

An initiative moves through phases. Each phase has an owning sub-skill, an
output, and a gate that must pass before the next phase starts.

| Phase | Skill | Output | Gate |
|---|---|---|---|
| Intake | `executor-initiative` | Initiative folder, charter | Human approves the charter's problem statement and success criteria |
| Discovery | `executor-discovery` | Research, options comparison | Human picks an approach |
| Architecture | `executor-architecture` | Architecture, ADRs, interfaces | Human approves the structure |
| Design | `executor-architecture` | Component designs | Human approves, or waives for simple initiatives |
| Specification | `executor-spec` | Spec, risks, verification strategy | Human reviews the written spec |
| Planning | `executor-planning` | One or more plans with tasks | Human picks an execution mode |
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

Executing a plan is different: once the human approves the plan and picks an
execution mode, `executor-execution` runs to completion without check-ins.
Approval happens at phase boundaries, not inside them.

**Recovery when a gate was crossed without approval:** name it plainly to
the human ("I crossed the discovery gate without your pick — here is what I
did meanwhile, and here is the decision you still own"), and treat nothing
produced past the gate as approved. Do not quietly pretend the approval
happened.

```mermaid
flowchart TB
    I["Intake, charter"] --> DI["Discovery, research, options"]
    DI --> AR["Architecture, ADRs, interfaces"]
    AR --> DE["Design, components"]
    DE --> SP["Specification, spec, risks, verification"]
    SP --> PL["Planning, plans, tasks"]
    PL --> EX["Execution, dispatch loop"]
    EX --> RV["Review, verdicts, rulings"]
    RV --> VF["Verification, evidence"]
    VF --> HO["Handoff, merge, archive"]
    RV -->|"findings"| EX
    VF -->|"gap found"| EX
```

## Routing

| You need to… | Skill |
|---|---|
| Start a body of work, allocate an initiative | `executor-initiative` |
| Understand the problem, compare approaches | `executor-discovery` |
| Decide structure, record a decision, define interfaces | `executor-architecture` |
| Write the requirements contract | `executor-spec` |
| Turn a spec into tasks | `executor-planning` |
| Run the plan with subagents | `executor-execution` |
| Review a task, a fix round, or a branch | `executor-review` |
| Prove the work actually works | `executor-verification` |
| Merge, archive, and close out | `executor-handoff` |

Read the contract references before writing anything into either store:

- [references/layout.md](references/layout.md) — exact directory structure
- [references/frontmatter.md](references/frontmatter.md) — required fields per document type
- [references/indexes.md](references/indexes.md) — index formats and maintenance
- [references/safety.md](references/safety.md) — secret hygiene, required because `.executor/` may be committed

## Rulings, Not Stalls

Inside a phase, a running Executor does not wait on a human. Ambiguities,
conflicts, plan defects, a cap you would have asked to exceed — decide them,
record the decision as a ruling, keep going.

A ruling is written the moment it is made, to the initiative's rulings log
and to `.local/decisions/`. It names what you decided, why, and what it
costs if wrong. A wrong ruling costs rework the human can see and undo. A
session parked on a question costs their whole day.

**Four things stop you, and only these:** an irreversible or destructive
operation; a security-sensitive action; a side effect outside this worktree
that norms say you ask about first (a merge, a push to a shared branch, a
publish); a defect so deep that every path forward is a guess.

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

[Read docs/executor/INDEX.md → INIT-0004, phase: planning]
[Read INIT-0004/INDEX.md → planning entered, gate not passed,
 one plan INIT-0004-P01 exists, execution_mode: null]

Me: "INIT-0004 is in planning: plan P01 (7 tasks) is drafted, but you have
not picked an execution mode. Two options: 1) subagent-driven — a fresh
implementer per task with independent review per diff; 2) inline — faster,
no independent review. Which?"

[TURN ENDS. No pre-dispatching, no reading ahead into executor-execution,
 no work in this message beyond the question.]

Human: "Subagent."

Me: [records execution_mode: subagent, status: active, bumps updated_at]
$ scripts/exec-initiative phase INIT-0004 planning passed "subagent mode"
$ scripts/exec-initiative phase INIT-0004 execution entered
[Routes to executor-execution and follows ITS skill from here.]
```

Note what did **not** happen: no inline implementation during planning, no
gate crossed in the same message that presented it, no invented state when
the indexes disagreed with memory, no phase transition without the script.
The whole discipline is: ground first, work one phase, end turns at gates,
record through scripts.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "This is small, skip the initiative" | Correct — if it produces no lasting deliverable. If it does, it gets an initiative with three short documents. |
| "I'll cite the other initiative's ADR, it's right there" | That coupling is what makes registries unreadable. State the requirement in your own words; declare the dependency at initiative level. |
| "The workspace is scratch, I'll delete it when done" | The execution record is the point. Nothing deletes it. |
| "I'll allocate the ID later" | IDs allocated retroactively collide and get invented. List, then write. |
| "The ledger has the ruling, that's enough" | The ledger dies with the plan's relevance. Rulings go to `.local/decisions/` the moment they are made. |
| "No secrets in this one, skipping the scan" | The scan is cheap and the failure is unrecoverable once pushed. Run it. |
| "Phases are overhead, I'll write the plan directly" | A plan with no spec argues from nothing. If discovery and architecture are genuinely unnecessary, record them as skipped and say why. |
| "I already read the indexes earlier this session" | Session memory is not state. The ritual runs every session; compaction and interruptions make stale confidence expensive. |
| "The next step is obvious, I'll start it while they review" | A gate ends your turn. Work produced past an unpassed gate is work the approval cannot cover. |
| "It's just a small inline edit to unblock the document" | Inline execution in a document phase is the primary drift failure. Record what blocks you instead, or rule on it if a plan is running. |
| "I drifted, but the work is good, I'll keep it quietly" | An unrecorded violation is a defect discovered by a reviewer later. Run Drift Recovery: stop, assess, repair to the record, re-ground. |
