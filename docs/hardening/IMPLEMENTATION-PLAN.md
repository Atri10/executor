# Executor Hardening — Implementation Plan

Dependency-ordered waves. Ordering constraints honored: ledger write-paths
before the verbs that read them; `exec-step` verb additions before the
decision-table regeneration; `exec` front-door last.

Two shared primitives land first inside Wave 1 because everything else sits
on them:

- `exec_roles()` in `_exec-lib.sh` — machine-readable dispatch registry
  (from `layout.md:296-315`): `role | id_pattern | template | log_target |
  needs` where `needs` ∈ `brief` (brief+context), `diff` (review package),
  `fix` (fix package), `none`.
- `exec_verbs()` in `_exec-lib.sh` — machine-readable decision table:
  `verb | actuator | counted` (whether the no-progress guard may count it).
  `exec-step` emits only verbs listed here; `exec table` renders SKILL.md's
  table from it; `exec-graph` checks every verb has exactly one row.

## Wave 1 — ledger write paths

Gaps: G-01, G-02, G-03, G-04, G-11, G-19, G-22, G-23, G-26, plus registry
`ready` half of G-07.

Files:
- `skills/executor/scripts/_exec-lib.sh` — add `exec_roles()`,
  `exec_dispatch_row()` helper (header-name column append), product-path
  argument for `exec_row_liveness`, dispatch-row append helper.
- `skills/executor/scripts/exec-prompt` (new) — `exec-prompt ROLE
  TEMPLATE|--file F KEY=VAL…`: fills `[BRACKET]` placeholders, refuses while
  any `[A-Z_]+` bracket remains unfilled, writes to a stated out path.
- `skills/executor/scripts/exec-heartbeat` (new) — `exec-heartbeat PLAN
  TASK_ID`: wraps `exec_touch_heartbeat` on the resolved workspace.
- `skills/executor/scripts/exec-seen` (new) — `exec-seen PLAN TASK_ID`:
  rewrites the open row's Last-Seen cell to now (header-name lookup,
  tolerates missing column).
- `skills/executor/scripts/exec-ladder` (new) — `exec-ladder PLAN TASK_ID
  revive|redispatch`: increments `revived-rvN` on the open row under the
  plan workspace, refreshes Last-Seen, enforces `EXEC_MAX_REVIVE` (refuses
  at bound), emits the filled revive-preamble path and (for redispatch) the
  fresh brief/context paths.
- `skills/executor/scripts/exec-dispatch` (new) — `exec-dispatch PLAN
  --task N --role impl [--model M]`, `--role review --task Tnn [--round N]
  --base SHA --head SHA`, `--role fix --task Tnn`, `--role supervisor
  --task Tnn`, `--role verify --task Vnn`. One locked act: resolves
  workspace → optional `exec-branch task start` (skipped for
  `sequential: true` plans) → mints agent ID → builds per-role input file →
  `exec-run PLAN task TID` (ledger + Tasks cell + fix cap; annotation arg
  added) → appends dispatches.md row → renders prompt via exec-prompt →
  prints `AGENT= … PROMPT= … REPORT= …` lines.
- `skills/executor/scripts/exec-run` — `task` action gains optional
  annotation (`exec-run PLAN task TID "(agent X, base sha)"` →
  `Tnn: dispatched (annotation)`); seed registry `ready` in exec-workspace.
- `skills/executor/scripts/exec-report` — registry Tasks cell refresh inside
  the existing lock.
- `skills/executor/scripts/exec-supervise` — `open_rows` also emits Role;
  `action_for` derives the product path (review→`reviews/verdicts/`,
  else→`reports/`).
- Prompt templates — heartbeat contract line added to
  implementer/task-reviewer/re-review/final-reviewer/evidence-runner/
  supervisor prompts; `result:` field added to report frontmatter in
  implementer-prompt.md (contract for G-06, consumed in Wave 2).
- `scripts/validate-skills.sh` — enforce heartbeat-contract presence in
  worker-role templates.

Tests (`scripts/test-executor.sh`):
- `exec-dispatch` mints correct IDs per role; row lands with
  Started==Last-Seen, Outcome=running; prompt file exists with zero
  `[A-Z_]+` brackets; ledger carries the annotated dispatched line.
- `exec-ladder` rewrites Outcome to `revived-rv1`, then refuses at bound;
  emits preamble path.
- `exec-seen`/`exec-heartbeat` update liveness signals (age decreases;
  suspect→alive).
- Reviewer-row liveness: open REVIEW row + implementer report on disk →
  row reports ALIVE/zombie-off-verdict, not zombie.
- `exec-report` refreshes registry Tasks cell.
- `exec-prompt` refuses unfilled brackets.
- Registry seeds `ready`, flips `running` on `exec-run start`.

Wave check: fixture workspace → `exec-dispatch` produces complete dispatch
state with zero hand edits; `exec-supervise` reads it.

## Wave 2 — exec-step verb additions

Gaps: G-05, G-06, G-07 (emit half), G-14 (wake hints), G-20, G-24, G-25.

Files:
- `skills/executor/scripts/exec-step`:
  - Digest gains `reports/` listing.
  - Guard counts only `counted` verbs per `exec_verbs()`; WAIT/ASK/DONE exempt.
  - New verbs: `RUN-START <plan>` (registry row `ready`), `REVIEW <tid> Rnn`,
    `FIX <tid> Rnn`, `CRITIQUE <init> <component>`.
  - REPORT narrows to report ∧ latest verdict clean.
  - Fold 2 reads report `result:` frontmatter: `blocked`→ADJUDICATE,
    `needs-context`→ASK.
  - Fold 2 review-pending: report ∧ ¬verdict ∧ open reviewer row → WAIT
    (kills the REPORT livelock); ∧ no reviewer row → REVIEW.
  - Fold 2 fix-pending: latest verdict exists ∧ unclean → FIX.
  - Phase fold: entered ∧ artifact present ∧ component critique not clear →
    CRITIQUE (reads `exec-critique … check`); clear → PHASE-GATE.
  - Every emit gains a wake hint in parens.
- `skills/executor/scripts/exec-initiative` — `phase … check` dry-run event
  (validates `passed` conditions without writing); exec-gate check mode
  switched to it (fixes G-17 here, one line).

Tests:
- Simulated report-without-verdict + open reviewer row: repeated `exec-step`
  never yields `ADJUDICATE loop` (the G-05 regression).
- NEEDS_FIX verdict → `FIX` emitted; `result: blocked` report → ADJUDICATE;
  `result: needs-context` → ASK.
- `ready` registry row → RUN-START; WAIT×4 → still WAIT (no loop verdict).
- `exec-initiative … check` exits non-zero on missing artifact and writes
  nothing.

Wave check: `EXEC_NO_PROGRESS_LIMIT=3` fixture — reviewer in flight, N
consecutive folds, all emit REVIEW/WAIT, none emits ADJUDICATE loop.

## Wave 3 — presentation + resume surfaces

Gaps: G-08, G-12, G-13, G-15, G-21.

Files:
- `skills/executor/scripts/exec-adjudicate` (new) — `exec-adjudicate PLAN
  TASK_ID`: assembles `state/adjudication/<TID>-evidence.md` (report +
  latest verdict + diff path + dispatch-row extract + rulings tail),
  renders supervisor prompt, appends SUPERVISOR dispatch row.
- `skills/executor/scripts/exec-present` (new) — `exec-present INIT PHASE`:
  fixed-shape gate card (artifact paths + byte sizes, `exec-initiative
  check` readiness, critique clearance, open findings count). No artifact
  bytes emitted.
- `skills/executor/scripts/exec-status` (new) — writes
  `.executor/RESUME.md`: registry rows, `exec-step` next verb per in-flight
  plan + per initiative, open dispatch rows with liveness, store-check
  drift count. Prints path.
- `skills/executor/scripts/exec-initiative` — `document INIT ID KIND PATH`
  subcommand: appends the Documents row under registry lock (G-21 repair
  arm).
- `skills/executor/scripts/exec-store-check` — findings lines gain a repair
  hint suffix from a class→repair table (matrix lives in the script).

Tests:
- exec-adjudicate evidence pack exists, names report+verdict+row; supervisor
  row lands in dispatches.
- exec-present output contains no artifact body (assert byte cap /
  fixed-shape fields).
- exec-status digest lists a live plan's verb and an open row.
- `exec-initiative document` registers a row; store-check I1 goes clean.

Wave check: scratch run → kill → `exec-status` alone names the next verb
and the open row.

## Wave 4 — front door + router

Gaps: G-09, G-14 (protocol half), G-18.

Files:
- `skills/executor/scripts/exec` (new) — bare `exec` = exec-status digest +
  `exec-step` scan; `exec <verb-args>` dispatches to `exec-<verb>`; `exec
  verbs` prints `exec_verbs()`; `exec table` renders the decision table.
- `skills/executor/SKILL.md` — shrinks to a router (~≤100 lines): the
  decision table becomes generated output embedded verbatim, procedure
  prose deleted in the same commit per graph item 4.
- `scripts/validate-skills.sh` — check SKILL.md's decision table equals
  `exec table` output (drift detector for the generated table).
- `exec-step` header — replace stale `exec-package` references.

Tests: `exec` unknown verb → exit 2 usage; `exec step` == `exec-step`;
SKILL.md table matches `exec table`.

## Wave 5 — graph check + markdown hardening sweep

Gaps: G-10 (CI half), G-15 residual, requirement 2/3/4.

Files:
- `skills/executor/scripts/exec-graph` (new) — `exec-graph check`:
  (a) every verb in `exec_verbs()` has exactly one actuator row;
  (b) every ledger artifact has exactly one writer path — dispatches rows
      via exec-dispatch/exec-ladder/exec-report only, Outcome cells via
      exec-ladder/exec-report/sync_dispatch_outcomes only;
  (c) every role's product has a reader+gate (report→exec-report, verdict→
      exec_run_audit/exec-report gate 2, evidence→exec-store-check X3);
  (d) every ID pattern has exactly one minter (exec-id for docs,
      exec-dispatch for agents, `id:` frontmatter for artifacts);
  (e) referential integrity: ledger task IDs resolve to `### Task N:`
      headings; open dispatch rows resolve to ledger-known tasks;
      `## Tnn` rulings cite known lanes; initiative INDEX rows resolve to
      folders and back.
- SKILL.md files — strip controller-procedure prose superseded by scripts
  (dispatches-row logging prose, revive-ladder manual steps, prompt-assembly
  prose). Contracts, grammars, role I/O stay.
- `scripts/test-executor.sh` — dangling-reference fixtures FAIL.

Wave check: `exec-graph check` green on a healthy fixture, names the
dangling ref on a broken one.

## Cross-cutting

- Bash 3.2 floor (no `declare -A`, no mapfile) — enforced by the suite's
  first check.
- Column lookup by header name everywhere; missing `Last-Seen`/`Status`
  columns tolerated.
- Every new script: `set -euo pipefail`, `_exec-lib.sh` sourced, `exec_die`
  failures, mktemp+mv writes, `store_lock` for shared stores, header block
  with SPDX + usage + rationale.
- `sequential: true` plans skip `exec-branch task start` inside
  exec-dispatch.
- Worktree protocol untouched: `.executor` at main root, docs at worktree
  root.

## Landed status (2026-10-05)

- Wave 1 — **done.** exec_roles/exec_verbs in _exec-lib.sh; exec-prompt,
  exec-heartbeat, exec-seen, exec-ladder, exec-dispatch landed; exec-run
  task annotation + ready-seed; exec-report registry refresh; supervise
  product-path by role; heartbeat contract in worker prompts.
- Wave 2 — **done.** RUN-START / REVIEW / FIX / CRITIQUE emitted; REPORT
  narrowed to verdict-clean; result: frontmatter routed
  (blocked→ADJUDICATE, needs-context|needs_context→ASK); reviewer-in-flight
  WAIT kills the G-05 livelock; emits carry wake hints; `phase … check`
  dry-run landed and exec-gate check mode uses it (G-17).
- Wave 3 — **done.** exec-adjudicate (mechanical evidence pack →
  supervisor dispatch), exec-present (gate card), exec-status (resume
  digest + .executor/RESUME.md). G-21 (initiative document register)
  remains open — not blocking.
- Wave 4 — **done.** exec front-door (bare=status, `exec <name>`
  dispatch, `exec verbs`/`exec roles`); SKILL.md decision table regenerated
  from exec_verbs with a "do not hand-edit" banner. SKILL.md full router
  shrink remains — prose still ~500 lines.
- Wave 5 — **partial.** exec-graph check green (verbs/writers/roles/ids/
  refs + registry→workspace paths) — 50 checks. The per-class repair
  matrix (G-15 residual: exec-store-check AUDIT classes → named repairs)
  and the SKILL.md prose strip remain open.

Suite: 140 passed, 0 failed on this checkout.
