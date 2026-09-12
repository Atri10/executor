# Changelog

All notable changes to The Executor are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). As of 0.1.0 the
project is tagged; between releases, entries are dated and `main` moves.

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

## [0.1.0] — 2026-09-03

**The genesis release.** The Executor takes a major idea from intake through
architecture, spec, plan, execution, review, and verification — with a
strict per-initiative ID namespace ("nothing floats"), separated thinking
and execution stores, and a script-enforced contract at every state
transition: plans lint before they dispatch, reviews gate merges, verdict
audits catch unjudged work, and the stores themselves check their own
integrity. Ten skills, fourteen `exec-*` scripts, one CI pipeline of five
gates.

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
