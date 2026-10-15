---
name: executor-architecture
description: Use when `executor next` enters `architecture` or `design` — an approach has been chosen and structure must be decided before a spec exists, when superseding a decision, when a task is blocked on a missing interface, or when declaring that an initiative needs no ADRs or designs.
---

# Architecture & Design

Two phases, one skill. **Architecture** settles what the parts are, what
may depend on what, and what every shared seam looks like exactly.
**Design** settles how one component works inside its boundary.

This is the layer that decides whether the spec has anything to argue
from. A plan built on prose architecture produces tasks whose halves do
not meet.

Read [`../executor/SKILL.md`](../executor/SKILL.md) and its references
before writing a payload. ID grammar, the citation rule, and the pump
contract come from there and are binding.

## Outputs

| Artifact | Kind | Produced when |
|---|---|---|
| Architecture | `arch` (`INIT-NNNN-ARCH-01`) | Every initiative reaching this phase gets exactly one. It may be a single page. |
| Decision | `adr` (`INIT-NNNN-ADR-nn`) | One per decision that had a live alternative and that a future reader could reasonably reverse. |
| Interface | `ifce` (`INIT-NNNN-IFCE-nn`) | One per seam crossed by more than one task or plan. |
| Design | `design` (`INIT-NNNN-DSGN-nn`) | One per component whose internals are not obvious from ARCH plus IFCE. |

Each is an `author` `DISPATCH` — the worker writes the payload to
`respond_to`, `executor ingest` validates and journals it, the
`executor-critique` audit grades it against the whole set.

**No code is written in this phase.** The only code-shaped text produced
is signatures and type declarations inside an `ifce` — those are
contract text, not implementation. Writing implementation here means
the gate has nothing left to reject.

## Preconditions

| Check | If it fails |
|---|---|
| `executor status` shows the charter `cleared` and its intake gate passed | Route to `executor-initiative`. Architecture with no success criteria optimises for nothing. |
| Discovery produced an `options` artifact with a recommendation the human accepted, **or** the discovery gate was `waived` | Stop. Architecture without a chosen approach silently invents the approach, and the human never got to reject it. |
| `executor status` shows `discovery` passed (or waived) | Do not proceed on an unpassed gate. Restructuring after a spec exists invalidates the spec. |

## Procedure

### 1. Ground yourself

`executor status` — then read the `charter` payload (problem, success
criteria, constraints, scope boundaries), the accepted `options`
payload, and any evidence section whose measurements bear on structure.
Everything you write must be traceable to a constraint or criterion in
one of those. A component nobody asked for is the cheapest thing to
delete now and the most expensive later.

### 2. Triage what this initiative warrants

| Signal | Produce |
|---|---|
| More than one component, or one component with an externally visible boundary | `arch` — always |
| A choice was made where another option was genuinely viable | An `adr` for that choice |
| Two tasks (or two plans) will touch opposite sides of one call, schema, event, or file format | An `ifce` for that seam |
| A component has non-obvious internal state, a real algorithm, or contested file decomposition | A `design` for that component |
| One component, one plan, one task, no seam | `arch` only — declare the rest skipped ([Skipping](#skipping-declared)) |

Over-producing is the second failure mode of this phase; the first is
prose where a signature belongs. Neither is fixed by writing more
documents — it is fixed by writing the documents the seams demand and
no others.

### 3. The `arch` payload

The `DISPATCH` for `schema: "arch"` names `INIT-NNNN-ARCH-01`. Its
`sections`: context and forces, component inventory, boundaries, data
flow, failure modes, deployment shape. The `adrs[]` and `ifces[]`
fields carry the inventory — one entry per `adr`/`ifce` artifact, so
the arch is the index a reader lands on.

The **boundaries** section is the load-bearing one. See
[Boundaries](#boundaries-the-rule-that-does-the-work). If you cannot
say which side of a boundary a component sits on, the boundary is
wrong — fix it before continuing, because every later document
inherits it.

### 4. Harvest the decisions into ADRs

Re-read the `arch` sections and mark every sentence of the form "we
use X" or "X owns Y" where something else was possible. Each mark is
either an `adr` artifact or a one-line note in the arch saying no
alternative existed.

One `adr` payload per marked decision — `adrs[]` entries in the arch
name them. Every ADR carries a falsifier and a `cost_if_wrong`. See
[The falsifier rule](#the-falsifier-rule) and
[Reversibility discipline](#reversibility-discipline).

**A decision made in this phase is an `adr`, never a `ruling`.**
Rulings are runtime decisions taken without the human mid-run; in
architecture the human is in the loop and the record is a tracked
artifact.

### 5. An `ifce` for every shared seam

The test: would two implementers who never read each other's task both
have to agree on this name, this type, this error, or this ordering?
Then it is an `ifce` payload, not a paragraph.

`ifces[]` in the arch names each one: `provides`/`consumes` lists, the
exact signatures, exact types, exact error cases, ordering and
lifecycle, `stability` in the section body. See
[Interfaces](#interfaces-the-highest-leverage-document).

### 6. Cross-link through `cites`

Each payload's `cites` names the artifacts it argues from: an `adr`
cites the `arch`; an `ifce` cites the `arch`; a `design` cites the
`arch` and its `ifce`. The fold turns `cites` into edges — a cite to
an artifact that does not exist is a `dangling_ref` rejection, and
`executor check` flags the same as a dangling edge.

**Citation rule, absolute:** no payload inside `INIT-0004` may cite an
ID from another initiative. If your architecture depends on another
initiative's output, state the requirement in your own words and
declare the relationship in the charter.

### 7. Gate on the human

When every dispatched artifact clears its audit, `executor next` emits
`GATE architecture`. Present, in this order and nothing more:

1. The component inventory and the boundary rules, in a sentence each.
2. Each decision as: what we chose, what it costs, what would make it
   wrong, `one-way` or `two-way`.
3. Each interface as: name, stability, who consumes it.
4. What you did **not** produce and why.

**The gate ends your turn** — item 4 above is the last line of your
message. The human answers with a `gate_decision` via `executor
decide`. A spec written against unapproved structure has to be
rewritten, not amended.

### 8. Design phase

`PHASE-ENTER design` then `DISPATCH`es per component that needs one —
`schema: "design"`, one `design` artifact per component. Its
`sections` cover the component's internals; its public surface is not
restated — it points at the `ifce`. Then the same `GATE` discipline:
present and end your turn.

If no component needs one, skip explicitly — never silently: the
human's `gate_decision` carries `decision: "waived"` and the `note`
naming why (single component, internals folded into ARCH-01).

## Boundaries: the rule that does the work

**Dependencies point inward, toward policy.** Business rules and the
interfaces they need sit at the centre. Frameworks, databases,
transports, queues, clocks, filesystems, vendor SDKs, and UI live at
the edge as replaceable details.

| Layer | May depend on | Must never depend on | Why |
|---|---|---|---|
| Policy (entities, use cases) | Other policy, ports it owns | Anything at the edge | Policy that imports a framework type cannot be tested or replaced without it |
| Ports (interfaces) | Policy types only | Concrete adapters | The inner layer owns the interface; the outer layer implements it |
| Adapters (HTTP, DB, CLI, vendor clients) | Ports, policy types | Other adapters | Adapter-to-adapter coupling turns two replaceable details into one unreplaceable pair |
| Composition root | Everything | Nothing depends on it | Concrete wiring belongs in exactly one place, at the outermost edge |

Consequences to state in the `arch`, not assume:

- **Adapters are humble.** A controller, presenter, repository, or
  listener translates formats and calls a use case. Business branching
  inside an adapter is a rule the tests cannot reach.
- **Plain models cross boundaries.** No ORM rows, framework request
  objects, or vendor response types pass into or out of policy —
  otherwise every vendor upgrade is a policy change.
- **A boundary you cannot enforce is a diagram.** Say how each one is
  enforced: package structure, visibility, import lint, build
  constraint, or a narrow API. Name it in the payload.
- **Name the exceptions.** If a boundary is deliberately violated for
  cost reasons, say where, why, and what it will cost to undo. An
  unnamed violation gets copied by the next component.

## The falsifier rule

**An ADR with no falsifier is an opinion with a schema.** Every `adr`
states, in observable terms, what would make this decision wrong —
`cost_if_wrong` plus a falsifier in its sections.

| Weak | Strong |
|---|---|
| "This is wrong if requirements change." | "Wrong if a single tenant exceeds 40 GB — per-cell SQLite stops fitting on one node." |
| "Revisit if it doesn't scale." | "Revisit when p99 placement latency exceeds 200 ms at 10k tenants, measured by the placement benchmark." |
| "Wrong if the team dislikes it." | "Wrong if more than one adapter needs the same escape hatch — that means the port is modelling the wrong thing." |

A falsifier must be checkable by someone who was not in the room, and
it must name the **trigger** that sends a reader back to this document.

## Reversibility discipline

`reversibility: one-way|two-way` in each ADR's sections has teeth.

| | Two-way door | One-way door |
|---|---|---|
| Examples | Internal module layout, logging shape, a library that is behind a port | Public API shape, on-disk format, wire protocol, data model, anything a third party or stored data commits to |
| Scrutiny | Decide fast, one paragraph, one alternative named | At least three options, each with its cost stated, and what you would need to learn to change your mind |
| Failure mode | Deliberating for a day over a decision reversible in an hour | Deciding in an hour something reversible only by a migration |
| Revisit | Freely, when the falsifier fires | Only with a superseding `adr` and a stated migration path |

Never label a one-way door two-way to skip the work — the label is what
a later reader trusts when deciding how hard to think before changing
it.

## Interfaces: the highest-leverage document

**The failure it prevents:** two tasks build incompatible halves of one
seam because the plan described the interface in prose. Task 3 writes
`placeCell(tenant, region)` returning a cell id; Task 5 calls
`place_cell(tenantId)` expecting a result object. Both pass their own
tests. Integration is a rewrite, and nobody is wrong.

An `ifce` payload is what an independent implementer reads to learn
what their neighbours expose. Requirements, all mandatory:

| Requirement | Why |
|---|---|
| Exact signature — name, parameter order, parameter names | A name invented in a brief is a name the neighbour never sees |
| Exact types, including nullability, units, ranges, and encodings | "A timestamp" is four incompatible representations |
| Exact error cases, each with what a caller must do about it | An unlisted error becomes a crash or a swallowed failure, chosen at random by whoever hits it first |
| Ordering and lifecycle — what must be initialised before what, what is idempotent, what may be concurrent, what cancellation means | Two correct implementations can still deadlock or double-apply |
| `stability: draft` \| `stable` \| `frozen` in the section | Tells a consumer whether they may build against it now |
| Named consumers — `consumes` entries | Changing an interface with no consumer list is changing it blind |

**A task blocked by a missing signature is an architecture gap, not a
planning detail.** The fix is to write or amend the `ifce` — never to
let the implementer choose a name, and never to bury the signature in
one task's `goal` where its counterpart cannot read it.

### Stability lifecycle

| Value | Meaning | Changing it |
|---|---|---|
| `draft` | Architecture in progress | Edit freely; nothing depends on it yet |
| `stable` | Gate passed, plans may be written against it | Update every named consumer in the same redraft |
| `frozen` | A plan is executing against it | Do **not** edit. A new `ifce` supersedes it, and a `ruling` on the running plan records the switch |

Freezing at execution start is what lets an implementer trust the
contract they were handed. An interface that changes under a running
plan invalidates the dispatches already minted.

## Designs

A `design` payload covers exactly one component: responsibilities, what
it explicitly does not do, its state, its algorithms, its edge cases,
its testing seams, and its file decomposition.

### Testing seams

State, for the component: what is injected (clock, store, transport,
random source), what fakes exist, and what must be exercised for real.
Core behaviour must be testable without the real framework, database,
network, vendor, or hardware — that requirement is what a seam is for.

### File decomposition

- **One clear responsibility per file**, with a well-defined interface.
- **Files that change together live together. Split by responsibility,
  not by technical layer.** A layer-sliced tree makes one conceptual
  change edit five directories.
- **Prefer smaller, focused files over large ones that do too much.**
- **In existing codebases, follow established patterns.** If a file you
  must modify has grown unwieldy, propose the split here so planning
  can task it deliberately.

Decomposition decided in a design is decided once, with the whole
component in view. Decided in a plan, it is decided per task — which is
how two tasks create two files with the same responsibility.

## Skipping, declared

| Output | May be skipped when | Never skipped when |
|---|---|---|
| `adr` | No choice had a live alternative — say so in one line in the `arch` | Any option was viable and was rejected |
| `design` | Internals are obvious from `arch` plus `ifce`, or the component is a single function | State, ordering, or algorithms are non-trivial |
| `ifce` | The whole initiative is one component with no seam crossed by more than one task | Two tasks or two plans touch the same call, schema, event, or format |
| `arch` | Only by explicit human waiver, with the structure then carried by the `spec` | Default — it can be one page, but it exists |

The engine expects the artifacts a phase declares; an artifact the
initiative legitimately does not need is recorded as a `ruling` naming
the skip and its reason — silence is the failure, not the absence.

## Supersession

**Correcting a decision means a new `adr` that supersedes the old
one** — never editing the old payload to hide the reasoning: the
superseded reasoning is why the new decision is defensible. The fold
keeps the latest payload per artifact; supersession is recorded in the
new artifact's sections (`supersedes: INIT-NNNN-ADR-03`, what changed,
the old falsifier firing) and the old artifact is redrafted with its
status marked superseded — its body otherwise untouched.

The same rule governs `arch`, `ifce`, and `design`. A `frozen`
interface is especially strict: supersede it, never edit it, because
its consumers were written against the text they read.

## Self-Critique

Run this yourself before the gate — an adversarial pass, not a
dispatch.

**The mismatch test.** Pick any two components on opposite sides of a
seam. Hand their sections to two readers who will never read each
other's. Could they produce halves that fail to connect — different
names, different types, different error contracts, different ordering
assumptions? If yes, name what is missing and write it into the `ifce`.
This is the acceptance test for the whole phase.

- [ ] Every component has a one-line responsibility, and no component
      has two.
- [ ] Every dependency in the data-flow section is permitted by the
      boundary table; every deliberate exception is named with its
      cost.
- [ ] Every boundary states how it is enforced, not just that it
      exists.
- [ ] Every "we use X" has an `adr`, or a one-line note that no
      alternative existed.
- [ ] Every `adr` has an observable falsifier with a revisit trigger,
      and a `reversibility` that matches the scrutiny actually applied.
- [ ] Every `ifce` operation has exact types, exact error cases with
      caller responses, and stated ordering or lifecycle requirements.
- [ ] Every `design` names its testing seams and its file
      decomposition.
- [ ] Every `cites` entry starts with this initiative's ID.
- [ ] No credential, token, key, connection string, or personal data
      appears anywhere — auth and config are described as a redacted
      existence statement plus a safe pointer, per
      [`../executor/references/safety.md`](../executor/references/safety.md).
- [ ] Every one-way-door decision in the design session's dossier has
      an `adr`, and every `adr`'s chosen option matches the session's
      decided concept — or supersedes it with a stated reason.
- [ ] The strongest rejected concept from the design session appears in
      the ADR's alternatives, argued honestly, not as a strawman.

## Verification

Run these in this session and cite their output at the gate:

1. `executor status` — every `arch`/`adr`/`ifce`/`design` artifact
   `cleared`, or each open finding named for the gate.
2. `executor check` — `cites` resolve, no dangling edges, the `arch`
   carries a `mermaid` block in its data-flow section.
3. For each `ifce`: count its `provides` entries against the operations
   its sections specify with exact types and error cases — equal.
4. `executor check --secrets` — exit 0.

## Handoff to specification

`executor-spec` reads your output as the contract it argues from: the
`arch` for structure and boundaries, the `adr` artifacts for what is
already decided (and therefore not up for debate in the spec), the
`ifce` artifacts for exact surfaces, the `design` artifacts for
internals. A spec requirement that contradicts an active `adr` is a
defect in one of them — resolve it by superseding the `adr`, not by
quietly specifying around it.

## Common rationalizations

| Excuse | Reality |
|---|---|
| "The interface is obvious from the task description" | Then write it down in one minute. Obvious-to-you is how `placeCell` meets `place_cell`. |
| "I'll add the falsifier later" | Later you no longer remember what would have changed your mind, which is the only part with future value. |
| "It's reversible, so it doesn't need an ADR" | Two-way doors get short `adr`s, not no `adr`s. The record is what stops the same debate reopening monthly. |
| "I'll fix the old ADR so it reads correctly" | You have deleted the reasoning that justifies the new decision. New `adr`, `supersedes` in its sections, old body untouched. |
| "This initiative is small, no architecture needed" | Then the `arch` is one page. Skipping is a `waived` decision with a note, never an absence. |
| "The implementer can pick the signature" | The implementer cannot see the neighbour who calls it. That is the definition of an architecture gap. |
| "I'll record this as a ruling" | Rulings are runtime decisions mid-run. In architecture the human is present: it is an `adr`. |
| "I'll draw the boundaries and enforce them in review" | Review is not enforcement. Name the package rule, visibility, or lint that makes the violation fail. |
