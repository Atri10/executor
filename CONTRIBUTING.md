# Contributing to The Executor

Thanks for your interest in improving The Executor. This repository is a
library of agent-readable skill documents plus the shell scripts they call —
no build step, no test framework, no runtime. The contributions that matter
most are:

1. **Skill edits** — clearer routing, better gates, sharper prompts.
2. **Script fixes** — the `skills/executor/scripts/` helpers must keep
   resolving paths from `skills/executor/references/layout.md`, never
   inventing locations.
3. **Documentation** — anything a reader of this README would find confusing
   or missing.

## Repository layout

| Path | What lives there |
|---|---|
| `skills/executor/` | Router skill: contract, ID grammar, phase gates |
| `skills/executor/references/` | The normative documents: layout, frontmatter, indexes, safety |
| `skills/executor/scripts/` | Executable helpers (`exec-id`, `exec-workspace`, `exec-scan-secrets`, …) |
| `skills/executor-*/` | One skill per lifecycle phase, each with its own `SKILL.md` |
| `docs/` | Documentation for using The Executor itself |

`skills/executor/references/layout.md` is normative: paths, document types,
and directory names resolve from it. If you move or add a document type,
update it first.

## Getting started

```bash
git clone git@github.com:Atri10/executor.git
cd executor
```

That's the whole setup — the skills are plain Markdown and the scripts are
POSIX-ish bash with no dependencies beyond `git` and `find`.

## How changes are reviewed

- **Skills and references are prose with load-bearing behavior.** A reviewer
  reads your change the way an agent would execute it: would a fresh agent
  route correctly? Would a gate still stop the right things?
- **Match the existing voice.** Declarative, imperative sentences; rules
  stated with their reason; no marketing tone.
- **Every diagram is Mermaid** with the dark-theme init line used elsewhere
  in the repo, never ASCII art.
- **Behavioral changes to the contract** (ID grammar, gate ordering, store
  layout) must update `references/layout.md`, `references/frontmatter.md`, or
  `references/indexes.md` in the same change, and call out the behavioral
  delta in the PR description.

## Submitting changes

1. Branch from `main`: `git checkout -b feature/<what>` (or `fix/<what>`,
   `docs/<what>`).
2. Make the change in a focused commit. Conventional Commits style:
   `feat(skills): ...`, `fix(scripts): ...`, `docs: ...`.
3. Before committing, check the diff for accidental secrets — this repo
   includes a scanner you can borrow for the check:
   `skills/executor/scripts/exec-scan-secrets <paths>`.
4. Open a pull request describing **what behavior changes for an agent** and
   **why**. Link any issue it resolves.

## Reporting issues

- **Bug in a skill or script** — open a regular issue with the exact skill
  text or script invocation, what the agent did, and what it should have
  done.
- **Docs unclear or wrong** — same channel; wrong docs are bugs.
- **Security-sensitive disclosure** — do not open a public issue. See
  [SECURITY.md](SECURITY.md).

## CI

Every PR runs five checks; all must pass before merge:

| Check | What it enforces |
|---|---|
| **ShellCheck** (`--severity=warning`) | Every `exec-*` script parses and is warning-clean — these run inside users' agents with git and filesystem access |
| **Prompt-injection lint** | Skill markdown is *executed as instruction by agents*; the linter blocks override directives, concealment, exfiltration endpoints, fetch-and-execute, and credential literals |
| **Skill validation** | Frontmatter present, `name`/`description` set, description carries a "Use when" trigger, fences balanced, no duplicate skill names |
| **Secret scan** | The Executor's own `exec-scan-secrets` over the repo, plus gitleaks over full history |
| **Script smoke** | Usage paths work; the plan-lint and run-audit gates actually fire on known violations |

Run all of them locally before pushing:

```bash
shellcheck --severity=warning skills/executor/scripts/exec-* skills/executor/scripts/_exec-lib.sh
python3 scripts/lint-prompt-injection.py skills/
bash scripts/validate-skills.sh skills
bash skills/executor/scripts/exec-scan-secrets .
```

The injection linter is heuristic and errs toward false positives — a
flagged line is a human-review prompt in the PR diff, not an accusation.
If your skill legitimately discusses these patterns (as this project's
anti-drift tables do), add the surrounding forbidding context the linter
recognizes, or tighten the pattern in `scripts/lint-prompt-injection.py`
in the same PR.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE) that covers the repository.
