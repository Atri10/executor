# Changelog

All notable changes to The Executor are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). As of 0.1.0 the
project is tagged; between releases, entries are dated and `main` moves.

## [Unreleased] — 2026-09-22

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

## [Unreleased] — 2026-09-12

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
- 2026-09-12 — **Regression suite:** `scripts/test-issue9-fixes.sh`
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
