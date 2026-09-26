#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
# Validate every skill file's structural contract: frontmatter parseable,
# name/description present, description carries a "Use when ..." trigger,
# markdown fences balanced. Runs in CI and before any local release.
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

if [ "$fail" -ne 0 ]; then
  echo "skill validation: FAILURES"
  exit 1
fi
echo "skill validation: all clean"
