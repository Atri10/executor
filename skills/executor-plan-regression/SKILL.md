---
name: executor-plan-regression
description: Use when plans under docs/executor/*/plans/ are all drafted and before any executor-execution begins — audits the whole plan set for cross-plan consistency, spec coverage, interface fidelity, and contract drift, repairs what it finds, and gates execution on the result.
---

# Executor — Plan Regression

The phase between planning and execution that the plan set earns by
surviving one adversarial read as a *set*. Every per-plan check that
already exists — `exec-plan-lint`, the planning self-review — reads ONE
plan. This phase reads all of them against each other and against the
contracts they claim to satisfy, because the defects that actually ship
are seams: an `Assumes` section promising a signature the predecessor plan
never produces, a spec requirement no plan's `Covers:` claims, two plans
both provisioning the same queue with different shapes.

This skill runs after planning has drafted every plan and **before** the
human picks an execution mode — defects found here repair cheaply; the
same defect found during execution costs a fix loop per dependent task.

## When to Use

- `executor-planning` has finished drafting the plan set (one or more
  plans) and the `planning` phase has been marked entered.
- Before every `executor-execution` run start — `exec-run PLAN start`
  refuses while this phase is entered-but-not-passed.
- When a plan set changes mid-initiative — a plan rewritten, a new plan
  added, a spec amended after plans were locked — the audit re-runs for
  the changed plans.

## Ownership Boundary

You audit and repair **plan documents**. Findings that live in the spec
or an interface contract get a ruling and a targeted amendment to THAT
document — never a plan edit that papers over a contract defect. You
never write implementation code; you never modify `.executor/<INIT>/Pnn/`
workspaces (those belong to execution).

## Inputs

| Need | From |
|---|---|
| The plan set | `plans/*.md` in the initiative folder — on disk, not the INDEX |
| The requirements | the spec each plan's `spec:` frontmatter names |
| The contracts | every `INIT-…-IFCE-*` the plans cite |
| Global constraints | the spec's constraint block, plus each plan's `## Global constraints` if present |
| The run store home | `../executor/scripts/exec-plan-regression PLAN_FILE dir` |

Resolve the artifact root first:

```bash
../executor/scripts/exec-plan-regression "$PLAN" init
# → .executor/INIT-0004/plan-regression/summary.md (seeded, one header)
```

`init` also seeds `.executor/INIT-0004/rulings.md` — the initiative-level
log where every ruling this phase produces lands (`exec-ruling "$PLAN"
initiative "<decision>" "<why>" "<cost>"`).

## The Audit — per plan, one `regression-P<nn>.md`

For each plan in the set, write its audit to
`exec-plan-regression PLAN audit` (`.executor/<INIT>/plan-regression/
regression-P<nn>.md`). Frontmatter `kind: regression`, `plan: <id>`,
`round: 1` (increment on re-audit after repair). Verdict line at top:
`PASS — 0 defects` or `FAIL — N defects (X high, Y medium, Z low)`.

Walk these checks **in this order** — each class cheap to verify, and the
order surfaces contract-breaking defects before polish ones:

1. **Spec coverage.** Union every plan's `Covers:` lines and `implements:`
   pointers; diff against the spec's `R<nn>` requirement set. A
   requirement with no claiming plan is a HIGH. A `Covers:` entry naming
   a requirement that does not exist is a HIGH (the author split by
   memory, not by the spec).
2. **Cross-plan Assumes/Produces closure.** Every signature, type, file
   path, topic name, or env var a later plan's `## Assumes` (or its
   tasks' `Consumes:`) names must resolve to a `Produces:` in an earlier
   plan or to an IFCE that already exists. Unresolved → HIGH.
3. **Interface fidelity.** Every IFCE a plan cites must exist, and every
   literal the plan quotes from it (field names, signatures, enum values,
   topic literals) must match the contract byte-for-byte in the parts
   that matter. Drifted literals → HIGH; paraphrase where exactness was
   required → MEDIUM.
4. **Ordering & dependency map.** The `Execution order:` statement must
   be acyclic and consistent with `Assumes` direction (a plan that
   assumes P03's output cannot precede it). Task-level `Depends on:`
   inside one plan must not reference another plan's tasks. Broken
   order → HIGH; a cycle → HIGH.
5. **Constraint propagation.** Every global constraint the spec declares
   (`C<nn>`) must either be restated in each plan's binding block or be
   provably scoped out by the constraint's own wording. A constraint
   binding tasks that never see it → MEDIUM (the run's C20-amendment
   defect was exactly this).
6. **File-map collisions.** Two tasks in different plans writing the same
   file is legal only when the dependency map makes the ordering
   explicit; silent collision → MEDIUM.
7. **Vocabulary consistency.** Same concept, two names across plans
   (queue `x.dlq` vs `x-dead-letter`) → MEDIUM: naming drift is how two
   plans provision incompatible halves of one seam.
8. **Plan lint.** `exec-plan-lint` must pass for every plan — mechanical
   contract, zero tolerance.
9. **Skipped-phase honesty.** If the initiative skipped architecture or
   spec, verify the plan does not cite contracts that were never written.

Dispatched audit subagents are right for multi-plan sets — one agent per
plan, all receiving the full plan set plus spec + IFCE paths as inputs so
cross-plan checks are real, not per-plan guesses. A single plan still
gets the audit: coverage vs its spec and lint checks apply.

## Repair — per plan, one `fix-P<nn>.md`

For every plan with findings, write the repair log to
`exec-plan-regression PLAN fix` (same dir, `fix-P<nn>.md`). `kind:
repair`, `verdict:` pointing at the audit file.

Rules of the repair pass:

- **Repair the plan file in place.** The audit's job ends at naming the
  defect; this pass edits `plans/INIT-…-P<nn>-*.md` (and re-runs
  `exec-plan-lint`). Fix-package-style "attach the patch" is for code;
  plans are edited directly — they are the deliverable.
- **Contract defects route outward.** A finding whose truth lives in an
  IFCE or the SPEC amends that document (targeted edit + `updated_at`
  bump), with the amendment listed in the fix log's `## Contract
  amendments` section — never adapt the plan around a broken contract.
- **Every repair is re-verified.** After repairs, re-run the audit for
  that plan (`round: 2`). The fix log's `## Verification` section records
  the re-audit result per finding — not grep counts, the actual check
  that would have caught the defect re-run.
- **Findings you cannot repair are rulings, not deletions.** A defect the
  plan needs human input on goes to the initiative rulings log via
  `exec-ruling "$PLAN" initiative …` and the summary row stays `audited`
  until answered — or the human waives it (below).

## The summary — `summary.md`

`exec-plan-regression PLAN init` seeds it; you fill the table. One row
per plan:

| Plan | Status | Audit | Repairs | Notes |
|---|---|---|---|---|
| INIT-0004-P01 | clean | regression-P01.md r2 | fix-P01.md r1 | 56 defects → 0 |
| INIT-0004-P02 | waived | regression-P02.md r1 | — | human waived low-severity DTO naming |

`Status` vocabulary: `clean` (audit passed or all findings repaired and
re-audited), `audited` (report exists, findings open), `waived` (human
explicitly accepted the open findings — record the waiver as an
initiative ruling too). `draft`/`audited` rows block the gate.

## The gate

`../executor/scripts/exec-plan-regression "$PLAN" check` exits non-zero
unless every plan on disk is `clean` or `waived` with its audit file
present. When it passes:

```bash
../executor/scripts/exec-initiative phase INIT-0004 plan-regression passed "N plans, M defects repaired"
```

Then — and only then — executor-planning's gate fires (the human picks an
execution mode) and `exec-run PLAN start` will accept the run. The gate is
enforced twice: the phase-order machine refuses `execution entered` without
it, and `exec-run start` refuses once planning has passed. A finding
the human waives is recorded twice: `waived` in the summary AND an
initiative ruling via `exec-ruling … initiative …` naming what was
waived and why — a waived defect with no ruling is an undocumented skip.

**Re-entry.** Execution discovering a plan defect that predates the run
(a wrong `Assumes`, a spec drift) re-enters this phase for the affected
plans: amend, re-audit, re-clear — before the dependent task dispatches.

## Hard rules

- Never hand-build artifact paths — `exec-plan-regression` resolves them.
- Never write audit output under `docs/executor/` (thinking store) or
  inside a `Pnn/` workspace (one plan's ledger). The initiative-level
  `plan-regression/` dir is the only legal home.
- Never mark a plan `clean` from a fix log alone — `check` requires the
  audit file; re-audit after repair is what makes the row honest.
- Contract amendments (IFCE/SPEC edits) are rulings: `exec-ruling "$PLAN"
  initiative …` the moment the amendment is made.
- Human waivers are the only path to `waived` — you may recommend, never
  self-grant.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "P01 executed fine already, skip its audit" | Plans are audited against the SET — a clean P01 run does not prove P02's assumptions about it |
| "The defect is small, I'll note it in the plan" | A defect noted but unrepaired is a `audited` row — the gate stays closed until it's repaired or the human waives it |
| "Re-running the audit is expensive" | Re-audit only the repaired plan's changed checks — but run them; the previous report does not expire by wishing |
| "Planning already reviewed each plan" | Per-plan review reads one file; the defects this phase exists for live between files |
