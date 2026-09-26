# Branch model — implementation plan

Implements `docs/branch-model.md`. Nothing here is built yet; this is the
task breakdown for review.

## Goal

Task branches become the default execution shape (task → plan →
initiative), with `sequential: true` as the declared escape hatch, worktrees
for parallel waves, and mechanical enforcement at every gate.

## Ordering rationale

The ledger must be able to record a branch before any script creates one
(T01), so recording lands first. Task branches (T02) are the foundation
everything else hangs off. The escape hatch (T03) and the topology audit
(T04) both depend on T02 existing. Side/spike (T05) and worktrees (T06) are
independent of each other but both need T02. Docs (T07) come after behavior
settles; tests (T08) grow alongside each task and are consolidated last.

## Tasks

### T01 — Record the branch in the ledger

**Change.** `dispatches.md` gains a `Branch` column; the dispatch row
records the task branch and its fork commit (`task/INIT-0004-P01-T03 @
a1b2c3d`). The ledger's completion line records the merge commit when the
task merges (`… complete (commits a1b2c3d..d4e5f6a, merge e5f6a7b, review
clean)`).

**Files.** `skills/executor/scripts/_exec-lib.sh` (seed template),
`skills/executor/scripts/exec-run` (`task` action writes the branch),
`skills/executor/references/layout.md` (dispatch table shape).

**Acceptance.** A dispatched task's row names its branch and fork commit;
`exec-run check` reports a dispatched task with no branch recorded.

**Depends on.** —

### T02 — `exec-branch task start|merge|abandon`

**Change.** New subcommands:

- `task start PLAN TASK_ID` — refuses a dirty tree; forks
  `task/<TASK_ID>` from the **plan branch tip**; records branch + fork
  commit in the ledger; prints the branch name. Idempotent on resume.
- `task merge PLAN TASK_ID` — refuses unless the task's latest R-verdict is
  clean; merges `--no-ff` into the plan branch; records the merge commit;
  deletes the task branch.
- `task abandon PLAN TASK_ID [-f]` — refuses when the branch carries
  commits not on the plan branch unless `-f`; returns to the plan branch.

**Files.** `skills/executor/scripts/exec-branch`,
`skills/executor/scripts/_exec-lib.sh` (a shared `exec_verdict_clean` call
for the R-verdict gate — the function already exists).

**Acceptance.** A task with a clean R-verdict merges; one with
`NEEDS_FIX` is refused with the verdict path named; a refused merge leaves
the working tree unchanged; `abandon` refuses to drop unique commits
without `-f`.

**Depends on.** T01.

### T03 — The `sequential: true` escape hatch

**Change.** Plan frontmatter may declare `sequential: true`. Execution then
commits tasks directly to the plan branch and creates no task branches.
`exec-plan-lint` validates the justification: every task after the first
must declare `Depends on:` the immediately preceding task.

**Files.** `skills/executor/scripts/exec-plan-lint`,
`skills/executor-execution/SKILL.md` (dispatch flow branches on the flag),
`skills/executor/references/frontmatter.md` (plan fields).

**Acceptance.** A plan with `sequential: true` and a linear dependency
chain lints clean and runs without task branches; the same flag on a plan
whose tasks fan out is refused with the offending task named.

**Depends on.** T02.

### T04 — Topology audit in `exec-run check`

**Change.** New audits: the current branch matches the dispatched task;
every completed task's recorded merge commit exists on the plan branch; no
task branch holds unmerged commits when the plan's final verdict is clean;
orphan worktrees under `.executor/worktrees/` are reported.

**Files.** `skills/executor/scripts/exec-run`.

**Acceptance.** On a task branch for T02 while the ledger says T03 is
dispatched, the audit fails naming both; a completed task whose merge
commit is missing from the plan branch fails; a clean run passes.

**Depends on.** T01, T02.

### T05 — `exec-branch side|spike`

**Change.** `side start|merge` for in-scope work that is neither plan nor
task (fork from the initiative branch; merge on a human ruling recorded via
`exec-ruling … initiative`). `spike start|abandon` for throwaway
experiments (fork from the initiative branch; never merges; `abandon`
deletes).

**Files.** `skills/executor/scripts/exec-branch`.

**Acceptance.** `side merge` refuses without a recorded ruling; `spike`
has no merge path at all; both refuse a dirty tree.

**Depends on.** T02 (shares the fork/clean-tree helpers).

### T06 — Worktrees for parallel waves

**Change.** `task start --worktree` creates
`.executor/worktrees/<TASK-ID>/` on the task branch and prints the path;
`task merge` and `task abandon` remove it. `exec-branch status` lists
worktrees and flags orphans. Store resolution is already correct
(`exec_root` = worktree, `exec_main_root` = main repo) — this task adds
lifecycle, not resolution.

**Files.** `skills/executor/scripts/exec-branch`,
`skills/executor-execution/SKILL.md` (parallel-wave dispatch).

**Acceptance.** Two tasks dispatched with `--worktree` run concurrently
without touching each other's files; merging one removes only its worktree;
an orphaned worktree is reported by `status`.

**Depends on.** T02.

### T07 — Skill and reference docs

**Change.** `executor-execution` documents the dispatch flow (branch per
task, fork from tip, merge gate); `executor-handoff` documents the branch
stack and worktree teardown; `references/layout.md` gains the branch
grammar table; `README.md`'s branch-model section is rewritten to match
this spec and links it.

**Files.** `skills/executor-execution/SKILL.md`,
`skills/executor-handoff/SKILL.md`,
`skills/executor/references/layout.md`, `README.md`.

**Acceptance.** A reader can derive every branch name and gate from the
docs alone; no doc contradicts `docs/branch-model.md`.

**Depends on.** T02–T06.

### T08 — Regression fixtures

**Change.** Extend `scripts/test-issue9-fixes.sh` with a task-branch
fixture: fork from the plan tip, merge refused on a `NEEDS_FIX` verdict,
merge accepted on a clean one, `abandon` refusing unique commits, the
`sequential: true` path creating no task branches, and the topology audit
firing on a branch/task mismatch.

**Files.** `scripts/test-issue9-fixes.sh`.

**Acceptance.** The suite passes on macOS and Linux (the CI matrix is
Linux — the `ls` multi-path lesson applies to every new check).

**Depends on.** T02–T04.

## Verification

- `scripts/test-issue9-fixes.sh` — extended suite, green on Linux CI.
- `scripts/validate-skills.sh`, `scripts/lint-prompt-injection.py`,
  ShellCheck `--severity=warning` — unchanged gates, must stay clean.
- A manual end-to-end run on a scratch repo: two plans, one sequential and
  one with a parallel wave, exercising every gate and one edge case from
  the spec's table (an unrelated `side/` change mid-run).

## Out of scope

- Changing the contribution conventions (`feature/`, `fix/`, `docs/`,
  `release/`) — those govern changes to The Executor itself.
- Automatic base-branch syncing into the initiative branch; the spec keeps
  it a human decision.
- Any change to the plan → initiative gate, which already works.
