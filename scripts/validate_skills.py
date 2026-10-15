#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Validate every skill file's structural contract, cross-platform.

Port of validate-skills.sh — the awk box-drawing check was byte-vs-char
broken on mawk (Linux); in Python the check is character-exact on every OS.

Checks: frontmatter parseable with name/description + "Use when" trigger;
balanced code fences; no HTML comments outside code blocks; unique skill
names; exactly one Self-Critique and one Verification section per SKILL.md;
dispatch registry in references/layout.md matches *-prompt.md on disk;
no box-drawing characters outside inline code spans.

Usage: scripts/validate_skills.py [SKILLS_DIR]   (default: skills)
Exit 0 clean, 1 with FAIL lines on stderr.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BOX = re.compile(r"[├└│┌┐┘┬┴┼╭╮╯╰═║╔╗╚╝]")
CODE_SPAN = re.compile(r"`[^`]*`")
PROMPT_REF = re.compile(r"`([a-z0-9-]+/[a-z0-9-]+-prompt\.md)`")


def _strip_spans(line: str) -> str:
    return CODE_SPAN.sub("", line)


def check_frontmatter(sk: Path, rel: str, fail: list[str]) -> None:
    lines = sk.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        fail.append(f"FAIL {rel}: no frontmatter block")
        return
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail.append(f"FAIL {rel}: unterminated frontmatter")
        return
    fm = "\n".join(lines[1:end])
    if not re.search(r"^name:", fm, re.M):
        fail.append(f"FAIL {rel}: no name: field")
    if not re.search(r"^description:", fm, re.M):
        fail.append(f"FAIL {rel}: no description: field "
                    f"(routing depends on it)")
    if "Use when" not in fm:
        fail.append(f"FAIL {rel}: description lacks a 'Use when' trigger")


def check_fences(f: Path, rel: str, fail: list[str]) -> None:
    n = sum(1 for l in f.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("```"))
    if n % 2:
        fail.append(f"FAIL {rel}: unbalanced code fences ({n})")


def check_html_comments(f: Path, rel: str, fail: list[str]) -> None:
    """HTML comments outside code fences (and outside html/xml/svg code
    samples) split tables and seed invisible guidance into outputs."""
    in_fence, fence_lang = False, ""
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if s.startswith("```"):
            if not in_fence:
                in_fence, fence_lang = True, s[3:].strip().lower()
            else:
                in_fence, fence_lang = False, ""
            continue
        if in_fence and fence_lang in ("html", "xml", "svg"):
            continue  # the comment is the sampled language, not markdown
        # outside a fence, or inside a fence of another language: `<!--`
        if "<!--" in _strip_spans(line):
            fail.append(f"FAIL {rel}:{i}: HTML comment in markdown")


def check_sections(sk: Path, rel: str, fail: list[str]) -> None:
    text = sk.read_text(encoding="utf-8")
    for sec in ("Self-Critique", "Verification"):
        n = len(re.findall(rf"^## {sec}\s*$", text, re.M))
        if n != 1:
            fail.append(f"FAIL {rel}: expected exactly one '## {sec}' "
                        f"section, found {n}")


def check_registry(dir_: Path, fail: list[str]) -> None:
    layout = dir_ / "executor" / "references" / "layout.md"
    if not layout.exists():
        return
    lines = layout.read_text(encoding="utf-8").splitlines()
    registered: set[str] = set()
    on = False
    for l in lines:
        if l.startswith("## Dispatch registry"):
            on = True
            continue
        if on and l.startswith("## "):
            break
        if on and l.startswith("|"):
            registered.update(PROMPT_REF.findall(l))
    if not registered:
        fail.append(f"FAIL {layout}: no prompt templates under "
                    f"## Dispatch registry")
        return
    for rel in sorted(registered):
        p = dir_ / rel
        if not p.exists():
            fail.append(f"FAIL {layout}: registered prompt missing: {rel}")
            continue
        body = p.read_text(encoding="utf-8")
        for token in ("respond_to", "dispatch_id", "kind"):
            if token not in body:
                fail.append(f"FAIL {rel}: prompt lacks dispatch contract "
                            f"token `{token}`")
    # every *-prompt.md on disk must be registered
    on_disk = {str(p.relative_to(dir_))
               for p in dir_.rglob("*-prompt.md")}
    for p in sorted(on_disk - registered):
        fail.append(f"FAIL {p}: prompt on disk not in Dispatch registry")


def check_box_drawing(f: Path, rel: str, fail: list[str]) -> None:
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if BOX.search(_strip_spans(line)):
            fail.append(f"FAIL {rel}:{i}: box-drawing character — draw it "
                        f"as a mermaid diagram or a table")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "skills")
    fail: list[str] = []

    skills = sorted(root.glob("*/SKILL.md"))
    for sk in skills:
        rel = str(sk)
        check_frontmatter(sk, rel, fail)
        check_sections(sk, rel, fail)

    names = {}
    for sk in skills:
        m = re.search(r"^name:\s*(\S+)", sk.read_text(encoding="utf-8"),
                      re.M)
        if m:
            names.setdefault(m.group(1), []).append(str(sk))
    for name, paths in names.items():
        if len(paths) > 1:
            fail.append(f"FAIL: duplicate skill name '{name}': {paths}")

    for f in root.rglob("*.md"):
        rel = str(f)
        check_fences(f, rel, fail)
        check_html_comments(f, rel, fail)
        check_box_drawing(f, rel, fail)

    check_registry(root, fail)

    if fail:
        print("\n".join(fail), file=sys.stderr)
        print("skill validation: FAILURES", file=sys.stderr)
        return 1
    print("skill validation: all clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
