#!/usr/bin/env bash
# Shared helpers for the Executor scripts. Sourced, never executed directly.
#
# Single source of truth for ID parsing, frontmatter reading, and store
# locations, so no two scripts can drift to different conventions.

exec_die() { echo "$*" >&2; exit 2; }

# Working-tree root — the checkout you are currently on. Tracked artifacts
# belong here, because they are committed on this branch.
exec_root() {
  git rev-parse --show-toplevel 2>/dev/null || exec_die "not inside a git repository"
}

# Main repository root, identical to exec_root outside a worktree.
#
# Inside a linked worktree these differ, and the difference is load-bearing:
# removing a worktree deletes everything in it. If the execution store lived
# in the worktree, finishing a branch would destroy the very reports, verdicts,
# and rulings the Executor exists to keep. --git-common-dir points at the main
# repository's .git from any worktree, so its parent is the durable root.
exec_main_root() {
  local common
  common=$(git rev-parse --git-common-dir 2>/dev/null) || exec_die "not inside a git repository"
  case "$common" in
    /*) ;;                                   # already absolute
    *)  common="$(exec_root)/$common" ;;     # relative, e.g. plain ".git"
  esac
  cd "$(dirname "$common")" && pwd
}

# Tracked thinking store: worktree root, so specs and plans commit on the
# branch that produced them.
exec_docs_store() { echo "$(exec_root)/docs/executor"; }

# Untracked execution store: main root, so it survives worktree teardown and
# every worktree of the same repository shares one execution record. Plan IDs
# are unique repo-wide, so sharing cannot collide.
exec_run_store()  { echo "$(exec_main_root)/.executor"; }

# Read one frontmatter scalar from a markdown file. Frontmatter is the block
# between the first '---' line and the next '---' line. Prints nothing when
# absent, so callers can test for empty.
exec_frontmatter() {
  local file=$1 key=$2
  [ -f "$file" ] || return 0
  awk -v key="$key" '
    { sub(/\r$/, "") }                   # CRLF files: compare and match CR-stripped lines
    NR == 1 && $0 != "---" { exit }
    NR == 1 { infm = 1; next }
    infm && $0 == "---" { exit }
    infm {
      # match "key: value", tolerating surrounding whitespace
      if (match($0, "^[ \t]*" key "[ \t]*:")) {
        v = substr($0, RSTART + RLENGTH)
        sub(/\r$/, "", v)                   # CRLF files: strip carriage return
        gsub(/^[ \t]+|[ \t]+$/, "", v)
        gsub(/^["'\'']|["'\'']$/, "", v)
        print v
        exit
      }
    }
  ' "$file"
}

# INIT-0004-P01 -> INIT-0004
exec_initiative_of() {
  case "$1" in
    INIT-[0-9][0-9][0-9][0-9]*) echo "${1:0:9}" ;;
    *) return 1 ;;
  esac
}

# INIT-0004-P01 -> P01
exec_plan_segment_of() {
  case "$1" in
    INIT-[0-9][0-9][0-9][0-9]-P[0-9][0-9]) echo "${1:10}" ;;
    *) return 1 ;;
  esac
}

# Zero-pad a bare number to two digits; pass through anything already padded.
exec_pad2() { printf '%02d' "$((10#${1#0}))" 2>/dev/null || echo "$1"; }

# Resolve an initiative's folder from its ID. Folder names are
# INIT-NNNN-<slug>, so the ID prefix is the lookup key and the slug is
# cosmetic.
exec_initiative_dir() {
  local id=$1 store
  store=$(exec_docs_store)
  [ -d "$store" ] || exec_die "no initiative store at $store"
  local match
  match=$(find "$store" -maxdepth 1 -type d -name "${id}-*" -print -quit 2>/dev/null)
  [ -n "$match" ] || match=$(find "$store" -maxdepth 1 -type d -name "$id" -print -quit 2>/dev/null)
  [ -n "$match" ] || exec_die "no initiative folder for $id under $store"
  echo "$match"
}

# Ensure the run store exists and is self-ignoring. Writing the .gitignore
# unconditionally means no subsystem can forget it and no user has to add it
# by hand — that omission is what made the legacy store pollute git status.
exec_ensure_run_store() {
  local store
  store=$(exec_run_store)
  mkdir -p "$store"
  [ -f "$store/.gitignore" ] || printf '*\n' > "$store/.gitignore"
  echo "$store"
}

# The plan's execution workspace: .executor/<INIT>/<Pnn>/
# Resolved from the plan's `id:` frontmatter so renaming the plan file never
# orphans its artifacts. Plans predating the Executor have no id: — those fall
# back to the file's basename, which preserves legacy behaviour exactly.
exec_workspace_dir() {
  local plan=$1
  [ -f "$plan" ] || exec_die "no such plan file: $plan"
  local store plan_id init seg dir
  store=$(exec_ensure_run_store)
  plan_id=$(exec_frontmatter "$plan" id)

  if [ -n "$plan_id" ] && init=$(exec_initiative_of "$plan_id") \
     && seg=$(exec_plan_segment_of "$plan_id"); then
    dir="$store/$init/$seg"
  else
    local slug
    slug=$(basename "$plan" .md)
    [ -n "$slug" ] && [ "$slug" != "." ] && [ "$slug" != ".." ] \
      || exec_die "cannot derive a workspace name from: $plan"
    dir="$store/legacy/$slug"
  fi

  mkdir -p "$dir/briefs" "$dir/reports" "$dir/reviews/diffs" "$dir/reviews/verdicts"
  echo "$dir"
}

# Extract a task's ID from its plan heading.
# Heading form: '### Task 3: Name — `INIT-0004-P01-T03`'
exec_task_id() {
  local plan=$1 n=$2
  awk -v n="$n" '
    {
      line = $0
      indent = 0
      while (substr(line, indent + 1, 1) == " ") indent++
      stripped = substr(line, indent + 1)
      if (stripped ~ /^(`{3,}|~{3,})/) {
        match(stripped, /^(`{3,}|~{3,})/)
        len = RLENGTH
        ch = substr(stripped, 1, 1)
        if (!infence) { infence = 1; flen = len; fch = ch }
        else if (ch == fch && len >= flen) { infence = 0 }
      }
    }
    !infence && $0 ~ ("^### Task[ \t]+" n "([^0-9]|$)") {
      if (match($0, /INIT-[0-9]{4}-P[0-9]{2}-T[0-9]{2}/)) {
        print substr($0, RSTART, RLENGTH)
      }
      exit
    }
  ' "$plan"
}

# Task body extraction shared by exec-brief, exec-context, and
# exec-review-package. Fence tracking follows CommonMark rules the plan
# format relies on: backtick and tilde fences, fence length (a shorter
# run does not close a longer one), and indentation up to three spaces.
# Everything else (indented code blocks) is out of scope for plans and
# rejected by plan lint, not silently parsed here.
exec_task_body() {
  local plan=$1 n=$2
  awk -v n="$n" '
    {
      line = $0
      # Measure leading whitespace for fence detection (max 3 spaces).
      indent = 0
      while (substr(line, indent + 1, 1) == " ") indent++
      stripped = substr(line, indent + 1)
      if (stripped ~ /^(`{3,}|~{3,})/) {
        match(stripped, /^(`{3,}|~{3,})/)
        len = RLENGTH
        ch = substr(stripped, 1, 1)
        if (!infence) { infence = 1; flen = len; fch = ch }
        else if (ch == fch && len >= flen) { infence = 0 }
        # A closing fence of the same char and sufficient length closes.
        # A longer opening fence requires an equal-or-longer closer.
      }
    }
    !infence && $0 ~ ("^### Task[ \t]+" n "([^0-9]|$)") { intask = 1; next }
    # A level-2 or level-3 heading ends the task body — a plan-level
    # section after the last task is not part of that task.
    !infence && intask && /^#{2,3} / { exit }
    intask { print }
  ' "$plan"
}

# Extract one numbered requirement's full text from a spec document.
# Requirement heading form: '### R01 — <title>'. Body runs to the next
# level-2 or level-3 heading (a '## ' section after the requirements is
# not part of the last requirement).
exec_requirement_body() {
  local spec=$1 rid=$2
  awk -v rid="$rid" '
    /^#{2,3} / {
      if (inreq) exit
      h = $0; sub(/^#+[ \t]+/, "", h); sub(/[ \t]+$/, "", h)
      if (index(h, rid " ") == 1) inreq = 1
      next
    }
    inreq { print }
  ' "$spec"
}

# Extract a full '## Section' body from a document, to the next '## '
# heading. Used for Interfaces and Global Constraints so long sections
# are never silently truncated. Heading match is exact: '## Interfaces'
# requested must not match '## Interfaces and seams'.
exec_section_body() {
  local doc=$1 section=$2
  awk -v sec="$section" '
    /^## / {
      if (insec) exit
      h = $0; sub(/^##[ \t]+/, "", h); sub(/[ \t]+$/, "", h)
      if (h == sec) { insec = 1; next }
    }
    insec { print }
  ' "$doc"
}

# Semantic run audit shared by exec-run check/complete and exec-branch
# audit. This is the canonical gate (/017): it parses verdict
# CONTENT (the latest verdict per task and for the branch must be clean:
# spec_verdict PASS or null — re-review verdicts carry null — with
# quality APPROVED), reduces the ledger to the
# latest state per unique task, and requires the exact plan task set.
# Prints diagnostics to stderr; returns nonzero on any violation.
exec_run_audit() {
  local plan=$1 dir=$2
  # Callers set plan_id; die loudly rather than auditing against an empty ID.
  local plan_id=${plan_id:?exec_run_audit: caller must set plan_id}
  local violations=0

  # --- Ledger reduction: latest state per unique task ID ----------------
  #duplicate completion lines never inflate the count, and a
  # later in-fix/reopen event supersedes an earlier complete.
  local task_states
  task_states=$(awk -v pid="${plan_id}" '
    $0 ~ ("^" pid "-T[0-9][0-9]: ") {
      tid = $1; sub(/:$/, "", tid)
      state = $0; sub(/^"?"?[^:]*: */, "", state)
      # Keep only the last event per task (input order).
      last[tid] = state
      seen[tid] = 1
    }
    END { for (t in last) print t "\t" last[t] }
  ' "$dir/progress.md" 2>/dev/null || true)

  # --- Expected task set from the plan ----------------------------------
  # Fence-aware: a '### Task N' inside a code fence is an example, not a
  # task — the same convention exec-plan-lint enforces.
  local expected
  expected=$(awk '{
    line = $0
    indent = 0
    while (substr(line, indent + 1, 1) == " ") indent++
    stripped = substr(line, indent + 1)
    if (match(stripped, /^(`{3,}|~{3,})/)) {
      len = RLENGTH; ch = substr(stripped, 1, 1)
      if (!infence) { infence = 1; flen = len; fch = ch }
      else if (ch == fch && len >= flen) { infence = 0 }
    }
    if (!infence && $0 ~ /^### Task [0-9]+/ &&
        match($0, /INIT-[0-9]{4}-P[0-9]{2}-T[0-9]{2}/)) {
      print substr($0, RSTART, RLENGTH)
    }
  }' "$plan" 2>/dev/null | sort -u)

  # Unknown ledger task IDs (not in the plan) are a violation.
  while IFS=$'\t' read -r tid state; do
    [ -n "$tid" ] || continue
    if ! printf '%s\n' "$expected" | grep -qxF "$tid"; then
      echo "AUDIT: $tid appears in the ledger but no task heading in $plan declares it" >&2
      violations=$((violations + 1))
    fi
  done <<< "$task_states"

  # Every expected task must be complete (latest state wins).
  local completed=0
  while IFS= read -r tid; do
    [ -n "$tid" ] || continue
    state=$(printf '%s\n' "$task_states" | awk -F'\t' -v t="$tid" '$1 == t { print $2 }')
    # Ledger grammar allows an annotation after the state word:
    # "complete (commits a1b2c3d..b7c8d9e, review clean)". Compare the word.
    if [ "${state%%[ (]*}" != "complete" ]; then
      echo "AUDIT: $tid is not complete (latest ledger state: ${state:-absent})" >&2
      violations=$((violations + 1))
    else
      completed=$((completed + 1))
      # Verdict audit: file must exist AND its content must pass.
      local vfile
      vfile=$(ls "$dir/reviews/verdicts/${tid}-R"*-verdict.md 2>/dev/null | sort | tail -1)
      if [ -z "$vfile" ]; then
        echo "AUDIT: $tid is complete but no verdict file exists in reviews/verdicts/ — the task is unjudged" >&2
        violations=$((violations + 1))
      else
        if ! exec_verdict_clean "$vfile"; then
          echo "AUDIT: $tid verdict ($(basename "$vfile")) is not clean — needs spec_verdict: PASS or null with quality: APPROVED" >&2
          violations=$((violations + 1))
        fi
      fi
    fi
  done <<< "$expected"

  # Final verdict: file must exist AND content must pass.
  local final="$dir/reviews/verdicts/${plan_id}-final-verdict.md"
  if [ -f "$final" ]; then
    if ! exec_verdict_clean "$final"; then
      echo "AUDIT: final verdict is not clean — needs spec_verdict: PASS or null with quality: APPROVED" >&2
      violations=$((violations + 1))
    fi
  else
    echo "AUDIT: no final verdict ($final) — whole-branch review has not run" >&2
    violations=$((violations + 1))
  fi

  # Latest final-R verdict supersedes the base final verdict:
  # if a final fix-wave re-review failed, the run is not clean.
  local latest_final_r
  latest_final_r=$(ls "$dir/reviews/verdicts/${plan_id}-final-R"*-verdict.md 2>/dev/null | sort | tail -1)
  if [ -n "$latest_final_r" ] && ! exec_verdict_clean "$latest_final_r"; then
    echo "AUDIT: latest final re-review ($(basename "$latest_final_r")) is not clean — it supersedes the earlier clean verdict" >&2
    violations=$((violations + 1))
  fi

  return $((violations > 0))
}

# A verdict file is clean iff spec_verdict is PASS (first-pass verdicts) or
# null (re-review verdicts carry null — the spec was judged in R01) AND the
# reviewer's gate field says quality: APPROVED. Both fields are read from
# frontmatter only — a 'spec_verdict: PASS' line in the verdict body is
# prose, not a verdict.
exec_verdict_clean() {
  local sv q
  sv=$(exec_frontmatter "$1" spec_verdict)
  q=$(exec_frontmatter "$1" quality)
  { [ "$sv" = "PASS" ] || [ "$sv" = "null" ]; } && [ "$q" = "APPROVED" ]
}

# Generic store lock: one writer at a time for any shared
# store mutation. mkdir is atomic on POSIX; a failed mkdir means the
# lock is held, and the bounded wait assumes a crashed holder after
# ~10s (same policy as exec-initiative's registry lock).
store_lock() {
  local dir=$1
  local lock="$dir/.store.lock" waited=0
  mkdir -p "$dir"
  while ! mkdir "$lock" 2>/dev/null; do
    waited=$((waited + 1))
    if [ "$waited" -gt 100 ]; then
      [ -n "$lock" ] && rm -rf "$lock"
      continue
    fi
    sleep 0.1
  done
}

store_unlock() { rmdir "$1/.store.lock" 2>/dev/null || true; }

# Unique temp name for atomic writes under a lock: shared
# fixed-name temp files are how concurrent writers lost rows.
store_tmp() { mktemp "${1%/}/.store-tmp.XXXXXX"; }

# True when a `key:` line appears inside the document's frontmatter block
# (the first ---...--- region). Body code fences and prose never satisfy
# required-field checks.
exec_frontmatter_has() {
  local file=$1 key=$2
  awk -v key="$key" '
    NR == 1 && $0 !~ /^---[[:space:]]*$/ { exit 1 }
    NR > 1 && /^---[[:space:]]*$/ { exit found ? 0 : 1 }
    $0 ~ ("^" key ":") { found = 1 }
  ' "$file"
}
