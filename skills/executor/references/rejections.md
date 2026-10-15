# Rejection Codes

Every refusal `executor ingest`, `executor decide`, and
`executor check` can emit, with the field it points at and the action
that clears it. This is the authoritative list: the codes are raised in
`engine/executor/` (`engine.py` for the semantic pass, `schemas.py` for
the structural one, `store.py` for the journal), and a code that appears
in neither is not a code.

A rejection is a **refusal, not an error**: nothing is written, the
journal is unchanged, and the dispatch stays open. The fix is in the
payload or in the run's state — never in the engine.

## Structural — `schemas.py`

These fire before the fold sees the payload. Each names the field path
and one of: the expected type, the pattern, the bound, or the rejection
rule that caught it.

| Code | Field | Means | Clear it by |
|---|---|---|---|
| `type` | the field | The JSON type is wrong (a string where an object belongs, an integer where a string does) | Sending the declared type |
| `required` | the field | A required key is missing | Adding the key |
| `enum` | the field | The value is outside the closed set (`kind`, `severity`, `result`, `verdict`, …) | Using a listed value |
| `pattern` | the field | The string does not match its anchored pattern (an ID shape, a commit sha prefix) | The exact shape from `references/frontmatter.md` |
| `minLength` / `maxLength` / `minItems` / `minimum` | the field | A bound was crossed (a blank title, a 12 001-char section, a zero `round`) | Meeting the bound |
| `notMatch` | any prose or cell | Markdown syntax in a string: a pipe table, a code fence, a heading, a bullet marker, a pipe or newline inside a table cell | `prose` / `bullets` / `tables` / `code` fields |
| `nonBlank` | any prose, bullet, or cell | The string is whitespace only: it passes `minLength` and renders an empty paragraph, an empty bullet, or a blank cell | Real content |
| `row_width` | `tables[].rows[n]` | The row's cell count differs from its `columns` count | One cell per column |
| `empty_section` | `sections[n]` | A section carries none of `prose`, `bullets`, `tables`, `code` | Giving it one shape |
| `additionalProperties` | the extra key | A closed object carries an unknown key | Removing the key |
| `duplicate` | `tasks` / `criteria` / findings | Two rows share an ID | Unique IDs |
| `oneOf` | the field | None of the object's permitted shapes matched | The shape list from `references/frontmatter.md` |
| `not_json` | `$` | The file is not parseable JSON | Valid JSON on one line or block |
| `unknown_kind` | `$.kind` | No schema is registered for the `kind` | A kind from the payload vocabulary |

## Semantic — `engine.py`

These fire after the structure is valid: the payload is well-formed and
means something the protocol forbids.

| Code | Field | Means | Clear it by |
|---|---|---|---|
| `no_open_slot` | `$` | The payload answers no open dispatch, or answers the wrong one | Pointing `dispatch_id` at the open slot, or re-running `executor next` |
| `no_open_gate` | `$.phase` | A `gate_decision` names a phase whose gate is not open | The current gate, from `executor status` |
| `unauthorized` | `$.kind` | A payload kind only a human may write (`gate_decision`, `ruling`, `resume`) came through `ingest` | `executor decide`, which stamps `actor: human` |
| `halted` | `$.kind` | A worker payload arrived while the run is halted | A human `resume` first |
| `not_halted` | `$.kind` | `resume` arrived on a running run | Nothing — remove the payload |
| `unknown_entity` | `$.for_task`, `$.plan`, `$.target` | The named task, plan, or artifact does not exist | An ID from the fold, verbatim |
| `unknown_rev` | `$.commits`, `$.merge_sha`, `$.state_commit` | The commit does not exist in the repository, or is not a real revision | A sha from an executed `git` command |
| `empty_range` | `$.commits` | The report or evidence lists no commits | The commits the change actually made |
| `range_mismatch` | `$.commit_base` | The commit range is not a contiguous ancestry | `base` is an ancestor of `head` |
| `round_mismatch` | `$.round` | The verdict names a review round the engine did not mint for that task | The `round` from the dispatch's context |
| `package_mismatch` | `$.reviewed_package_sha` | The verdict's package sha differs from the minted package — a verdict about another diff | The sha in `reviews/R<NN>.package.json` |
| `mismatch` | `$.plan_id` | The plan payload's `plan_id` disagrees with its `id` | Both naming the same plan |
| `dangling_ref` | `$.cites`, `$.depends_on`, `$.consumes` | The payload references an artifact or task that was never authored | An authored ID from this initiative |
| `missing_evidence` | `$.findings`, `$.artifacts` | A finding or criterion names an artifact the payload does not carry | The artifact, or dropping the reference |
| `incomplete` | `$.plan` | A `merge` payload names a plan whose tasks are not all complete | Every task reported and merged |
| `already_merged` | `$.plan` | The plan was already merged | Nothing — the second payload is a duplicate |

## Journal and store — `store.py`

| Code | Means | Clear it by |
|---|---|---|
| `no_meta` | No `meta.json` in the initiative directory: not a store, or one from before v2 | `executor new`, or pointing at an initialized store |
| `no_initiative` | The named initiative directory is absent, or no initiative exists at all | The ID from `executor status`, or `executor new` |
| `ambiguous` | Two active initiatives and no ID was given | Naming the initiative explicitly |
| `store_locked` | Another process holds the store lock | Waiting for it, or removing a stale lock only after confirming its owner is gone |
| `engine_too_old` | The store was written by a newer major engine than the one installed | Installing executor ≥ the store's major version |
| `store_outdated` | The store predates this engine's major version | `executor migrate --dry-run` first, then `executor migrate` |
| A chain break | A `line_sha` does not match its line: the journal was edited by hand | Restoring from the run-store backup, or the line `executor check` names |

## CLI and engine errors — `cli.py`, `engine.py`, `policy.py`

Command-level failures, not payload refusals: the command did nothing.

| Code | Means | Clear it by |
|---|---|---|
| `usage` | The command line is malformed | The usage line in the error |
| `unknown_phase` | An autonomy command named a phase outside `PHASES` | A phase from the phase list |
| `unknown_mode` | An autonomy mode is not `allow`, `gate`, or `deny` | One of the three |
| `exists` | `executor new` was given a title whose initiative directory is already present | A different title, or the existing initiative |
| `git_error` | A `git` call the engine made failed | Fixing the repository state; the stderr is in the message |
| `bad_timestamp` | A journal timestamp is unreadable — the store was damaged | Repairing the line, not the reader |
| `policy_invalid` | A policy file is malformed, or carries an inverted bound (`suspect_s` above `deadline_s`) | A valid `config.json` / `policy.json` |
| `exec_root` | The command ran outside a git repository | Running inside the repository |
| `missing_file` | A path the command was given does not exist | The path from `executor status` or `executor doctor` |

## What a controller does with one

1. Read the field path and the code from the command's JSON output.
2. Fix the named thing — usually the worker's payload, occasionally the
   dispatch it answered.
3. Re-ingest. The slot is still open, because a rejection wrote nothing.

**Never** work around a rejection by re-authoring the journal, by
re-ingesting a different payload that happens to pass, or by asking the
engine to accept it. A rejection is the protocol saying the attempt was
not what it claimed to be; the record of the refusal is the point.
