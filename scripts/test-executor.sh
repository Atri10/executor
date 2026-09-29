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

**Implements:** `INIT-0001-SPEC-01-R01`
**Depends on:** none

**Files:**
- Modify: `api.ts`

**Interfaces:**
- Consumes: api contract

**Requirements:**
- INIT-0001-SPEC-01-R01

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Implement**
- [ ] **Step 3: Run the test and see it pass**

Run: `bun test`
Expected: PASS
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
{ printf -- '---\nid: INIT-0001-P01\nspec: INIT-0001-S01\ninterfaces: []\ntasks: 1\nexecution_mode: inline\n---\n\n'; printf '%s\n' "$TASK"; printf '```markdown\n- Create: docs/executor/INIT-0002/x.md\n```\n'; } > "$d/plan.md"
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
# Brainstorming is required before planning: entry refused with no decided
# session feeding planning, accepted once one exists.
if bash "$S/exec-initiative" phase INIT-0001 planning entered "go" >/dev/null 2>&1; then
  bad "planreg: planning entered with no decided brainstorm session feeding planning"
fi
mkdir -p "$IDIR/brainstorm/sessions/20260928T000000Z-split"
printf -- '---\nkind: brainstorm\nid: null\ninitiative: INIT-0001\nmode: decision\nquestion: How does the spec split into plans?\nfeeds: [planning]\nstatus: active\ndecided: one-plan\ncreated_at: 2026-09-28T00:00:00Z\nupdated_at: 2026-09-28T00:00:00Z\n---\n\n## Options\n### A — one-plan\n### B — two-plans\n### C — per-component\n\n## Adversarial pass\nB doubles review cost.\n\n## Outcome\nA.\n' > "$IDIR/brainstorm/sessions/20260928T000000Z-split/session.md"
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
AUDIT=$(bash "$S/exec-plan-regression" "$d/plan.md" audit 01)
case "$AUDIT" in */regression-P01-R01.md) ;; *) bad "planreg: audit path not round-suffixed ($AUDIT)";; esac
printf -- '---\nkind: regression\nplan: INIT-0001-P01\nround: R01\nverdict: FAIL\nhigh: 1\nmedium: 0\nlow: 0\n---\n' > "$AUDIT"
printf '| INIT-0001-P01 | clean | regression-P01-R01.md | — | 1 defect |\n' >> "$d/.executor/INIT-0001/plan-regression/summary.md"
if bash "$S/exec-plan-regression" "$d/plan.md" check >/dev/null 2>&1; then
  bad "planreg: check passed a clean row whose latest audit is FAIL"
fi
AUDIT2=$(bash "$S/exec-plan-regression" "$d/plan.md" audit 02)
printf -- '---\nkind: regression\nplan: INIT-0001-P01\nround: R02\nverdict: PASS\nhigh: 0\nmedium: 0\nlow: 0\n---\n' > "$AUDIT2"
[ -f "$AUDIT" ] || bad "planreg: round-2 audit overwrote round 1"
[ "$(bash "$S/exec-plan-regression" "$d/plan.md" latest)" = "$AUDIT2" ] || bad "planreg: latest does not name the round-2 audit"
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
# Both variants are the full task fixture renumbered; they differ only in
# the dependency line, so the sequential rule is the only thing under test.
TASK2=$(printf '%s' "$TASK" | sed -e 's/Task 1: Probe — `INIT-0001-P01-T01`/Task 2: Second — `INIT-0001-P01-T02`/')
TASK2_CHAINED=$(printf '%s' "$TASK2" | sed -e 's/^\*\*Depends on:\*\* none$/**Depends on:** `INIT-0001-P01-T01`/')
printf '%s\n%s\n%s\n' "$SEQ_FM" "$TASK" "$TASK2" > "$d/seq.md"
if bash "$S/exec-plan-lint" "$d/seq.md" >/dev/null 2>&1; then
  bad "seqflag: sequential: true linted clean with no dependency chain"
fi
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

# 38. Brainstorm entry gates: `specification entered` and `planning
# entered` refuse until a decided (status: active) session's feeds: names
# the phase. A draft session, or one feeding a different phase, does not
# count. The phase ladder is walked with minimal deliverables so the gate
# under test is the brainstorm check, not an ordering failure.
d=$(fixture entrygate)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-probe"
SDIR="$IDIR/brainstorm/sessions/s1"
mkdir -p "$SDIR" "$IDIR/discovery" "$IDIR/architecture" "$IDIR/specs" "$IDIR/risks" "$IDIR/verification" "$IDIR/plans"
printf -- '---\nid: INIT-0001-RSCH-01\n---\n\nx\n' > "$IDIR/discovery/INIT-0001-RSCH-01-r.md"
printf -- '---\nid: INIT-0001-ARCH-01\n---\n\nx\n' > "$IDIR/architecture/INIT-0001-ARCH-01-a.md"
bash "$S/exec-initiative" phase INIT-0001 intake passed "ok" >/dev/null 2>&1
bash "$S/exec-initiative" phase INIT-0001 discovery entered >/dev/null 2>&1
bash "$S/exec-initiative" phase INIT-0001 discovery passed "picked" >/dev/null 2>&1
bash "$S/exec-initiative" phase INIT-0001 architecture entered >/dev/null 2>&1
bash "$S/exec-initiative" phase INIT-0001 architecture passed "ok" >/dev/null 2>&1
bash "$S/exec-initiative" phase INIT-0001 design entered >/dev/null 2>&1
bash "$S/exec-initiative" phase INIT-0001 design passed "waived" >/dev/null 2>&1

# No session at all -> specification refuses.
if bash "$S/exec-initiative" phase INIT-0001 specification entered >/dev/null 2>&1; then
  bad "entrygate: specification entered with no brainstorm session"
fi
# A draft session does not count.
printf -- '---\nkind: brainstorm\nstatus: draft\nfeeds: [specification]\ndecided: null\n---\n\n## Options\n\nx\n' > "$SDIR/session.md"
if bash "$S/exec-initiative" phase INIT-0001 specification entered >/dev/null 2>&1; then
  bad "entrygate: specification entered on a draft session"
fi
# An active session feeding only planning does not open specification.
printf -- '---\nkind: brainstorm\nstatus: active\nfeeds: [planning]\ndecided: A\n---\n\n## Options\n\nx\n' > "$SDIR/session.md"
if bash "$S/exec-initiative" phase INIT-0001 specification entered >/dev/null 2>&1; then
  bad "entrygate: specification entered on a session feeding planning"
fi
# An active session feeding specification opens the gate.
printf -- '---\nkind: brainstorm\nstatus: active\nfeeds: [specification]\ndecided: A\n---\n\n## Options\n\nx\n' > "$SDIR/session.md"
bash "$S/exec-initiative" phase INIT-0001 specification entered >/dev/null 2>&1 \
  || bad "entrygate: decided specification session refused"

# Now satisfy specification's artifacts and pass it, then gate planning.
printf -- '---\nid: INIT-0001-SPEC-01\n---\n\nx\n' > "$IDIR/specs/INIT-0001-SPEC-01-s.md"
printf -- '---\nid: INIT-0001-RISK-01\n---\n\nx\n' > "$IDIR/risks/INIT-0001-RISK-01-r.md"
printf -- '---\nid: INIT-0001-VRFY-01\n---\n\nx\n' > "$IDIR/verification/INIT-0001-VRFY-01-v.md"
bash "$S/exec-initiative" phase INIT-0001 specification passed "ok" >/dev/null 2>&1 \
  || bad "entrygate: specification passed refused with artifacts present"

# The specification session does not feed planning -> planning refuses.
if bash "$S/exec-initiative" phase INIT-0001 planning entered >/dev/null 2>&1; then
  bad "entrygate: planning entered on a specification-only session"
fi
# A session feeding planning opens the gate.
printf -- '---\nkind: brainstorm\nstatus: active\nfeeds: [specification, planning]\ndecided: A\n---\n\n## Options\n\nx\n' > "$SDIR/session.md"
bash "$S/exec-initiative" phase INIT-0001 planning entered >/dev/null 2>&1 \
  || bad "entrygate: decided planning session refused"
ok "brainstorm sessions gate specification and planning entry"

# 39. exec-id allocates BRN ids and increments past existing ones — a
# session already carrying INIT-0001-BRN-01 in its frontmatter must make
# the next allocation 02, so concurrent sessions never share an id.
d=$(fixture brnid)
cd "$d"
bash "$S/exec-initiative" new Brn > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-brn"
first=$(bash "$S/exec-id" INIT-0001 BRN)
[ "$first" = "INIT-0001-BRN-01" ] || bad "brnid: first allocation was '$first'"
mkdir -p "$IDIR/brainstorm/sessions/s1"
printf -- '---\nkind: brainstorm\nid: INIT-0001-BRN-01\nstatus: draft\n---\n\n## Options\n\nx\n' > "$IDIR/brainstorm/sessions/s1/session.md"
second=$(bash "$S/exec-id" INIT-0001 BRN)
[ "$second" = "INIT-0001-BRN-02" ] || bad "brnid: allocation past BRN-01 returned '$second'"
ok "exec-id allocates and increments BRN ids"

# 40. exec-plan-regression check: the clearance gate reads the LATEST
# audit round's verdict, so a 'clean' row against a FAIL audit is caught,
# and a PASS re-audit round clears it. Waived needs a note.
d=$(fixture regcheck)
cd "$d"
bash "$S/exec-initiative" new Reg > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-reg"
printf '%s\n%s\n' "$FM" "$TASK" > "$IDIR/plans/INIT-0001-P01-plan.md"
RD="$d/.executor/INIT-0001/plan-regression"
bash "$S/exec-plan-regression" "$IDIR/plans/INIT-0001-P01-plan.md" init > /dev/null 2>&1
# Audit round 1 FAILs.
printf -- '---\nkind: regression\nverdict: FAIL\n---\n\nFAIL — 2 defects\n' > "$RD/regression-P01-R01.md"
# A 'clean' row is a lie while the latest audit FAILs.
printf '| INIT-0001-P01 | clean | regression-P01-R01.md | fix-P01-R01.md | |\n' >> "$RD/summary.md"
if bash "$S/exec-plan-regression" "$IDIR/plans/INIT-0001-P01-plan.md" check >/dev/null 2>&1; then
  bad "regcheck: clean row accepted while latest audit FAILs"
fi
# A PASS re-audit round clears the row.
printf -- '---\nkind: regression\nverdict: PASS\n---\n\nPASS — 0 defects\n' > "$RD/regression-P01-R02.md"
bash "$S/exec-plan-regression" "$IDIR/plans/INIT-0001-P01-plan.md" check >/dev/null 2>&1 \
  || bad "regcheck: clean row refused after a PASS re-audit"
# A waived row with no note is a self-granted waiver.
perl -pi -e 's/\| INIT-0001-P01 \| clean \|/| INIT-0001-P01 | waived |/' "$RD/summary.md"
if bash "$S/exec-plan-regression" "$IDIR/plans/INIT-0001-P01-plan.md" check >/dev/null 2>&1; then
  bad "regcheck: waived row accepted with no note"
fi
perl -pi -e 's/(INIT-0001-P01 \| waived \| regression-P01-R01.md \| fix-P01-R01.md \|) \|/$1 human waived low-severity naming |/' "$RD/summary.md"
bash "$S/exec-plan-regression" "$IDIR/plans/INIT-0001-P01-plan.md" check >/dev/null 2>&1 \
  || bad "regcheck: waived row with a note refused"
ok "plan-regression check reads the latest audit round and gates waivers"

# 41. exec-store-check B2: a pre-initiative session at the store root that
# claims an initiative is adoption-in-name-only — it was never moved.
d=$(fixture storeb2)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
RDIR="$d/docs/executor/brainstorm/sessions/2026-09-28-feature"
mkdir -p "$RDIR"
printf -- '---\nkind: brainstorm\ninitiative: INIT-0001\nstatus: draft\ndecided: null\nquestion: q\n---\n\n## Options\n\nx\n' > "$RDIR/session.md"
out=$(bash "$S/exec-store-check" 2>&1 || true)
echo "$out" | grep -q 'adopt it' || bad "storeb2: root session claiming an initiative not flagged"
ok "store-check flags a root session adopted in name only"

# 42. exec-store-check B3: a session carrying an allocated BRN id is a
# document and needs a Documents-table row; an id that is not BRN-nn is
# refused. A correctly-registered session passes.
d=$(fixture storeb3)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-probe"
SDIR="$IDIR/brainstorm/sessions/s1"
mkdir -p "$SDIR"
printf -- '---\nkind: brainstorm\nid: INIT-0001-BRN-01\ninitiative: INIT-0001\nstatus: draft\ndecided: null\nquestion: q\n---\n\n## Options\n\nx\n' > "$SDIR/session.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "storeb3: BRN id with no Documents row passed store check"
fi
regdoc "$IDIR" INIT-0001-BRN-01 brainstorm draft "brainstorm/sessions/s1/session.md"
bash "$S/exec-store-check" >/dev/null 2>&1 \
  || bad "storeb3: registered BRN session still failed store check"
# A non-BRN id on a session is refused.
perl -pi -e 's/id: INIT-0001-BRN-01/id: INIT-0001-FOO-01/' "$SDIR/session.md"
perl -pi -e 's/INIT-0001-BRN-01/INIT-0001-FOO-01/' "$IDIR/INDEX.md"
if bash "$S/exec-store-check" >/dev/null 2>&1; then
  bad "storeb3: a session with a non-BRN id passed store check"
fi
ok "store-check requires a Documents row and a BRN id for sessions"

# 43. exec-store-check P1: an initiative that entered execution with the
# plan-regression gate unpassed is flagged — and a passed gate requires
# the clearance summary to exist on disk.
d=$(fixture storep1)
cd "$d"
bash "$S/exec-initiative" new Probe > /dev/null 2>&1
IDIR="$d/docs/executor/INIT-0001-probe"
# Mark execution entered (and the branch it implies) without passing
# plan-regression.
perl -pi -e 's/^\| execution \| — \| — \|/| execution | 2026-09-28 | — |/' "$IDIR/INDEX.md"
perl -pi -e 's/^\*\*Status:\*\* active/**Status:** active\n\n**Branch:** initiative\/INIT-0001 (forked 2026-09-28)/' "$IDIR/INDEX.md"
out=$(bash "$S/exec-store-check" 2>&1 || true)
echo "$out" | grep -q 'plan-regression' || bad "storep1: execution entered without plan-regression not flagged"
ok "store-check flags execution entered without plan-regression clearance"

# ---------------------------------------------------------------------
# Thin-controller engine: exec-step, exec-supervise, exec-report.
# These assert the contracts the redesign exists to enforce, each of which
# was a reproduced failure mode — not the implementation's shape.

eng=$(fixture engine)
mkdir -p "$eng/docs/executor/INIT-0001-x/plans"
ENGPLAN="$eng/docs/executor/INIT-0001-x/plans/INIT-0001-P01.md"
cat > "$ENGPLAN" <<'PLANEOF'
---
id: INIT-0001-P01
initiative: INIT-0001
kind: plan
title: Engine probe
status: active
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
spec: INIT-0001-SPEC-01
---

# Plan

### Task 1: First — `INIT-0001-P01-T01`
**Depends on:** `none`

### Task 2: Second — `INIT-0001-P01-T02`
**Depends on:** `INIT-0001-P01-T01`
PLANEOF
commit_all "$eng" plan
cd "$eng"
WS="$eng/.executor/INIT-0001/P01"
bash "$S/exec-workspace" "$ENGPLAN" >/dev/null

# Rewrite the dispatch log to a known state. The seed has no Last-Seen
# column; writing one also proves the readers locate columns by name.
engrow() { # started outcome
  cat > "$WS/dispatches.md" <<EOF
---
kind: dispatches
plan: INIT-0001-P01
created_at: 2026-09-12T07:00:00Z
updated_at: 2026-09-12T07:00:00Z
---

| Task | Role | Model | Agent | Branch | Started | Outcome | Context | Last-Seen |
|---|---|---|---|---|---|---|---|---|
| INIT-0001-P01-T01 | IMPL-P01-T01 | top | g1 | task/T01 | $1 | $2 | brief.md | $1 |
EOF
}
engledger() { printf '%s\n' "$1" >> "$WS/progress.md"; }
OLD5=$(TZ=UTC date -u -v-5d +%Y-%m-%d 2>/dev/null || date -u -d '5 days ago' +%Y-%m-%d)
TODAYD=$(date -u +%Y-%m-%d)
rm -f "$WS/state/.step-stamp"

out=$(bash "$S/exec-step" "$ENGPLAN" 2>/dev/null)
case "$out" in
  "DISPATCH INIT-0001-P01-T01"*) ok "step: a fresh run dispatches its first task" ;;
  *) bad "step: fresh run emitted '$out', expected a DISPATCH of T01" ;;
esac

engrow "$TODAYD" running
out=$(bash "$S/exec-step" "$ENGPLAN" 2>/dev/null)
[ "$out" = "WAIT" ] && ok "step: a live worker blocks new dispatches" \
  || bad "step: open row emitted '$out', expected WAIT"

# The failure this whole redesign exists to prevent: a worker that FINISHED
# but whose row was never closed must be reported, never re-dispatched —
# a revive over a completed artifact is a duplicate agent on one task.
printf '# Report: done\n' > "$WS/reports/INIT-0001-P01-T01-report.md"
out=$(bash "$S/exec-step" "$ENGPLAN" 2>/dev/null)
case "$out" in
  "REPORT "*) ok "step: output on disk outranks every staleness clock" ;;
  *) bad "step: finished worker emitted '$out', expected REPORT" ;;
esac
rm -f "$WS/reports/INIT-0001-P01-T01-report.md"

# The ladder must advance and must stop. Attempt counts come from the
# dispatch log, never a counter file a worker could delete.
engrow "$OLD5" running
[ "$(bash "$S/exec-supervise" "$ENGPLAN" 2>/dev/null)" = "REVIVE INIT-0001-P01-T01" ] \
  && ok "supervise: a first failure resumes the same agent" \
  || bad "supervise: first failure did not emit REVIVE"
engrow "$OLD5" revived-rv1
[ "$(bash "$S/exec-supervise" "$ENGPLAN" 2>/dev/null)" = "REDISPATCH INIT-0001-P01-T01" ] \
  && ok "supervise: a resumed worker escalates to a fresh agent" \
  || bad "supervise: second failure did not emit REDISPATCH"
engrow "$OLD5" revived-rv2
[ "$(bash "$S/exec-supervise" "$ENGPLAN" 2>/dev/null)" = "ADJUDICATE INIT-0001-P01-T01" ] \
  && ok "supervise: a spent ladder escalates to adjudication" \
  || bad "supervise: exhausted ladder did not emit ADJUDICATE"

# gate-on-commit: nothing reaches state unreviewed, and a refusal writes
# nothing at all (a half-written ledger is worse than an unwritten one).
engrow "$OLD5" complete
printf '# Report: built\n' > "$WS/reports/INIT-0001-P01-T01-report.md"
bash "$S/exec-report" "$ENGPLAN" "$WS/reports/INIT-0001-P01-T01-report.md" aaa1111 bbb2222 >/dev/null 2>&1 || true
grep -q 'INIT-0001-P01-T01: complete' "$WS/progress.md" \
  && bad "report: an unreviewed task was ledgered complete" \
  || ok "report: an unreviewed task never reaches the ledger"

cat > "$WS/reviews/verdicts/INIT-0001-P01-T01-R01-verdict.md" <<'VEOF'
---
kind: verdict
task: INIT-0001-P01-T01
round: R01
spec_verdict: NEEDS_FIX
quality: CHANGES_REQUESTED
---
VEOF
bash "$S/exec-report" "$ENGPLAN" "$WS/reports/INIT-0001-P01-T01-report.md" aaa1111 bbb2222 >/dev/null 2>&1 || true
grep -q 'INIT-0001-P01-T01: complete' "$WS/progress.md" \
  && bad "report: a NEEDS_FIX verdict was committed" \
  || ok "report: a NEEDS_FIX verdict blocks the commit"

# A later NEEDS_FIX must not be cleared by an earlier clean round.
cat > "$WS/reviews/verdicts/INIT-0001-P01-T01-R02-verdict.md" <<'VEOF'
---
kind: verdict
task: INIT-0001-P01-T01
round: R02
spec_verdict: PASS
quality: APPROVED
---
VEOF
bash "$S/exec-report" "$ENGPLAN" "$WS/reports/INIT-0001-P01-T01-report.md" aaa1111 bbb2222 >/dev/null 2>&1
grep -q 'INIT-0001-P01-T01: complete' "$WS/progress.md" \
  && ok "report: a clean latest verdict commits and closes the row" \
  || bad "report: a clean verdict did not commit"
grep -qE '^\| INIT-0001-P01-T01 \|.*\| complete \|' "$WS/dispatches.md" \
  && ok "report: commit closes the task's dispatch row" \
  || bad "report: commit left the dispatch row open"

# A second commit is refused, not duplicated.
before=$(grep -c 'complete' "$WS/progress.md")
bash "$S/exec-report" "$ENGPLAN" "$WS/reports/INIT-0001-P01-T01-report.md" aaa1111 bbb2222 >/dev/null 2>&1 || true
[ "$(grep -c 'complete' "$WS/progress.md")" = "$before" ] \
  && ok "report: a completed task cannot be committed twice" \
  || bad "report: re-committing duplicated the ledger line"

# The livelock guard: an action the actuators keep refusing must become a
# recorded adjudication instead of a silent infinite loop.
rm -f "$WS/state/.step-stamp"
bash "$S/exec-step" "$ENGPLAN" >/dev/null 2>&1
bash "$S/exec-step" "$ENGPLAN" >/dev/null 2>&1
bash "$S/exec-step" "$ENGPLAN" >/dev/null 2>&1
out=$(bash "$S/exec-step" "$ENGPLAN" 2>/dev/null)
case "$out" in
  "ADJUDICATE loop:"*) ok "step: a no-progress loop escalates instead of spinning" ;;
  *) bad "step: repeated unchanged emits stayed at '$out'" ;;
esac
engledger 'INIT-0001-P01-T02: dispatched (branch task/T02, base aaa1111)'
out=$(bash "$S/exec-step" "$ENGPLAN" 2>/dev/null)
case "$out" in
  "ADJUDICATE loop:"*) bad "step: a real state change did not reset the counter" ;;
  *) ok "step: a real state change resets the no-progress counter" ;;
esac

# Unsolicited human input is the ingress a pump needs; a stop must be a
# recorded event with a state change, not a judgment call.
out=$(bash "$S/exec-ruling" "$ENGPLAN" INIT-0001-P01-T01 "halt" "spec assumption is wrong" "work paused" \
        --unsolicited "stop everything — the spec assumption is wrong" --stop 2>&1 || true)
case "$out" in
  *"STOP INIT-0001-P01:"*) ok "ruling: a stop prints one relayable STOP line" ;;
  *) bad "ruling: a stop printed no STOP line" ;;
esac
grep -q 'stop everything — the spec assumption is wrong' "$WS/rulings.md" \
  && ok "ruling: unsolicited human words are stored verbatim" \
  || bad "ruling: the human's words were not stored verbatim"
grep -q '| INIT-0001-P01 | .*blocked' "$eng/.executor/INDEX.md" \
  && ok "ruling: a stop blocks the run" \
  || bad "ruling: a stop did not block the run"
bash "$S/exec-ruling" "$ENGPLAN" T d w c --stop >/dev/null 2>&1 \
  && bad "ruling: a bare --stop was accepted" \
  || ok "ruling: --stop without --unsolicited is refused"

# ---------------------------------------------------------------------
# Autonomy: which phase gates may clear without a human, and how a human
# takes one back. The contract that matters most is the failure direction:
# every ambiguity must resolve to deny.

au=$(fixture autonomy)
cd "$au"
bash "$S/exec-initiative" new Auto > /dev/null 2>&1
AIDIR="$au/docs/executor/INIT-0001-auto"
# `|| true` on the setup transitions: intake is already entered by the
# seed, so re-entering it is correctly refused. Under `set -e` an expected
# refusal inside a fixture aborts the suite before any assertion runs.
for ph in intake discovery architecture design; do
  bash "$S/exec-initiative" phase INIT-0001 $ph entered >/dev/null 2>&1 || true
  bash "$S/exec-initiative" phase INIT-0001 $ph skipped "smoke scaffolding" >/dev/null 2>&1 || true
done
mkdir -p "$AIDIR/brainstorm/sessions/s1"
printf -- '---\nkind: brainstorm\nstatus: active\nfeeds: [specification]\ndecided: A\n---\n\n## Options\n\nx\n' \
  > "$AIDIR/brainstorm/sessions/s1/session.md"
bash "$S/exec-initiative" phase INIT-0001 specification entered >/dev/null 2>&1

# No policy file: an auto-pass must be refused, never defaulted.
bash "$S/exec-gate" INIT-0001 specification --auto >/dev/null 2>&1 \
  && bad "autonomy: auto-passed with no policy file" \
  || ok "autonomy: no policy file refuses an auto-pass"
grep -q 'auto-passed' "$AIDIR/INDEX.md" \
  && bad "autonomy: a refused auto-pass still recorded" \
  || ok "autonomy: a refused auto-pass writes nothing"

autonomy_policy() { # enabled mode
  cat > "$AIDIR/autonomous.md" <<EOF
---
kind: autonomous
initiative: INIT-0001
enabled: $1
---

| Phase | Mode | Why |
|---|---|---|
| specification | $2 | |
EOF
}

autonomy_policy false allow
bash "$S/exec-gate" INIT-0001 specification --auto >/dev/null 2>&1 \
  && bad "autonomy: auto-passed under a disabled policy" \
  || ok "autonomy: a disabled policy refuses an auto-pass"

autonomy_policy true deny
bash "$S/exec-gate" INIT-0001 specification --auto >/dev/null 2>&1 \
  && bad "autonomy: auto-passed a deny-mode phase" \
  || ok "autonomy: mode deny refuses an auto-pass"
[ "$(bash "$S/exec-gate" INIT-0001 specification --policy)" = "INIT-0001 specification: deny" ] \
  && ok "autonomy: --policy reports the declared mode" \
  || bad "autonomy: --policy did not report the mode"

# A pick-class phase is one a script cannot decide: bash counts files, it
# cannot choose between designs. `allow` without a recorded verdict must
# still refuse, and must say why.
autonomy_policy true allow
bash "$S/exec-gate" INIT-0001 specification --auto >/dev/null 2>&1 \
  && bad "autonomy: a pick-class gate was decided without a verdict" \
  || ok "autonomy: pick-class without a scored verdict is refused"

mkdir -p "$AIDIR/specs" "$AIDIR/risks" "$AIDIR/verification" "$AIDIR/verdicts"
printf -- '---\nid: INIT-0001-SPEC-01\ninitiative: INIT-0001\nkind: spec\nstatus: active\ntitle: Smoke spec\ncreated_at: 2026-09-29T00:00:00Z\nupdated_at: 2026-09-29T00:00:00Z\nsupersedes: null\nsuperseded_by: null\nspec: null\nrequirements_count: 1\n---\n\n## R01 — A requirement\n\nBody.\n' > "$AIDIR/specs/INIT-0001-SPEC-01-smoke.md"
printf -- '---\nid: INIT-0001-RISK-01\ninitiative: INIT-0001\nkind: risk\nstatus: active\ntitle: Smoke risk\ncreated_at: 2026-09-29T00:00:00Z\nupdated_at: 2026-09-29T00:00:00Z\nsupersedes: null\nsuperseded_by: null\n---\n\nx\n' > "$AIDIR/risks/INIT-0001-RISK-01-smoke.md"
printf -- '---\nid: INIT-0001-VRFY-01\ninitiative: INIT-0001\nkind: verification\nstatus: active\ntitle: Smoke vrfy\ncreated_at: 2026-09-29T00:00:00Z\nupdated_at: 2026-09-29T00:00:00Z\nsupersedes: null\nsuperseded_by: null\nspec: INIT-0001-SPEC-01\ncriteria_count: 1\nevidence_types: [unit]\n---\n\n| V01 | R01 verified by unit test | unit |\n' > "$AIDIR/verification/INIT-0001-VRFY-01-smoke.md"
printf -- '---\nkind: verdict\nspec_verdict: PASS\nquality: APPROVED\n---\n' > "$AIDIR/verdicts/INIT-0001-SPEC-01-scored-verdict.md"

bash "$S/exec-gate" INIT-0001 specification --auto >/dev/null 2>&1 \
  && ok "autonomy: a pick-class gate with a recorded verdict auto-passes" \
  || bad "autonomy: a permitted auto-pass was refused"
# Marker AND date: the marker says no human was involved, the date keeps
# the row ordered. A date alone is indistinguishable from a human pass.
grep -qE '^\| specification \| [^|]*\| \*\*auto-passed\*\* [0-9]{4}-[0-9]{2}-[0-9]{2} \|' "$AIDIR/INDEX.md" \
  && ok "autonomy: the phase log records a typed auto-pass, not a human pass" \
  || bad "autonomy: the auto-pass marker or date is missing from the phase log"
[ "$(bash "$S/exec-step" INIT-0001 2>/dev/null)" = "PHASE-ENTER INIT-0001 planning" ] \
  && ok "autonomy: exec-step advances past an auto-passed phase" \
  || bad "autonomy: exec-step did not advance past an auto-passed phase"

# Taking it back. Only a phase that actually finished can be superseded,
# and superseding reopens it — otherwise a human who rejects an autonomous
# pass would have to hand-edit the log.
bash "$S/exec-initiative" phase INIT-0001 specification superseded "the human rejected the design" >/dev/null 2>&1 \
  && ok "autonomy: an auto-pass can be superseded by a human" \
  || bad "autonomy: superseding an auto-passed phase was refused"
grep -qE '^\| specification \| — \| \*\*superseded\*\*' "$AIDIR/INDEX.md" \
  && ok "autonomy: supersession clears Entered and marks the gate" \
  || bad "autonomy: supersession did not reopen the phase"
[ "$(bash "$S/exec-step" INIT-0001 2>/dev/null)" = "PHASE-ENTER INIT-0001 specification" ] \
  && ok "autonomy: exec-step re-enters a superseded phase" \
  || bad "autonomy: exec-step did not re-enter a superseded phase"

bash "$S/exec-initiative" phase INIT-0001 handoff superseded "no such gate" >/dev/null 2>&1 \
  && bad "autonomy: superseded a phase that never passed" \
  || ok "autonomy: a never-passed phase cannot be superseded"
# `planning` has its own brainstorm-entry requirement, so this setup step
# may legitimately be refused; the assertion below is about the reason
# note, not about whether the phase could be entered here.
bash "$S/exec-initiative" phase INIT-0001 planning entered >/dev/null 2>&1 || true
bash "$S/exec-initiative" phase INIT-0001 planning skipped "smoke" >/dev/null 2>&1 || true
bash "$S/exec-initiative" phase INIT-0001 planning superseded "" >/dev/null 2>&1 \
  && bad "autonomy: superseded without stating a reason" \
  || ok "autonomy: supersession requires a stated reason"
before=$(cksum < "$AIDIR/INDEX.md")
# Check-only exits 1 when the gate is not ready — that is the answer, not
# a suite failure, and the point of the assertion is what it did or did
# not write on the way out.
bash "$S/exec-gate" INIT-0001 planning >/dev/null 2>&1 || true
after=$(cksum < "$AIDIR/INDEX.md")
case "$after" in
  "$before") ok "autonomy: check-only mode mutates nothing" ;;
  *) bad "autonomy: check-only mode wrote to the phase log" ;;
esac

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
