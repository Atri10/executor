---
name: executor-plan-regression
description: Use when plans are all drafted and `executor next` enters `plan_regression` — the engine audits the whole plan set for cross-plan consistency, spec coverage, interface fidelity, and contract drift, repairs what it finds, and gates execution on the result.
---

# Executor — Plan Regression

> **Engine.** `executor <verb>` means
> `python3 <skills-dir>/executor/scripts/executor <verb>`; the engine ships
> inside the router skill, so nothing is on `PATH`.

The phase between planning and execution that the plan set earns by
surviving one adversarial read as a *set*. Every per-plan check that
already exists — the planning self-review — reads ONE plan. This phase
reads all of them against each other and against the contracts they
claim to satisfy, because the defects that actually ship are seams: an
`Assumes` section promising a signature the predecessor plan never
produces, a spec requirement no plan's `Covers:` claims, two plans both
provisioning the same queue with different shapes.

This phase runs after planning has drafted every plan and **before**
the human picks an execution mode — defects found here repair cheaply;
the same defect found during execution costs a fix loop per dependent
task. In v2 the engine runs the loop: `executor next` dispatches an
`audit` per plan, routes `FAIL` verdicts to a `repair` dispatch that
re-drafts the plan, and re-dispatches a fresh audit until every plan is
`cleared`, the `max_audit_rounds` cap fires an `ESCALATE`, or the phase
`GATE` opens.

## When to Use

- `executor-planning` has finished drafting the plan set and `next`
  emits `PHASE-ENTER plan_regression`.
- When a plan set changes mid-initiative — a plan rewritten, a new plan
  added, a spec amended after plans were locked — the affected plan is
  audited again: the fold keys critiques per target, so a re-drafted
  plan goes back through the loop.
- During execution, if a dispatched worker surfaces a plan defect that
  predates the run (a wrong `Assumes`, spec drift), the plan is
  re-entered here — amend, re-audit, re-clear before the dependent task
  dispatches.

## Ownership Boundary

The `repair` dispatch redrafts **plan payloads**. Findings that live in
the spec or an interface contract get `status: "routed"` — the
controller amends THAT document and records the amendment as a
`ruling` via `executor decide`; never a plan edit that papers over a
contract defect. The repairer never writes implementation code.

## Inputs

| Need | From |
|---|---|
| The plan set | `plans/<PLAN>/plan.json` in the tracked store — the journal's `plan` payloads |
| The requirements | the `spec` artifact's `requirements` each plan cites |
| The contracts | every `ifce` artifact the plans cite |
| Global constraints | the spec's `constraints`, plus each plan's `accepts` |
| Prior verdicts | the journal — `executor status` shows each plan's critique row |

## The Round Loop

Three roles, each an engine dispatch — never one agent grading its own
work:

| Engine role | Writes | Briefing |
|---|---|---|
| `audit` round 1 | an `audit` payload (`verdict`, `findings`) | [plan-auditor-prompt.md](plan-auditor-prompt.md) |
| `repair` | a redrafted `plan` payload at the same round | [plan-repairer-prompt.md](plan-repairer-prompt.md) |
| `audit` round 2+ | an `audit` payload verdicting every prior finding | [plan-reauditor-prompt.md](plan-reauditor-prompt.md) |

```mermaid
sequenceDiagram
    participant E as Engine
    participant A as Audit worker
    participant R as Repair worker
    participant Q as Re-audit worker
    E->>A: DISPATCH audit/PLAN — plan set, spec, IFCEs in context
    A-->>E: audit payload — verdict FAIL + findings
    E->>E: routed findings become rulings; contract source amended
    E->>R: DISPATCH repair/PLAN — open findings in context
    R-->>E: redrafted plan payload
    E->>Q: DISPATCH audit/PLAN round+1 — fresh worker
    Q-->>E: audit payload — PASS clears, FAIL loops
    E->>E: round cap reached -> ESCALATE to the human
```

- **One auditor per plan, all fed the whole set** — the cross-plan
  checks are cross-plan by definition. Audits of different plans run in
  parallel dispatches; a repair and the audit that grades it never do.
- **Rounds are minted per target by the engine.** A re-audit echoes the
  round the dispatch carried; a payload claiming another round is
  rejected (`round_mismatch`).
- **Round cap is `max_audit_rounds` per plan.** At the cap, `next`
  emits `ESCALATE` with the still-open findings: take them to the human
  for a ruling, a spec change, or a recorded waiver. The engine will
  not mint a fourth round, and you will not improvise one.

## The Audit — per plan per round, one `audit` payload

The auditor writes `verdict: PASS | FAIL` and `findings`. `PASS` means
zero `critical` and zero `important` open; the fold keeps the critique
`fail` until a `PASS` lands, so a repairer's summary never clears
anything.

Walk these checks **in this order** — each class cheap to verify, and
the order surfaces contract-breaking defects before polish ones:

1. **Spec coverage.** Union every plan's `Covers:` lines and
   `implements:` pointers; diff against the spec's `R<nn>` requirement
   set. A requirement with no claiming plan is `critical`. A `Covers:`
   entry naming a requirement that does not exist is `critical` (the
   author split by memory, not by the spec).
2. **Cross-plan Assumes/Produces closure.** Every signature, type, file
   path, topic name, or env var a later plan's `Assumes` (or its tasks'
   `Consumes:`) names must resolve to a `Produces:` in an earlier plan
   or to an `ifce` that exists. Unresolved → `critical`.
3. **Interface fidelity.** Every `ifce` a plan cites must exist, and
   every literal the plan quotes (field names, signatures, enum values,
   topic literals) must match the contract byte-for-byte in the parts
   that matter. Drifted literals → `critical`; paraphrase where
   exactness was required → `important`.
4. **Ordering & dependency map.** The `depends_on` graph must be
   acyclic and consistent with `Assumes` direction (a plan that assumes
   P03's output cannot precede it). Task-level `depends_on` inside one
   plan must not name another plan's tasks. Broken order → `critical`;
   a cycle → `critical`.
5. **Constraint propagation.** Every global constraint the spec
   declares (`C<nn>`) must either be restated in each plan's binding
   block or be provably scoped out by the constraint's own wording. A
   constraint binding tasks that never see it → `important`.
6. **File-map collisions.** Two tasks in different plans writing the
   same file is legal only when `depends_on` makes the ordering
   explicit; silent collision → `important`.
7. **Vocabulary consistency.** Same concept, two names across plans
   (queue `x.dlq` vs `x-dead-letter`) → `important`: naming drift is
   how two plans provision incompatible halves of one seam.
8. **Task contract completeness.** Every task carries `title`, `goal`,
   `files`, `accepts`, and `depends_on` — the schema enforces their
   presence, but not their content. A task whose `accepts` a fresh
   implementer cannot verify (`"works correctly"`, no observable
   outcome) is `critical`: nobody can finish a task its contract does
   not describe.
9. **Skipped-phase honesty.** If the initiative skipped architecture or
   spec, verify the plan does not cite contracts that were never
   written — a cite to a missing artifact is `critical`, and
   `executor check` flags it as a dangling edge too.

A single-plan set still gets the audit: coverage against its spec, the
seams to its `ifce` artifacts, and task contracts all apply.

## Repair — the redrafted `plan` payload

Before dispatching repair, sort the findings:

- **`routed` findings are the controller's.** Amend the SPEC or IFCE at
  its source, record the amendment as a `ruling` via `executor decide`,
  and let the fold see it — the re-auditor reads the amended contract.
  Never adapt a plan around a broken contract.
- **`cross-artifact` findings go to the side that is wrong.** Decide
  which plan owns the fix before the dispatch; one finding, one
  repairer.
- **`component` findings go to that plan's repair dispatch.**

The repairer re-drafts the whole `plan` payload — the un-finding'd
parts carry over unchanged; a repair is a redraft, not a rewrite.
Findings it cannot own stay `open`; the next audit grades the result.
A finding that needs human input is an `ASK` — the controller presents
it, and the human's `ruling` answers it.

## The gate

When every plan's critique row is `clean`, `executor next` emits
`GATE` for `plan_regression` — this is also where the human picks the
execution mode. Present `executor status`: the plans, their rounds,
any waived findings, and the mode question. The human answers with:

```bash
executor decide - <<'JSON'
{"kind": "gate_decision", "v": "v1", "phase": "plan_regression",
 "decision": "approved", "by": "human",
 "note": "3 plans clean; execution mode: subagent-driven"}
JSON
```

A waived defect is recorded twice: `decision: "waived"` in the
`gate_decision` AND a `ruling` naming what was waived and why — a
waiver with no ruling is an undocumented skip, and the auditor's
`waived` statuses are recommendations, never grants.

**Re-entry.** Execution discovering a plan defect that predates the
run re-enters the audit loop for the affected plans before the
dependent task dispatches — the fold has no memory of "already passed"
for a target whose artifact was redrafted.

## Hard rules

- Never hand-build dispatch paths — `respond_to` comes from the
  `DISPATCH` action.
- Never mark a plan clean from a repair payload alone — the fold needs
  the next `audit` verdict `PASS`; a fresh audit is what makes the row
  honest.
- Never let a repairer audit its own repair, and never dispatch a role
  without its briefing's placeholders filled.
- Contract amendments (IFCE/SPEC edits) are `ruling` payloads the
  moment the amendment is made.
- Human waivers are the only path to `waived` — you may recommend,
  never self-grant.

## Self-Critique

Before presenting the gate, run this against `executor status` and
every latest audit, and fix what it catches:

1. **Does every plan have a critique row**, and is every row at its
   latest round? A plan stuck at round 1 while a repair landed is a
   stale audit.
2. **Was every repair graded by a fresh auditor?** A `repair` dispatch
   with no following `audit` means a clean claim with no re-audit.
3. **Did any repair weaken the plan to pass** — a deleted requirement,
   a dropped `Covers:` line, a loosened value? Read the redrafted
   payload's `tasks`; each one is a new `critical`.
4. **Was every `routed` finding applied to the contract** and journaled
   as a `ruling` — not repaired inside a plan?
5. **Is every waived finding backed by the human's words** in a
   `gate_decision` or `ruling`? A waiver you recommended but they did
   not state is not one.
6. **Did any plan hit `max_audit_rounds`?** Then the human decides —
   the `ESCALATE` action is the presentation, not a fourth round.
7. **Did the set change after its audit** — a plan re-drafted or its
   spec amended — without a re-audit?

## Verification

Run these in this session and cite their output when presenting the
gate:

1. `executor status` — every plan row `cleared`, or each open finding
   named for the human.
2. `executor check` — journal refolds clean; no dangling `cites` edges;
   the naming grammar holds on every file.
3. `executor check --secrets` — exit 0; the stores may be committed.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "P01 executed fine already, skip its audit" | Plans are audited against the SET — a clean P01 run does not prove P02's assumptions about it |
| "The defect is small, I'll note it in the plan" | A defect noted but unrepaired keeps the critique `fail` — the gate stays closed until it is repaired or the human waives it |
| "Re-running the audit is expensive" | Re-audit only the repaired plan's changed checks — but run them; the previous report does not expire by wishing |
| "Planning already reviewed each plan" | Per-plan review reads one file; the defects this phase exists for live between files |
