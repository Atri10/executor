#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
#
# Regression fixtures for the executor scripts' contracts.
#
# Each case recreates a reproduced failure against disposable synthetic
# repositories and asserts the fixed behavior. Run from the repo root:
#   bash scripts/test-executor.sh
# Exit 0 = all cases pass; nonzero names the failing case.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT/skills/executor/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/executor-tests.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT
pass=0; fail=0
ok()   { pass=$((pass + 1)); echo "ok   - $1"; }
bad()  { fail=$((fail + 1)); echo "FAIL - $1" >&2; }
fixture() {
  local d="$WORK/$1"; mkdir -p "$d"
  git -C "$d" init -q -b main
  git -C "$d" config user.email fixture@example.invalid
  git -C "$d" config user.name fixture
  # Throwaway repos must not inherit a global commit.gpgsign — a signing
  # agent (1Password, gpg) that is locked or absent aborts every fixture
  # commit and the suite dies mid-run with a git error, not a test result.
  git -C "$d" config commit.gpgsign false
  git -C "$d" config tag.gpgsign false
  printf '%s\n' "$d"
}
commit_all() { git -C "$1" add -A && git -C "$1" commit -qm "${2:-fixture}"; }
# Register a fixture doc in the initiative INDEX Documents table — I1/I3
# require every on-disk doc to have a row whose Status cell matches the
# document's frontmatter status. regdoc IDIR ID KIND STATUS RELPATH
regdoc() { printf '| %s | %s | t | %s | `%s` |\n' "$2" "$3" "$4" "$5" >> "$1/INDEX.md"; }

FM=$'---
id: INIT-0001-P01
initiative: INIT-0001
kind: plan
title: Probe
status: active
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
spec: INIT-0001-SPEC-01
interfaces: []
tasks: 1
execution_mode: inline
---
'
TASK=$'### Task 1: Probe — `INIT-0001-P01-T01`

**Files:**
- Modify: `api.ts`

**Interfaces:**
- Consumes: api contract

**Requirements:**
- INIT-0001-SPEC-01-R01
'

# 1. Context carries all interfaces and constraints (no silent clipping).
d=$(fixture ctx-full)
cd "$d"
bash "$S/exec-initiative" new Probe > "$d/init.out" 2>/dev/null || true
IDIR="$d/docs/executor/INIT-0001-probe"
{ printf '%s\n' "$FM"; printf '## Interfaces\n\n'; for i in $(seq -w 1 45); do printf 'interface-%s signature\n' "$i"; done; printf '\n## Global Constraints\n\n'; for i in $(seq -w 1 35); do printf 'constraint-%s rule\n' "$i"; done; printf '\n%s\n' "$TASK"; } > "$d/plan.md"
bash "$S/exec-context" plan.md 1 "$d/ctx.md" > /dev/null 2>&1
for i in 01 45; do grep -q "interface-$i" "$d/ctx.md" || bad "ctx-full: interface-$i missing"; done
for i in 01 35; do grep -q "constraint-$i" "$d/ctx.md" || bad "ctx-full: constraint-$i missing"; done
ok "context carries all 45 interfaces and 35 constraints"

# 2. Evidence rounds are immutable and never overwrite.
d=$(fixture ev-rounds)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
r1=$(printf 'ROUND01\n' | bash "$S/exec-evidence" plan.md 01 '#3' smoke 2>/dev/null | tail -1)
r2=$(printf 'ROUND02\n' | bash "$S/exec-evidence" plan.md 02 '#3' smoke 2>/dev/null | tail -1)
[ "$r1" != "$r2" ] || { bad "ev-rounds: same path for rounds 01 and 02"; }
grep -q ROUND01 "$r1" || bad "ev-rounds: round01 content lost"
grep -q ROUND02 "$r2" || bad "ev-rounds: round02 content missing"
ok "evidence rounds are immutable"

# 3. Evidence aliases canonicalize (#3 == V3).
d=$(fixture ev-alias)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
p1=$(printf 'A\n' | bash "$S/exec-evidence" plan.md 01 '#3' smoke 2>/dev/null | tail -1)
p2=$(printf 'B\n' | bash "$S/exec-evidence" plan.md 01 'V3' smoke 2>/dev/null | tail -1)
base1=$(basename "$p1"); base2=$(basename "$p2")
case "$base2" in *-attempt*.txt) ok "evidence aliases canonicalize to one identity";; *) bad "ev-alias: V3 produced '$base2' instead of an attempt of '$base1'";; esac

# 4. Failed evidence capture leaves prior proof intact.
d=$(fixture ev-atomic)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
p1=$(printf 'KEEP\n' | bash "$S/exec-evidence" plan.md 01 '#3' smoke 2>/dev/null | tail -1)
if printf 'X\n' | bash "$S/exec-evidence" plan.md 02 '#3' smoke "$d/missing.txt" >/dev/null 2>&1; then
  bad "ev-atomic: missing input accepted"
fi
grep -q KEEP "$p1" || bad "ev-atomic: prior proof damaged"
ok "failed capture leaves prior proof intact"

# 5. Invalid method refused before any artifact.
d=$(fixture ev-method)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
if printf 'X\n' | bash "$S/exec-evidence" plan.md 01 '#4' banana >/dev/null 2>&1; then
  bad "ev-method: banana accepted"
fi
ok "invalid method refused"

# 6. Semantic audit rejects FAIL verdicts and incomplete plans.
d=$(fixture audit)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-audit"
{ printf '%s\n' "$FM"; printf '%s\n' "$TASK"; printf '### Task 2: Other — `INIT-0001-P01-T02`\n\n**Files:**\n- Modify: `b.ts`\n'; } > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: FAIL\nquality: NEEDS_FIXES\n---\nGATE: FAIL\n' > "$W/reviews/verdicts/INIT-0001-P01-T02-R01-verdict.md"
printf 'INIT-0001-P01-T01: complete\nINIT-0001-P01-T02: complete\n' >> "$W/progress.md"
if bash "$S/exec-run" plan.md check >/dev/null 2>&1; then
  bad "audit: FAIL verdict accepted"
fi
ok "semantic audit rejects FAIL verdicts"

# 7. Completion refused on failing audit leaves registry unchanged.
d=$(fixture complete)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-complete"
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
if bash "$S/exec-run" plan.md complete >/dev/null 2>&1; then
  bad "complete: accepted with no verdicts"
fi
ok "completion validates before mutation"

# 8. Empty dispatch table does not silently fail check.
d=$(fixture dispatch)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-dispatch"
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
bash "$S/exec-run" plan.md start > /dev/null 2>&1
printf 'INIT-0001-P01-T01: complete\n' >> "$W/progress.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-final-verdict.md"
printf -- '---\nkind: dispatches\nplan: INIT-0001-P01\nplan_file: plan.md\ncreated_at: 2026-09-12T07:00:00Z\nupdated_at: 2026-09-12T07:00:00Z\n---\n\n| Task | Role | Mode | Agent | Status | Notes |\n|---|---|---|---|---|---|\n' > "$W/dispatches.md"
printf -- '| INIT-0001-P01-T01 | complete | — | IMPL-P01-T01 | — |\n' >> "$W/progress.md"
bash "$S/exec-run" plan.md complete > /dev/null 2>&1
bash "$S/exec-run" plan.md check > /dev/null 2>&1 || bad "dispatch: empty table failed check"
ok "empty dispatch table accepted"

# 9. Phase transitions: skip refused, legal sequence accepted.
d=$(fixture phase)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
if bash "$S/exec-initiative" phase INIT-0001 handoff passed "probe" >/dev/null 2>&1; then
  bad "phase: direct handoff accepted"
fi
bash "$S/exec-initiative" phase INIT-0001 intake passed "ok" > /dev/null 2>&1 || bad "phase: legal intake pass refused"
bash "$S/exec-initiative" phase INIT-0001 discovery entered "start" > /dev/null 2>&1 || bad "phase: legal discovery enter refused"
ok "phase transition gates enforced"

# 10. ID namespace overflow refused.
d=$(fixture idbound)
cd "$d"
bash "$S/exec-initiative" new Ids > /dev/null 2>&1
ADIR="$d/docs/executor/INIT-0001-ids/architecture"
for n in $(seq -w 1 99); do printf -- '---\nid: INIT-0001-ADR-%s\n---\n\nx\n' "$n" > "$ADIR/INIT-0001-ADR-$n-x.md"; done
if bash "$S/exec-id" INIT-0001 ADR >/dev/null 2>&1; then
  bad "idbound: 100th ADR allocated silently"
fi
ok "ID namespace overflow refused"

# 11. Workspace refuses a different plan's ledger.
d=$(fixture wsid)
cd "$d"
bash "$S/exec-initiative" new WsId > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
printf '%s' "$FM" | sed 's/spec: INIT-0001-SPEC-01/spec: INIT-0001-SPEC-02/' > "$d/plan2.md"
printf '%s\n' "$TASK" >> "$d/plan2.md"
if bash "$S/exec-workspace" plan2.md >/dev/null 2>&1; then
  bad "wsid: different spec reused workspace"
fi
ok "workspace contract identity enforced"

# 12. Plan lint: CRLF forbidden path caught, read-only citation allowed, fenced example not a task.
d=$(fixture lint)
cd "$d"
printf '%s\n%s\n- Create: docs/executor/x/y/\n' "$FM" "$TASK" | sed 's/$/\r/' | sed 's/\r\r/\r/' > "$d/crlf.md"
perl -pi -e 's/\n/\r\n/g' "$d/crlf.md" 2>/dev/null || true
if bash "$S/exec-plan-lint" "$d/crlf.md" >/dev/null 2>&1; then
  bad "lint: CRLF forbidden path missed"
fi
printf '%s\n%s\nConsult docs/executor/INDEX.md; do not modify it.\n' "$FM" "$TASK" > "$d/cite.md"
bash "$S/exec-plan-lint" "$d/cite.md" >/dev/null 2>&1 || bad "lint: read-only citation rejected"
{ printf '%s\n' "$FM"; printf '%s\n' "$TASK"; printf '```markdown\n### Task 9: Example — `INIT-0001-P01-T09`\n```\n'; } > "$d/fenced.md"
bash "$S/exec-plan-lint" "$d/fenced.md" >/dev/null 2>&1 || bad "lint: fenced example counted as task"
ok "plan lint CRLF/citation/fence contracts"

# 13. Store check: missing frontmatter title fails; body code block cannot satisfy required fields.
d=$(fixture store)
cd "$d"
bash "$S/exec-initiative" new Store > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-store"
printf -- '---\nid: INIT-0001-RSCH-01\ninitiative: INIT-0001\nkind: research\nstatus: active\nquestion: q\nsources: []\nconfidence: measured\n---\n\n```yaml\ntitle: fake\ncreated_at: 2026-09-12T07:00:00Z\nupdated_at: 2026-09-12T07:30:00Z\n```\n' > "$SDIR/discovery/INIT-0001-RSCH-01-bodyonly.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "store: body code block satisfied required fields"
fi
ok "store required fields scoped to frontmatter"

# 14. Titles with pipes refused.
d=$(fixture title)
cd "$d"
if bash "$S/exec-initiative" new 'Queue: retry | policy' >/dev/null 2>&1; then
  bad "title: pipe accepted"
fi
ok "pipe titles refused"

# 15. Re-review verdicts (spec_verdict: null) do not poison the audit.
# The re-review template mandates spec_verdict: null; the audit must read
# the gate field (quality) for rounds past R01. Regression: before the fix
# any task surviving a fix round could never pass `exec-run check`.
d=$(fixture rereview)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
bash "$S/exec-run" plan.md start > /dev/null 2>&1
printf 'INIT-0001-P01-T01: complete\n' >> "$W/progress.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: null\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R02-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-final-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: null\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-final-R02-verdict.md"
printf -- '| INIT-0001-P01-T01 | complete | — | IMPL-P01-T01 | — |\n' >> "$W/progress.md"
bash "$S/exec-run" plan.md complete > /dev/null 2>&1
bash "$S/exec-run" plan.md check > /dev/null 2>&1 || bad "rereview: clean fix-round run rejected"
ok "re-review verdicts (spec_verdict: null) pass the audit"

# 16. A NEEDS_FIXES latest verdict fails the audit even when spec_verdict
# is null — the gate field is the truth for re-review verdicts.
d=$(fixture rereview-dirty)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
bash "$S/exec-run" plan.md start > /dev/null 2>&1
printf 'INIT-0001-P01-T01: complete\n' >> "$W/progress.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: null\nquality: NEEDS_FIXES\n---\nGATE: FAIL\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R02-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-final-verdict.md"
printf -- '| INIT-0001-P01-T01 | complete | — | IMPL-P01-T01 | — |\n' >> "$W/progress.md"
if bash "$S/exec-run" plan.md check >/dev/null 2>&1; then
  bad "rereview-dirty: NEEDS_FIXES re-review accepted"
fi
ok "NEEDS_FIXES re-review verdict fails the audit"

# 17. Seeded markdown carries no HTML comments anywhere.
d=$(fixture seeds)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-probe"
W="$d/.executor/INIT-0001/P01"
for f in "$IDIR/charter.md" "$IDIR/INDEX.md" "$W/progress.md" "$W/rulings.md" "$W/preflight-scan.md" "$W/dispatches.md"; do
  if grep -q '<!--' "$f"; then
    bad "seeds: $(basename "$f") contains an HTML comment"
  fi
done
ok "seeded markdown carries no HTML comments"

# 18. Store check D7 flags comments in tracked docs; clean stores pass.
d=$(fixture stored7)
cd "$d"
bash "$S/exec-initiative" new Store > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-store"
bash "$S/exec-store-check" >/dev/null 2>&1 || bad "stored7: fresh seeded initiative failed store check"
printf -- '\n<!-- leftover guidance -->\n' >> "$SDIR/charter.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "stored7: HTML comment in charter passed store check"
fi
ok "store check rejects HTML comments in tracked docs"

# 19. Annotated 'complete' ledger lines satisfy the audit. The documented
# grammar is `T01: complete (commits a1b2..b7c8, review clean)` — the audit
# must read the state word, not the whole line. Regression: before the fix
# a conforming annotated ledger could never pass `exec-run check`.
d=$(fixture annotated)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
bash "$S/exec-run" plan.md start > /dev/null 2>&1
printf 'INIT-0001-P01-T01: complete (commits a1b2c3d..b7c8d9e, review clean)\n' >> "$W/progress.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-final-verdict.md"
printf -- '| INIT-0001-P01-T01 | complete | a1b2c3d..b7c8d9e | clean | — |\n' >> "$W/progress.md"
bash "$S/exec-run" plan.md complete > /dev/null 2>&1
bash "$S/exec-run" plan.md check > /dev/null 2>&1 || bad "annotated: documented ledger grammar rejected"
ok "annotated 'complete (…)' ledger lines pass the audit"

# 20. A fenced '### Task' example does not inflate the audit's expected set.
d=$(fixture fencedtask)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
{ printf '%s\n' "$FM"; printf '%s\n' "$TASK"; printf '```markdown\n### Task 9: Example — `INIT-0001-P01-T09`\n```\n'; } > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
bash "$S/exec-run" plan.md start > /dev/null 2>&1
printf 'INIT-0001-P01-T01: complete\n' >> "$W/progress.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\nGATE: PASS\n' > "$W/reviews/verdicts/INIT-0001-P01-final-verdict.md"
printf -- '| INIT-0001-P01-T01 | complete | — | IMPL-P01-T01 | — |\n' >> "$W/progress.md"
bash "$S/exec-run" plan.md complete > /dev/null 2>&1
bash "$S/exec-run" plan.md check > /dev/null 2>&1 || bad "fencedtask: fenced example counted as an expected task"
ok "fenced task examples do not inflate the expected set"

# 21. A fenced example naming a store path is not a mutation target, but a
# real one still fails with the correct (file-absolute) line number.
d=$(fixture fencedpath)
cd "$d"
printf -- '---\nid: INIT-0001-P01\nspec: INIT-0001-S01\ninterfaces: []\ntasks: 1\nexecution_mode: inline\n---\n\n### Task 1: a — `INIT-0001-P01-T01`\n\n**Files:**\n- Modify: `a.ts`\n\n```markdown\n- Create: docs/executor/INIT-0002/x.md\n```\n' > "$d/plan.md"
bash "$S/exec-plan-lint" "$d/plan.md" > /dev/null 2>&1 || bad "fencedpath: fenced store-path example failed lint"
printf -- '---\nid: INIT-0001-P01\nspec: INIT-0001-S01\ninterfaces: []\ntasks: 1\nexecution_mode: inline\n---\n\n### Task 1: a — `INIT-0001-P01-T01`\n\n**Files:**\n- Create: docs/executor/INIT-0002/x.md\n' > "$d/plan.md"
out=$(bash "$S/exec-plan-lint" "$d/plan.md" 2>&1) && bad "fencedpath: real store-path mutation passed lint"
case "$out" in *"line 12 "*) ;; *) bad "fencedpath: violation reported wrong line ($out)";; esac
ok "fenced store paths exempt; real ones fail at the right line"

# 22. Plan lint: an absent required key fails — presence precedes value.
# Regression: P02/P03 shipped missing execution_mode/interfaces/tasks and
# lint passed because only id/spec were checked.
d=$(fixture lintkeys)
cd "$d"
{ printf '%s' "$FM" | grep -v '^execution_mode:'; printf '%s\n' "$TASK"; } > "$d/plan.md"
if bash "$S/exec-plan-lint" "$d/plan.md" >/dev/null 2>&1; then
  bad "lintkeys: absent execution_mode: passed lint"
fi
{ printf '%s' "$FM" | grep -v '^tasks:'; printf '%s\n' "$TASK"; } > "$d/plan.md"
if bash "$S/exec-plan-lint" "$d/plan.md" >/dev/null 2>&1; then
  bad "lintkeys: absent tasks: passed lint"
fi
{ printf '%s' "$FM" | grep -v '^interfaces:'; printf '%s\n' "$TASK"; } > "$d/plan.md"
if bash "$S/exec-plan-lint" "$d/plan.md" >/dev/null 2>&1; then
  bad "lintkeys: absent interfaces: passed lint"
fi
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-plan-lint" "$d/plan.md" > /dev/null 2>&1 || bad "lintkeys: complete frontmatter rejected"
ok "plan lint refuses absent required keys"

# 23. Plan lint: a 40+ line implementation-language fence is a pasted
# implementation, not a sketch; exempt tags (sql/text/untagged) are fine.
d=$(fixture lintsketch)
cd "$d"
{ printf '%s\n' "$FM"; printf '%s\n' "$TASK"; printf '```java\n'; for i in $(seq 1 45); do printf 'int x%d = 0;\n' "$i"; done; printf '```\n'; } > "$d/plan.md"
out=$(bash "$S/exec-plan-lint" "$d/plan.md" 2>&1) && bad "lintsketch: 45-line java block passed lint"
case "$out" in *"40-line sketch cap"*) ;; *) bad "lintsketch: wrong violation ($out)";; esac
{ printf '%s\n' "$FM"; printf '%s\n' "$TASK"; printf '```sql\n'; for i in $(seq 1 45); do printf 'select %d;\n' "$i"; done; printf '```\n'; } > "$d/plan.md"
bash "$S/exec-plan-lint" "$d/plan.md" > /dev/null 2>&1 || bad "lintsketch: sql fixture block rejected"
ok "plan lint enforces the 40-line sketch cap with exemptions"

# 24. Plan lint: task-body implementation volume cap — >60 lines and >60%
# of the body. Two 35-line fences stay under the per-block cap, so only
# the volume rule can fire here.
d=$(fixture lintvol)
cd "$d"
{ printf '%s\n' "$FM"; printf '%s\n' "$TASK";
  printf '```java\n'; for i in $(seq 1 35); do printf 'int x%d = 0;\n' "$i"; done; printf '```\n';
  for i in $(seq 1 10); do printf 'prose line %d\n' "$i"; done
  printf '```java\n'; for i in $(seq 1 35); do printf 'int y%d = 0;\n' "$i"; done; printf '```\n'; } > "$d/plan.md"
out=$(bash "$S/exec-plan-lint" "$d/plan.md" 2>&1) && bad "lintvol: 70-line impl body passed lint"
case "$out" in *">60%"*) ;; *) bad "lintvol: wrong violation ($out)";; esac
{ printf '%s\n' "$FM"; printf '%s\n' "$TASK";
  for i in $(seq 1 80); do printf 'prose line %d\n' "$i"; done
  printf '```java\n'; for i in $(seq 1 35); do printf 'int x%d = 0;\n' "$i"; done; printf '```\n'; } > "$d/plan.md"
bash "$S/exec-plan-lint" "$d/plan.md" > /dev/null 2>&1 || bad "lintvol: 35-of-120 impl lines (minority sketch) rejected"
ok "plan lint enforces the task-body volume cap"

# 25. Store check D8: an architecture doc needs a top-level mermaid
# diagram; one nested inside another fence does not count.
d=$(fixture archdia)
cd "$d"
bash "$S/exec-initiative" new Arch > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-arch"
ARCH='---
id: INIT-0001-ARCH-01
initiative: INIT-0001
kind: architecture
status: active
title: Probe arch
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
supersedes: null
superseded_by: null
components: []
interfaces: []
decisions: []
---

# Probe arch

Components and data flow.
'
printf '%s\n' "$ARCH" > "$SDIR/architecture/INIT-0001-ARCH-01-main.md"
regdoc "$SDIR" INIT-0001-ARCH-01 architecture active 'architecture/INIT-0001-ARCH-01-main.md'
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "archdia: arch doc without mermaid passed"
fi
{ printf '%s\n' "$ARCH"; printf '````markdown\n```mermaid\nflowchart TD\n```\n````\n'; } > "$SDIR/architecture/INIT-0001-ARCH-01-main.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "archdia: mermaid nested inside a markdown fence counted"
fi
{ printf '%s\n' "$ARCH"; printf '```mermaid\nflowchart TD\n  A --> B\n```\n'; } > "$SDIR/architecture/INIT-0001-ARCH-01-main.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "archdia: arch doc with mermaid rejected"
ok "D8 requires a real top-level mermaid diagram in architecture"

# 26. Store check D8 spec contract: numbered ### R<nn> headings, a
# verification: pointer that resolves to a same-initiative VRFY doc of
# the right kind, and global_constraints matching the C<nn> rows.
d=$(fixture specd8)
cd "$d"
bash "$S/exec-initiative" new Spec > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-spec"
printf -- '---\nid: INIT-0001-VRFY-01\ninitiative: INIT-0001\nkind: verification\nstatus: active\ntitle: Probe vrfy\ncreated_at: 2026-09-12T07:00:00Z\nupdated_at: 2026-09-12T07:00:00Z\nsupersedes: null\nsuperseded_by: null\nspec: INIT-0001-SPEC-01\ncriteria_count: 1\nevidence_types: [unit]\n---\n\n| V01 | R01 verified by unit test | unit |\n' > "$SDIR/verification/INIT-0001-VRFY-01-probe.md"
SPECBASE='---
id: INIT-0001-SPEC-01
initiative: INIT-0001
kind: spec
status: active
title: Probe spec
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
supersedes: null
superseded_by: null
implements: []
decisions: []
verification: INIT-0001-VRFY-01
plans: []
global_constraints: 1
---

# Probe spec

### R01 — the requirement

Requirement text.

| C01 | the one constraint |
'
printf '%s\n' "$SPECBASE" > "$SDIR/specs/INIT-0001-SPEC-01-probe.md"
regdoc "$SDIR" INIT-0001-VRFY-01 verification active 'verification/INIT-0001-VRFY-01-probe.md'
regdoc "$SDIR" INIT-0001-SPEC-01 spec active 'specs/INIT-0001-SPEC-01-probe.md'
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "specd8: conforming spec+vrfy rejected"
printf '%s\n' "$SPECBASE" | sed 's/^### R01 — the requirement/Requirement paragraph, no heading/' > "$SDIR/specs/INIT-0001-SPEC-01-probe.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "specd8: spec without ### R<nn> heading passed"
fi
printf '%s\n' "$SPECBASE" | sed 's/^verification: INIT-0001-VRFY-01/verification: null/' > "$SDIR/specs/INIT-0001-SPEC-01-probe.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "specd8: spec with verification: null passed"
fi
printf '%s\n' "$SPECBASE" | sed 's/^verification: INIT-0001-VRFY-01/verification: INIT-0001-VRFY-99/' > "$SDIR/specs/INIT-0001-SPEC-01-probe.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "specd8: spec with dangling verification passed"
fi
printf '%s\n' "$SPECBASE" | sed 's/^verification: INIT-0001-VRFY-01/verification: INIT-0002-VRFY-01/' > "$SDIR/specs/INIT-0001-SPEC-01-probe.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "specd8: spec with cross-initiative verification passed"
fi
printf '%s\n' "$SPECBASE" | sed 's/^global_constraints: 1/global_constraints: 3/' > "$SDIR/specs/INIT-0001-SPEC-01-probe.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "specd8: global_constraints 3 vs 1 C-row passed"
fi
printf '%s\n' "$SPECBASE" > "$SDIR/specs/INIT-0001-SPEC-01-probe.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "specd8: restored spec rejected"
ok "D8 spec contract: headings, verification link, constraint count"

# 27. Store check D8 options: an active OPTS needs recommends: set and a
# filled ## Decision; a draft is exempt.
d=$(fixture optsd8)
cd "$d"
bash "$S/exec-initiative" new Opts > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-opts"
OPTS='---
id: INIT-0001-OPTS-01
initiative: INIT-0001
kind: options
status: STATUSHERE
title: Probe options
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
supersedes: null
superseded_by: null
question: which way
sources: []
confidence: measured
recommends: RECOMMENDS
---

# Probe options

DECISIONSEC
'
printf '%s\n' "$OPTS" | sed 's/STATUSHERE/active/; s/RECOMMENDS/null/; s/DECISIONSEC//' > "$SDIR/discovery/INIT-0001-OPTS-01-probe.md"
regdoc "$SDIR" INIT-0001-OPTS-01 options active 'discovery/INIT-0001-OPTS-01-probe.md'
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "optsd8: active options with recommends: null passed"
fi
printf '%s\n' "$OPTS" | sed 's/STATUSHERE/active/; s/RECOMMENDS/INIT-0001-RSCH-01/; s/DECISIONSEC//' > "$SDIR/discovery/INIT-0001-OPTS-01-probe.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "optsd8: active options without ## Decision passed"
fi
printf '%s\n' "$OPTS" | sed 's/STATUSHERE/active/; s/RECOMMENDS/INIT-0001-RSCH-01/; s/DECISIONSEC/## Decision\n\nPicked A on 2026-09-12./' > "$SDIR/discovery/INIT-0001-OPTS-01-probe.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "optsd8: active options with decision rejected"
printf '%s\n' "$OPTS" | sed 's/STATUSHERE/draft/; s/RECOMMENDS/null/; s/DECISIONSEC//' > "$SDIR/discovery/INIT-0001-OPTS-01-probe.md"
sed -i.bak 's/| INIT-0001-OPTS-01 | options | t | active |/| INIT-0001-OPTS-01 | options | t | draft |/' "$SDIR/INDEX.md" && rm -f "$SDIR/INDEX.md.bak"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "optsd8: draft options held to the active contract"
ok "D8 options: active needs recommends + Decision; draft exempt"

# 28. Store check D8 verification: criteria_count must equal the distinct
# V<nn> criteria across table rows and ### V<nn> manual blocks.
d=$(fixture vrfyd8)
cd "$d"
bash "$S/exec-initiative" new Vrfy > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-vrfy"
VBASE='---
id: INIT-0001-VRFY-01
initiative: INIT-0001
kind: verification
status: active
title: Probe vrfy
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
supersedes: null
superseded_by: null
spec: INIT-0001-SPEC-01
criteria_count: COUNTHERE
evidence_types: [unit]
---

CRITHERE
'
printf -- '---\nid: INIT-0001-SPEC-01\ninitiative: INIT-0001\nkind: spec\nstatus: active\ntitle: s\ncreated_at: 2026-09-12T07:00:00Z\nupdated_at: 2026-09-12T07:00:00Z\nsupersedes: null\nsuperseded_by: null\nimplements: []\ndecisions: []\nverification: INIT-0001-VRFY-01\nplans: []\nglobal_constraints: null\n---\n\n### R01 — r\n\ntext\n' > "$SDIR/specs/INIT-0001-SPEC-01-s.md"
printf '%s\n' "$VBASE" | sed 's/COUNTHERE/2/; s/CRITHERE/| V01 | first | unit |/' > "$SDIR/verification/INIT-0001-VRFY-01-probe.md"
regdoc "$SDIR" INIT-0001-SPEC-01 spec active 'specs/INIT-0001-SPEC-01-s.md'
regdoc "$SDIR" INIT-0001-VRFY-01 verification active 'verification/INIT-0001-VRFY-01-probe.md'
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "vrfyd8: criteria_count 2 vs 1 row passed"
fi
printf '%s\n' "$VBASE" | sed 's/COUNTHERE/2/; s/CRITHERE/| V01 | first | unit |\n| V02 | second | unit |/' > "$SDIR/verification/INIT-0001-VRFY-01-probe.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "vrfyd8: criteria_count 2 with 2 rows rejected"
printf '%s\n' "$VBASE" | sed 's/COUNTHERE/2/; s/CRITHERE/| V01 | first | unit |\n\n### V02\n\nManual criterion block./' > "$SDIR/verification/INIT-0001-VRFY-01-probe.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "vrfyd8: table row + manual block miscounted"
ok "D8 verification: criteria_count matches V<nn> criteria"

# 29. Store check D8 doc-code boundary: thinking kinds reject
# implementation-language fences; structural/untagged fences are fine.
d=$(fixture doccode)
cd "$d"
bash "$S/exec-initiative" new Doc > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-doc"
RSCH='---
id: INIT-0001-RSCH-01
initiative: INIT-0001
kind: research
status: active
title: Probe research
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
supersedes: null
superseded_by: null
question: how
sources: []
confidence: measured
---

# Probe research

FENCEHERE
'
printf '%s\n' "$RSCH" | sed 's/FENCEHERE/```java\nvoid f() {}\n```/' > "$SDIR/discovery/INIT-0001-RSCH-01-probe.md"
regdoc "$SDIR" INIT-0001-RSCH-01 research active 'discovery/INIT-0001-RSCH-01-probe.md'
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "doccode: research doc with java fence passed"
fi
printf '%s\n' "$RSCH" | sed 's/FENCEHERE/```json\n{"a": 1}\n```/' > "$SDIR/discovery/INIT-0001-RSCH-01-probe.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "doccode: json fence rejected in thinking doc"
printf '%s\n' "$RSCH" | sed 's/FENCEHERE/```\nanything untagged\n```/' > "$SDIR/discovery/INIT-0001-RSCH-01-probe.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "doccode: untagged fence rejected in thinking doc"
ok "D8 doc-code boundary: impl fences banned, structural fences fine"

# 30. Store check B1/B2: discovery passed with no brainstorm session and no
# recorded skip fails; a session dir with a session.md satisfies it; a bare
# dir (no record) or a record with no ## Options fails B2.
d=$(fixture bstorm)
cd "$d"
bash "$S/exec-initiative" new Brain > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-brain"
printf '| discovery | 2026-09-12 | 2026-09-13 | |\n' >> "$SDIR/INDEX.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "bstorm: discovery passed with empty brainstorm and no skip note"
fi
mkdir -p "$SDIR/brainstorm/sessions/2026-09-12-shape"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "bstorm: a bare session dir (no session.md) satisfied B2"
fi
cat > "$SDIR/brainstorm/sessions/2026-09-12-shape/session.md" <<'EOF'
---
kind: brainstorm
id: null
initiative: INIT-0001
question: Which shape?
status: draft
decided: null
created_at: 2026-09-12T00:00:00Z
updated_at: 2026-09-12T00:00:00Z
---

# Which shape?

## Options
### A — flat
### B — nested

## Outcome
open
EOF
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "bstorm: a session dir with session.md did not satisfy B1/B2"
rm -rf "$SDIR/brainstorm/sessions/2026-09-12-shape"
printf '**Notes:** brainstorm skipped — spike already explored the shape.\n' >> "$SDIR/INDEX.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "bstorm: INDEX skip note did not satisfy B1"
ok "B1/B2 require a recorded brainstorm session or a recorded skip"

# 31. Store check I5/P1: execution-phase progress without a **Branch:** line
# fails; with one it passes; execution entered without plan-regression
# passed/skipped fails P1.
d=$(fixture brline)
cd "$d"
bash "$S/exec-initiative" new Branch > /dev/null 2>&1
SDIR="$d/docs/executor/INIT-0001-branch"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "brline: fresh initiative wrongly required a branch"
printf '| execution | 2026-09-12 | — | |\n' >> "$SDIR/INDEX.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "brline: execution progress without **Branch:** passed"
fi
printf '**Branch:** initiative/INIT-0001\n' >> "$SDIR/INDEX.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "brline: execution entered without plan-regression passed/skipped passed P1"
fi
printf '| plan-regression | 2026-09-12 | **skipped** | fixture |\n' >> "$SDIR/INDEX.md"
bash "$S/exec-store-check" > /dev/null 2>&1 || bad "brline: **Branch:** + skipped plan-regression did not satisfy I5/P1"
ok "I5/P1 require **Branch:** and plan-regression clearance once execution has progress"

# 32. Phase artifact gates: passed requires the phase's deliverable on
# disk; skipped requires a reason note.
d=$(fixture artgate)
cd "$d"
bash "$S/exec-initiative" new Gate > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-gate"
bash "$S/exec-initiative" phase INIT-0001 intake passed "ok" > /dev/null 2>&1 || bad "artgate: intake pass refused"
bash "$S/exec-initiative" phase INIT-0001 discovery entered "go" > /dev/null 2>&1 || bad "artgate: discovery enter refused"
if bash "$S/exec-initiative" phase INIT-0001 discovery passed "done" >/dev/null 2>&1; then
  bad "artgate: discovery passed with no RSCH/OPTS artifact"
fi
printf -- '---\nid: INIT-0001-RSCH-01\ninitiative: INIT-0001\nkind: research\nstatus: draft\ntitle: r\ncreated_at: 2026-09-12T07:00:00Z\nupdated_at: 2026-09-12T07:00:00Z\nsupersedes: null\nsuperseded_by: null\nquestion: q\nsources: []\nconfidence: low\n---\n\nfinding\n' > "$IDIR/discovery/INIT-0001-RSCH-01-r.md"
bash "$S/exec-initiative" phase INIT-0001 discovery passed "done" > /dev/null 2>&1 || bad "artgate: discovery pass refused with artifact present"
bash "$S/exec-initiative" phase INIT-0001 architecture entered "go" > /dev/null 2>&1 || bad "artgate: architecture enter refused"
if bash "$S/exec-initiative" phase INIT-0001 architecture skipped >/dev/null 2>&1; then
  bad "artgate: skip accepted with no reason note"
fi
bash "$S/exec-initiative" phase INIT-0001 architecture skipped "single-file change, no arch needed" > /dev/null 2>&1 || bad "artgate: reasoned skip refused"
ok "phase passed is artifact-gated; skipped requires a note"

# 32b. Plan-regression pipeline: once planning has passed, a run cannot
# start until the plan set is audited clean or waived; the phase gate
# refuses without a clean summary; the summary must name every plan.
d=$(fixture planreg)
cd "$d"
bash "$S/exec-initiative" new Regress > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-regress"
mkdir -p "$IDIR/plans"
printf '%s\n%s\n' "$FM" "$TASK" > "$IDIR/plans/INIT-0001-P01-probe.md"
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-initiative" phase INIT-0001 intake passed "ok" > /dev/null 2>&1 || bad "planreg: intake pass refused"
for ph in discovery architecture design specification; do
  bash "$S/exec-initiative" phase INIT-0001 "$ph" skipped "fixture: not needed" > /dev/null 2>&1 || bad "planreg: $ph skip refused"
done
bash "$S/exec-initiative" phase INIT-0001 planning entered "go" > /dev/null 2>&1 || bad "planreg: planning enter refused"
bash "$S/exec-initiative" phase INIT-0001 planning passed "1 plan" > /dev/null 2>&1 || bad "planreg: planning pass refused"
bash "$S/exec-initiative" phase INIT-0001 plan-regression entered "go" > /dev/null 2>&1 || bad "planreg: plan-regression enter refused"
bash "$S/exec-workspace" "$d/plan.md" > /dev/null 2>&1
if bash "$S/exec-run" "$d/plan.md" start >/dev/null 2>&1; then
  bad "planreg: run started after planning without plan-regression clearance"
fi
if bash "$S/exec-initiative" phase INIT-0001 plan-regression passed "premature" >/dev/null 2>&1; then
  bad "planreg: phase passed with no summary artifact"
fi
bash "$S/exec-plan-regression" "$d/plan.md" init > /dev/null 2>&1 || bad "planreg: init refused"
if bash "$S/exec-plan-regression" "$d/plan.md" check >/dev/null 2>&1; then
  bad "planreg: check passed with no audit row"
fi
AUDIT=$(bash "$S/exec-plan-regression" "$d/plan.md" audit)
printf -- '---\nkind: regression\nplan: INIT-0001-P01\nround: 1\n---\nPASS — 0 defects\n' > "$AUDIT"
printf '| INIT-0001-P01 | clean | regression-P01.md | — | 0 defects |\n' >> "$d/.executor/INIT-0001/plan-regression/summary.md"
bash "$S/exec-plan-regression" "$d/plan.md" check > /dev/null 2>&1 || bad "planreg: check refused a clean set"
bash "$S/exec-initiative" phase INIT-0001 plan-regression passed "1 plan clean" > /dev/null 2>&1 || bad "planreg: phase pass refused with clean summary"
bash "$S/exec-run" "$d/plan.md" start > /dev/null 2>&1 || bad "planreg: run refused after clearance"
ok "plan-regression gates the run and the phase log"

# 32c. Branch model: task branches fork from the plan tip, merge only on a
# clean R-verdict, abandon guards unique commits, and the topology audit
# catches a branch that names no task of the plan.
d=$(fixture branchmodel)
cd "$d"
bash "$S/exec-initiative" new Branch > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-branch"
mkdir -p "$IDIR/plans"
printf '%s\n%s\n' "$FM" "$TASK" > "$IDIR/plans/INIT-0001-P01-probe.md"
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
git add -A && git commit -qm init
bash "$S/exec-initiative" branch INIT-0001 > /dev/null 2>&1 || bad "branch: initiative branch refused"
# The fork point is recorded in INDEX.md — commit it, or the clean-tree
# guard on the next branch operation correctly refuses.
git add -A && git commit -qm "record fork point"
bash "$S/exec-branch" "$d/plan.md" start > /dev/null 2>&1 || bad "branch: plan branch start refused"
bash "$S/exec-workspace" "$d/plan.md" > /dev/null 2>&1
bash "$S/exec-run" "$d/plan.md" start > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
tb=$(bash "$S/exec-branch" "$d/plan.md" task start INIT-0001-P01-T01 2>/dev/null)
[ "$tb" = "task/INIT-0001-P01-T01" ] || bad "branch: task start printed '$tb'"
[ "$(git branch --show-current)" = "task/INIT-0001-P01-T01" ] || bad "branch: not on the task branch after start"
grep -qE "^INIT-0001-P01-T01: dispatched \(branch task/INIT-0001-P01-T01, base " "$W/progress.md" \
  || bad "branch: the ledger does not record the task branch and fork commit"
printf 'x\n' > api.ts
git add -A && git commit -qm "task work"
if bash "$S/exec-branch" "$d/plan.md" task merge INIT-0001-P01-T01 >/dev/null 2>&1; then
  bad "branch: task merge accepted with no verdict at all"
fi
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: NEEDS_FIX\n---\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
if bash "$S/exec-branch" "$d/plan.md" task merge INIT-0001-P01-T01 >/dev/null 2>&1; then
  bad "branch: task merge accepted a NEEDS_FIX verdict"
fi
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
bash "$S/exec-branch" "$d/plan.md" task merge INIT-0001-P01-T01 > /dev/null 2>&1 \
  || bad "branch: task merge refused a clean verdict"
[ "$(git branch --show-current)" = "plan/INIT-0001-P01" ] || bad "branch: not back on the plan branch after merge"
git show-ref --verify --quiet refs/heads/task/INIT-0001-P01-T01 && bad "branch: task branch survived the merge"
grep -qE "^INIT-0001-P01-T01: complete \(merge " "$W/progress.md" \
  || bad "branch: the merge commit is not recorded in the ledger"
bash "$S/exec-branch" "$d/plan.md" task start INIT-0001-P01-T01 > /dev/null 2>&1
printf 'y\n' > api.ts
git add -A && git commit -qm "more work"
if bash "$S/exec-branch" "$d/plan.md" task abandon INIT-0001-P01-T01 >/dev/null 2>&1; then
  bad "branch: abandon dropped unique commits without -f"
fi
bash "$S/exec-branch" "$d/plan.md" task abandon INIT-0001-P01-T01 -f > /dev/null 2>&1 \
  || bad "branch: abandon -f refused"
# Topology audit: a task branch naming no task of the plan is drift.
git checkout -q -b task/INIT-0001-P01-T09 plan/INIT-0001-P01
if bash "$S/exec-run" "$d/plan.md" check >/dev/null 2>&1; then
  bad "branch: topology audit passed on a task branch naming no task of the plan"
fi
git checkout -q plan/INIT-0001-P01
git branch -D task/INIT-0001-P01-T09 > /dev/null 2>&1
ok "task branches fork from the tip, merge on a clean verdict, and the topology audit fires"

# 32d. Sequential escape hatch: the flag is refused unless the dependency
# chain justifies it, and a justified plan lints clean.
d=$(fixture seqflag)
cd "$d"
SEQ_FM=$(printf '%s' "$FM" | sed -e 's/^tasks: 1$/tasks: 2/' -e 's/^execution_mode: inline$/execution_mode: inline\nsequential: true/')
TASK2=$'### Task 2: Second — `INIT-0001-P01-T02`

**Files:**
- Modify: `b.ts`
'
printf '%s\n%s\n%s\n' "$SEQ_FM" "$TASK" "$TASK2" > "$d/seq.md"
if bash "$S/exec-plan-lint" "$d/seq.md" >/dev/null 2>&1; then
  bad "seqflag: sequential: true linted clean with no dependency chain"
fi
TASK2_CHAINED=$'### Task 2: Second — `INIT-0001-P01-T02`

**Depends on:** `INIT-0001-P01-T01`

**Files:**
- Modify: `b.ts`
'
printf '%s\n%s\n%s\n' "$SEQ_FM" "$TASK" "$TASK2_CHAINED" > "$d/seq.md"
bash "$S/exec-plan-lint" "$d/seq.md" > /dev/null 2>&1 \
  || bad "seqflag: a justified sequential plan was refused"
ok "sequential: true requires the dependency chain to justify it"

# 33. Dispatch outcome sync: terminal ledger states close running rows;
# an in-fix boundary closes all but the newest live row.
d=$(fixture dispsync)
cd "$d"
bash "$S/exec-initiative" new Sync > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
printf -- '| Task | Role | Outcome |\n|---|---|---|\n| INIT-0001-P01-T01-R01 | IMPL | running |\n| INIT-0001-P01-T01-R02 | FIX | running |\n' > "$W/dispatches.md"
printf 'INIT-0001-P01-T01: in-fix\n' >> "$W/progress.md"
bash "$S/exec-run" plan.md start > /dev/null 2>&1
grep -q 'T01-R01 | IMPL | done |' "$W/dispatches.md" || bad "dispsync: in-fix did not close the older running row"
grep -q 'T01-R02 | FIX | running |' "$W/dispatches.md" || bad "dispsync: in-fix closed the live row too"
printf 'INIT-0001-P01-T01: complete\n' >> "$W/progress.md"
bash "$S/exec-run" plan.md start > /dev/null 2>&1
grep -q 'T01-R02 | FIX | complete |' "$W/dispatches.md" || bad "dispsync: terminal state did not close the last row"
ok "dispatch outcomes sync with ledger state"

# 34. Fix-round cap: five rounds maximum, counted by round NUMBER not
# line count; a recorded ruling is the escape hatch.
d=$(fixture fixcap)
cd "$d"
bash "$S/exec-initiative" new Cap > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
printf 'INIT-0001-P01-T01: fix round 1/5\nINIT-0001-P01-T01: fix round 2/5\nINIT-0001-P01-T01: fix round 1/5\nINIT-0001-P01-T01: fix round 2/5\n' >> "$W/progress.md"
bash "$S/exec-run" plan.md task INIT-0001-P01-T01 > /dev/null 2>&1 || bad "fixcap: max round 2 over 4 lines wrongly capped"
printf 'INIT-0001-P01-T01: fix round 5/5\n' >> "$W/progress.md"
if bash "$S/exec-run" plan.md task INIT-0001-P01-T01 >/dev/null 2>&1; then
  bad "fixcap: sixth round dispatched past the cap"
fi
printf '## INIT-0001-P01-T01 — adjudicated: remaining findings deferred to P02\n' >> "$W/rulings.md"
bash "$S/exec-run" plan.md task INIT-0001-P01-T01 > /dev/null 2>&1 || bad "fixcap: ruling did not release the cap"
ok "fix-round cap counts max round; rulings release it"

# 35. exec-fix-package assembles verdict findings + report + brief +
# context into one dispatch file; a missing verdict refuses.
d=$(fixture fixpkg)
cd "$d"
bash "$S/exec-initiative" new Fix > /dev/null 2>&1
printf '%s\n%s\n' "$FM" "$TASK" > "$d/plan.md"
bash "$S/exec-workspace" plan.md > /dev/null 2>&1
W="$d/.executor/INIT-0001/P01"
mkdir -p "$W/reviews/verdicts" "$W/briefs" "$W/reports"
printf -- '---\nkind: verdict\nspec_verdict: FAIL\nquality: NEEDS_FIXES\n---\n\n## 3. Findings\n\n- FINDMARK the contract is violated\n' > "$W/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md"
printf -- '---\nkind: brief\n---\n\nBRIEFMARK contract text\n' > "$W/briefs/INIT-0001-P01-T01-brief.md"
printf -- '---\nkind: context\n---\n\nCTXMARK seam text\n' > "$W/briefs/INIT-0001-P01-T01-context.md"
printf -- '---\nkind: report\n---\n\nREPMARK what was tried\n' > "$W/reports/INIT-0001-P01-T01-report.md"
bash "$S/exec-fix-package" plan.md INIT-0001-P01-T01 > /dev/null 2>&1 || bad "fixpkg: package generation failed"
PKG="$W/reviews/fix-packages/INIT-0001-P01-T01-R01-fix-package.md"
[ -f "$PKG" ] || bad "fixpkg: package not written to reviews/fix-packages/"
for m in FINDMARK BRIEFMARK CTXMARK REPMARK 'kind: fix-package'; do
  grep -q "$m" "$PKG" || bad "fixpkg: package missing $m"
done
grep -q '<!--' "$PKG" && bad "fixpkg: package carries an HTML comment"
if bash "$S/exec-fix-package" plan.md INIT-0001-P01-T02 >/dev/null 2>&1; then
  bad "fixpkg: missing verdict accepted"
fi
ok "exec-fix-package assembles findings + contract verbatim"

# 36. exec-context: Modify lines resolve annotated paths — backticked or
# bare — and trailing '(...)' annotations and ':N-M' ranges never reach
# the filesystem lookup. Regression: vocab P04 reported existing files
# as "does not exist yet" because 'content_store.py (add DbContentStore)'
# was looked up verbatim.
d=$(fixture ctxmod)
cd "$d"
bash "$S/exec-initiative" new Ctx > /dev/null 2>&1
printf 'export function probe() {}\n' > "$d/api.ts"
printf 'const plain = 1\n' > "$d/plain.ts"
commit_all "$d" "files"
{ printf '%s\n' "$FM"; printf '### Task 1: Probe — `INIT-0001-P01-T01`\n\n**Files:**\n- Modify: `api.ts` (add helper)\n- Modify: plain.ts:5-9\n\n**Interfaces:**\n- Consumes: api contract\n\n**Requirements:**\n- INIT-0001-SPEC-01-R01\n'; } > "$d/plan.md"
bash "$S/exec-context" plan.md 1 "$d/ctx.md" > /dev/null 2>&1
grep -q 'api.ts.*does not exist yet' "$d/ctx.md" && bad "ctxmod: annotated backticked path reported missing"
grep -q 'plain.ts.*does not exist yet' "$d/ctx.md" && bad "ctxmod: line-range path reported missing"
grep -q 'api.ts.*symbol skeleton' "$d/ctx.md" || bad "ctxmod: api.ts skeleton not extracted"
grep -q 'plain.ts.*symbol skeleton' "$d/ctx.md" || bad "ctxmod: plain.ts not found at HEAD"
ok "Modify annotations and line ranges resolve to real paths"

# 37. Requirement extraction covers paragraph-form items ('R21. text')
# and every heading shape, never matching R011 for R01.
d=$(fixture reqgram)
cd "$d"
printf -- '## Requirements\n\nR21. Alpha requirement text.\nR22. Beta requirement text.\n\n### R03 — Gamma heading\n\ngamma body\n\nR011. Not R01.\n' > "$d/spec.md"
out=$( . "$S/_exec-lib.sh"; exec_requirement_body "$d/spec.md" R21 )
case "$out" in *"Alpha requirement text"*) ;; *) bad "reqgram: paragraph form R21 not extracted ($out)";; esac
case "$out" in *Beta*) bad "reqgram: R21 bled into R22";; esac
out=$( . "$S/_exec-lib.sh"; exec_requirement_body "$d/spec.md" R03 )
case "$out" in *"gamma body"*) ;; *) bad "reqgram: heading form R03 not extracted ($out)";; esac
out=$( . "$S/_exec-lib.sh"; exec_requirement_body "$d/spec.md" R01 )
[ -z "$out" ] || bad "reqgram: R011 matched a lookup for R01"
ok "requirement extraction covers paragraph and heading grammars"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
