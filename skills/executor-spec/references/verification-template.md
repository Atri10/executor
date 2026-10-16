# Verification Strategy Template

The `vrfy` artifact: `kind: "vrfy"`, id `INIT-NNNN-VRFY-NN`, answered by
an `author` dispatch to its `respond_to`. `executor-verification`
executes it row by row and can only report what a row told it to
observe — every vague cell here becomes an unverifiable claim there.

A section is data, not markdown: `prose`, `bullets`, `tables`
(`columns` plus `rows`), and `code` for commands and manual steps. The
engine renders the `.md`; a pipe table or a fence inside a string is a
`notMatch` rejection.

## Payload skeleton

```json
{"kind": "vrfy", "v": "v1", "dispatch_id": "D00035",
 "id": "INIT-0004-VRFY-01",
 "title": "Cell placement acceptance strategy",
 "summary": "Nine criteria over the spec's requirements and constraints: four unit, three integration, one manual, one smoke.",
 "cites": ["INIT-0004-SPEC-01"],
 "criteria": [
   {"id": "V01", "criterion": "R01 deterministic placement",
    "procedure": "cd services/placement && npx vitest run test/placement/deterministic.test.ts",
    "cites": ["INIT-0004-SPEC-01-R01"]},
   {"id": "V02", "criterion": "R02 an unknown cell is rejected with 422",
    "procedure": "curl -s -o /tmp/b -w '%{http_code}' localhost:8080/place -d '{\"tenant\":\"t1\",\"cell\":\"cell-9999\"}' then jq -r .error /tmp/b",
    "cites": ["INIT-0004-SPEC-01-R02"]},
   {"id": "V03", "criterion": "R02 no placement recorded on rejection",
    "procedure": "after V02: psql -Atc \"select count(*) from placement where tenant='t1'\"",
    "cites": ["INIT-0004-SPEC-01-R02"]},
   {"id": "V09", "criterion": "R14 operator can evict a cell from the console",
    "procedure": "1. Open http://localhost:3000/cells — the table lists cell-1 … cell-4.\n2. Click Evict on the cell-3 row — a confirm dialog appears naming cell-3.\n3. Confirm — within 2 seconds the cell-3 row's status reads draining.\n4. Reload the page — the status still reads draining.\n5. Run: psql -Atc \"select action,target from audit order by id desc limit 1\" — output is cell.evict|cell-3.",
    "cites": ["INIT-0004-SPEC-01-R14"]}
 ],
 "sections": [
   {"id": "how-to-run", "title": "How to run this",
    "prose": "Anything the verifier needs once, before any row: the working directory, how to start dependencies, which fixture data to load. Name real commands. If a row needs a running service, the command that starts it goes here, not repeated in every row.",
    "code": [{"lang": "bash", "source": "cd services/placement\ndocker compose up -d postgres      # placement rows land here\nnpm ci"}]},
   {"id": "evidence-expected", "title": "Evidence that counts",
    "tables": [{"columns": ["Criterion", "Evidence"],
                "rows": [["V01", "3 passed, exit 0"], ["V02", "422 then unknown_cell"], ["V05", "p99 <= 50 ms printed"]]}]},
   {"id": "coverage", "title": "Coverage",
    "tables": [{"columns": ["Spec item", "Criteria"],
                "rows": [["R01", "V01"], ["R02", "V02, V03"], ["R09", "V04"], ["R11", "V05"], ["R14", "V09"], ["C01", "V06"]]}],
    "prose": "A spec item with no criterion is a hole: the requirement exists and nothing will ever prove it. Fix it here, before the gate."},
   {"id": "status", "title": "Status",
    "prose": "This artifact defines how results get produced; it does not claim any. A criterion's status is its latest evidence event, which `executor status` counts as proven, failed, unavailable, or unanswered."}
 ]}
```

`criteria[]` is what the fold reads: `id`, `criterion`, `procedure`, and
`cites` pointing at the spec rows each proves. `procedure` is the exact
command, or numbered manual steps, copy-paste correct against the real
repository.

## Row rules

| Field | Rule |
|---|---|
| `id` | `V<nn>`, sequential, never renumbered — plans and verdicts cite them |
| `criterion` | The `R<nn>` or `C<nn>` proven, plus its short name |
| `procedure` | The exact command, or numbered manual steps. Copy-paste correct |
| `cites` | The spec rows this criterion proves |

**One row per requirement, minimum.** A requirement needing two methods —
a unit test for the calculation and a manual check of the rendered
result — gets two rows. **Every global constraint gets a row too:** a
version floor nobody checks is a version floor nobody meets.

## Evidence rules

Acceptable evidence names something a second person could observe
independently: an exit code, a specific count, a named field value, a
named log line, a named on-screen state.

| Disqualified | Replace with |
|---|---|
| "tested thoroughly" | The command and its expected output |
| "works" / "behaves correctly" | The specific assertion that holds |
| "tests pass" | Which test file, which test name, how many assertions |
| "verified manually" | Numbered steps and the expected state after each |
| "no errors" | Exit code 0 plus the named absence you checked for |
| "looks right" | The named field value or rendered string |
| "the API returns success" | The exact status code and the exact body field |

## Negative and boundary rows

A requirement stating a rejection, a limit, or an error response needs a
criterion proving the *failure* path.

| Requirement shape | Required row |
|---|---|
| Rejects X with status S | Send X, observe S — not "valid requests still work" |
| Up to N items | Observe behaviour at N and at N+1 |
| Times out after T | Observe the timeout firing, and observe it not firing under T |
| Emits log line L | Observe L present after the trigger, and absent without it |

V02 and V03 are one requirement split across two criteria for exactly
this reason: the status code and the absence of a side effect are two
separate observations, and a rejection that still writes a row is a bug
a single row would miss.

## Choosing a method

| Method | Use when | Evidence looks like |
|---|---|---|
| `unit` | The behaviour is a function of inputs, no I/O | Test file, test count, exit 0 |
| `integration` | The behaviour crosses a boundary — HTTP, DB, filesystem, process | Status code, row count, file content |
| `manual` | A human must observe a rendered state or perform a real interaction | Numbered steps, one observation per step |
| `smoke` | Proving the thing runs at all, or a constraint on the environment | Command output, version string, exit 0 |
| `static` | The requirement is a property of the artifact itself — a signature, a config value, a schema — provable without running it | The cited file:line, or the linter/type-checker output |

Prefer the cheapest method that actually observes the requirement. A unit
test that mocks the boundary the requirement is about proves nothing —
that requirement is `integration`.

## Before answering the dispatch

1. `cites` names the current, non-superseded spec ID.
2. Every criterion carries a `procedure` a stranger could run cold.
3. Every `R<nn>` and `C<nn>` in the spec appears in the coverage section.
4. Every procedure is copy-paste correct against the real repository —
   paths, commands, and flags checked, not assumed.
5. No criterion's evidence appears as prose: evidence arrives later, as a
   payload from the run, and this artifact only defines how it is
   produced.
