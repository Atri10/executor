---
description: Create a new Executor initiative — allocates INIT-NNNN, its store, and its docs root.
argument-hint: <initiative title>
---

!python3 ${CLAUDE_PLUGIN_ROOT}/skills/executor/scripts/executor new "$ARGUMENTS"

If the run above failed for a missing title, ask for one. Otherwise load the `executor` skill and run `executor next` for the first action.
