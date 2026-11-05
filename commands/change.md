---
description: File a mid-run change request (the engine mints CR-NNNN and computes its blast radius), or list every change and its state.
argument-hint: [<payload.json|-> | --list] [INIT-ID]
---

To **list** existing changes:

```bash
python3 <plugin>/skills/executor/scripts/executor change --list [INIT-ID]
```

To **file** a change: author a `change_request` payload (schema in the `executor-initiative` skill), then:

```bash
python3 <plugin>/skills/executor/scripts/executor change <payload.json|-> [INIT-ID]
```

The reply reports the minted `CR-NNNN` and its blast radius — the tasks, criteria, artifacts, and plans it touches. The engine then drives a regression lane; do not edit specs or plans outside it.

$ARGUMENTS
