# Executor v2 — engine design

Single-file-of-truth design for the `executor` v2 engine. It supersedes the
bash `skills/executor/scripts/exec-*` suite for new initiatives. Breaking
changes are intended; v1 stores are read-only history, never imported.

## The one rule

**The engine is the only writer. Agents emit typed JSON payloads; the engine
validates them and writes every file. Nothing human-readable is a source of
truth — every rendered file is a projection of `events.jsonl`.**

This inverts v1's failure mode, where the LLM authored structure (tables,
frontmatter, filenames) and scripts grepped it back. Here structure is owned
by code; the agent only fills values.

## CLI

Seven commands. The pump loop is exactly `next` → relay → `ingest`.

```
executor new "<title>"          # scaffold INIT-NNNN
executor next                   # → one typed action + minted payload slot
executor ingest <path.json>     # validate → fold → render, or typed rejection
executor status                 # human gate card / current position
executor check [--secrets]      # journal re-fold, chain verify, integrity audit
executor migrate [--dry-run]    # version upgrade via upcaster chain
executor graph [--format ...]   # the whole initiative as nodes+edges
```

## Stores

```
<repo>/.executor/
  meta.json                 # engine_version, schema_version, store_version
  <INIT-NNNN>/
    events.vN.jsonl         # append-only, hash-chained journal — the truth
    state.json              # derived cache; rebuilt by `check`
    meta.json               # initiative meta
    autonomy.json           # per-phase deny|gate|allow (fail-closed)
    slots/                  # minted payload slots (in-flight dispatches)
    in/                     # validated payloads (raw agent JSON)
    out/                    # rendered prompts + packages
    views/                  # rendered progress/dispatch/verdict/summary
<repo>/docs/executor/<INIT-NNNN>/   # committed thinking store
    index.json + index.md   # initiative index (rendered)
    charter.json + charter.md
    spec.json  + spec.md
    plans/P<nn>.json + P<nn>.md
    …                       # per-artifact .json source + rendered .md
```

- `.executor/` is gitignored (machine-local, as v1).
- `state.json` carries `last_seq`; `executor check` refolds from the
  journal and treats a mismatch as drift — `state.json` is never required
  correct.

## IDs & the graph — everything has an ID, nothing dangles

Every entity carries a canonical ID and every reference must resolve. The
graph is queryable with one command:

```
executor graph [--format json|mermaid]   # the whole initiative as nodes+edges
```

- **ID grammar** — `INIT-NNNN` initiatives; `INIT-NNNN-<KIND>-NN` artifacts
  (`CHTR`, `OPTS`, `ARCH`, `ADR-`, `IFCE`, `DSGN`, `SPEC`, `RISK`, `VRFY`,
  `BRN`); `INIT-NNNN-PNN` plans; `INIT-NNNN-PNN-TNN` tasks; `R<nn>`/`C<nn>`/
  `V<nn>` requirements/constraints/criteria scoped to their artifact;
  `d-<seq>` dispatches; event `seq`; verdict `…-R<nn>`.
- **Nodes** — initiatives, phases, artifacts + typed children, tasks,
  dispatches, verdicts, findings, rulings, events, branches.
- **Edges** — `contains`, `depends_on`, `cites`, `implements`, `reviews`,
  `finds`, `repairs`, `gates`, `dispatched`, `fixes`.
- **No danglings, enforced** — ingest rejects a payload whose `cites`,
  `depends_on`, `provides`/`consumes`, or evidence refs point at IDs that
  don't exist; `executor check` asserts zero dangling edges and orphans.
- `events.vN.jsonl` is the only durable runtime record. `executor export`
  (folded into `handoff`) commits a snapshot of it + `meta.json` into
  `docs/executor/<INIT>/` so the provenance is durable and recoverable.

## Event

One JSON object per journal line, engine-written only:

```json
{
  "seq": 14, "ts": "2026-10-15T11:50:33Z",
  "actor": "worker|engine|pump|human|supervisor",
  "kind": "<event kind>",
  "entity": "INIT-0003-P04-T11",
  "dispatch_id": "d-00014",
  "payload_sha": "<sha256 of canonical payload>",
  "prev_sha": "<sha256 of previous event line>",
  "data": { "...kind-specific fields..." }
}
```

- `payload_sha` → idempotent ingest; the same payload twice is a no-op.
- `prev_sha` → tamper-evident chain; `check` re-verifies every link.
- `actor` → authorization. `gate_pass`, `ruling`, `halt`, `autonomy` events
  are only valid from `human`/`supervisor`; the pump cannot mint them.
- `seq` + `dispatch_id` minted by the engine, never by the agent.

## Payloads

Agents emit JSON to a minted `respond_to` slot (or `--stdin`). Every payload
has `kind`, a `v` schema version, `engine_version`, and kind fields.
`kind` must match the action `next` emitted. Kinds:

- **artifact** — `charter`, `spec`, `plan`, `arch`, `adr`, `ifce`, `design`,
  `risk`, `vrfy`, `options`, `brainstorm` — structured `sections[]`,
  `requirements[]`, `constraints[]`, `adrs[]`, `cites[]`; committed to
  `docs/executor/` (`.json` + rendered `.md`).
- **runtime** — `report`, `verdict`, `heartbeat`, `evidence`, `gate_decision`,
  `ruling`, `halt`, `needs_context`, `model_deviation`, `spawn_error`,
  `review_package` — runtime transitions, `.executor/`-local.

Validation is two layers, always both:

1. **Structural** — strict: required keys, closed enums, types, no unknown
   keys, `kind` == emitted action's expected kind.
2. **Semantic** — over live state: `round` == minted; `commit_base`/`head`
   resolve and `base != head`; every `cites:` ID exists; every `evidence`
   path exists at `commit_head`; `model_actual` vs dispatched → auto
   `model_deviation`; non-empty `concerns[]` → `needs_ruling` events;
   foreign commits between `base` and `HEAD` → warning finding.

Rejection → `{code, field, expected, got, hint}`, nothing written; two
consecutive rejections on one action → `escalate`/`needs_human`.

## Machines (hard-coded)

Initiative phases: `intake → discovery → architecture → design →
specification → planning → plan_regression → execution → review →
verification → handoff`. Each authoring phase: artifact drafted → `critique`
(AUDIT↔REPAIR loop) → `gate` (human `gate_pass` or autonomy `allow`). Reject,
`paused`, `abandoned`, `superseded`, `reopen`, `skipped` are first-class.

Task: `pending → dispatched → (reported | suspect) → reviewed → (fix→dispatched
| complete)`; `suspect → dead → (revive→dispatched | escalate)`;
`parked`/`blocked`/`needs_context`/`late_payload`/`retry` supported. Caps:
`max_fix_rounds` (default 5), ingest-retry 2, `next` no-progress livelock
detector. A plan has its own machine (task loop → `final_review` → merge).

## Authorization & liveness

- `autonomy.json` fail-closed per phase; `halt` events prioritized by `next`.
- Liveness = `dispatched_at` + `deadline` + optional `heartbeat` payload at
  the slot + a payload-sweep before `dead` (a filled slot is `reported`, not
  dead). `spawn_error` (401/429/DNS) is an event on the dispatch return path,
  not a burned rung.
- Issue-#9 fix: `DISPATCH role=review` produces a `review_package` carrying
  diff + `FIX_BASE` + verbatim requirement + prior findings/verdicts; ingest
  of a verdict requires `reviewed_package_sha`.

## Branch model

Branch lifecycle is events (`branch_fork`, `branch_merge`). Merge is gated
on the plan's `final_review` clean. Preflight computes task→file ownership
overlap deterministically; first `DISPATCH` refuses until semantic findings
carry rulings. Foreign commits between round base and `HEAD` flag a warning.

## Portability & versioning

Python ≥3.11 stdlib only; a vendored JSON-Schema-subset validator, zero
third-party deps. `engine_version` + `schema_version` stamped by the engine
on every store/payload/event; `store_version` in the journal header.
`migrate` replays the journal through per-version upcasters into
`events.vN.jsonl` (`--dry-run` previews); store newer than engine → refuse
with the minimum required version. `executor check` is the integrity verb
(`--secrets` scans without ever printing a match).
