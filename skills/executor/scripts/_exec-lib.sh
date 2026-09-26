#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
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

# Reduce a plan ledger to the latest state per task: one "tid<TAB>state"
# line per task, input order retained implicitly by last-write-wins.
#
# Two line shapes are real in the wild and both are parsed:
#   canonical:  INIT-0004-P01-T03: complete (commits a1b2c3d..d4e5f6a)
#   narrative:  - 2026-09-25T09:56Z — T03 complete (b8af4bc) — APPROVED
#               - T03 APPROVED (dd605c3f, spec 4.7)
# The narrative shape is drift — writers MUST emit the canonical form — but
# a parser that cannot read it audits nothing, which is how verdict and
# task-table checks silently no-oped in live runs. 'approved' normalizes to
# 'complete': a task whose review passed is complete for audit purposes.
# The state returned is the first word after the task marker, lowercased;
# trailing annotations stay available in the raw line, never in the state.
exec_ledger_states() {
  local progress=$1 pid=$2
  [ -f "$progress" ] || return 0
  awk -v pid="$pid" '
    {
      line = $0
      # Canonical: "^<pid>-T<nn>: <state>", optionally bullet-prefixed —
      # the only form scripts write. Anchored to line start (after an
      # optional bullet) on purpose: seed guidance text and prose that
      # merely mention an ID ("Example: X-T03: dispatched") must not parse
      # as a real event — that false positive was a live defect.
      if (match(line, "^[ \t]*(-[ \t]+)?" pid "-T[0-9][0-9]:[ \t]")) {
        seg = substr(line, RSTART, RLENGTH)
        tid = seg; sub(/^[ \t]*-[ \t]+/, "", tid); sub(/:.*/, "", tid)
        st = substr(line, RSTART + RLENGTH); sub(/[ (].*$/, "", st)
        last[tid] = tolower(st)
        next
      }
      # Narrative drift: a bullet line carrying a bare T<nn> token followed
      # by a state word. The bullet requirement is what keeps italic
      # guidance text ("…shape: X-T03: complete…") from self-matching.
      if (line ~ /^[ \t]*- / && match(line, /(^|[^A-Za-z0-9-])T[0-9][0-9][ \t]+(dispatched|in-fix|complete|parked|approved|fix|ruling|blocked|minor)/)) {
        seg = substr(line, RSTART, RLENGTH)
        t = seg; sub(/^[^A-Za-z0-9-]*/, "", t); sub(/[ \t].*/, "", t)
        st = seg; sub(/.*[ \t]/, "", st); st = tolower(st)
        if (st == "approved") st = "complete"
        last[pid "-" toupper(t)] = st
      }
    }
    END { for (t in last) print t "\t" last[t] }
  ' "$progress"
}

# Count ledger lines that record a task state but are NOT the strict
# canonical "^<pid>-T<nn>: " form — the drift the dual parser tolerates.
# check reports these as NOTEs: readable but one grammar change away from
# invisible. A bulleted full-ID line parses (the ID is unambiguous) but is
# still drift; a narrative bullet is drift too.
exec_ledger_drift_count() {
  local progress=$1 pid=$2
  [ -f "$progress" ] || { echo 0; return 0; }
  awk -v pid="$pid" '
    $0 ~ ("^" pid "-T[0-9][0-9]: ") { next }
    $0 ~ ("^[ \t]*-[ \t]+" pid "-T[0-9][0-9]:") { n++; next }
    /^[ \t]*- / && match($0, /(^|[^A-Za-z0-9-])T[0-9][0-9][ \t]+(dispatched|in-fix|complete|parked|approved|fix|ruling|blocked|minor)/) { n++ }
    END { print n + 0 }
  ' "$progress"
}

# Record the branch a task is executing on. Two surfaces, one act:
#
#   - the ledger's State changes line, canonical shape, which is what
#     exec_ledger_states parses and what a resume scan reads;
#   - the dispatches.md Branch cell, which is what a human reads.
#
# The dispatch cell is best-effort: a task with no dispatches row yet gets
# no row created here (rows carry Agent/Model the controller owns), and
# the ledger line is the authoritative record either way.
#
#   exec_record_task_branch DIR TASK_ID BRANCH BASE_SHA
exec_record_task_branch() {
  local dir=$1 tid=$2 branch=$3 base=$4
  [ -f "$dir/progress.md" ] || return 0
  printf '%s: dispatched (branch %s, base %s)\n' "$tid" "$branch" "$base" >> "$dir/progress.md"
  local dfile="$dir/dispatches.md"
  [ -f "$dfile" ] || return 0
  local tmp
  tmp=$(mktemp "$dir/.branch.XXXXXX") || return 0
  if awk -v tid="$tid" -v branch="$branch" '
    BEGIN { bcol = 0; last = 0 }
    $0 ~ /^\|[ \t]*Task[ \t]*\|/ {
      # Locate the Branch column by name — a differently-shaped table is
      # never rewritten in the wrong cell.
      n = split($0, h, "|")
      for (i = 2; i <= n; i++) {
        c = h[i]; gsub(/^[ \t]+|[ \t]+$/, "", c)
        if (c == "Branch") { bcol = i; break }
      }
      rows[NR] = $0; next
    }
    $0 ~ ("^\\|[ \t]*" tid "(-R[0-9]+)?[ \t]*\\|") { last = NR }
    { rows[NR] = $0 }
    END {
      if (bcol && last) {
        split(rows[last], f, "|")
        f[bcol] = " " branch " "
        rebuilt = f[1]
        for (i = 2; i <= length(f); i++) rebuilt = rebuilt "|" f[i]
        rows[last] = rebuilt
      }
      for (i = 1; i <= NR; i++) print rows[i]
    }
  ' "$dfile" > "$tmp"; then
    mv "$tmp" "$dfile"
  else
    rm -f "$tmp"
  fi
  return 0
}

# The branch a task is recorded on, or empty. Reads the ledger's canonical
# dispatch line ("<tid>: dispatched (branch <name>, base <sha>)") — the
# same line exec_record_task_branch writes.
exec_task_branch() {
  local dir=$1 tid=$2
  [ -f "$dir/progress.md" ] || return 0
  awk -v tid="$tid" '
    $0 ~ ("^" tid ": dispatched \\(branch ") {
      line = $0
      sub(/^.*\(branch /, "", line)
      sub(/,.*$/, "", line)
      b = line
    }
    END { if (b != "") print b }
  ' "$dir/progress.md"
}

# The fork commit recorded beside a task's branch, or empty.
exec_task_branch_base() {
  local dir=$1 tid=$2
  [ -f "$dir/progress.md" ] || return 0
  awk -v tid="$tid" '
    $0 ~ ("^" tid ": dispatched \\(branch ") {
      line = $0
      sub(/^.*, base /, "", line)
      sub(/\\).*$/, "", line)
      b = line
    }
    END { if (b != "") print b }
  ' "$dir/progress.md"
}

# Seed a plan workspace's four ledger files (idempotent — existing files
# are never rewritten). Every script that writes into a workspace calls
# this first, so no entry point can produce the bare-dir drift seen in
# live runs (a P02 workspace with no rulings/preflight/frontmatter because
# the controller resolved paths by hand instead of running exec-workspace).
#   exec_seed_workspace DIR PLAN_FILE
exec_seed_workspace() {
  local dir=$1 plan=$2
  local plan_id spec_id stamp
  plan_id=$(exec_frontmatter "$plan" id)
  spec_id=$(exec_frontmatter "$plan" spec)
  [ -n "$plan_id" ] || plan_id="(no id: — legacy plan)"
  [ -n "$spec_id" ] || spec_id="(none)"
  stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  if [ ! -f "$dir/progress.md" ]; then
    cat > "$dir/progress.md" <<EOF
---
kind: ledger
plan: $plan_id
plan_file: $plan
spec: $spec_id
created_at: $stamp
updated_at: $stamp
---

# Executor ledger

*A ledger whose plan: line names a different plan is not yours — leave it and start your own. One line per state change goes under "## State changes" at the bottom; the table below is the scan index. Bump updated_at on every append — a stale updated_at is a NOTE in exec-run check.*

## Task status

*State: pending | dispatched | in-fix | complete | parked | blocked. One row per task, filled as it moves. The resume scan reads this table first: a task with no row has never been dispatched.*

| Task | State | Commits | Review | Notes |
|---|---|---|---|---|

## State changes

*Append-only, one line per state change, newest last. Canonical shape is one ID-prefixed line per event — the task's full ID, a colon, then the state word (dispatched / in-fix / complete / parked) with optional annotations. Narrative bullet lines are tolerated by the parser but flagged as drift by exec-run check — write the canonical form. Never quote an example task ID in this file — the ledger parser will read it as a real event.*
EOF
  fi

  [ -f "$dir/rulings.md" ] || cat > "$dir/rulings.md" <<EOF
---
kind: rulings
plan: $plan_id
plan_file: $plan
created_at: $stamp
updated_at: $stamp
---

# Rulings — $plan_id

*Append-only. Every decision taken on the human's behalf, written the moment it is made and mirrored into .local/decisions/ — including questions answered by the human mid-run (logged by exec-ruling with the question attached). Entries are appended at the end of this file by exec-ruling.*
EOF

  [ -f "$dir/preflight-scan.md" ] || cat > "$dir/preflight-scan.md" <<EOF
---
kind: preflight
plan: $plan_id
plan_file: $plan
created_at: $stamp
updated_at: $stamp
---

# Preflight conflict scan — $plan_id

*One row per task pair sharing a file or interface, one row per task for self-consistency, and a ruling beside every finding. Written before Task 1 dispatches; read whenever a task surprises you.*

## Scan

*Severity: conflict | self-inconsistent | clean. Every pair sharing a file or symbol gets a row; every task gets a self-check row. A finding with no ruling is unresolved — do not dispatch until every finding is ruled.*

| Tasks | Shared surface | Produced vs consumed | Finding | Severity | Ruling |
|---|---|---|---|---|---|

## Method

*What was checked: the dependency map rows, the file map, the interface signatures, the test expectations. State the inputs you walked so a reader can see the scan's scope.*

Check every task pair sharing a file, every interface contract the plan cites, and every task against itself:

- Signature resolution — every consumed reference resolves to a produced signature: same name, same shape, same argument order.
- Interface-contract consistency — two contracts defining the same field or type declare the same shape; dict[str, list[str]] beside a record shape for one name is a conflict, not a dialect.
- Prose-vs-code consistency — implementation code embedded in a task body does not contradict that task's own Requirements/Produces line.
- Unspecified contract points — a field used across a seam whose element type or shape no cited contract defines gets a Finding row naming the field and the seam.
EOF

  [ -f "$dir/dispatches.md" ] || cat > "$dir/dispatches.md" <<EOF
---
kind: dispatches
plan: $plan_id
plan_file: $plan
created_at: $stamp
updated_at: $stamp
---

# Dispatch log — $plan_id

*Context: the brief and context file paths each agent received, so 'bad context or bad model?' has a one-line answer. Rows append BELOW the header, never above it.*
*Agent identities follow the grammar ROLE-Pnn-Tnn[-Rnn]: IMPL for implementers, REVIEW for reviewers (round-suffixed, REVIEW-P01-final for the whole-branch review), VERIFY for evidence runs. A resumed agent keeps its identity. See references/layout.md.*
*Branch is the task branch the agent worked on (task/<TASK-ID>), written by exec-branch task start; a sequential plan leaves it empty.*

| Task | Role | Model | Agent | Branch | Started | Outcome | Context |
|---|---|---|---|---|---|---|---|
EOF
}

# Seed the initiative-level rulings log — the home for decisions that
# span plans (plan-regression rulings, contract amendments, answered
# questions that affect the whole initiative). Created on first need by
# exec-workspace or exec-ruling; identical contract to the per-plan log.
exec_seed_initiative_rulings() {
  local init_id=$1
  local store rdir file stamp
  store=$(exec_ensure_run_store)
  rdir="$store/$init_id"
  file="$rdir/rulings.md"
  [ -f "$file" ] && { echo "$file"; return 0; }
  mkdir -p "$rdir"
  stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  cat > "$file" <<EOF
---
kind: rulings
initiative: $init_id
created_at: $stamp
updated_at: $stamp
---

# Rulings — $init_id (initiative-wide)

*Append-only. Decisions that span or transcend a single plan — plan-set regression rulings, contract amendments (IFCE/SPEC), questions answered by the human mid-run. Per-plan rulings stay in the plan's own rulings.md; a decision that later plans must obey belongs here. Entries are appended by exec-ruling with TASK_ID 'initiative'.*
EOF
  echo "$file"
}

# The initiative-level execution directory: .executor/<INIT>/ — home of
# artifacts that span plans (plan-regression/, rulings.md). mkdir so the
# contract location always exists when a plan workspace does.
exec_initiative_run_dir() {
  local plan_id=$1 init dir
  init=$(exec_initiative_of "$plan_id") \
    || exec_die "cannot derive initiative from plan id '$plan_id'"
  dir="$(exec_ensure_run_store)/$init"
  mkdir -p "$dir"
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
# Requirement body for the grammars real specs use: heading forms
# '### R01 — t', '### R01: t', bare '### R01', '### R01. t', and
# paragraph-form 'R01. <text>' / 'R01: <text>' items (INIT-0004-SPEC-02
# writes requirements as paragraphs, not headings). A heading-form body
# runs to the next heading; a paragraph item runs to the next R<nn> item
# or heading, and its 'R01.' marker is not part of the text. rid followed
# by a non-alphanumeric or EOL only — R011 never matches R01.
exec_requirement_body() {
  local spec=$1 rid=$2
  awk -v rid="$rid" '
    /^#+[ \t]+/ {
      if (inreq) exit
      h = $0; sub(/^#+[ \t]+/, "", h); sub(/[ \t]+$/, "", h)
      if (h ~ ("^" rid "([^0-9A-Za-z]|$)")) inreq = 1
      next
    }
    !inreq && $0 ~ ("^" rid "[.:]([ \t]+|$)") {
      inreq = 1
      line = $0
      sub(("^" rid "[.:][ \t]*"), "", line)
      if (line != "") print line
      next
    }
    inreq && /^R[0-9][0-9][.:][ \t]/ { exit }
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
# Ledger parsing goes through exec_ledger_states, which tolerates the
# narrative drift shape real controllers write.
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
  task_states=$(exec_ledger_states "$dir/progress.md" "$plan_id")

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

  # Final verdict: file must exist AND content must pass. Both filename
  # cases exist in the wild (-FINAL- on case-insensitive filesystems);
  # the canonical name is lowercase -final- per references/layout.md.
  local final="$dir/reviews/verdicts/${plan_id}-final-verdict.md"
  if [ ! -f "$final" ] && [ -f "$dir/reviews/verdicts/${plan_id}-FINAL-verdict.md" ]; then
    echo "note: ${plan_id}-FINAL-verdict.md uses uppercase FINAL — canonical is -final-; rename on next touch" >&2
    final="$dir/reviews/verdicts/${plan_id}-FINAL-verdict.md"
  fi
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
  # Two globs, each guarded: `ls a b` exits non-zero when either path is
  # missing (invisible on case-insensitive APFS, fatal on Linux CI), and
  # under pipefail that status propagates through the pipeline.
  local latest_final_r
  latest_final_r=$( { ls "$dir/reviews/verdicts/${plan_id}-final-R"*-verdict.md 2>/dev/null || true
                      ls "$dir/reviews/verdicts/${plan_id}-FINAL-R"*-verdict.md 2>/dev/null || true; } \
                    | sort | tail -1)
  if [ -n "$latest_final_r" ] && ! exec_verdict_clean "$latest_final_r"; then
    echo "AUDIT: latest final re-review ($(basename "$latest_final_r")) is not clean — it supersedes the earlier clean verdict" >&2
    violations=$((violations + 1))
  fi

  [ "$violations" -eq 0 ]
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
