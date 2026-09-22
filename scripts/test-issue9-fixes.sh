#!/usr/bin/env bash
# Regression fixtures for the issue #9 fix plan.
#
# Each case recreates a reproduced failure against disposable synthetic
# repositories and asserts the fixed behavior. Run from the repo root:
#   bash scripts/test-issue9-fixes.sh
# Exit 0 = all cases pass; nonzero names the failing case.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT/skills/executor/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/issue9-fixes.XXXXXX")"
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
  printf '%s\n' "$d"
}
commit_all() { git -C "$1" add -A && git -C "$1" commit -qm "${2:-fixture}"; }

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
printf -- '| Task | Role | Mode | Agent | Status | Notes |\n|---|---|---|---|---|---|\n' > "$W/dispatches.md"
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

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
