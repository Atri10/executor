---
name: executor-critique
description: Audit an initiative's authored artifacts against each other, repair what fails, and clear — or refuse to clear — the phase that produced them. Use when `executor next` emits a `DISPATCH` with `role: "audit"` or `role: "repair"`, when a phase's documents need independent judgment before the gate opens, or when a component's critique is not clear. One contract, one engine loop, every component.
---

# Critique — the gate every authoring phase passes through

## Why this exists

Before this discipline existed, two of eleven phases could reject a bad
deliverable. Plan regression and task review dispatched independent
auditors; the other nine refused on file existence, on a count, or on a
human nod. Architecture and specification ran genuinely adversarial
self-critiques — and one agent grading its own work is not review.

That gap had a concrete cost. **Upstream drift was structurally
undetectable.** An implementation that satisfied every `R-nn` and every
`C-nn` while violating the ARCH — adapters importing each other, an ORM
row crossing into policy, a seam renamed from the IFCE — passed every
gate in the system. There was no seat at which it could be caught after
planning.

This skill is that seat. In v2 it is not a separate stage: the engine
runs the loop itself. For each artifact a phase produces, `executor
next` dispatches an **auditor**, routes `FAIL` verdicts to a **repair**
dispatch, and re-dispatches a fresh audit until the artifact clears, the
round cap `max_audit_rounds` forces an `ESCALATE`, or the phase gate
opens. The human sees the result at the `GATE`; the audits and repairs
in between are journaled payloads, not conversations.

## The shape

```text
DISPATCH audit/<artifact> R1  ->  DISPATCH repair/<artifact> R1
   ->  DISPATCH audit/<artifact> R2  ->  ...  ->  cleared | ESCALATE
```

One auditor per artifact, fed the **whole phase set** — the defects this
stage exists for live *between* documents, so an auditor that reads one
file cannot see them. Repairs re-draft the artifact at the same round
with the open findings in `context.findings`. The re-auditor is always
fresh: the engine names a new `dispatch_id` and `round`, and the fold
never credits an artifact with auditing itself.

**Rounds are capped by policy, then the human.** `max_audit_rounds` per
target. An artifact that still fails at the cap does not loop — `next`
emits `ESCALATE` and the open findings go to the human, not to a fourth
repair.

## The contract

1. **One audit per artifact, judged against the whole set.** The set is
   what makes seams visible; `context` names the artifact, the auditor
   reads its siblings anyway.
2. **The checklist is fixed, numbered, and ordered cheap → expensive**,
   so contract-breaking defects surface before polish. Every catalog row
   produces a finding or is named clean — a check with no output did not
   run.
3. **Severity is a consequence scale, never a fix-difficulty scale.** A
   one-word fix to a drifted name is still `critical`.
   - `critical` — the next phase fails, or builds the wrong thing
   - `important` — likely rework, or a seam mismatch caught late
   - `minor` — clarity only
   - `info` — observation, no action needed
   `verdict: PASS` means **zero critical and zero important** among the
   findings you report. The fold trusts your verdict — a `PASS` beside
   findings you listed as open is a lie in the journal, not a gray area.
4. **Findings carry stable ids across rounds** (`F01`, `F02`, …) and a
   `status`: `open`, `fixed`, `waived`, `routed`. An auditor that
   re-finds a repaired defect reuses its id — a new id for the same
   defect erases the history that proves the loop is converging.
5. **Contracts are a finding class the repairer may not touch.** A
   defect in an upstream document is marked `routed` and goes back to a
   `ruling` via `executor decide`, never papered over downstream.
6. **A waiver is the human's alone.** An auditor may mark a finding
   `waived` as a *recommendation* and say why in `claim`/`evidence`; the
   waiver lands only when the human's `gate_decision` is `waived` with a
   `note`, or a `ruling` names it. A waiver nobody granted is an open
   finding wearing another status.
7. **Weakening is not addressing.** A finding closed by deleting a
   requirement, dropping a coverage claim, or loosening an exact value
   is still open — and the weakening is itself a new `critical` finding.

## The components

Every authoring phase audits its artifacts before its gate opens. The
`audit` dispatch's `entity` is the artifact id; the catalog below is
keyed by phase.

| Phase | Targets | Catalog |
|---|---|---|
| intake | charter | charter |
| discovery | research, options | discovery |
| architecture | architecture, adr, ifce | architecture |
| design | design | design |
| specification | spec, risk, vrfy | specification |
| planning / plan_regression | every plan | plans |
| execution | plan (whole-branch) | code |
| verification | vrfy + evidence | verification |
| handoff | the run itself | handoff |

`plans` audits each `PLAN` artifact — the plan-set contract lives in
`executor-plan-regression`, and one audit contract covers it rather
than two gates that could disagree.

## The catalogs

Each catalog is a fixed, numbered list. The auditor reads the section
matching the phase its target was authored in.

### `charter`

1. Goals are stated as outcomes, not as tasks.
2. Non-goals are explicit and are actually non-goals.
3. Every success criterion is checkable without reading the implementation.
4. Scope boundary holds: nothing in the initiative is outside it.
5. The problem statement would let a stranger recognize it.

### `discovery`

1. **Does the options document honestly represent the research?** Every
   option traceable to a cited finding; a finding that supports no
   option is a finding the document is hiding.
2. **Are the axes fair to every option?** An axis answered only for the
   recommended option is rigging, and rigging is `critical`.
3. Are the non-recommended options straw men? Name the strongest
   version of each.
4. Does the recommendation state what would falsify it?
5. Does anything cite prior art that the research never looked at?

### `architecture`

1. **Are the boundaries enforceable?** A boundary you cannot enforce is
   a diagram. Name the mechanism that holds it.
2. Does every `ifce` cited by a plan exist, and does every quoted
   literal match byte-for-byte?
3. Does each `adr` carry a falsifier specific enough to be wrong? "This
   is wrong if requirements change" is not a falsifier.
4. Is each decision labelled with its reversibility cost?
5. Do the components compose — hand two readers who will never read
   each other's work the halves, and ask whether they could each build
   theirs?

### `design`

1. Does the design state its state machine, or declare that it has
   none?
2. Are ordering and concurrency decisions explicit, including the ones
   that look safe because they are single-threaded today?
3. Are edge cases enumerated, or is there a stated reason none exist?
4. Are the testing seams named — the places a test can reach in?
5. Does the file decomposition avoid two components writing one file?

### `specification`

1. **Is every requirement verifiable?** A requirement no `vrfy`
   criterion can prove is a wish.
2. Does every requirement trace to a goal in the charter, and every
   goal to at least one requirement?
3. **Does any requirement contradict an active `adr`?** A contradiction
   is a defect in one of them, and it is the one defect that survives
   every downstream gate unless it is caught here.
4. Is there placeholder prose — "handle edge cases", "add appropriate
   error handling"? Declared `critical`, and blocking nothing
   mechanically until an auditor says so.
5. Does every risk have a mitigation that is a plan, not an intention?
6. Does the `vrfy` criteria count match the `spec`'s requirement count?

### `plans`

The plan-set contract: spec coverage, cross-plan `depends_on` closure,
interface fidelity, ordering, constraint propagation, file-map
collisions, vocabulary consistency, skipped-phase honesty. See
`executor-plan-regression/SKILL.md`.

### `code`

This is the **upstream-drift seat** — the checks that had nowhere to
live. The target is the plan's merged diff, reviewed against the
tracked store:

1. **Does the branch obey the ARCH's boundaries?** The architecture
   artifacts are a required input here, not an optional one. Adapters
   importing each other, a domain type crossing into a transport type,
   a dependency pointing the wrong way: each is `critical`.
2. **Do the `ifce` signatures match the implementation
   byte-for-byte?** A renamed seam is `critical`; a seam that drifted
   in meaning is worse.
3. Is the `dsgn` still true of the code, or did implementation quietly
   replace a design decision?
4. Do the `adr`s still describe what was built?
5. Plus the whole-branch coherence `executor-review` already audits.

### `verification`

1. Does every `vrfy` criterion carry an `evidence` payload that was
   **observed**, not expected?
2. Did any evidence run change code, tests, or config to get green?
   Then the criterion was not proven — it was edited.
3. Is every unanswered criterion explained rather than upgraded by
   inference?
4. Does any `evidence` cite a `state_commit` that predates the code it
   claims to describe?

### `handoff`

1. Every executed plan's tasks all reached a verdict — a plan whose
   merge journaled with no review is `critical`.
2. `executor status` shows no task `dispatched` for a plan that
   finished — a stale dispatch is a dead worker nobody buried.
3. No placeholder survived into the `vrfy` outcomes.
4. Every superseded `adr` is linked from its successor.
5. `executor check --secrets` is clean and the suite is green **on the
   current tree**.

## What this skill never does

- **Never lets the controller audit its own work.** If you are the
  controller and an artifact is not clear, the move is to let the
  dispatch run or present to the human — never to clear the phase by
  another route.
- **Never marks an artifact clean from a repair log alone.** The fold
  requires the next `audit` payload's `verdict: PASS`; a repair's own
  summary does not clear anything.
- **Never audits inline.** The auditor is a `DISPATCH`; its output is
  an `audit` payload. A verdict the controller formed is a verdict
  nobody independent formed.

## Self-Critique

Before you report the stage clear, check each of these yourself:

1. **Did every catalog row produce a finding or a named-clean?** A
   check with no output did not run.
2. **Did I re-audit, or did I read the repair payload and believe it?**
   Verify a `fixed` claim against the artifact text, not the summary.
3. **Did any repair weaken the artifact to pass?** Read the new
   `sections`/`requirements` for deleted requirements, dropped claims,
   loosened values. Each is a new `critical`.
4. **Is every finding traceable to a quote?** A finding you cannot
   quote is not a finding.
5. **Did I mark a finding `waived` the human never granted?** That is
   not a waiver.
6. **Does `executor status` show the artifact cleared, or merely
   quiet?** Quiet is a dead loop, not a clean one.

## Verification

```bash
executor status        # artifact rows: cleared, not under_audit
executor check         # journal refolds clean; no dangling edges
```

`executor status` is the gate view: every artifact in the phase either
`cleared` or named in the `GATE` presentation with its open findings.
A critique you did not check is a critique you did not clear.
