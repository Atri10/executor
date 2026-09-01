# Security Policy

## Scope

This repository ships **documentation and shell scripts**, not a service.
There is nothing here that listens on a network or holds credentials. The
realistic risks are therefore about *content*, not exploits:

1. **Secrets leaking through generated artifacts.** The Executor's whole
   purpose is producing documents that may be committed — charters, specs,
   review diffs, reports. A credential pasted into any of them can reach
   git history.
2. **Prompt-injection through skill text.** Skills are instructions an agent
   executes with tool access. A malicious contribution could try to steer an
   agent toward destructive or exfiltrating actions.
3. **Script behavior.** The helpers in `skills/executor/scripts/` run with
   the user's permissions and touch only paths derived from
   `skills/executor/references/layout.md`.

## Reporting a vulnerability

Do **not** open a public issue for anything above.

Use GitHub's **private vulnerability reporting** on this repository
(Security tab → Report a vulnerability). Include:

- the affected file(s) or skill text,
- the scenario in which the harm occurs,
- a minimal reproduction if the issue is in a script.

You will get an acknowledgment within 7 days. Disclosure is coordinated with
you; we default to crediting reporters in the release notes unless you prefer
otherwise.

## Supported versions

This project distributes a living main branch rather than releases. Security
fixes land on `main` and users update by re-copying `skills/` into their
agent's skill directory. Verify against latest `main` before reporting.

## What the project already does about secret leakage

- `skills/executor/references/safety.md` defines what may never be written
  into an Executor artifact and requires a redacted existence statement
  instead.
- `skills/executor/scripts/exec-scan-secrets` scans both artifact stores
  before handoff and reports file and line **without printing the matched
  value**.
- Runtime tool state (session keys, server-info, logs) is directed outside
  the repository so fresh session tokens can never land in tracked files.

If you find a bypass for the scanner, or a skill that causes agents to write
secrets despite the rules above, that is exactly the kind of report we want.
