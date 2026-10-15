# Document Identity Contract

Every Executor document is a typed JSON payload, not a markdown file with
frontmatter: the payload's fields carry the ID graph, the journal carries
the history, and `engine/executor/schemas.py` validates every field the
moment `executor ingest` accepts it. The rendered `.md` beside it is a
derived view — a projection of the payload, never the authority.

Values come from repository state, executed commands, or the human's
explicit statement. **Never invent a timestamp, an ID, a verdict, or a
provenance claim.** If a check did not run, the payload says so.

## Common fields (every payload)

```json
{"kind": "spec",                    "v": "v1",
 "id": "INIT-0004-SPEC-01",         "title": "Cell placement",
 "summary": "…",                   "sections": [{"id": "…", "title": "…", "body": "…"}],
 "dispatch_id": "D00112"}
```

- `kind` and `v` name the schema; `id` must match the owning initiative's
  namespace (`INIT-NNNN-<KIND>-NN` for artifacts, `INIT-NNNN-PNN` for a
  plan, `INIT-NNNN-PNN-TNN` for a task).
- `dispatch_id` binds the payload to the open slot it answers; the engine
  rejects a payload that answers nothing or the wrong slot.
- `sections` carry the document body — one entry per section, each with
  its own `id` so a reviewer cites `INIT-0004-SPEC-01 §R3`, not a page.

## Per-kind fields

An artifact may also carry `cites` (IDs of upstream documents it argues
from), `requirements` (`R<n>` rows), `constraints` (`C<n>` rows), and
`risks`. A **spec** uses all three: `requirements` are the contract a plan
argues from, `constraints` are the verbatim global rules tasks inherit,
`risks` names the register entries it leans on. A **charter** declares the
initiative's cross-initiative links in `cites` — the one place another
initiative's ID may appear.

| Kind | Extra fields that matter |
|---|---|
| `charter` | `cites` may carry other initiative IDs (`depends_on` etc.) |
| `options` | `summary` names the recommended approach |
| `spec` | `requirements`, `constraints`, `risks`; `cites` its ARCH/DSGN |
| `vrfy` | `criteria` — `V<n>` rows; each criterion is a dispatchable unit |
| `plan` | `tasks` — each `id`, `title`, `goal`, `files`, `accepts`, `depends_on` |

## Task identity

Tasks live inside a plan payload's `tasks` array, addressed by ID
everywhere: `INIT-0004-P01-T03`. The ID is what `executor next` puts in
a `DISPATCH`'s `entity`, what a `report` echoes in `task`, and what
every verdict, fix, and ruling references. A task with no ID cannot be
dispatched.

## Validation before writing

The schema does the checking: closed objects, anchored ID patterns,
required fields, `round` echoing the engine's minted value, `dispatch_id`
binding to an open slot. `executor ingest` rejects anything else with a
named code. If you find yourself reasoning about whether a field is legal,
that reasoning belongs to the schema — run the payload, read the
rejection.

## The one cross-initiative rule

No field in any payload may carry another initiative's ID except the
charter's `cites` — the canonical, machine-readable home for every
cross-initiative link. Everything else must state the requirement in its
own words; a citation is not a dependency.
