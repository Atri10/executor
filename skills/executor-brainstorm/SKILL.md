---
name: executor-brainstorm
description: Use when an initiative phase surfaces a genuinely open design question, competing approaches, or unknowns the current contract does not resolve — runs a recorded divergent ideation session (text or visual), converges on options the downstream phase can pick from, and files the session in the initiative's brainstorm store.
---

# Executor — Brainstorm

The ideation skill. Other skills *converge* — specs fix requirements,
plans fix tasks, verdicts fix judgments. This one diverges: it widens the
option space until the choice is real, then hands a converged candidate
set back to whatever phase called it. A brainstorm that produces one
option is a discovery report wearing the wrong name.

## When to Use

- **Discovery entry** — the charter leaves open design questions,
  competing approaches, or unknowns a research pass won't settle
  (executor-discovery delegates here).
- **Mid-architecture / mid-spec** — two structures both satisfy the
  constraints and the difference is real (a state-shape call, a sync
  boundary, a storage engine family).
- **Planning forks** — decompositions with genuinely different task
  shapes, where picking wrong means a plan rewrite.
- **On demand** — "let's brainstorm X" always routes here, inside or
  outside an initiative.

Not for: requirements gathering (that's discovery's question loop),
yes/no questions (ask directly), or anything the existing documents
already answer.

## Inputs

| Need | From |
|---|---|
| The question | One sentence, in the session record's `question:` field — if you cannot state it, you are not brainstorming, you are discovering |
| Constraints | Charter/spec/ADR text that bounds the space — brainstorm inside them, not around them |
| Session home | `docs/executor/<initiative>/brainstorm/sessions/<UTC>-<topic>/` for initiative work; a plain markdown file under the same path shape outside one |
| Human availability | Sessions are dialogue by default — the human is the ranking function |

## The session

```bash
date -u +%Y%m%dT%H%M%SZ   # the session directory's timestamp prefix
mkdir -p docs/executor/INIT-0004-*/brainstorm/sessions/<stamp>-<topic>
```

### Diverge first — three moves, all required

1. **Generate ≥3 candidate options** before evaluating any. One option is
   a conclusion, not a brainstorm; two options is a false binary. The
   second-best option exists to make the best one argue for itself — write
   it honestly and show why it loses, never strawman it.
2. **Steal a generation pass.** For each option, name the closest known
   approach (a repo pattern, a published design, a prior initiative) and
   what it borrows or rejects from it. Options with no known ancestor are
   usually reinvention — flag them.
3. **Attack the favorite.** One adversarial pass on the leading option:
   what would make this wrong, what does it cost at 10×, what does the
   rollback look like. If it survives, the pick is earned; if it doesn't,
   you just saved a plan rewrite.

### Converge on the human's pick — or record the tie

Present the surviving options compactly — name, one-line shape, the
tradeoff that decides it — and ask the human to pick (harness ask-tool if
available, else end your turn with the menu). Their pick is recorded in
the session, not decided for them. If they decline to pick, the session
closes with `status: draft` and the open question named — an undecided
session is a real outcome, not a failure to hide.

## Recording — `session.md`

Every session — text or visual — gets one file:

```markdown
---
kind: brainstorm
id: INIT-0004-BRN-01            # or null outside an initiative
initiative: INIT-0004
question: Which placement strategy survives tenant-scale?
status: draft                   # draft while open; active once the human picks; withdrawn if abandoned
created_at: <UTC>
updated_at: <UTC>
decided: null                   # option name, once picked
---

# <question>

## Constraints
<verbatim constraints that bound the space>

## Options
### A — <name>
Shape, one paragraph. Borrows: <what>. Costs: <what breaks at 10×>.
### B — <name>
…
### C — <name>
…

## Adversarial pass
<what attacking the favorite surfaced>

## Outcome
<pick, or the open question the human carries>
```

Plus an INDEX line in the initiative's `INDEX.md` Documents table
(`INIT-0004-BRN-01`, kind `brainstorm`) — sessions are documents, not
scratch.

**Skip is auditable, never silent** (the B1 contract discovery enforces):
if ideation was considered and declined, one INDEX line —
`*Brainstorming considered at <phase> entry: not needed — <reason>.*` —
beats an empty sessions dir that reads as never-considered.

## Visual mode

Same mechanics, rendered. `executor-discovery`'s
[visual-companion.md](../executor-discovery/visual-companion.md) owns the
server: start it, offer it explicitly (consent is a turn-ending message),
walk screens instead of paragraphs. Synthetic data only. The text session
record is the deliverable either way — a visual session that produced no
`session.md` produced nothing reviewable.

## Output handoff

The calling phase gets exactly three things back: the surviving options
ranked, the session path, and `decided:` filled or the open question
named. Discovery turns a decided session into its OPTS comparison;
architecture turns it into an ADR's alternatives; planning turns it into
the winning decomposition. Nobody re-litigates a `decided` session
downstream — supersede it by writing a new one.

## Common Rationalizations

| Excuse | Reality |
|---|---|
| "I already know the answer" | Then it was a decision, not an open question — record it and move on; do not stage a brainstorm |
| "Two options is enough" | A binary choice is the most common way to be wrong — generate the third |
| "The human will pick anyway" | Your adversarial pass is what makes their pick informed — skipping it is presenting a menu you cooked to lose |
| "A one-line skip note is enough" | It is, when it is true and recorded — an empty dir with no note is a gate violation B1 catches |
