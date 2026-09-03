# Changelog

All notable changes to The Executor are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project does
not use versioned releases yet — entries are dated, and users track `main`.

## [Unreleased]

### Added

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

- 2026-09-02 — `exec-evidence` script: writes one criterion's raw observed
  output to `.executor/<INIT>/<Pnn>/verification/evidence/round-NN/` with a
  per-round `state.txt` (branch, commit, dirtiness). The VRFY outcomes
  table's Evidence column now names these files.

### Fixed

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
