# DSGN Template — Component Design

One `design` artifact per component whose internals are not obvious from
the `arch` plus its `ifce`. In v2 the document is a payload:
`kind: "design"`, written by an `author` dispatch to its `respond_to`;
`executor ingest` validates and journals it.

A design covers **one** component's insides. Its public surface is not
restated here — it points at the interface artifact. If this design
describes two components, split it; if it restates the IFCE, delete the
restatement, because two copies of a signature drift.

Copy the structure below. Guidance sits in italic lines — replace each
one with content.

## Payload skeleton

```json
{"kind": "design", "v": "v1", "dispatch_id": "D00021",
 "id": "INIT-0004-DSGN-01",
 "title": "Placement service internals",
 "summary": "…",
 "cites": ["INIT-0004-ARCH-01", "INIT-0004-IFCE-01"],
 "sections": [
   {"id": "responsibility", "title": "Responsibility",
    "prose": "Chooses the cell a tenant belongs to and records the binding."},
   {"id": "nonresponsibilities", "title": "What this component does not do",
    "bullets": ["Does not decide whether a request is admissible — `admission-control` does."]},
   {"id": "surface", "title": "Public surface",
    "prose": "Consumed: `CellStore`, `MetricsPort` — see INIT-0004-IFCE-01. Exposed: `place(request) -> Placement`."},
   {"id": "state", "title": "State",
    "tables": [{"columns": ["State", "Type", "Lifetime", "Mutated by", "Rule"],
                "rows": [["rules", "PlacementRules", "process", "never after construction", "Immutable"]]}]},
   {"id": "algorithms", "title": "Algorithms",
    "prose": "Step by step, with the ordering and the complexity.",
    "tables": [{"caption": "place(request)",
                "columns": ["Step", "Action", "Why the order matters"],
                "rows": [["1", "store.candidates(region, sizeClass)", "checked before scoring so the empty case costs no work"]]}]},
   {"id": "edges", "title": "Edge cases",
    "tables": [{"columns": ["Case", "Required behaviour"],
                "rows": [["No candidates", "NoCapacity, no metric, no store write"]]}]},
   {"id": "errors", "title": "Error handling",
    "tables": [{"columns": ["Origin", "Handling"],
                "rows": [["StoreUnavailable", "Propagate unchanged — the edge maps it to 503"]]}]},
   {"id": "seams", "title": "Testing seams",
    "tables": [{"columns": ["Seam", "Injected as", "Fake", "Tested for real where"],
                "rows": [["CellStore", "constructor parameter", "InMemoryCellStore", "Adapter test against a real SQLite file"]]}]},
   {"id": "files", "title": "File structure",
    "tables": [{"columns": ["Path", "Responsibility", "Changes when"],
                "rows": [["core/placement/place.ts", "The place() use case", "The placement flow changes"]]}]},
   {"id": "open", "title": "Open questions",
    "bullets": ["None."]}
 ]}
```

**The tables in this document are the content your payload's `tables[]`
carries.** A pipe table, a fence, or a heading inside any string is a
schema rejection: the engine renders the `.md` from this data, so a
payload never carries formatting.

## 1. Responsibility

*One line, matching the ARCH inventory exactly. If they disagree, one is
wrong — fix it here and redraft the ARCH in the same pass.*

Chooses the cell a tenant belongs to and records the binding.

## 2. What this component does not do

*Explicit non-responsibilities. This is where scope creep is cheapest to
stop, and where an implementer learns which neighbour to call.*

- Does not decide whether a request is admissible — `admission-control`
  does.
- Does not open a database handle — only `sqlite-cell-store` does.
- Does not format responses or map errors to status codes — `http-edge`
  does.

## 3. Public surface

*Point, do not copy.*

Consumed: `CellStore`, `MetricsPort` — see `INIT-0004-IFCE-01`.
Exposed: `place(request) -> Placement` — see `INIT-0004-IFCE-01`.

## 4. State

*Every piece of state the component holds, who may mutate it, and how long
it lives. State with no named owner is state two code paths will fight
over.*

| State | Type | Lifetime | Mutated by | Rule |
|---|---|---|---|---|
| `rules` | `PlacementRules` | process | never after construction | Immutable; a rules change is a restart |
| `scoreCache` | `Map<CellId, number>` | one `place()` call | `score()` only | Never outlives the call; no cross-request caching, because a stale score binds a full cell |
| none | — | — | — | The component holds no connection, no session, no clock |

**Concurrency:** `place()` is re-entrant and holds no shared mutable
state between calls. Two concurrent placements for the same tenant are
resolved by the store's unique constraint (`INIT-0004-IFCE-01`), not
here.

## 5. Algorithms

*Step by step, with the ordering and the complexity. If the order of two
steps matters, say why — that "why" is what stops a later refactor from
swapping them.*

### `place(request)`

1. `candidates = store.candidates(request.region, request.sizeClass)`.
2. If empty → raise `NoCapacity`. (Checked before scoring so the empty
   case costs no work.)
3. Score each candidate: `score = freeBytes / capacityBytes`, tie-break
   by the store's returned order — which is ascending `usedBytes`, and
   is part of the contract, so we do not re-sort.
4. `store.bind(request.tenant, best.id)`.
5. On `AlreadyBound` → return the existing placement (idempotent from
   the caller's view). On `CellNotAdmitting` → retry from step 1 exactly
   once, then raise.
6. Emit `placement.bound` with cell and duration via `MetricsPort`.

**Complexity:** O(n) in candidate count, n bounded by cells per region
(currently ≤ 64). No sort — the store returns ordered.

## 6. Edge cases

*The cases a reasonable implementer would get wrong, each with the
required behaviour. This table is the design's highest-value section for
whoever writes the tests.*

| Case | Required behaviour |
|---|---|
| No candidates | `NoCapacity`, no metric emitted, no store write |
| Exactly one candidate at 100% capacity | Still rejected — capacity check is in scoring, not only in the store |
| `AlreadyBound` | Return the existing placement; do not re-bind, do not raise |
| `CellNotAdmitting` twice in a row | Raise after the single retry; do not loop |
| Metrics emit fails | Placement still succeeds; the error is swallowed and counted |
| Tie between two identical scores | Lower `usedBytes` wins, i.e. store order |

## 7. Error handling

*Which errors this component raises, which it translates, and which it
lets through untouched. Silent translation is how a caller loses the
ability to react.*

| Origin | Handling |
|---|---|
| `StoreUnavailable` | Propagate unchanged — the edge maps it to 503 |
| `AlreadyBound` | Absorbed; converted into a successful return |
| `CellNotAdmitting` | Absorbed once, then propagated |
| Metrics errors | Absorbed and counted; never affect the result |

## 8. Testing seams

*What is injected, what fakes exist, and what must be exercised for real.
Core behaviour must be testable without the real framework, database,
network, vendor, or clock — that requirement is what a seam is for.*

| Seam | Injected as | Fake | Tested for real where |
|---|---|---|---|
| `CellStore` | constructor parameter | `InMemoryCellStore` — enforces the same unique constraint | Adapter test against a real SQLite file |
| `MetricsPort` | constructor parameter | `RecordingMetrics` | Not tested for real; emission is fire-and-forget |
| Clock | not needed — the store owns `boundAt` | — | — |

Tests target the behaviour in section 6, not the call sequence in
section 5 — asserting that `candidates` was called once tests the
plumbing, and passes after the logic breaks.

## 9. File structure

*Decomposition, decided once here with the whole component in view.*

| Path | Responsibility | Changes when |
|---|---|---|
| `core/placement/place.ts` | The `place()` use case | The placement flow changes |
| `core/placement/score.ts` | Scoring and tie-breaking | The scoring rule changes |
| `core/placement/errors.ts` | `NoCapacity` and the absorbed-error policy | The error contract changes |
| `core/ports/cell-store.ts` | The `CellStore` port declaration | `INIT-0004-IFCE-01` changes |
| `test/placement/place.test.ts` | Section 6 edge cases | Behaviour changes |

Rules this table follows:

- **One clear responsibility per file**, with a well-defined interface.
- **Files that change together live together. Split by responsibility,
  not by technical layer** — a layer-sliced tree makes one conceptual
  change edit five directories.
- **Prefer smaller, focused files over large ones that do too much.**
  Agents reason best about code they can hold in context at once, and
  edits are more reliable when files are focused.
- **In an existing codebase, follow the established patterns.** If the
  codebase uses large files, do not unilaterally restructure. If a file
  this work must modify has grown unwieldy, propose the split here —
  with its boundary named — so planning can task it deliberately rather
  than an implementer improvising it mid-task.

## 10. Open questions

*What this design does not settle, so the spec does not assume it did.*

- Whether eviction belongs here or in a separate component. Deferred;
  the `CellStore` port leaves room for either.

## Quality bar

- The responsibility line matches the ARCH inventory word for word.
- The non-responsibilities name the neighbour that owns each excluded
  concern.
- Every state row has an owner, a lifetime, and a mutation rule.
- Every algorithm step whose order matters says why.
- The edge-case table is specific enough to become test names directly.
- Every seam names its fake, and nothing that must be real is faked.
- The file table gives every file one responsibility and a "changes
  when".
- Every `cites` entry names an artifact that exists — the fold checks
  the references and a dangling one is an audit finding.
- No credentials, tokens, or connection-string values.
