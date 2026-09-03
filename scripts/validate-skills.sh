#!/usr/bin/env bash
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

# Duplicate skill names across directories
tmp=$(mktemp)
find "$dir" -name SKILL.md -exec awk '/^name:/{print FILENAME, $2}' {} \; > "$tmp"
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
