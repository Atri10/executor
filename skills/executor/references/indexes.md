# Index Contract

Indexes answer "what exists and where is it." In v2 they are **derived
views, not hand-maintained documents**: the journal is the state, the
engine refolds it on every command, and a hand-written index contradicting
it is impossible because nothing but the engine writes them. `executor
check` reports any committed index that disagrees with the fold.

## 1. `executor status` — the live initiative index

Every initiative, its phase and phase state, its counts — printed from the
fold on demand:

```text
INITIATIVE INIT-0004 - cloud-tenant-cells
phase: execution (gate_pending)
events: 96 | artifacts: 9 | tasks: 7
policy: audit<=5 fix<=5 evidence<=5 autonomy[execution]=deny (from default)
change: CR-0001 scoped (2 task(s), 3 criteria)
-> GATE execution: awaiting a human decision (ingest a gate_decision payload)
```

The `phase:` value is the fold's `phase_state` — `in_progress`,
`gate_pending`, `passed`, or `-` before the phase is entered. The
`policy:` line prints the audit/fix/evidence caps, the autonomy of the
current phase, and the layer the fix cap came from (`default`, `project`,
or `initiative`). A `change:` line appears while a `change_request` is
open, with its radius counts and `coarse` when no task binds a changed id.

This is the session-opening ground truth: which initiative exists, which
phase it is in, what is open. `executor doctor` adds open dispatches and
the autonomy policy in force; `executor graph` draws the whole initiative
as nodes and edges (JSON or Mermaid).

## 2. `docs/executor/<INIT-NNNN>/meta/` — the committed index

The one index that is a file: `meta/index.json` (machine-readable) and
`meta/index.md` (the human-readable rendering of the same data). It exists
so a reader of the tracked store can see the artifacts the initiative
authored, the plans it ran, the tasks it left open, the evidence it has,
and the changes it absorbed — all named by their canonical ids.

**It is written on every projection, not only at handoff.** It is a pure
function of the fold, so it cannot drift, and a tracked store without it is
unusable mid-run. `executor check` re-renders it and reports any committed
index whose bytes disagree with the fold — which is what "the journal is
canonical" means in practice, not a promise.

## 3. `.executor/<INIT-NNNN>/views/` — the run views

A tree with one stable index at its root:

| Leaf | Owns |
|---|---|
| `views/index.md` | the root index: every aggregate, plan and task leaf by id |
| `views/progress.md` | every task, its state, its rounds, and the rulings in order |
| `views/dispatches.md` | every dispatch and its outcome (`answered`, `abandoned`, `spawn_error`, `open`), with the sentence that explains seq-derived ids |
| `views/summary.md` | phase states, open critique findings, task completion, and every change |
| `views/graph.json` | entities and edges, machine-readable |
| `views/plans/<PLAN-ID>/plan.md` | one plan: status, merge, its tasks |
| `views/tasks/<TASK-ID>/task.md` | one task: contract, every review round, every finding, its reports |

The engine re-renders them after every accepted ingest. There is no
per-round view file: a task with six rounds has one leaf, so the tree grows
with entities rather than rounds. A view is never edited by hand: a view
that is wrong is a fold that is wrong, and the fix is an event, not an edit.

Two properties matter and are worth knowing when reading one:

1. **A view is a function of the journal.** The stamp it carries is the
   journal tip, never the wall clock, so a re-render of the same journal is
   byte-identical. That is what lets `executor check` compare a view with a
   fresh render instead of guessing.
2. **A leaf has one owner.** If a fact appears in two leaves, one of them
   is stale; report it.

## What replaced the phase log

The v1 phase log — entered/skipped/passed rows — is now the journal's
`phase_entered`, `gate_opened`, and `gate_decision` events. A human
approval reads `by: "human"`; an autonomy-cleared one reads `by: "auto"`.
A skipped phase is a `waived` `gate_decision` carrying a `note`, so the
reason is journaled, scoped to its phase, and greppable — not a markdown
row nobody can check.

## Maintenance rules

1. **Nothing hand-writes an index.** A stale view is an engine bug; report
   it, never patch it. `executor migrate --apply` is the one writer that
   rewrites projections wholesale, and it reads the journal to do it.
2. **The journal wins every disagreement.** `executor check` refolds,
   re-renders the committed index, and flags any projection that
   contradicts it — the journal is canonical.
3. **Rows are never deleted.** A finished initiative keeps its committed
   index and its exported journal (`export/events.jsonl`) forever.
4. **A change is part of the record.** `changes/<CR-ID>/change.md` carries
   the request, its blast radius and its state (`requested`, `scoped`,
   `applied`, `withdrawn`), so the committed store answers "what changed
   mid-run and what did it cost" without opening the journal.
