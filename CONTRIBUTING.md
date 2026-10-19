# Contributing to The Executor

Thanks for your interest in improving The Executor. This repository is a
library of agent-readable skill documents plus the Python engine those
skills drive — no build step, no runtime dependency beyond Python 3.11+. The
contributions that matter most are:

1. **Skill edits** — clearer routing, better gates, sharper prompts.
2. **Engine fixes** — the engine in `engine/executor/` is the enforcer of
   every contract the skills describe; a rule stated in prose and not
   enforced in code is a rule that will drift.
3. **Documentation** — anything a reader of this README would find confusing
   or missing.

## Repository layout

| Path | What lives there |
|---|---|
| `engine/executor/` | The engine source: `cli.py`, `engine.py`, `schemas.py`, `paths.py`, `store.py`, `views.py`, `policy.py` |
| `engine/tests/` | The suite, including the tree-walking contract tests |
| `skills/executor/` | Router skill: contract, ID grammar, phase gates |
| `skills/executor/references/` | The normative documents: layout, branches, frontmatter, indexes, safety, test-quality |
| `skills/executor/scripts/executor` | The launcher users run; resolves the engine relative to itself |
| `skills/executor/scripts/lib/executor/` | The shipped engine — a generated mirror of `engine/executor/` |
| `skills/executor-*/` | One skill per lifecycle phase, each with its own `SKILL.md` |
| `scripts/` | `run_tests.py`, `sync_engine.py`, `mutate.py`, the validators |

`skills/executor/references/layout.md` is normative: paths, document types,
and directory names resolve from it. If you move or add a document type,
update it first.

### The bundled engine

The engine ships **inside** the router skill because an installed skill is a
copied directory: `npx skills add` copies `skills/executor/` and nothing
outside it, so an engine kept only at `engine/` would never reach a user.
`skills/executor/scripts/lib/executor/` is that shipped copy.

**Never edit the bundle by hand.** `engine/executor/` is the source; the
bundle is generated from it. After changing the engine:

```bash
python3 scripts/sync_engine.py          # rewrite the bundle
python3 scripts/sync_engine.py --check  # what CI runs
```

A change that edits only one side fails `test_engine_ships_with_skill.py`
and the `--check` CI step, by design — two copies of one package that are
allowed to differ means the repository tests one engine and ships another.

## Getting started

```bash
git clone git@github.com:Atri10/executor.git
cd executor
pip install -r requirements-dev.txt     # coverage, the one dev tool
```

The engine itself has zero third-party dependencies. From a clone it also
runs as a package:

```bash
PYTHONPATH=engine python3 -m executor --version
```

## How changes are reviewed

- **Skills and references are prose with load-bearing behavior.** A reviewer
  reads your change the way an agent would execute it: would a fresh agent
  route correctly? Would a gate still stop the right things?
- **Match the existing voice.** Declarative, imperative sentences; rules
  stated with their reason; no marketing tone.
- **Every diagram is Mermaid**, never ASCII art — `flowchart` for process
  or hierarchy, `sequenceDiagram` for message exchange, `stateDiagram-v2`
  for state. Short labels, labeled edges, several small diagrams over one
  dense one.
- **Behavioral changes to the contract** (ID grammar, gate ordering, store
  layout, branch model) must update `references/layout.md`,
  `references/branches.md`, `references/frontmatter.md`, or
  `references/indexes.md` in the same change, and call out the behavioral
  delta in the PR description.
- **A behavior change needs a test that would fail without it.** The suite
  holds a 100% branch-coverage floor, so an uncovered branch fails CI rather
  than being merged untested.

## Submitting changes

1. Branch from `main`: `git checkout -b feature/<what>` (or `fix/<what>`,
   `docs/<what>`).
2. Make the change in a focused commit. Conventional Commits style:
   `feat(engine): ...`, `fix(skills): ...`, `docs: ...`.
3. Before committing, check the diff for accidental secrets — the engine
   includes a scanner you can borrow for the check:
   `python3 skills/executor/scripts/executor check --secrets`.
4. Open a pull request describing **what behavior changes for an agent** and
   **why**. Link any issue it resolves.

## Reporting issues

- **Bug in a skill or the engine** — open a regular issue with the exact
  skill text or command invocation, what the agent did, and what it should
  have done.
- **Docs unclear or wrong** — same channel; wrong docs are bugs.
- **Security-sensitive disclosure** — do not open a public issue. See
  [SECURITY.md](SECURITY.md).

## CI

Every PR runs these checks; all must pass before merge:

| Check | What it enforces |
|---|---|
| **Engine suite** (macOS, Linux, Windows) | The full suite at a 100% branch-coverage floor, plus `python -m executor --version` on each OS |
| **Bundled-engine sync** | `scripts/sync_engine.py --check`: the shipped copy is byte-identical to `engine/executor/` |
| **Installed-skill smoke** | The skill is copied out of the repo, `PYTHONPATH` is dropped, and the launcher runs — the install path users actually take |
| **Skill validation** | Frontmatter + `Use when` trigger, balanced fences, no duplicate names; every `SKILL.md` carries `## Self-Critique` and `## Verification`; every dispatch role in `references/layout.md` has a registered prompt template carrying the required markers; no `*-prompt.md` exists unregistered; no ASCII-art diagrams |
| **Prompt-injection lint** | Skill markdown is *executed as instruction by agents*; the linter blocks override directives, concealment, exfiltration endpoints, fetch-and-execute, and credential literals |
| **Secret scan** | The engine's own `executor check --secrets` against a fresh initiative, plus gitleaks over full history |

Run them locally before pushing:

```bash
python3 scripts/run_tests.py            # suite + coverage floor
python3 scripts/sync_engine.py --check  # bundle drift
python3 scripts/validate_skills.py      # skill contract
python3 scripts/lint-prompt-injection.py skills/
```

Mutation testing is available for a module whose tests you changed:
`python3 scripts/mutate.py engine/executor/<module>.py`. A surviving mutant
is either a missing assertion or a genuinely equivalent change, and the
latter belongs in `scripts/mutation-allow.json` with its reason.

The injection linter is heuristic and errs toward false positives — a
flagged line is a human-review prompt in the PR diff, not an accusation.
If your skill legitimately discusses these patterns (as this project's
anti-drift tables do), add the surrounding forbidding context the linter
recognizes, or tighten the pattern in `scripts/lint-prompt-injection.py`
in the same PR.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE) that covers the repository.
