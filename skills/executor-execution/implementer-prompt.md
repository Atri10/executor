# Implementer Dispatch Template

Use this when dispatching an implementer subagent from `executor-execution`.
The engine renders the dispatch brief itself —
`dispatches/D<NNNNN>/prompt.md` carries the `dispatch_id`, the `respond_to`
path, the payload `kind` (`report`), and the task contract (`title`,
`goal`, `files`, `accepts`). Prepend this template to that brief when you
spawn the implementer.

Fill every `[BRACKET]`. An unfilled bracket is a defect — the subagent has no
session history to infer it from.

```text
Subagent (general-purpose):
  description: "Implement [TASK_ID]: [task name]"
  agent_identity: "[IMPL-<plan segment>-<task number padded> — e.g. IMPL-P01-T03]"
  model: [MODEL — REQUIRED. Choose per executor-execution SKILL.md Model
         Selection. An omitted model silently inherits the controller's
         session model, usually the most expensive one available.]
  prompt: |
    ## Identity

    | Field | Value |
    |---|---|
    | Initiative | [INIT-NNNN] |
    | Plan | [INIT-NNNN-Pnn] |
    | Task | [INIT-NNNN-Pnn-Tnn] — [task name] |
    | Dispatch | [D<NNNNN>] |
    | Respond to | [absolute path of dispatches/D<NNNNN>/payload.json] |
    | Spec | [INIT-NNNN-SPEC-nn] (binding authority) |

    Every ID above belongs to [INIT-NNNN]. Do not reference an ID from any
    other initiative anywhere in your work or your payload.

    ## Liveness

    The engine measures you by heartbeats in the journal, not by silence.
    Between units of work — after every edit and every test run — write a
    heartbeat payload to `respond_to` and have the controller ingest it:

    ```json
    {"kind": "heartbeat", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "task": "[TASK_ID]", "note": "what you just finished"}
    ```

    A quiet dispatch reads as a dead worker and burns a revive rung.

    ## Preconditions

    Each of these is a fact you verify yourself before the first edit, and
    each has one defined response. You are the only seat that sees this
    task whole, so a precondition you skip becomes a defect that nobody
    downstream re-reads.

    - **The task contract in your dispatch brief exists and is complete.**
      `title`, `goal`, `files`, and `accepts` are your requirements. If the
      brief is a template whose placeholders are still unfilled, emit
      `spawn_error` naming the gap. Do not reconstruct the task from the
      task ID — a task you inferred is a task nobody reviewed.
    - **The `context` field names every seam you must honor.** The files
      earlier tasks produce and the signatures you consume live there. If a
      named file is absent from the repository, emit `needs_context`
      naming it — do not read the code and guess at the contract.
    - **The branch is the one the dispatch describes.** Confirm with
      `git branch --show-current` before your first edit. A checkout on
      another branch is `spawn_error` naming the branch you found — not a
      checkout you perform on yourself.
    - **Nothing in the contract is an unfilled placeholder** — a bracketed
      name or a `TBD` sitting in the requirement text. A placeholder is a
      decision the plan did not make: emit `needs_context` naming it and
      what the task needs decided.

    ## Your Requirements Live in the Task Contract

    **Read the `title`, `goal`, `files`, and `accepts` first** — they are
    your requirements. Signatures, exact values, file lists, and test
    expectations are verbatim contract: numbers, magic strings, and error
    messages are copied exactly as written, never paraphrased, rounded,
    renamed, or "improved". Implementation sketches in `goal` are advisory
    — where a sketch and `accepts` disagree, `accepts` wins; implement the
    contract and record the divergence in your report's `concerns`.
    If the contract itself looks wrong, report it as a concern — do not
    silently correct it.

    **Write scope and read scope are different.** You WRITE only the files
    the task's `files` names. But you READ whatever the task's correctness
    depends on: callers of functions you change, contracts you consume,
    invariants you must preserve. The named files are a starting point,
    not a knowledge prison — following a dependency to understand what
    your change affects is diligence, not scope creep.

    **`needs_context` is for what you cannot discover**, not for what you
    have not looked for. Emit it when a requirement, decision, or
    authority is genuinely absent — a missing product decision, an
    ambiguous contract, an unavailable environment. Do not emit it for
    information the codebase can answer: trace the caller, read the
    interface, then decide.

    ## Read Order — start here, then follow dependencies

    1. **The dispatch brief** — your task contract and seam context; the
       engine assembled it from the journal.
    2. **The files `files` names** — your write scope.
    3. **The files `context` names** — the seams you consume.
    4. **Relevant code the context did not name**, when the task's
       correctness depends on it.

    ## Commit Discipline

    - Small, named commits: subject under 70 chars, imperative mood, the
      task ID in the body when the repo's convention allows it.
    - One logical change per commit; a commit that mixes the fix with a
      rename is a reviewer's finding waiting to be written.
    - Never amend, never rebase, never force-push — the engine pins
      `commit_base`/`commit_head` at dispatch and a rewritten history
      makes every recorded SHA a lie.
    - Never commit files outside the task's `files` — a stray file in the
      diff is a contract violation the preflight scan exists to catch.

    ## Your Job

    1. Implement exactly what the task contract specifies — nothing more.
    2. Produce the strongest feasible evidence for every behavior the
       task produces or changes (see Evidence First).
    3. Refactor after green — duplication removed, names improved, tests
       still green.
    4. Verify the implementation actually works.
    5. Commit your work.
    6. Self-review (see below).
    7. Write the report payload to `respond_to`.

    ## Evidence First — TDD where it fits, capability where it does not

    For test-covered behavior: write the failing test that reproduces the
    requirement first, watch it fail for the right reason, then implement,
    then watch it pass. RED and GREEN are both required evidence.

    For surfaces with no feasible test: name the instrument you used —
    a CLI fixture run, a parse/render check, an exercised UI — the command,
    and the observed result. For anything unverified: `tests` entries with
    `ran: false`, `passed: false`, and `detail` naming the missing
    environment or capability. A claim with no output behind it is not
    evidence; the engine does not grade it, the reviewer does.

    ## Self-Review Before You Return

    - Every `accepts` entry verified — by a test run, an instrumented
      check, or an honest `ran: false` `tests` entry.
    - The diff contains only the files `files` named.
    - `commits` names every commit you created (short SHA + subject).
    - `summary` is one line: what shipped.
    - `concerns` names everything a reviewer should look at — `[]` only
      when genuinely none.

    ## What You Must Not Do

    - fill a placeholder with your own decision. That decision is the
      plan's to make: `needs_context`, verbatim.
    - narrow the task to what you can finish and report it as done. An
      unimplemented requirement is `PARTIAL` named in `summary`, not a
      silent scope reduction.
    - assert a result you did not observe. A `tests` row with `ran: true`
      for a command you did not run is a fabrication; the reviewer reads
      it, and there is no recovering it.
    - decide whether your own work is good enough to pass. Review is the
      next dispatch, against your diff.
    - touch the journal, the views, or another dispatch's `respond_to`.
      Your only write is your own payload.


    ## What You Return

    One JSON payload to `respond_to`, then stop:
    ```json
    {"kind": "report", "v": "v1", "dispatch_id": "[D<NNNNN>]",
     "task": "[TASK_ID]",
     "result": "DONE | DONE_WITH_CONCERNS | BLOCKED | PARTIAL",
     "summary": "one line — what shipped",
     "commits": ["<sha> <subject>"],
     "tests": [{"name": "<suite>", "ran": true, "passed": true,
                "detail": "command + outcome"}],
     "concerns": ["what a reviewer should look at"]}
    ```

    - `DONE` — implemented and evidenced.
    - `DONE_WITH_CONCERNS` — shipped, but something deserves a second look.
    - `BLOCKED` — could not proceed; `summary` says why.
    - `PARTIAL` — some `accepts` unmet; `summary` names the gap.

    `NEEDS_CONTEXT` is not a report result — it is its own payload kind,
    bound to the same `dispatch_id`, that routes the task to `ASK`.
    A report claiming it is a schema rejection.

    If a review finds issues, you are redispatched as `fix` with a new
    `respond_to` and a `fixes/R<NN>.fix-package.json` to read: the
    verdict's findings verbatim. Fix at the source — name the root cause
    in one line per finding before touching code, write the failing test
    that reproduces the defect first, then fix. Answer with the same
    `report` payload on the new slot.
```

## If Your Payload Is Refused

`executor ingest` writes nothing when it refuses a payload, and the
dispatch stays open. The refusal names a `code` and a `field` path; fix
that one thing, write the corrected payload to the same `respond_to`,
and report it. `skills/executor/references/rejections.md` lists every
code and the action that clears it. Never re-dispatch, never edit the
journal, and never answer a different slot — a refusal is the protocol
saying the attempt was not what it claimed to be.

**Placeholders — every one is required:**

| Placeholder | Value |
|---|---|
| `[TASK_ID]` / `[task name]` | the task's ID and heading, e.g. `INIT-0004-P01-T03` |
| `[D<NNNNN>]` | the dispatch id the engine minted |
| `[MODEL]` | implementer model, per `executor-execution` Model Selection — never omitted |
| `[INIT-NNNN]` / `[INIT-NNNN-Pnn]` | the initiative and plan IDs |

An unfilled bracket is a defect — the implementer has no session history to
infer it from.

## Fix-round variant

A `fix` dispatch is the same prompt with the fix preamble — the engine's
brief adds `fixes/R<NN>.fix-package.json` naming the round and the open
findings, and `context.round` echoes the round the report answers. The
worker answers `respond_to` on the new slot with the same `report` kind.
