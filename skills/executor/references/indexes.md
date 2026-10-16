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
phase: execution (active)
events: 96 | artifacts: 9 | tasks: 7
-> GATE execution: awaiting a human decision
```

This is the session-opening ground truth: which initiative exists, which
phase it is in, what is open. `executor doctor` adds open dispatches and
the autonomy policy in force; `executor graph` draws the whole initiative
as nodes and edges (JSON or Mermaid).

## 2. `docs/executor/<INIT-NNNN>/meta/` — the committed index

The one index that is a file. The engine writes it at handoff, and only at
handoff — `meta/index.json` (machine-readable) and `meta/index.md` (the
human-readable rendering of the same data). It exists so a completed
initiative is self-describing inside the tracked store: the artifacts it
authored, the plans it ran, and the phase path it took, all named by their
canonical ids.

Before handoff there is no committed index on purpose: an index written
mid-run is a second source of truth that can only drift. Live state lives
in `executor status`.

## 3. `.executor/<INIT-NNNN>/views/` — the run views

`views/progress.md`, `views/dispatches.md`, `views/summary.md`,
`views/graph.json` and one `<TASK-ID>-R<NN>-verdict.md` per review round —
the engine re-renders them after every accepted ingest. They are the
reading surface for "what did we actually execute," and they are never
edited by hand: a view that is wrong is a fold that is wrong, and the fix
is an event, not an edit.

## What replaced the phase log

The v1 phase log — entered/skipped/passed rows — is now the journal's
`phase_entered`, `gate_opened`, and `gate_decision` events. A human
approval reads `by: "human"`; an autonomy-cleared one reads `by: "auto"`.
A deliberately declined phase is recorded the same place a decision is: a
`ruling` payload through `executor decide`, which is journaled, scoped,
and auditable — not a markdown row nobody can grep.

## Maintenance rules

1. **Nothing hand-writes an index.** A stale view is an engine bug; report
   it, never patch it.
2. **The journal wins every disagreement.** `executor check` refolds and
   flags a committed index or view that contradicts it — the journal is
   canonical.
3. **Rows are never deleted.** A finished initiative keeps its committed
   index and its exported journal (`export/events.jsonl`) forever.
