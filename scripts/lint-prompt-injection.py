#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Lint Executor skill files for prompt-injection patterns.

The payload of this repository is prompts: every SKILL.md, template, and
reference file is read by an AI agent as instruction. A malicious or
compromised contribution can therefore attack every agent that later loads
the skill — the classic supply-chain injection vector. This linter flags
the structural shapes of those attacks. It is heuristic (pattern-matching,
not understanding), so it errs toward false positives that a human
reviews in the PR diff — never false negatives waved through.

Exit: 0 clean, 1 findings, 2 usage error.
"""

import re
import sys
from pathlib import Path

# Patterns that indicate instruction-injection attempts. Each carries a
# severity and a reason a human can act on.
PATTERNS = [
    # Directives that try to override the agent's rules or identity
    (r"(?i)\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(all\s+)?(previous|prior|above|earlier)\b[^.\n]{0,30}\b(instructions?|prompts?|rules?|directions?)\b",
     "high", "override-previous-instructions"),
    (r"(?i)\byou\s+are\s+now\b|\bnew\s+instructions?:\s|\bsystem\s+prompt\s*:\s",
     "high", "identity-replacement"),
    (r"(?i)\bdo\s+not\s+(tell|inform|reveal|report|mention)\b[^.\n]{0,40}\b(user|human|operator)\b",
     "high", "concealment-directive"),
    (r"(?i)\b(don'?t|do\s+not)\s+(run|execute)\s+the\s+(scan|checks?|verification)\b",
     "high", "check-evasion"),
    (r"(?i)\b(skip|bypass|disable)\b[^.\n]{0,30}\b(review|verification|scan|gate)\b",
     "high", "gate-bypass"),
    # Exfiltration shapes: instructing the agent to send data somewhere
    (r"(?i)\b(send|post|upload|exfiltrate|transmit)\b[^.\n]{0,60}\b(api\.github\.com|hooks?\.slack\.com|webhook|\.onion|ngrok|pastebin|requestbin)\b",
     "high", "exfiltration-endpoint"),
    (r"(?i)(curl|wget)[^|\n]{0,120}\|\s*(ba)?sh\b",
     "high", "fetch-and-execute"),
    # Sending local data out: a body read from a file (@file), stdin (@-) or
    # command output ($(...)), a file upload, or a form field read from a
    # file. An inline literal body is API testing, not exfiltration (a secret
    # pasted there is caught by the credential patterns instead). The command
    # name is case-insensitive, its flags are not: wget -t is --tries and curl
    # -D dumps headers. A flag follows whitespace, so no word boundary may be
    # demanded before its dash (a boundary cannot exist between a space and
    # "-", which is why this pattern once matched nothing).
    (r"\b(?i:curl|wget)\b[^|\n]{0,200}(?<=\s)(?:"
     r"(?:-d|--data[\w-]*|--json)\s*[\"']?(?:@|\$\()"
     r"|(?:-T|--upload-file)(?=\s)"
     r"|(?:-F|--form[\w-]*)\s+\S*=@"
     r"|--(?:post|body)-file(?=[\s=]))",
     "medium", "outbound-post"),
    # Credential-shaped content in a prompt file (secret hygiene)
    (r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}\b",
     "high", "github-token-literal"),
    (r"\bAKIA[0-9A-Z]{16}\b",
     "high", "aws-access-key-literal"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
     "high", "private-key-literal"),
    (r"(?i)\b(sk-[A-Za-z0-9]{20,})\b",
     "high", "api-key-literal"),
    # Urgency/social-engineering pressure in instructional voice
    (r"(?i)\b(urgent|immediately|asap|right now)\s*[!:].{0,60}(do|execute|run|delete|push)",
     "medium", "urgency-pressure"),
    # Instructions to modify the harness/other skills from within a skill
    (r"(?i)\b(modify|edit|overwrite|delete)\b[^.\n]{0,40}\b(this\s+skill|other\s+skills?|the\s+harness|system\s+files)\b",
     "medium", "self-modification"),
]

# Fenced code blocks are quoted examples more often than live attacks —
# still scanned, but a finding inside a fence is downgraded so humans can
# triage quickly. A fence is closed only by a marker of the same kind, at
# least as long as the opener, with no text after it, and indented at most
# three spaces past the opener, as Markdown renders it. Honouring any marker
# would let one stray ~~~ inside a ``` block flip the tracker and file the
# real injection that follows as a harmless example; honouring indentation is
# what lets a template quote an indented ``` block inside its own fence.
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")


def fence_ranges(text: str):
    ranges = []
    lines = text.splitlines()
    opener = None
    opener_indent = 0
    start = 0
    for i, line in enumerate(lines, 1):
        m = FENCE.match(line.expandtabs(4))
        if not m:
            continue
        indent, run, rest = len(m.group(1)), m.group(2), m.group(3)
        if opener is None:
            opener, opener_indent, start = run, indent, i
        elif (run[0] == opener[0] and len(run) >= len(opener)
              and not rest.strip() and indent <= opener_indent + 3):
            ranges.append((start, i))
            opener = None
    if opener is not None:  # unterminated fence
        ranges.append((start, len(lines)))
    return ranges, opener is not None


def in_ranges(n, ranges):
    return any(a <= n <= b for a, b in ranges)


FORBID_CONTEXT = re.compile(
    r"(?i)(never|don'?t|do not|without|instead of|rather than|pollute|"
    r"regressions?|guarantee|how you would|fails?|anti-?pattern|rationaliz)")


def lint_file(path: Path):
    # newline="" keeps \r\n as written: in text mode Python translates it to
    # \n, and while splitlines() agrees either way, the *translated* text is
    # then scanned for patterns that end at a line boundary. On Windows a file
    # written with CRLF would otherwise be linted as if its lines were LF,
    # and line numbers in the findings could drift.
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()
    ranges, unbalanced = fence_ranges(text)
    findings = []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        context = " ".join(lines[max(0, lineno - 3):lineno])  # current line + 2 before
        for pattern, severity, name in PATTERNS:
            m = re.search(pattern, line)
            if m and name == "gate-bypass" and FORBID_CONTEXT.search(context):
                continue  # surrounding text forbids the bypass or runs a failure-mode exercise — guidance, not an attack
            if m:
                sev = severity
                note = ""
                if in_ranges(lineno, ranges):
                    sev = "info"
                    note = " (inside code fence — likely a quoted example; confirm)"
                findings.append((lineno, sev, name, note, line.strip()[:100]))
    if unbalanced:
        findings.append((0, "medium", "unterminated-code-fence", "", "file ends inside a fenced block"))
    return findings


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    missing = [a for a in sys.argv[1:] if not Path(a).exists()]
    if missing:
        for a in missing:
            print(f"error: no such file or directory: {a}", file=sys.stderr)
        return 2
    blocking = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
        for f in files:
            for lineno, sev, name, note, excerpt in lint_file(f):
                marker = "BLOCK" if sev in ("high", "medium") else "note"
                if marker == "BLOCK":
                    blocking += 1
                print(f"{marker} {f.as_posix()}:{lineno} [{name}]"
                      f"({sev}){note}\n    {excerpt}")
    if blocking:
        print(f"\n{blocking} finding(s) require human review in the PR diff", file=sys.stderr)
        return 1
    print("prompt-injection lint: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
