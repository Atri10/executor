#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
# Validate every skill file's structural contract: frontmatter parseable,
# name/description present, description carries a "Use when ..." trigger,
# markdown fences balanced, every SKILL.md carries its Self-Critique and
# Verification sections, every dispatch role in the registry has a prompt
# template that carries the dispatch contract, and no markdown file draws
# a diagram in box-drawing characters. Runs in CI and before any release.
#
# Usage: scripts/validate-skills.sh [SKILLS_DIR]   (default: skills)
set -euo pipefail

dir=${1:-skills}
fail=0

for sk in "$dir"/*/SKILL.md; do
  [ -f "$sk" ] || continue
  rel=${sk#./}

  # Frontmatter present and delimited
  if ! head -1 "$sk" | grep -q '^---$'; then
    echo "FAIL $rel: no frontmatter block"
    fail=1
    continue
  fi
  fm=$(awk 'NR==1{next} /^---$/{exit} {print}' "$sk")

  grep -q '^name:' <<<"$fm" || { echo "FAIL $rel: no name: field"; fail=1; }
  grep -q '^description:' <<<"$fm" || {
    echo "FAIL $rel: no description: field (routing depends on it)"; fail=1;
  }
  # Trigger phrase: the description must say WHEN to use the skill, so
  # description-based routing fires on the right requests.
  grep -q 'Use when' <<<"$fm" || {
    echo "FAIL $rel: description lacks a 'Use when' trigger"; fail=1;
  }
done

# Markdown fences balanced in every md file under skills/
while IFS= read -r -d '' f; do
  n=$(grep -c '^\s*```' "$f" || true)
  if [ $((n % 2)) -ne 0 ]; then
    echo "FAIL ${f#./}: unbalanced code fences ($n)"
    fail=1
  fi
done < <(find "$dir" -name '*.md' -print0)

# No HTML comments in markdown bodies or in markdown skeleton fences.
# A `<!-- -->` between a table header and its rows splits the table in most
# renderers, and comments seeded into generated files are invisible leftover
# guidance. Comments inside ```html/xml/svg code samples are the sampled
# language, not markdown comments, and stay legal.
while IFS= read -r -d '' f; do
  awk -v file="${f#./}" '
    {
      line = $0
      indent = 0
      while (substr(line, indent + 1, 1) == " ") indent++
      stripped = substr(line, indent + 1)
      if (match(stripped, /^(`{3,}|~{3,})/)) {
        mlen = RLENGTH; ch = substr(stripped, 1, 1)
        info = substr(stripped, mlen + 1)
        gsub(/^[ \t]+|[ \t]+$/, "", info)
        if (!infence) { infence = 1; flen = mlen; fch = ch; markup = (tolower(info) ~ /^(html|xml|svg)/) }
        else if (ch == fch && mlen >= flen) { infence = 0; markup = 0 }
        next
      }
      if (line ~ /<!--/ && !(infence && markup)) {
        printf "FAIL %s:%d: HTML comment %s — generated/seeded markdown carries no comments; write guidance as visible text\n", file, NR, (infence ? "inside a markdown fence" : "in markdown body")
        bad = 1
      }
    }
    END { exit bad }
  ' "$f" || fail=1
done < <(find "$dir" -name '*.md' -print0)

# Duplicate skill names across directories
tmp=$(mktemp)
find "$dir" -name SKILL.md -print0 | xargs -0 awk '/^name:/{print FILENAME, $2}' > "$tmp"
dups=$(awk '{print $2}' "$tmp" | sort | uniq -d)
if [ -n "$dups" ]; then
  echo "FAIL duplicate skill names: $dups"
  fail=1
fi
rm -f "$tmp"

# Every SKILL.md carries the two sections that make a phase self-checking:
# an adversarial pass over its own output (Self-Critique) and the checks
# that prove it before the gate is claimed (Verification). Exactly one of
# each — two copies drift apart.
for sk in "$dir"/*/SKILL.md; do
  [ -f "$sk" ] || continue
  for sec in "Self-Critique" "Verification"; do
    n=$(grep -cxE "## ${sec}" "$sk" || true)
    if [ "$n" -ne 1 ]; then
      echo "FAIL ${sk#./}: expected exactly one '## ${sec}' section, found $n"
      fail=1
    fi
  done
done

# Dispatch registry (references/layout.md): every template the registry
# names must exist and carry the dispatch contract, and every *-prompt.md
# on disk must be registered. A dispatch without a dedicated prompt is an
# agent briefed from memory; a prompt nobody registered is dead weight.
layout="$dir/executor/references/layout.md"
if [ -f "$layout" ]; then
  registered=$(awk '
    /^## Dispatch registry/ { on = 1; next }
    on && /^## / { exit }
    on && /^\|/ {
      while (match($0, /`[a-z0-9-]+\/[a-z0-9-]+-prompt\.md`/)) {
        print substr($0, RSTART + 1, RLENGTH - 2)
        $0 = substr($0, RSTART + RLENGTH)
      }
    }
  ' "$layout" | sort -u)
  [ -n "$registered" ] || { echo "FAIL ${layout#./}: no prompt templates found under ## Dispatch registry"; fail=1; }
  while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    p="$dir/$rel"
    if [ ! -f "$p" ]; then
      echo "FAIL dispatch registry names $rel but $p does not exist"
      fail=1
      continue
    fi
    for marker in 'Subagent (general-purpose):' 'agent_identity:' 'model:' '## Identity' \
                  '## Self-Critique Before You Return' '## Verification' '## What You Return' \
                  '**Placeholders'; do
      grep -qF -- "$marker" "$p" || { echo "FAIL ${p#./}: prompt template lacks '$marker'"; fail=1; }
    done
  done <<< "$registered"
  while IFS= read -r -d '' p; do
    rel=${p#"$dir"/}
    printf '%s\n' "$registered" | grep -qxF "$rel" \
      || { echo "FAIL ${p#./}: prompt template is not listed in the dispatch registry (references/layout.md)"; fail=1; }
  done < <(find "$dir" -name '*-prompt.md' -print0)
fi

# No ASCII-art diagrams. Box-drawing characters draw trees and boxes whose
# edges live only in whitespace — nothing renders or checks them, and they
# silently drift from the structure they claim to show. Mermaid carries the
# structure explicitly. Inline code spans are exempt, so prose can still
# name the characters it bans.
while IFS= read -r -d '' f; do
  awk -v file="${f#./}" '
    {
      line = $0
      gsub(/`[^`]*`/, "", line)
      # Alternation, NOT a bracket expression. mawk — the default awk on
      # Ubuntu and Debian — is byte-oriented rather than character-oriented,
      # so /[├└│┌…]/ does not mean "any of these characters": the multi-byte
      # sequence degenerates into a set of individual BYTES, and any line
      # containing ordinary UTF-8 whose bytes overlap one of them matches.
      # An em-dash in prose was enough to fail the whole run. The validator
      # passed on macOS and failed on every Linux runner, which is the worst
      # split to have — the platform nobody develops on is the one that
      # reports the problem. Written as explicit alternation each
      # alternative is the full byte sequence of one character, so byte
      # matching and character matching agree and both awks reject the
      # same lines.
      if (line ~ /├|└|│|┌|┐|┘|┬|┴|┼|╭|╮|╯|╰|═|║|╔|╗|╚|╝/) {
        printf "FAIL %s:%d: box-drawing character — draw it as a mermaid diagram or a table\n", file, NR
        bad = 1
      }
    }
    END { exit bad }
  ' "$f" || fail=1
done < <(find "$dir" -name '*.md' -print0)

if [ "$fail" -ne 0 ]; then
  echo "skill validation: FAILURES"
  exit 1
fi
echo "skill validation: all clean"
