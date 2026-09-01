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
    NR == 1 && $0 != "---" { exit }
    NR == 1 { infm = 1; next }
    infm && $0 == "---" { exit }
    infm {
      # match "key: value", tolerating surrounding whitespace
      if (match($0, "^[ \t]*" key "[ \t]*:")) {
        v = substr($0, RSTART + RLENGTH)
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
    /^```/ { infence = !infence }
    !infence && $0 ~ ("^#+[ \t]+Task[ \t]+" n "([^0-9]|$)") {
      if (match($0, /INIT-[0-9]{4}-P[0-9]{2}-T[0-9]{2}/)) {
        print substr($0, RSTART, RLENGTH)
      }
      exit
    }
  ' "$plan"
}
