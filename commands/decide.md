---
description: Record a human decision — gate_decision, ruling, resume, or halt.
argument-hint: [INIT-ID]
---

A human decision is a payload whose `kind` is `gate_decision`, `ruling`, `resume`, or `halt` — the engine rejects every other kind here, and worker payloads never go through `decide`. Author the payload to the schema documented in the `executor-initiative` skill, then submit it:

```bash
python3 <plugin>/skills/executor/scripts/executor decide <payload.json|-> [INIT-ID]
```

The launcher resolves its engine relative to itself, so the path works from the plugin install directory and from any project directory. Use `-` and stdin rather than leaving a scratch file behind.

$ARGUMENTS
