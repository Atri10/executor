# Changelog

All notable changes to The Executor are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). As of 0.1.0 the
project is tagged; between releases, entries are dated and `main` moves.


## [Unreleased]

The write side is scripted. Every state mutation the pump used to perform
by hand — dispatch rows, `revived-rvN` cells, `Last-Seen`, evidence
selection, prompt bracket-filling — is now a single script call behind
one `exec` front door.

### Added

- `exec` — the single entry point: bare `exec` prints the resume digest;
  `exec <name>` dispatches to `exec-<name>`; `exec verbs`/`exec roles`
  print the machine-readable registries.
- `exec-status` — one-file resume digest (initiatives + plan runs + open
  rows + store drift); `--write` stamps `.executor/RESUME.md` so a fresh
  agent reorients in one read.
- `exec-dispatch` — one locked act: mints the agent ID, builds the
  role's input file, marks the ledger, appends the dispatches.md row,
  renders a bracket-clean prompt.
- `exec-ladder` — `revive`/`redispatch` rewrites `revived-rvN` cells and
  enforces `EXEC_MAX_REVIVE` itself; emits the prompt path.
- `exec-seen`, `exec-heartbeat` — the two liveness witnesses workers and
  supervise actually consume.
- `exec-prompt` — renders a role template; refuses while any
  `[UPPER_SNAKE]` bracket remains unfilled.
- `exec-adjudicate` — mechanically assembles the adjudication evidence
  pack (report + verdict + diff + open rows + ledger/rulings tails) then
  dispatches SUPERVISOR; the adjudicated party no longer selects the
  adjudicator's evidence.
- `exec-present` — the fixed-shape gate card for PHASE-GATE; artifact
  bytes never enter the pump's context.
- `exec-graph` — `check` verifies every `exec-step` verb has exactly one
  actuator row, every ledger file has a script writer, every role's
  template resolves, ID grammars carry placeholders, and ledger↔plan↔
  dispatch↔registry references resolve (dangling = FAIL, not NOTE).
- `exec-step` verbs — `RUN-START` (registry `ready`), `REVIEW` (report ∧ ¬verdict ∧ ¬reviewer),
  `FIX` (verdict unclean), `CRITIQUE` (phase entered ∧ component unclear);
  `REPORT` narrows to verdict-clean; every emit carries a `(wake on …)`
  condition; WAIT/ASK exempt from the no-progress guard.
- `exec-initiative phase … check` — dry-run event: validates `passed`
  conditions and writes nothing; `exec-gate`'s check mode uses it (the
  old "check" used to pass the gate for real).
- Report `result:` frontmatter is routed: `blocked` → ADJUDICATE,
  `needs-context`/`needs_context` → ASK — a finished worker can no longer
  silently burn revive rungs.
- `docs/hardening/` — `gap-graph.md` (26-gap ledger with status column),
  `graph.tsv`, `IMPLEMENTATION-PLAN.md` (waves + landed status).

### Fixed

- REPORT livelock: a report with a reviewer in flight emits `WAIT`
  indefinitely instead of three identical `REPORT`s and an `ADJUDICATE
  loop` on a healthy run.
- `exec_product_exists` crashed BSD/bash-3.2 runs on glob specs (`rest`
  unbound under `set -u` inside `local`); supervisor zombies now report
  instead of dying.
- `exec-report` now refreshes the registry's Tasks cell inside its own
  store lock (the header had always claimed it did; it never did).
- `exec-workspace` seeds the registry row `ready` (previously lied
  `running` before `exec-run start`); `exec-gate` check mode no longer
  mutates the phase log it claims to inspect.

### Changed

- `skills/executor/SKILL.md` decision table is generated from
  `_exec-lib.sh` `exec_verbs` — the single table `exec-step`, the scripts,
  and `exec-graph check` all consume; hand-edit is prohibited because a
  table and a script disagreeing is how stale rows get followed.


## [0.6.0] — 2026-09-29

The controller no longer carries the work. The pipeline is two axes of
script-driven state with dispatched subagents at every step that needs
judgment, a critique gate on every authoring phase, and a fail-closed path
for unattended runs. The three defects this closes: only two of eleven
phases could reject a bad deliverable, upstream drift was structurally
undetectable, and the pump's "never authors" rule had no mechanism behind it.



### Added
- 2026-09-29 — **The thin-controller engine: scripts and subagents own
  the pipeline, the main agent only drives it.** During execution the
  controller's whole job is now: run `exec-step`, do the one action it
  prints, repeat. Four new scripts carry the mechanical truth:

  - `exec-step` — folds a plan run (or an initiative's phase log, or
    every in-flight run) and emits exactly one typed action:
    `DISPATCH`, `REPORT`, `REVIVE`, `REDISPATCH`, `ADJUDICATE`,
    `GATE-STAGE`, `REPAIR-STATE`, `PHASE-ENTER`, `PHASE-GATE`, `ASK`,
    `WAIT`, `DONE`. It never writes state and never improvises. Every
    emit is stamped; an action emitted repeatedly with no state change
    escalates to `ADJUDICATE` instead of looping forever.
  - `exec-supervise` — owns worker liveness and the revive ladder
    (`REVIVE` → `REDISPATCH` → `ADJUDICATE`), counted from the dispatch
    log itself rather than a counter file a worker could delete.
  - `exec-report` — gate-on-commit. The only path a worker's result
    takes into run state: nothing reaches the ledger without a clean
    latest-round verdict, and a refusal writes nothing at all.
  - `exec-step` and `exec-supervise` share one liveness implementation
    (`exec_row_liveness` in `_exec-lib.sh`): output presence outranks
    the worker heartbeat, which outranks row age, so a finished worker
    is never re-dispatched and a slow one is never declared dead.

  Four new dispatch roles, registered in `references/layout.md`:
  `AUTHOR` (authors a phase artifact the controller will later gate),
  `DECIDE` (answers a decision-class question), `SUPERVISOR` (the only
  role permitted to classify human prose or adjudicate a spent lane),
  and a `revive-preamble.md` fragment prepended to a re-dispatched
  worker so it verifies on-disk state before overwriting it.

  `skills/executor/SKILL.md` gains a **Pump Contract**: the decision
  table mapping each action word to its actuator, what a pump never does
  (author, judge, improvise a transition, absorb a dead worker's work),
  and how to handle a human interrupting mid-run.

- 2026-09-29 — **Ingress for unsolicited human input.** A human who says
  "stop everything" or "actually, do it this way" between two tasks had
  no mechanical path to be obeyed, which left the controller to
  improvise — the exact unenforced-judgment failure the engine exists to
  remove. `exec-ruling` gains `--unsolicited "<verbatim>"`, which stores
  the human's words unparaphrased and marks the ruling as unsolicited
  rather than asked-and-answered; `--stop` additionally blocks the run
  and prints a single relayable `STOP` line. Mutually exclusive with
  `--answered`, in either argument order.
- 2026-09-28 — **A dispatch registry and a prompt per dispatched role.**
  `references/layout.md` gains a Dispatch registry: every role that
  spawns a subagent (implementer, task reviewer, re-reviewer, final
  reviewer, plan auditor, plan repairer, plan re-auditor, evidence
  runner, prior-art scout, concept explorer, design critic) is listed
  with its identity grammar, its prompt template, and the dispatch log it
  writes to. New prompt files under the owning skill: the three
  plan-regression prompts, `evidence-runner-prompt.md`, and the three
  brainstorm prompts. `validate-skills.sh` fails on a dispatch role with
  no registered prompt, a prompt missing any of the required markers
  (`Subagent`, `agent_identity`, `model:`, `## Identity`,
  `## Self-Critique Before You Return`, `## Verification`,
  `## What You Return`, `**Placeholders`), or a `*-prompt.md` file no
  registry entry names.
- 2026-09-28 — **Self-Critique and Verification on every phase skill and
  every dispatch template.** Each `skills/*/SKILL.md` now carries a
  `## Self-Critique` section (an adversarial pass over the artifact the
  phase just produced) and a `## Verification` section (the commands that
  prove it, run in-session with output cited at the gate). The router,
  `executor-initiative`, `executor-discovery`, `executor-architecture`,
  `executor-spec`, `executor-planning`, `executor-execution`,
  `executor-review`, `executor-verification`, and `executor-handoff` all
  gained both; the four existing dispatch prompts gained the in-prompt
  versions.
- 2026-09-28 — **`exec-id BRN` allocation** and `brainstorm` frontmatter
  kinds (`mode: design | decision`, `feeds:`), so a session ID is
  allocated by the script and its downstream phase is machine-readable.


### Fixed
- 2026-09-29 — **CI's plan-lint control had gone stale, and its negative
  case had gone vacuous.** The positive control was a six-line stub written
  when the linter only checked store paths; when the task-body contract
  landed (`Implements`, `Depends on`, `Interfaces`, `Requirements`, checkbox
  steps, `Run`/`Expected`), the stub stopped satisfying them and the job
  began failing on its own control. The negative case was worse: written as
  an independent literal, it failed for seven unrelated reasons, so it would
  have passed with the store-path contract deleted outright — a test that
  looks green while testing nothing. The negative case is now derived from
  the positive by a single `sed` line, and asserted to produce exactly one
  violation naming that contract. Both directions are verified: neutering the
  store-path check fails the step loudly, and introducing a second violation
  is rejected as vacuous.

- 2026-09-29 — **Three cross-platform defects, all invisible on macOS and
  all caught only by running the suite on Linux.** The scripts ship to users
  on both, and two implementations of `awk` and `date` disagree in ways that
  changed behaviour rather than failing loudly:

  - **Worker liveness read differently per platform.** `date -j -f
    "%Y-%m-%d" <date>` on BSD *ignores* the date it was handed and returns
    roughly now, while GNU's `-d` parses it. The same dispatch row was
    therefore "alive" in a macOS run and "dead" an hour later on Ubuntu —
    a false DEAD verdict burns a revive rung and replaces an agent still
    holding its context. Replaced with `exec_timestamp_epoch`, which gives
    both platforms a fully-specified UTC string. A day-granular witness now
    anchors to the END of its day, because the schema says such a value
    "cannot tell a slow worker from a dead one", and negative ages clamp to
    zero.
  - **`validate-skills` rejected ordinary prose on Linux.** The box-drawing
    check used a bracket expression containing multibyte characters. mawk —
    the default awk on Debian and Ubuntu — is byte-oriented, so the set
    degenerated into individual BYTES and an em-dash in prose matched. The
    validator passed on macOS and failed on every Linux runner: the platform
    nobody develops on was the only one reporting the problem. Rewritten as
    explicit alternation, where byte and character matching agree.
  - **`exec-store-check` parsed timestamps in local time on macOS.** BSD's
    `date -j -f` needs `-u` to read UTC; the GNU branch already had it. Both
    call sites compare two values from the same function so the offset
    cancelled, and nothing was broken today — but it is a trap for the first
    caller who compares the result against an absolute threshold, and a
    one-character fix is cheaper than that bug later.

  A fourth fix is in the test harness itself: the shared-clearance-dir check
  passed `_ "$S"` to one sub-shell and not the other, so the second resolved
  to `/_exec-lib.sh`, died, returned empty, and `[ -z ... ]` reported it as
  PASSED. A gate that reports success when it never ran is the most dangerous
  thing a suite can contain, because it is a false green that is invisible
  precisely while the suite is green. Both registry checks now fail loudly if
  the sub-shell cannot read the registry.

  `script-smoke` now runs on a `[ubuntu-latest, macos-latest]` matrix. A
  Linux-only job catches these only when the author is on Linux; a macOS-only
  one never would have. Three assertions pin the parser's semantics — a
  day-granular value reads within its own day, a full ISO-Z value round-trips
  unchanged, and an older witness compares strictly older — so the property
   holds on any host and in any timezone rather than on one machine's clock.

### Changed
- 2026-09-29 — The dispatch log schema gains a **`Last-Seen`** column.
  `Started` is day-granular and cannot distinguish a 50-minute evidence
  run from a dead worker. Readers locate columns by header name, so
  workspaces seeded before the column existed still parse.
- 2026-09-29 — The canonical phase order moves to `exec_phases()` in
  `_exec-lib.sh`. `exec-initiative` validates transitions against it and
  `exec-step` folds the phase log against it; two hand-maintained copies
  would let a run advance and refuse in the same turn.
- 2026-09-29 — **Every authoring phase now passes a critique gate.**
  Previously only 2 of 11 phases could reject a bad deliverable:
  `plan-regression` and `review`. `design` and `verification` had no
  artifact gate at all, and architecture and specification ran adversarial
  *self*-critiques whose own skills refused the word critic. New
  `executor-critique` skill and `exec-critique` script generalize the
  plan-regression contract to all nine authoring components (`charter`,
  `discovery`, `architecture`, `design`, `specification`, `plans`, `code`,
  `verification`, `handoff`). The phase→component→catalog mapping is a
  registry row in `_exec-lib.sh`, so adding a component is data, not a
  fork. `exec-initiative phase … passed` now refuses unless the
  component's critique is `clean|waived`; the clearance is recorded in the
  phase log's Notes cell, since the critique gets no row of its own.

  The gate is hardened where `exec-plan-regression` was soft, which was the
  point of generalizing rather than forking: `verdict: PASS` beside a
  non-zero `high`/`medium` is refused instead of believed, the three-round
  cap is enforced by the script (`audit 04` exits 2 with a message), and a
  waiver needs both a note in the row and an initiative ruling naming it.
  `plans` resolves to the existing `plan-regression/` home and reads the
  same `summary.md`, so the shipped skill and its artifacts stay valid —
  one gate, two front doors, not two gates that can disagree.

  This also closes a structural hole: **upstream drift was undetectable.**
  No reviewer prompt in `executor-review` opened the architecture store,
  so an implementation satisfying every `R-nn` and `C-nn` while violating
  the ARCH passed every gate in the system. Two seats now catch it: the
  `code` component's critique catalog, and `final-reviewer-prompt.md`,
  which takes the architecture, IFCE and design stores as required inputs
  and adds an architecture-conformance check to what it reviews.
- 2026-09-29 — **The pump now actually dispatches the author.** The pump
  declared "Never authors … every one is a dispatch" while its `PHASE-ENTER`
  decision-table row only said to write the Entered cell — so `AUTHOR-<phase>`
  was a registered role that nothing ever dispatched, and the phase axis had a
  hole exactly where the controller was supposed to carry no weight. The row
  now dispatches the phase's `AUTHOR`, the phase-axis loop is written out, and
  `AUTHOR` covers `verification` and `handoff` alongside the six phases it
  already had.

  The `REPAIR-STATE` action is deliberately left as a script call rather than
  given a prompt, and SKILL.md now says why: the controller is the thing that
  drifted the store, so it is the thing that repairs it, and a subagent reading
  only a prompt would know less than the controller does at that moment.

  Every dispatch prompt gains the edge cases it was silently leaving to
  invention — a prompt is the only definition of what a subagent does, so an
  undefined state is an unreviewed behaviour. Measured before: one prompt in
  seventeen had `## Preconditions`, none had `## When You Cannot Proceed`, none
  handled an output file left behind by an aborted prior run, and three of the
  new `executor-critique` prompts lacked the dispatch ban the rest carry.

  Two defects worth calling out. `component-reauditor-prompt.md` hardcoded
  `R01`/`R02` throughout while its header claimed `R02+`, so a round `R03`
  dispatch would have written R03's findings into R02's file and re-verdicted
  R01's — the loop would have reported progress it never made. Every
  round-bearing value is now a placeholder. And `design-critic-prompt.md`
  required a ranking and a `RANKING:` return field while stating "you do not
  pick the winner", pre-empting the human's choice with an unreviewable
  judgment; it now reports what cuts each way instead of ordering the options.

  A new test reads the action vocabulary out of `exec-step` and the role
  registry out of `layout.md` rather than a hand-kept list, and fails when an
  action has no decision-table row, a role has no prompt on disk, a critique
  registry row has the wrong field count, or two components share a clearance
  directory. The last two caught a live bug: the `code` and `handoff` rows
  carried six fields instead of five, so both resolved their clearance record
  to a directory literally named `-`.
- 2026-09-29 — **Autonomous mode, fail-closed.** `exec-gate INIT PHASE
  --auto` clears a phase gate without a human only when the initiative's
  `autonomous.md` names that phase with mode `gate` or `allow`. Every
  ambiguity resolves to `deny`: no policy file, `enabled: false`, an
  unlisted phase, or an unrecognized mode. An auto-pass is recorded as
  `**auto-passed** <date>` — a visibly different result from a human
  `passed`, not a synonym — and it must satisfy the same artifact gate a
  human pass does. A pick-class phase (`design`, `specification`) in
  `allow` mode additionally requires a scored verdict already on disk:
  a script can count files, it cannot choose between designs.

  The event grammar gains `auto-passed` and `superseded`. `superseded` is
  the deliberate inverse of the "already passed" refusal — only a phase
  that actually finished can be overturned, it requires a stated reason,
  and it clears the Entered date so the phase reopens. Without it, a human
  who disagreed with an autonomous pass had no move but to hand-edit the
  phase log, which is the one thing the log exists to prevent.
  `exec-step` treats `**auto-passed**` as finished and `**superseded**`
  as reopened, so the pump advances and re-enters correctly.
- 2026-09-28 — **`executor-brainstorm` redesigned around full-feature
  design.** A session may start before any initiative exists (the dossier
  seeds `exec-initiative new`), and fans out to independent concept
  explorers plus a prior-art scout and a red-team critic. `mode`
  distinguishes a full `design` session from a single-question `decision`
  session; `exec-store-check` B2 is mode-aware and B3 requires a
  Documents-table row for every session ID.
- 2026-09-28 — **`executor-plan-regression` runs in numbered rounds.**
  Audit and repair files are round-suffixed (`regression-P02-R01.md`,
  `fix-P02-R01.md`); a re-audit is always a fresh auditor, never the
  repairer, and `check` requires the *latest* audit's `verdict: PASS` for
  a `clean` row. Legacy unsuffixed files read as round 1.
- 2026-09-28 — **Specification and planning are gated on a decided
  brainstorm session.** `exec-initiative phase <INIT> specification
  entered` refuses without a session whose `feeds:` names specification;
  `planning entered` refuses without one naming planning. A discovery
  skip note records that discovery needed no ideation — it does not
  satisfy the spec/plan gates.
- 2026-09-28 — **No ASCII-art diagrams anywhere.** `validate-skills.sh`
  rejects box-drawing characters used as diagram edges in skill markdown;
  the layout trees and the test-quality gate table moved to Mermaid.

### Fixed
- 2026-09-28 — **Prompt registry was unenforced.** Plan regression
  dispatched auditors with no template and overwrote round-1 findings;
  verification dispatched `VERIFY` runners with no prompt. Both are now
  registered templates and round-safe file naming.

## [0.5.1] — 2026-09-26

### Fixed
- 2026-09-26 — **Stale documentation after the branch model.** CONTRIBUTING's
  repository-layout table still described a `docs/` directory (the repo
  keeps none — normative content lives in `skills/executor/references/`),
  its references list was missing `branches.md` and `test-quality.md`, and
  its contract-update rule did not name the branch model. The README's
  `exec-branch` and `exec-run check` rows predated the task/side/spike
  subcommands and the topology audit.

## [0.5.0] — 2026-09-26

### Added
- 2026-09-26 — **Task branches and the branch model.** `references/branches.md`
  is normative: one branch per artifact level named after the artifact ID
  (`initiative/INIT-NNNN`, `plan/INIT-NNNN-Pnn`, `task/INIT-NNNN-Pnn-Tnn`),
  each forked from its parent and merged through the gate its level
  requires. `exec-branch task start|merge|abandon` forks a task branch from
  the **plan branch tip at dispatch** and merges it back only when the
  task's own R-verdict is clean — so the plan branch's history is only
  reviewed merges. `exec-branch side|spike` carry the work that is neither
  plan nor task (a side branch merges on a recorded initiative ruling; a
  spike never merges). `exec-branch status` prints the branch stack and
  flags orphan worktrees.
- 2026-09-26 — **Worktrees for parallel waves.** `task start --worktree`
  creates `.executor/worktrees/<TASK-ID>/` and leaves the main tree on the
  plan branch; `task merge` and `task abandon` remove it. Store resolution
  already handled this (`exec_root` = worktree for tracked docs,
  `exec_main_root` = main repo for the shared execution store).
- 2026-09-26 — **`sequential: true` escape hatch.** A plan may declare it to
  commit tasks directly to the plan branch (the two-level model).
  `exec-plan-lint` requires every task after the first to declare
  `**Depends on:**` the preceding task, so the flag states a fact about the
  dependency map rather than skipping isolation for convenience.
- 2026-09-26 — **Branch recording in the ledger.** `dispatches.md` gains a
  `Branch` column (after Agent, so existing column-index parsers keep
  working) and the ledger records the branch and fork commit at dispatch
  and the merge commit at merge.
- 2026-09-26 — **Topology audit in `exec-run check`.** A task branch must
  match the task the ledger says is in flight; every recorded merge commit
  must be an ancestor of the plan branch; a clean final verdict with a task
  branch still holding unmerged commits is drift; orphan worktrees and
  non-worktree debris under `.executor/worktrees/` are reported.

### Changed
- 2026-09-26 — **`exec-branch` grew subcommands** (`task`, `side`, `spike`)
  and `status` now prints the stack. The plan-level `start|merge|abandon`
  behaviour is unchanged.

## [0.4.0] — 2026-09-26

### Added
- 2026-09-26 — **Plan-set regression phase + skill.** New phase
  `plan-regression` sits between planning and execution, enforced by the
  phase-order machine: `exec-run PLAN start` refuses once planning has
  passed while the phase is not passed or skipped (before planning the
  gate does not apply — there is nothing to audit), and `execution
  entered` is refused outright without it. `executor-plan-regression`
  audits the whole plan set against the spec, interface contracts,
  sibling plans' Assumes/Produces, ordering, constraint propagation, and
  vocabulary — the defect class every per-plan check missed — then
  repairs plans in place, re-audits, and records clearance in
  `.executor/<INIT>/plan-regression/summary.md`. Companion script
  `exec-plan-regression` owns the artifact paths and the `check` that
  turns clearance into an exit code (audit-file kind, waiver notes, and
  stale rows included); `exec-initiative phase … passed` refuses without
  a clean summary; `exec-store-check` P1 fails an initiative that
  entered execution without it.
- 2026-09-26 — **Initiative-level execution artifacts.** `.executor/`
  gains `<INIT>/rulings.md` (cross-plan rulings, contract amendments,
  human-answered questions) and `<INIT>/plan-regression/` — the legal
  home for artifacts spanning plans. `frontmatter.md` gains `regression`,
  `repair`, `gate`, and `brainstorm` kinds.
- 2026-09-26 — **`executor-brainstorm` skill.** Dedicated ideation skill
  owning session mechanics (≥3 options, known-ancestor pass, adversarial
  pass on the favorite), `session.md` recording (`kind: brainstorm`,
  `decided:` field), and the visual-companion offer contract; discovery
  delegates to it. Also usable standalone and mid-architecture/planning.
- 2026-09-26 — **Mid-run ask contract.** Decisions now route three ways —
  rule silently (`exec-ruling`), ask on the spot (decision-class:
  contract conflicts, scope cuts, irreversible choices, product judgment;
  blocks only the affected lane), or stop the run (the four conditions).
  `exec-ruling --answered "<question>"` records the question beside the
  ruling so answered asks never look like silent controller picks.
- 2026-09-26 — **`exec-ruling` scope + answered flag.** `initiative` as
  the task ID writes the initiative-level rulings log; `--answered`
  attaches the question text to both the log entry and its
  `.local/decisions/` mirror.

### Changed
- 2026-09-26 — **BREAKING for in-flight initiatives:** execution now
  requires plan-regression clearance (or a recorded skip) once planning
  has passed. An initiative mid-flight when it upgrades records the
  decision explicitly:
  `exec-initiative phase <INIT> plan-regression skipped "<reason>"`.
  New initiatives get the phase row seeded by `exec-initiative new`.
- 2026-09-26 — **`exec-run check` audits more.** It now also reports
  missing verdicts for completed tasks, completed tasks absent from the
  Task status table, seeded files missing or lacking `kind:` frontmatter,
  sibling workspaces with a ledger but no registry row, empty scaffold
  directories, and cross-plan artifacts misfiled inside a plan's
  `reviews/`. `-FINAL-verdict.md` filenames are accepted with a rename
  note (canonical stays lowercase).
- 2026-09-26 — **Workspace seeding is entry-point-independent.**
  `exec_seed_workspace` runs from `exec-workspace`, `exec-run`,
  `exec-ruling`, `exec-brief`, `exec-context`, `exec-review-package`, and
  `exec-fix-package`, so a workspace resolved by any path carries its four
  seeded files.

### Fixed
- 2026-09-26 — **Ledger grammar the audits could not read.** `exec-run`
  counted `complete` by `^<PLAN>-T<nn>: complete`; real controllers write
  narrative lines (`- <ts> — T03 complete`), so every audit — verdict
  presence, task-table coverage, registry-drift, dispatch-outcome sync —
  silently no-oped while rows read `0/?`. A shared parser
  (`exec_ledger_states`) now reads both shapes, normalizes `approved` to
  `complete`, and reports narrative lines as drift notes instead of
  ignoring them.
- 2026-09-26 — **Unseeded workspaces.** `exec_seed_workspace` in
  `_exec-lib.sh` is now called by `exec-run`, `exec-ruling`, and
  `exec-workspace` — progress/rulings/preflight/dispatches with correct
  frontmatter exist no matter which entry point runs first. `exec-run
  check` audits their presence, their `kind:` fields, sibling workspaces
  missing registry rows, empty scaffold dirs, and cross-plan artifacts
  misfiled inside a plan's `reviews/`. `-FINAL-verdict.md` filenames are
  accepted with a rename note.
- 2026-09-26 — **`exec-plan-lint` documentation drift.** Planning's
  checklist credited three checks; the script enforces four — the
  sketch-vs-code cap is now documented.
- 2026-09-26 — **Final-verdict check was macOS-only.** `ls a b` exits
  non-zero when either path is missing; on case-insensitive APFS both
  `-final-` and `-FINAL-` variants resolve to the same file so the check
  passed locally, while on Linux a clean run was reported as missing its
  final verdict. Each path is now tested with `-f`, and the two final-R
  globs in `exec_run_audit` are guarded the same way (their status
  propagates under `pipefail`).

## [0.3.0] — 2026-09-22

### Added
- 2026-09-22 — **`exec-fix-package` assembles the fix dispatch.** One
  command produces the complete package a fix implementer is handed:
  the open findings verbatim from the task's latest verdict, the
  implementer's own report, and the brief and context files the work
  is judged against — written to `reviews/fix-packages/` under the
  plan workspace. Missing verdict, brief, or context refuses; a
  missing report warns and continues.
- 2026-09-22 — **Document contracts are checked, not documented.**
  `exec-store-check` D8 now verifies what each kind's contract
  actually claims: an architecture document carries a top-level
  mermaid diagram (a mermaid line inside another fence is quoted
  example text, not a diagram); a spec carries numbered `### R<nn>`
  requirement headings, a `verification:` pointer that resolves to a
  same-initiative `kind: verification` document, and a
  `global_constraints:` count matching its `C<nn>` rows; an active
  options document has `recommends:` set and a filled `## Decision`
  section (drafts are exempt); a verification document's
  `criteria_count:` matches its distinct `V<nn>` criteria across
  table rows and `### V<nn>` manual blocks. Thinking-only kinds
  (charter, research, options, risk, spec, verification) reject
  implementation-language code fences — contract-bearing kinds and
  structural fences (mermaid, json, yaml, diff, untagged) are exempt.
- 2026-09-22 — **Brainstorming is enforced, not scaffolded.** Check
  B1: once the discovery gate passes, the initiative must carry
  either a session directory under `brainstorm/sessions/` or a
  recorded skip note (INDEX.md or a discovery document). The empty
  scaffold with no record — the state every real initiative was in —
  now fails.
- 2026-09-22 — **Phase `passed` is artifact-gated.** `exec-initiative
  phase … passed` refuses when the phase's deliverable is absent:
  intake needs a substantive charter, discovery a research or options
  document, architecture an ARCH document, specification SPEC + RISK
  + VRFY together, planning a plan. `skipped` now requires a reason
  note — a bare `**skipped**` row is indistinguishable from an
  oversight.
- 2026-09-22 — **`exec-plan-lint` enforces the sketch contract.**
  Required frontmatter keys (`id`, `spec`, `interfaces`, `tasks`,
  `execution_mode`) fail when absent — a missing key no longer
  silently passes every value check. Implementation-language fenced
  blocks cap at 40 lines, and a task body embedding more than 60
  implementation lines at more than 60% of its length is rejected as
  over-specified — plans sketch; implementations belong to interface
  and design docs.
- 2026-09-22 — **Dispatch outcomes sync and fix rounds cap.** Every
  registry mutation in `exec-run` reconciles `dispatches.md`: rows
  for tasks whose latest ledger state is terminal close as
  `complete`/`parked`, an `in-fix` boundary closes all but the
  newest live row, and run completion closes plan-level rows —
  explicit outcomes are never overwritten, missing rows produce a
  NOTE. Fix dispatches refuse past the documented five-round maximum
  (counted by highest round number, not line count) unless a ruling
  or disposition record exists.
- 2026-09-22 — **Regression suite covers the new contracts.** Sixteen
  new cases (37 total) exercise absent-key refusal, sketch/volume
  caps, every D8 rule, B1, I5, artifact gates, dispatch sync, the
  fix-round cap and its ruling escape, fix-package assembly,
  annotated-path extraction, and the wider requirement grammars.

### Fixed
- 2026-09-22 — **`exec-context` resolves annotated Modify paths.** A
  `Modify:` line carrying an annotation — `` `file.py` (add Helper) ``,
  `file.py:88-104` — was looked up verbatim and every existing file
  reported "does not exist yet". Backticked paths are extracted
  before annotation stripping, `(...)` suffixes and documented
  trailing line ranges are removed, and BSD `sed` portability is
  fixed (`[[:space:]]` in place of `\s`).
- 2026-09-22 — **Requirement extraction matches real spec grammars.**
  `exec_requirement_body` covers `### R01 — t`, `### R01: t`, bare
  `### R01`, `### R01. t`, and paragraph-form `R01. <text>` /
  `R01: <text>` items — verified against a live spec whose
  requirements were paragraphs, not headings. `R011` no longer
  matches a lookup for `R01`.
- 2026-09-22 — **Execution progress requires branch provenance.**
  `exec-store-check` I5 fails an initiative whose INDEX records an
  entered/passed execution, review, verification, or handoff phase
  but carries no `**Branch:**` line — the fork point must be
  recoverable.
- 2026-09-22 — **The fix loop hands over the contract, not a
  paraphrase.** Fix dispatches previously carried only the reviewer's
  verdict and the implementer's report — the fixer iterated on a
  retelling of the requirements. `executor-execution` now routes fix
  work through `exec-fix-package`, which always includes the brief
  and context verbatim.

### Changed
- 2026-09-22 — **Plans contract; they do not implement.** The
  planning skill's task-body contract is rewritten around the
  contract/sketch boundary: files, signatures, invariants, exact
  values, and acceptance criteria are verbatim authority; embedded
  code is an advisory sketch that loses to the contract on any
  disagreement, and the implementer reports divergences rather than
  transcribing defects. `exec-brief` states this split in every
  brief's preamble; the implementer prompt repeats it. The execution
  skill's model-selection table no longer prices "complete code in
  the plan" as cheapest — embedded implementations are a defect
  signal and model choice routes by task complexity.
- 2026-09-22 — **Disputes escalate; dispositions stay honest.** A
  reviewer-vs-implementer contract or scope disagreement is a ruling
  trigger, not another fix round. Cap dispositions can defer polish
  but cannot launder correctness findings — the final reviewer
  re-examines them with the disposition visible.
- 2026-09-22 — **Layout documents the fix-package artifact.**
  `references/layout.md` shows `reviews/fix-packages/` in the
  workspace tree and `references/frontmatter.md` adds the
  `fix-package` kind to the execution-artifact vocabulary.

## [0.2.0] — 2026-09-12

### Fixed
- 2026-09-12 — **Review context survives rounds.** `exec-context` no
  longer silently clips plan Interfaces (was 40 lines) or Global
  Constraints (was 30); sections are extracted whole. Ruling records
  are matched whole — Decided, Why, and Cost stay together — and any
  backticked file counts, not just code extensions. Literal source
  content round-trips: `printf %b` no longer transforms escape
  sequences. `exec-review-package` extracts whole requirement nodes
  (was `head -6`), fails closed when the referenced spec cannot be
  resolved, records base/head SHAs and plan/spec blob hashes in the
  package header, and labels fix-delta ranges as delta semantics
  instead of "Missing" findings.
- 2026-09-12 — **Verification evidence is immutable and state-bound.**
  `exec-evidence` writes one file per round (`…-V03-R01-smoke.txt`);
  same-round re-runs append `-attempt2`, `-attempt3` instead of
  overwriting prior proof. State stamps are per round and carry the
  commit actually exercised. Captures publish atomically (temp +
  rename): a failed capture (missing input file) leaves prior evidence
  intact and creates no partial artifact. The documented method enum
  (`unit|integration|smoke|manual|static`) is enforced before any
  filesystem mutation; criterion aliases (`#3`, `V3`, `V03`) resolve to
  one canonical identity.
- 2026-09-12 — **Gates parse verdicts, not filenames.** A shared
  semantic audit (`exec_run_audit`) backs `exec-run check`, `exec-run
  complete`, and `exec-branch audit`: `spec_verdict: FAIL` verdict
  files, incomplete task sets, duplicate completion events, and a
  failing latest final re-review (which supersedes an earlier clean
  final verdict) all block. `complete` validates before mutating the
  registry; a refused completion leaves prior state unchanged. An
  empty dispatch table (valid for inline runs) no longer silently
  fails `check` under `pipefail`.
- 2026-09-12 — **Phase transitions are validated before mutation.**
  `exec-initiative phase` refuses passed-before-entered, entering past
  a non-passed predecessor, re-entry, and re-passing; skips are
  recorded events that unblock the next phase.
- 2026-09-12 — **Store and plan contracts close their gaps.**
  `exec-store-check` validates the full registry schema, rejects
  duplicate initiative rows, requires title/created_at/updated_at in
  frontmatter, scopes kind-specific required fields to parsed
  frontmatter (body code fences no longer satisfy checks), validates
  real calendar dates, detects filename-ID mismatches in nested
  directories, and scans for orphan evidence initiative-wide regardless
  of any single VRFY's citation count. `exec-initiative new` refuses
  titles containing pipes or newlines before they corrupt YAML and
  pipe tables. `exec-plan-lint` normalizes CRLF once (the body scan no
  longer silently skipped), counts and validates task headings with
  CommonMark fence tracking (fenced examples are not tasks), requires
  task IDs to name this plan and match the heading number, rejects
  duplicate task numbers, and treats read-only `docs/executor/`
  citations as legitimate — only Create/Modify/Test targets violate.
- 2026-09-12 — **Concurrency and identity guards.** Registry writes
  (`exec-run`) and ruling appends/sequence allocation (`exec-ruling`)
  take a store lock with unique temp names. `exec-id` refuses the
  two-digit namespace boundary instead of silently emitting IDs its
  own scanner can never see again. `exec-workspace` refuses reuse when
  the existing ledger names a different plan or spec (rename support
  preserved). `exec-branch start` refuses dirty trees;
  `exec-initiative branch` refuses reuse with mismatched recorded
  provenance.
- 2026-09-12 — **Visual companion stop contract.** `stop-server.sh`
  resolves both runtime state layouts — the flat runtime root that
  `start-server.sh` actually returns and the legacy nested `state/`
  form.
- 2026-09-12 — **The merge gate can pass after a fix round.** The run
  audit demanded `spec_verdict: PASS` from the latest verdict file, but
  re-review verdicts carry `spec_verdict: null` by template — one fix
  round permanently poisoned `exec-run check`, `exec-run complete`, and
  `exec-branch merge`. A verdict is now clean iff frontmatter
  `spec_verdict` is PASS or null (re-reviews judged findings, not the
  spec) AND `quality: APPROVED`; both fields are frontmatter-scoped, so
  a `spec_verdict:` line in the verdict body is prose, not a verdict.
  The audit also accepts the documented ledger annotation
  (`complete (commits a1b2..b7c8, …)`) and computes the expected task
  set fence-aware, so a fenced `### Task` example can no longer become
  an uncompletable task.
- 2026-09-12 — **Generated markdown carries no HTML comments.** Seeded
  files (`exec-initiative` charter, the four `exec-workspace` ledgers,
  `exec-brief`, `exec-context`) and the architecture/ADR/design/
  interface templates emit italic guidance lines instead of `<!-- -->`
  blocks, and all four templates now say to replace them (previously
  only the ARCH template did). Verdict skeletons drop their marker
  comment — frontmatter `kind: verdict` carries the provenance.
  `layout.md`'s rendering rule is now a blanket ban, not a placement
  rule.
- 2026-09-12 — **Plan and lint bookkeeping corrections.**
  `exec-plan-lint` drops a dead double-write of its body temp file and
  reports real file line numbers for forbidden paths (was body-relative
  offsets). `exec-evidence` sanitizes the resolved VRFY id before
  building a filename from it, validates input files before stamping
  state, and its header comment matches its real output names
  (`state-R<nn>.txt`, `…-V<nn>-R<nn>-<method>.txt`, `-attemptN`).
  `exec-initiative`'s INT/TERM trap exits instead of continuing
  unlocked, `phase skipped` preserves a recorded Entered date, and
  `branch` writes `**Branch:**` under `**Status:**` instead of at EOF —
  where it used to push later phase-log rows outside the table.
  `exec-branch abandon` validates its flag and branch existence before
  any destructive fallback, and `merge` surfaces audit diagnostics
  instead of swallowing them. `stop-server.sh` assigns the PID/ID file
  paths it was checking, so `stop` actually stops. `exec-scan-secrets`
  covers source/config extensions and checks every target. Store check
  exempts `state-R*.txt` in its orphan scan.

### Changed
- 2026-09-12 — **Skill contracts realigned with the fixes.** Re-review
  runs two jobs (impact review of the fix first, then finding closure);
  impact scope is bounded by causality, not the diff; location never
  sets severity. Test changes are graded by what they protect —
  legitimate contract migrations are not auto-Critical. Evidence
  demands are bounded: name the failure, the coverage gap, and a
  feasible method, or record uncertainty. Implementers separate write
  scope from read scope (follow dependencies; NEEDS_CONTEXT only for
  the undiscoverable) and pick the strongest feasible evidence per
  surface (capability map replaces the unconditional TDD Iron Law).
  Self-review adds impact, edge-case families, and assumption
  challenges. Verification's freshness rule is state-bound, not
  session-bound, and the `verification passed` transition is described
  as mechanically validated. Handoff requires the latest final verdict
  and an explicit recorded human acceptance for every
  FAILED/NOT-RUN/UNAVAILABLE criterion. Final review resolves the
  merge base from recorded initiative provenance instead of hardcoded
  `main`. Brainstorm sessions are recorded reasoning in any mode
  (text first-class), with explicit skipped/declined records; visual
  mode is a capability inside a session, not its definition.

### Added
- 2026-09-12 — **Regression suite:** `scripts/test-executor.sh`
  recreates 14 reproduced failure scenarios in disposable git fixtures
  and asserts the fixed behavior (context completeness, evidence
  immutability/aliases/atomicity, method validation, semantic audit,
  completion-before-mutation, empty dispatch, phase gates, ID
  boundary, workspace identity, plan-lint CRLF/citation/fence,
  frontmatter-scoped required fields, pipe-title refusal). CI gains a
  valid-control plan-lint negative fixture and an empty-dispatch
  clean-run case.
- 2026-09-12 — **Markdown structure is linted, not hoped for.**
  `validate-skills.sh` rejects HTML comments outside `html`/`xml`/`svg`
  code fences in every skill markdown file, and `exec-store-check`
  gains D7 (the same rule for tracked thinking-store docs), D5 branches
  for `charter`, `architecture`, and `design` kinds plus `recommends`
  for options docs, and D1 presence checks for `supersedes`/
  `superseded_by`. The regression suite grows to 21 cases (re-review
  verdict acceptance and rejection, comment-free seeds, D7, annotated
  ledger lines, fenced task examples, fenced store-path lint
  exemptions) and now runs in CI; shellcheck
  and `bash -n` cover `_exec-lib.sh`, `visual-companion/*.sh`, and
  `scripts/*.sh`, matching what CONTRIBUTING documented.

## [0.1.0] — 2026-09-03

**The genesis release.** The Executor takes a major idea from intake through
architecture, spec, plan, execution, review, and verification — with a
strict per-initiative ID namespace ("nothing floats"), separated thinking
and execution stores, and a script-enforced contract at every state
transition: plans lint before they dispatch, reviews gate merges, verdict
audits catch unjudged work, and the stores themselves check their own
integrity. Ten skills, thirteen `exec-*` scripts (plus the shared
`_exec-lib.sh`), one CI pipeline of five gates.

### Added
- 2026-09-03 — **Evidence lives in the tracked store:** `exec-evidence`
  now writes per-criterion evidence files to the initiative's
  `docs/executor/<init>/verification/evidence/PNN/` (one directory per
  plan, capital `P` plan segment, flat file names, `state.txt` stamped
  once per plan directory) instead of the untracked
  `.executor/…/round-NN/` location. The VRFY id is resolved through the
  SPEC's `verification:` field. Evidence is proof, and proof commits on
  the branch that produced it. `references/layout.md` and
  `executor-verification` document the new location as the contract.
- 2026-09-03 — **Thinking-store integrity gate:** new `exec-store-check`
  lints the tracked store — registry ↔ folders ↔ Documents table ↔
  frontmatter statuses ↔ spec/plan/VRFY cross-links ↔ evidence citations
  ↔ phase-log chronology. Catching the drift class found in the first
  live stores (unregistered documents, status contradictions, broken
  links, "To be filled" outcomes) by script instead of by human
  observation. `executor-handoff` Step 0 requires exit 0.
- 2026-09-03 — **Plan lint hardening:** `exec-plan-lint` additionally
  rejects missing/empty `interfaces:` and `execution_mode:` (the P02/P03
  live failure), `execution_mode` values outside `subagent|inline`,
  `tasks:` counts that disagree with the task headings, and plan
  `status:` outside `draft|active`. The frontmatter `workspace:` field
  is contract-required and no longer trips the literal-path check.
- 2026-09-03 — **Ledger table audit:** `exec-run check` now fails when a
  task complete in `## State changes` has no row in the Task status
  table — the prose-only ledger that made the resume scan blind (P04/P05
  live failure).

- 2026-09-03 — **Agent identity grammar:** every subagent dispatch now
  carries a conventional, role-and-position identity — implementers
  `IMPL-P01-T03`, task reviewers `REVIEW-P01-T03-R01`, the final
  whole-branch reviewer `REVIEW-P01-final`, evidence runners
  `VERIFY-P01-V01` (round-suffixed on re-runs). A resumed agent keeps its
  identity; fresh rounds 4-5 implementers take `-R4`/`-R5`. Defined in
  `references/layout.md`, wired into the implementer and reviewer prompt
  templates, the `exec-workspace` dispatches seed, and `executor-execution`'s
  identity-recording step. `exec-run check` reports non-conforming Agent
  cells as a NOTE (legacy stores are provenance, not failures).

- 2026-09-03 — **Branch model (issue #6):** one branch per initiative
  (`initiative/INIT-NNNN`, forked from the human's current branch, fork
  point recorded in the initiative INDEX) and one branch per plan
  (`plan/INIT-NNNN-Pnn`, forked from the initiative branch). New
  `exec-branch` script owns the plan-branch lifecycle — `start`, `status`,
  `merge` (`--no-ff`, gated on the review audit), `audit`, `abandon`
  (refuses unmerged work without `-f`). `exec-initiative` gains the
  `branch` subcommand. `executor-execution` Step 1 and `executor-handoff`
  Steps 5–6 document the flow; merging the initiative branch onward stays
  the human's decision.
- 2026-09-03 — **Plan lint (issue #7):** new `exec-plan-lint` rejects plans
  that write literal `docs/executor/` or `.executor/` paths into tasks
  (artifact locations are resolved by scripts), task headings without ID
  tokens, and missing frontmatter. Required by the planning gate
  (validation checklist item 10).

### Fixed

- 2026-09-03 — **Verdict audit (issue #5):** `exec-run check` now fails
  when a ledger-complete task has no verdict file in `reviews/verdicts/`
  and when a completed run lacks its final verdict — a skipped review,
  including the last task's, is a detected exit-1 failure instead of a
  human observation. `executor-execution` documents the final review as
  the regression gate (always last, always at the post-fix HEAD).
- 2026-09-03 — Task and final reviewer prompts gain a mechanical artifact
  placement check: run artifacts under `docs/executor/` (outside the
  VRFY-outcomes exception) or hand-built `.executor/` paths are Important
  findings citing the placement contract.

- 2026-09-02 — `exec-evidence` script introduced (per-round `state.txt`,
  VRFY outcomes table citing files). Superseded 2026-09-03 by the tracked
  evidence location above.

- 2026-09-02 — **Issue #1:** workspace seed comments (progress, preflight,
  dispatches) moved above their tables; comments placed after a table
  separator split the table in most Markdown renderers once rows are
  appended. Layout reference gains a "Markdown rendering rules" section
  codifying the discipline.
- 2026-09-02 — **Issue #2:** verification evidence no longer lands as loose
  files in an ad-hoc folder; `exec-evidence` defines the structure
  (`round-NN/<VRFY-id>-V<nn>-<method>.txt`) and `executor-verification`
  documents the workflow.
- 2026-09-02 — **Issue #3:** every generated execution artifact (briefs,
  contexts, ledger, rulings, preflight, dispatches, reports, verdicts,
  evidence) now carries the same YAML frontmatter identity block as
  thinking documents; the frontmatter contract documents all nine kinds.
- 2026-09-02 — `exec-run`: fixed a `grep -c` bug that crashed `task`,
  `complete`, and `check` on plans with zero completed tasks (grep prints 0
  AND exits 1 on no match, producing a multiline count under `|| echo 0`).
- 2026-09-02 — `exec-context`: fixed a pipefail abort when a task has no
  `Files:` block; the Modify-extraction grep now degrades to an empty list.

- 2026-09-01 — Initial public documentation: README, MIT LICENSE, and the
  full open-source community set — CONTRIBUTING.md, CODE_OF_CONDUCT.md,
  SECURITY.md, CHANGELOG.md, `.gitignore`, and GitHub issue/PR templates.
- 2026-09-01 — The Executor skill library: `executor` router plus nine
  phase skills (`executor-initiative`, `executor-discovery`,
  `executor-architecture`, `executor-spec`, `executor-planning`,
  `executor-execution`, `executor-review`, `executor-verification`,
  `executor-handoff`), their references, and the helper scripts under
  `skills/executor/scripts/` (`exec-id`, `exec-workspace`, `exec-brief`,
  `exec-review-package`, `exec-scan-secrets`, `exec-ruling`,
  `exec-initiative`).
