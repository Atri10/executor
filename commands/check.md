---
description: Verify the journal — hash chain, edges, liveness, layout, committed index; --secrets scans for leaked secrets.
argument-hint: [INIT-ID] [--secrets]
---

!python3 ${CLAUDE_PLUGIN_ROOT}/skills/executor/scripts/executor check $ARGUMENTS

If a violation is reported, run `/executor:doctor` and load the `executor` skill for repair routing. Do not hand-edit store files.
