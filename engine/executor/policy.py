# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Engine tunables, and the files that set them per project and per initiative.

Precedence, lowest first: DEFAULTS, the project file docs/executor/config.json,
the initiative file docs/executor/<INIT>/meta/policy.json. Both files are
committed with the docs, so a change to a threshold is reviewed like any other
change. Each file carries a version key `v`, so an unknown version is refused
rather than misread.

The engine never decides from a file. It journals the effective values as a
`policy` event at creation and again whenever they differ from the ones in
force, and every decision folds from that event. A decision can then be traced
to the policy in force when it was made, and a re-fold from the journal gives
the same answer on any machine.
"""
from __future__ import annotations

import copy
from pathlib import Path
from .paths import autonomy_file, initiative_policy_file, project_policy_file
from .schemas import POLICY, validate
from .store import PHASES, ExecError, Rejection, read_json, sha256

DEFAULTS: dict = {
    "max_fix_rounds": 5,        # fix dispatches per task before the run escalates
    "max_audit_rounds": 5,      # audit rounds per artifact or plan before escalation
    "max_evidence_tries": 5,    # evidence attempts per criterion before escalation
    "max_plans": 9,             # plans per initiative
    "spawn_retry_cap": 2,       # lost dispatches per entity and schema
    "suspect_s": 1800,          # silence before check warns about a dispatch
    "deadline_s": 3600,         # silence after which the next poll abandons it
    "clean_quality": ["APPROVED", "APPROVED_WITH_ROUTED_RESIDUALS"],
}

# Inclusive bounds for the integer tunables. max_plans stops at 99 because plan
# ids carry two digits (P01..P99).
BOUNDS: dict[str, tuple[int, int]] = {
    "max_fix_rounds": (1, 50),
    "max_audit_rounds": (1, 50),
    "max_evidence_tries": (1, 50),
    "max_plans": (1, 99),
    "spawn_retry_cap": (0, 20),
    "suspect_s": (60, 604800),
    "deadline_s": (60, 604800),
}


def policy_sha(values: dict) -> str:
    return sha256(values)


def default_state() -> dict:
    """The policy a journal is folded under before its first policy event. Autonomy
    is fail-closed: every phase denied until a recorded policy says otherwise."""
    values = copy.deepcopy(DEFAULTS)
    values["autonomy"] = normalize_autonomy({}, PHASES)
    return {"values": values, "sources": {key: "default" for key in DEFAULTS},
            "sha": policy_sha(values), "recorded": False}


# Autonomy modes per phase. Fail closed: only the exact words allow or gate permit an
# unattended pass. Anything else, including a misspelling, a non-string and a missing
# phase, is deny. A pick-class phase is handled by the engine, never by this table.
AUTONOMY_MODES = ("deny", "gate", "allow")


def normalize_autonomy(raw, phases) -> dict[str, str]:
    """Every phase mapped to deny unless the file names it with an exact allowed mode.
    Pure and total, so an unreadable or partial file degrades to deny, never to allow."""
    source = raw if isinstance(raw, dict) else {}
    return {p: (source[p] if isinstance(source.get(p), str) and source[p] in AUTONOMY_MODES
                else "deny")
            for p in phases}


def load_policy(root: Path, init_id: str) -> tuple[dict, dict]:
    """The effective policy, and per key the layer its value came from.

    A missing file contributes nothing. Anything else that is unreadable,
    malformed, out of range or self-contradictory raises ExecError with code
    policy_invalid: the engine stops rather than deciding from a half-read file."""
    values = copy.deepcopy(DEFAULTS)
    sources = {key: "default" for key in DEFAULTS}
    layers = (("project", project_policy_file(root)),
              ("initiative", initiative_policy_file(root, init_id)))
    for layer, path in layers:
        if not path.exists():
            continue
        doc = read_json(path)
        if not isinstance(doc, dict):
            raise ExecError(f"{layer} policy {path.name} is unreadable or not a "
                            f"JSON object", "policy_invalid")
        try:
            validate(doc, POLICY)
        except Rejection as exc:
            raise ExecError(f"{layer} policy {path.name}: {exc}", "policy_invalid") from exc
        for key, value in doc.items():
            if key == "v":
                continue
            if key in BOUNDS:
                low, high = BOUNDS[key]
                if not low <= value <= high:
                    raise ExecError(f"{layer} policy {path.name}: {key} must be "
                                    f"between {low} and {high}, got {value}",
                                    "policy_invalid")
            values[key] = value
            sources[key] = layer
    if values["suspect_s"] >= values["deadline_s"]:
        raise ExecError("suspect_s must be below deadline_s", "policy_invalid")
    return values, sources


def effective_policy(root: Path, init_id: str, init_idir: Path) -> tuple[dict, dict, str]:
    """The one policy the engine decides by: the layered tunables plus the normalized
    per-phase autonomy map, with the layer each value came from and the digest the
    journal records. Every reader (the policy event, check and doctor) calls this, so
    they cannot disagree about what the policy is."""
    values, sources = load_policy(root, init_id)
    values = {**values, "autonomy": normalize_autonomy(read_json(autonomy_file(init_idir)), PHASES)}
    sources = {**sources, "autonomy": "initiative" if autonomy_file(init_idir).exists()
               else "default"}
    return values, sources, policy_sha(values)
