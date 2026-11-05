---
description: Run the engine loop — emits the single typed action the initiative is waiting on (PHASE-ENTER, DISPATCH, GATE, MERGE, CHANGE-SCOPE, …).
argument-hint: [INIT-ID]
---

!python3 ${CLAUDE_PLUGIN_ROOT}/skills/executor/scripts/executor next $ARGUMENTS

Follow the emitted action exactly: when it names a phase or a dispatch role, load the matching `executor-*` skill and do only what that skill prescribes. Do not improvise a next step — the journal records what the action implies.
