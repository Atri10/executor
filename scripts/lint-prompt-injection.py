#!/usr/bin/env python3
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
    (r"(?i)\b(curl|wget)\b[^|\n]{0,200}\b(-d|--data|--upload-file|-T|--form)\b",
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
# triage quickly.
FENCE = re.compile(r"^(```|~~~)", re.M)


def fence_ranges(text: str):
    ranges = []
    lines = text.splitlines()
    inside = None
    start = 0
    for i, line in enumerate(lines, 1):
        if re.match(r"^\s*(```|~~~)", line):
            if inside is None:
                inside = True
                start = i
            else:
                inside = None
                ranges.append((start, i))
    if inside is not None:  # unterminated fence
        ranges.append((start, len(lines)))
    return ranges, inside is not None


def in_ranges(n, ranges):
    return any(a <= n <= b for a, b in ranges)


FORBID_CONTEXT = re.compile(
    r"(?i)(never|don'?t|do not|without|instead of|rather than|pollute|"
    r"regressions?|guarantee|how you would|fails?|anti-?pattern|rationaliz)")


def lint_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
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
    blocking = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        files = sorted(p.rglob("*.md")) if p.is_dir() else [p]
        for f in files:
            for lineno, sev, name, note, excerpt in lint_file(f):
                marker = "BLOCK" if sev in ("high", "medium") else "note"
                if marker == "BLOCK":
                    blocking += 1
                print(f"{marker} {f}:{lineno} [{name}]({sev}){note}\n    {excerpt}")
    if blocking:
        print(f"\n{blocking} finding(s) require human review in the PR diff", file=sys.stderr)
        return 1
    print("prompt-injection lint: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
