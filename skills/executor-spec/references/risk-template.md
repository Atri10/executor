# Risk Template (Pre-Mortem)

The `risk` artifact: `kind: "risk"`, id `INIT-NNNN-RISK-NN`, answered by
an `author` dispatch to its `respond_to`. The narrative comes first and
every row traces to it; a risk list written without the narrative is a
checklist from another project.

A section is data, not markdown: `prose`, `bullets`, `tables`
(`columns` plus `rows`), and `code`. The engine renders the `.md` — a pipe
table or a fence inside a string is a `notMatch` rejection, and a row whose
cell count differs from its columns is `row_width`.

## Payload skeleton

```json
{"kind": "risk", "v": "v1", "dispatch_id": "D00031",
 "id": "INIT-0004-RISK-01",
 "title": "Cell placement pre-mortem",
 "summary": "Four risks, two mitigated, two accepted: placement latency at 8k tenants and a split-cell outage with no runbook entry.",
 "cites": ["INIT-0004-SPEC-01", "INIT-0004-ARCH-01"],
 "risks": [
   {"id": "R1", "risk": "The available-cell scan is linear, so placement latency triples above 2k tenants",
    "likelihood": "high", "impact": "high",
    "mitigation": "Index candidates by region in the store port; V05 measures p99 at 10k"},
   {"id": "R2", "risk": "Two tenants land on the same cell despite the isolation rule",
    "likelihood": "medium", "impact": "high",
    "mitigation": "Unique constraint on (tenant, cell) enforced by the adapter"},
   {"id": "R3", "risk": "A cell loses its disk and the runbook has no entry for a split cell",
    "likelihood": "low", "impact": "high",
    "mitigation": null},
   {"id": "R4", "risk": "The migration path back is untested",
    "likelihood": "medium", "impact": "medium",
    "mitigation": null}
 ],
 "sections": [
   {"id": "failure-history", "title": "The failure history",
    "prose": "Past tense. Fix a date far enough out that the failure has consequences. Three to eight sentences. Name what users and operators saw, not what the code did.",
    "code": [{"lang": "text", "source": "It is 2027-01. Cell placement shipped in September. By November, placement latency at 8k tenants had tripled, because the available-cell scan was linear and nobody measured it above 2k. Two tenants landed on the same cell despite the isolation rule, and when that cell lost its disk both were down for eleven hours — the runbook had no entry for a split cell. We rolled back in December and discovered the migration path back to single-cell routing had never been exercised."}]},
   {"id": "register", "title": "Risk register",
    "tables": [{"columns": ["Id", "Risk", "Likelihood", "Impact", "Mitigation", "Accepted as"],
                "rows": [["R1", "linear scan above 2k tenants", "high", "high", "region index", "not accepted"], ["R3", "split cell, no runbook entry", "low", "high", "none", "accepted — operator training tracked separately"]]}]},
   {"id": "signals", "title": "Signals that a risk is materializing",
    "tables": [{"columns": ["Risk", "Signal", "Threshold", "Who notices"],
                "rows": [["R1", "placement p99 latency", "above 120 ms for an hour", "the existing placement dashboard"]]}]},
   {"id": "rejected", "title": "Options that failed and why",
    "tables": [{"columns": ["Mitigation", "Why it failed"],
                "rows": [["shard by tenant hash", "does not bound a single tenant's impact, which is requirement R09"]]}]}
 ]}
```

`risks[]` is the typed register the fold reads: `id`, `risk`,
`likelihood`, `impact`, and `mitigation` (null when accepted without
one). The prose sections carry the reasoning — the narrative and the
signals — and every row in the register cites the narrative it came
from.

## Rules that keep this artifact useful

- **Every risk is a sentence about the world, not the code.** "The scan
  is linear" is a defect; "placement latency triples above 2k tenants
  because the scan is linear" is a risk with a threshold.
- **A mitigation is a checkable action or null.** "Be careful" is not a
  mitigation; an index plus the row that measures it is.
- **Accepted without mitigation is a valid disposition** — write the
  acceptance in the register's `Accepted as` cell so the human can
  overrule it at the gate.
- **Signals carry a number and a noticer.** A risk nobody can observe is
  a wish.
- `likelihood`/`impact` are one of `low`, `medium`, `high`; a number
  without a basis is noise.
- No credentials or real incident identifiers — name the dashboard,
  never a tenant.
