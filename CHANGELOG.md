# Changelog

All notable changes to The Executor are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project does
not use versioned releases yet — entries are dated, and users track `main`.

## [Unreleased]

### Added

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
