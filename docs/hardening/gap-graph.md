# Executor Hardening — Gap Graph

Audit of the engine as found on `main @ 7f82c0b`. Every evidence line is a
file:line read during this audit, not carried forward from the seed ledger
unchecked. Node/edge inventory lives in `graph.tsv` beside this file.

Status vocabulary: `confirmed` — reproduced in the current checkout;
`disproven` — seed claim no longer holds; `nested` — found during this audit.

## Seed ledger — verification results

All 16 seed gaps confirmed. None disproven.

| ID | Verdict | Evidence (this checkout) | Classification | Status |
|---|---|---|---|---|
| G-01 | confirmed | `_exec-lib.sh:452` seeds 9 columns (`Task|Role|Model|Agent|Branch|Started|Outcome|Context|Last-Seen`); `executor-execution/SKILL.md:347` documents a stale 7-column example; `layout.md:40` says "controller logs each dispatch". No script appends a row — `exec-run` has `mark_dispatch` (ledger only, `exec-run:210-235`) and `sync_dispatch_outcomes` (closes rows, `exec-run:123-198`). | script-gap + schema-gap | closed — exec-dispatch appends the row (test: 9-col row, minted agent, annotated ledger) |
| G-02 | confirmed | `SKILL.md:127-128` decision-table rows instruct the pump to hand-rewrite `Outcome` to `revived-rv1`/`revived-rv2`; `exec-supervise:31-45` reads exactly that cell spelling as the ladder bound. | script-gap | | closed — exec-ladder writes revived-rvN + enforces bound (test) | closed — exec-ladder writes revived-rvN and enforces the bound |
| G-03 | confirmed | `_exec-lib.sh:450`: "the pump refreshes it each turn" — no script does it. Note the schema comment is itself wrong-headed: a pump that stamps `Last-Seen` every fold makes the fallback permanently fresh and the suspect/dead path unreachable. | script-gap + doc-gap | | closed — exec-seen refreshes open rows; wired into dispatch + supervise paths | closed — exec-seen refreshes open rows; wired into dispatch + supervise paths |
| G-04 | confirmed | `_exec-lib.sh:776` `exec_touch_heartbeat` — zero callers anywhere in `skills/` (rg: only definitions and `exec_heartbeat_age` readers). No `*-prompt.md` mentions heartbeat; worker contract does not instruct it. | script-gap | | closed — exec-heartbeat; prompts carry it (supervisor-prompt.md:41); TTL drives supervise | closed — exec-heartbeat; supervisor prompt carries it; TTL drives supervise |
| G-05 | confirmed | `exec-step:215-228` fold 2 emits `REPORT` on report-file-landed ∧ verdict-absent; `exec-report:63-73` refuses without a clean verdict; nothing dispatches a reviewer. Identical emit + unchanged digest → `ADJUDICATE loop` at `EXEC_NO_PROGRESS_LIMIT` (default 3) while a healthy review is in flight. | verb-gap | | closed — fold splits REVIEW vs REPORT; reviewer-in-flight → WAIT (test: 5 folds no ADJUDICATE) | closed — REVIEW vs REPORT split; reviewer-in-flight emits WAIT (test: 5 folds, no ADJUDICATE) |
| G-06 | confirmed | `exec-step:215-228` checks file existence + verdict only; the worker's return status (DONE/BLOCKED/… per `executor-execution/SKILL.md:531-536`) lives in the pump's memory — implementer-prompt.md:480 puts it in the *reply*, and the report's `status:` frontmatter is document status (`implementer-prompt.md:452`), not worker result. | verb-gap + schema-gap | | closed — fold reads result: frontmatter; blocked→ADJUDICATE, needs-context→ASK | closed — result: frontmatter routes blocked→ADJUDICATE, needs-context→ASK |
| G-07 | confirmed | `exec-run:269-302` `start)` (registry→running + plan-regression gate) has no emit; `exec-step` scans the registry only via ledger files. Compounding: `exec-workspace:70` seeds the registry row as `running`, so the registry already lies before run start. | verb-gap + schema-gap | | closed — RUN-START on registry ready; exec-workspace seeds ready, exec-run start flips | closed — RUN-START on registry ready; exec-workspace seeds ready, exec-run start flips |
| G-08 | confirmed | `exec-step:285-311` `step_scan` iterates `docs/executor/*/plans/*.md` + `docs/executor/plans/*.md` only — initiatives are not scanned; resume = `exec-initiative list` + per-axis folds + `exec-store-check`, assembled in pump context. | verb-gap | | closed — exec-status digest; --write stamps .executor/RESUME.md | closed — exec-status digest; --write stamps .executor/RESUME.md |
| G-09 | confirmed | `skills/executor/SKILL.md` is 645 lines of procedure; no `exec` front-door exists (`glob skills/executor/scripts/exec` → none). | script-gap + doc-gap | | closed — scripts/exec front-door: bare=status, `exec <name>` dispatch, `exec verbs`/`roles` | closed — scripts/exec front-door: bare=status, `exec <name>` dispatch, `exec verbs`/`roles` |
| G-10 | confirmed | `supervisor-prompt.md:12` — "an unfilled bracket is a defect"; `validate-skills.sh` lints templates statically (registry table check at `:103-139`), nothing validates fill-at-dispatch. | script-gap | | closed — exec-prompt refuses on unfilled slots (test, exit 2) | closed — exec-prompt refuses to emit while any slot is unfilled (test, exit 2) |
| G-11 | confirmed | `exec-run:577-583` NOTE-checks the Agent grammar post-hoc; grammar at `layout.md:317` (`<ROLE>-<scope>[-<qualifier>][-R<nn>]`) is lint-only. Nothing mints. | script-gap | | closed — exec-dispatch mints per exec_roles grammar | closed — exec-dispatch mints per exec_roles grammar |
| G-12 | confirmed | `supervisor-prompt.md:30,56-63` — `[EVIDENCE]` placeholder is pump-filled; the adjudicated party selects the adjudicator's evidence. | judgment-gap | | closed — exec-adjudicate assembles evidence pack then exec-dispatch --role supervisor | closed — exec-adjudicate assembles evidence pack then exec-dispatch --role supervisor |
| G-13 | confirmed | `SKILL.md:136` PHASE-GATE row ends "present the artifact" — pump reads + summarizes artifact bytes. | judgment-gap | | closed — exec-present emits the fixed-shape gate card | closed — exec-present emits the fixed-shape gate card |
| G-14 | confirmed | `SKILL.md:133` WAIT row says "stop and let the workers run"; no event re-invokes `exec-step`, and nothing prints the next-call condition. | verb-gap | | closed — emits carry "(wake on …)"; exec-status documents the re-invocation contract | closed — emits carry "(wake on …)"; exec-status documents the re-invocation contract |
| G-15 | confirmed | `exec-store-check` header lists R1–P1 classes (`exec-store-check:13-61`), all emitted as prose; `exec-step` fold 0 covers only the four seeded files (`exec-step:179-193`). No AUDIT class maps to a repair. | script-gap + verb-gap | | in-progress — exec-graph check green (verbs/writers/roles/ids/refs); per-class repair matrix pending | in-progress — exec-graph check green; per-class repair matrix still pending |
| G-16 | confirmed | `executor-execution/SKILL.md:534-536` — four-way status triage including "break the task into pieces" is pump judgment. | judgment-gap | | in-progress — blocked/needs-context route mechanically; task-split stays DECIDE (needs a spec) | in-progress — blocked/needs-context mechanical; task-split stays DECIDE by design |

## Nested gaps found during this audit

| ID | Gap | Evidence | Classification |
|---|---|---|---|
| G-17 | `exec-gate` check-only mode **mutates**: the "dry run" path calls `run_transition passed ""`, which is `exec-initiative phase … passed` — it writes the gate it claims to check. Output even prints "a human still has to run it" after having run it. | `exec-gate:77-90` | script-gap (correctness) |
| G-18 | Stale actuator name: `exec-step` header cites `exec-package`, which does not exist (redispatch and dispatch rows). | `exec-step:23,27` | doc-gap |
| G-19 | Reviewer/judge dispatch rows read as `zombie` forever: `exec_row_liveness` hardcodes `reports/${task}-report.md` as the product check, but a REVIEW row's product is `reviews/verdicts/*-verdict.md`. Under the G-05 fix (a REVIEW verb that dispatches a reviewer), the reviewer row would emit `ZOMBIE→REPORT <task>-report.md`, which is the implementer's report — re-livelock. | `_exec-lib.sh:845`; `exec-supervise:80-87` | script-gap |
| G-20 | No-progress guard over-fires on healthy waiting verbs. `WAIT`/`ASK` are "await external event" verbs — nothing the pump can do changes state, so 3 consecutive emits yield `ADJUDICATE loop`. The digest also omits `reports/` and `state/*.heartbeat`, so a report landing does not reset the counter. | `exec-step:60-101` | script-gap |
| G-21 | Documents-table rows for post-creation artifacts (specs, plans, RSCH, ADRs, brainstorm sessions adopted at intake) are hand-appended to `INDEX.md`; the contract literally names the Documents table as hand-edit surface. `exec-initiative` has no `document`/`register` command. | `executor-initiative/SKILL.md:447`; `exec-initiative` command list `:699-704` (new/resolve/phase/status/branch/list only) | script-gap |
| G-22 | `exec-report` header claims "the registry row's task count refreshes" but the commit block never touches `.executor/INDEX.md` — Tasks cell stays stale until some later `exec-run` call. | `exec-report:18-20` vs `:92-136` | script-gap |
| G-23 | `mark_dispatch` writes bare `Tnn: dispatched`, losing the documented annotation grammar `dispatched (model …, agent …, base sha)` — the base SHA that every review package needs never reaches the ledger. | `exec-run:235` vs `executor-execution/SKILL.md:521` | schema-gap |
| G-24 | Verb gap: NEEDS_FIX verdicts. When a verdict exists and is unclean, fold 2's `ls verdicts && continue` skips the task entirely → fold 3 re-emits `DISPATCH <same task>` (state not terminal). The fix path (`exec-fix-package`, resume-R1-3/fresh-R4-5, `fix round N/5` ledger) is pump memory; `exec-run task` enforces the cap but nothing assembles the fix dispatch. | `exec-step:224`; `exec-fix-package` exists but is unreferenced by any verb | verb-gap |
| G-25 | Critique-stage invisibility on the phase axis: after PHASE-ENTER + AUTHOR, `exec-step` jumps straight to PHASE-GATE. A critique in flight (or never started) is indistinguishable; the phase fold has no CRITIQUE verb and cannot see `.executor/<INIT>/critique/` state. | `exec-step:316-374`; `SKILL.md:113-115` | verb-gap |
| G-26 | `revive-preamble.md` exists as a template but assembly (prepend + fill `[REPORT_FILE]`) is manual; no `exec-prompt`-class tool renders any of the 16 prompt/preamble templates. | `revive-preamble.md:24-64` | script-gap |

## Gap classes → fix owners (summary)

- **script-gap** (state written by hand): G-01, G-02, G-03, G-04, G-17, G-19, G-20, G-21, G-22, G-26
- **verb-gap** (fold cannot say the right thing): G-05, G-06, G-07, G-08, G-14, G-15, G-24, G-25
- **judgment-gap** (pump deciding what a script/agent should): G-12, G-13, G-16
- **schema-gap** (formats disagree): G-01, G-06, G-07, G-23
- **doc-gap** (docs describe unenforced behavior): G-03, G-09, G-18

## Required fix shapes (verified against consumers)

| Gap | Fix shape |
|---|---|
| G-01/G-11/G-23/G-26 | `exec-dispatch PLAN --task N --role impl|review|fix|verify --model M`: mints ID per `layout.md:317` grammar, builds brief/context (exec-brief/exec-context) or diff package (exec-review-package/exec-fix-package), records BASE sha in the dispatched ledger annotation, appends the 9-column dispatches row (Started+Last-Seen=now, Outcome=running), calls `exec-run PLAN task <tid>` (which keeps enforce_fix_cap + Tasks cell), renders the role's prompt via `exec-prompt` into `state/<agent>-prompt.md`. Prints paths; pump only spawns. |
| G-02 | `exec-ladder PLAN Tnn revive\|redispatch`: rewrites open row's Outcome to `revived-rvN` (n=highest+1), refreshes Last-Seen, enforces `EXEC_MAX_REVIVE` itself (refuses at bound — supervise names the rung, ladder owns the write), emits the filled preamble path + assembled prompt. |
| G-03 | `exec-seen PLAN Tnn`: rewrite Last-Seen=now — called by pump only on *observed worker contact*, and internally by exec-dispatch/exec-ladder. Never auto-called per fold (per-fold stamping defeats the fallback). |
| G-04 | Keep the mechanism — it is the only minute-granular liveness signal and is required to kill the day-anchor weakness. `exec-heartbeat PLAN Tnn` wraps `exec_touch_heartbeat`; heartbeat contract added to worker prompts + `validate-skills.sh` enforcement. |
| G-05/G-24 | New verbs: `REVIEW <task> Rnn` (report ∧ ¬verdict ∧ no open reviewer row → exec-review-package + exec-dispatch) and `FIX <task> Rnn` (latest verdict unclean → exec-fix-package + exec-dispatch fix). `REPORT` narrows to report ∧ clean verdict. Fold ordering: liveness → fix-pending → review-pending → report-pending → dispatch. |
| G-06 | Add `result:` to report frontmatter contract (prompt templates updated); fold reads it: `blocked`→ADJUDICATE, `needs-context`→ASK, `done|done-with-concerns`→REVIEW, absent→REVIEW (backward compat). |
| G-07 | `exec-workspace` seeds registry Status=`ready` (not `running`); fold emits `RUN-START <plan>` when row is `ready`; `exec-run start` stays the actuator (it already carries the plan-regression gate). |
| G-08/G-09 | `exec-status` writes `.executor/RESUME.md` digest (registry rows, per-axis next verbs, open dispatch rows + liveness, store-check drift count). `exec` front-door: bare `exec` = resume digest; `exec <script-args>` dispatches to `exec-*` scripts by name. |
| G-10 | `exec-prompt ROLE PLAN [KEY=VAL…]`: resolves template from machine-readable role table (new `exec_roles()` in `_exec-lib.sh`, generated from `layout.md:296-315`), fills `[BRACKET]`s, refuses while any `[A-Z_]+` bracket remains, emits assembled prompt path under `state/prompts/`. |
| G-12 | `exec-adjudicate PLAN Tnn`: assembles evidence set mechanically — report + latest diff + dispatch row extract + rulings tail — writes evidence pack to `state/adjudication-<TID>-Rnn.md`, renders supervisor prompt via exec-prompt with [EVIDENCE] = that file. |
| G-13 | `exec-present INIT PHASE`: emits a fixed-shape gate card (artifact paths + sizes, gate readiness via `exec-initiative check`, critique clearance summary, open-finding count). No artifact bytes. |
| G-14 | Every verb emit appends a wake hint after the verb word in parens (existing convention), e.g. `WAIT (waiting on IMPL-P01-T03; re-check on reports/<T>-report.md landing or heartbeat TTL 1800s)`. WAIT/ASK/DONE exempt from no-progress guard (G-20). |
| G-15/G-21 | Repair matrix: store-check AUDIT classes mapped to named repairs in a data table; new `exec-initiative document INIT ID KIND PATH` registers a Documents row under the registry lock. REPAIR-STATE emits carry the repair command. |
| G-16 | Mechanical statuses stay mechanical (G-06 routing); plan-wrong/task-split route to ADJUDICATE (SUPERVISOR) — routing table in `exec-step`, not in pump prose. |
| G-17 | Add `check` event to `exec-initiative phase` (dry-run the `passed` validation, write nothing); `exec-gate` check mode calls it. |
| G-18 | Header corrected when the real actuators land. |
| G-19 | `exec_row_liveness` gains an optional product-path argument; `exec-supervise` derives it from the row's Role column (review→verdict glob, impl/fix→report, verify→outcomes ledger). |
| G-20 | Guard counts only mutation-verbs (REPAIR-STATE REVIVE REDISPATCH ADJUDICATE REPORT REVIEW FIX DISPATCH RUN-START PHASE-ENTER PHASE-GATE CRITIQUE); digest gains `reports/` listing. |
| G-22 | `exec-report` refreshes the registry Tasks cell inside its existing store_lock commit. |
| G-25 | New `CRITIQUE <init> <component>` verb: fold reads the component's summary (`exec-critique … check` contract) — entered-and-artifact-present ∧ ¬clearance → CRITIQUE; clearance → PHASE-GATE. AUTHOR-in-flight needs an initiative dispatches.md row (role table already logs AUTHOR there — layout.md:312). |
