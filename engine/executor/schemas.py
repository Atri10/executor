# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Payload schemas and a minimal strict validator.

Zero third-party dependencies: this is a deliberately small JSON-Schema
subset (type/properties/required/enum/items/additionalProperties/
minItems/minLength/maxLength/pattern/minimum/oneOf). A pattern must match the
WHOLE string, so an id with junk around it is not an id. Every object in
every schema is closed, and every payload the engine accepts is validated
against one of the schemas below: structural first, then the semantic pass
in engine.fold.
"""
from __future__ import annotations

import re

from .paths import (ARTIFACT_ID, DISPATCH_ID, PLAN_ID, TASK_ID,
                    artifact_pattern)
from .store import PHASES, Rejection

TYPES = {"object": dict, "array": list, "string": str,
         "integer": int, "number": (int, float), "boolean": bool,
         "null": type(None)}


def json_type(obj) -> str:
    """The JSON name of a value's type, so a rejection speaks the schema's
    vocabulary ("expected string, got integer") instead of Python's ("got
    int", "got NoneType"). bool is tested before int: in Python it is an
    int, in JSON it is not."""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "boolean"
    for name, py in (("integer", int), ("number", float), ("string", str),
                     ("array", list), ("object", dict)):
        if isinstance(obj, py):
            return name
    return type(obj).__name__


def validate(obj, schema: dict, field: str = "$") -> None:
    """Raise Rejection on the first violation. Strict by default: an
    object rejects unknown keys unless additionalProperties is set."""
    if not isinstance(schema, dict):
        return
    stype = schema.get("type")
    if stype:
        expected = TYPES[stype]
        # bool is a subclass of int in Python; keep them distinct.
        if stype in ("integer", "number") and isinstance(obj, bool):
            raise Rejection("type", field, stype, json_type(obj))
        if not isinstance(obj, expected):
            raise Rejection("type", field, stype, json_type(obj))
    if "enum" in schema and obj not in schema["enum"]:
        raise Rejection("enum", field, "|".join(map(str, schema["enum"])),
                        repr(obj))
    if stype == "string":
        if "minLength" in schema and len(obj) < schema["minLength"]:
            raise Rejection("minLength", field,
                            f"len>={schema['minLength']}", f"len={len(obj)}")
        if "maxLength" in schema and len(obj) > schema["maxLength"]:
            raise Rejection("maxLength", field,
                            f"len<={schema['maxLength']}", f"len={len(obj)}")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], obj):
            raise Rejection("pattern", field, schema["pattern"], obj[:60])
    if stype == "integer":
        if "minimum" in schema and obj < schema["minimum"]:
            raise Rejection("minimum", field, f">={schema['minimum']}",
                            str(obj))
    if stype == "object":
        req = schema.get("required", [])
        for k in req:
            if k not in obj:
                raise Rejection("required", f"{field}.{k}", "present",
                                "missing")
        props = schema.get("properties", {})
        ap = schema.get("additionalProperties", True)
        if ap is False:
            for k in obj:
                if k not in props:
                    raise Rejection("additionalProperties", f"{field}.{k}",
                                    "closed object", "extra key")
        elif isinstance(ap, dict):
            for k, v in obj.items():
                if k not in props:
                    validate(v, ap, f"{field}.{k}")
        for k, sub in props.items():
            if k in obj:
                validate(obj[k], sub, f"{field}.{k}")
    if stype == "array":
        if "minItems" in schema and len(obj) < schema["minItems"]:
            raise Rejection("minItems", field,
                            f">={schema['minItems']} items",
                            f"{len(obj)} items")
        if "items" in schema:
            for i, item in enumerate(obj):
                validate(item, schema["items"], f"{field}[{i}]")
    if "oneOf" in schema:
        for sub in schema["oneOf"]:
            try:
                validate(obj, sub, field)
                return
            except Rejection:
                continue
        raise Rejection("oneOf", field, "any of the variants",
                        "no variant matched")


# ------------------------------------------------------------ base

BASE = {
    "kind": {"type": "string", "minLength": 1},
    "v": {"type": "string", "minLength": 1},
    "engine_version": {"type": "string"},
    # Optional echo of the slot a payload answers. The engine binds by it when
    # present and by entity otherwise; a worker that cannot echo is still valid.
    "dispatch_id": {"type": "string", "pattern": DISPATCH_ID},
}


def _obj(props, req=None, extra=False):
    return {"type": "object", "properties": props,
            "required": req or [], "additionalProperties": extra}


def _arr(items, **kw):
    d = {"type": "array", "items": items}
    d.update(kw)
    return d


def _enum(*vals):
    return {"enum": list(vals)}


def _str(**kw):
    d = {"type": "string"}
    d.update(kw)
    return d


def _int(**kw):
    d = {"type": "integer"}
    d.update(kw)
    return d


def _base(kind: str) -> dict:
    """The keys every payload carries, with `kind` pinned to this schema's."""
    return {**BASE, "kind": _enum(kind)}


# ------------------------------------------------------------ artifacts

SECTION = _obj({
    "id": _str(minLength=1),
    "title": _str(minLength=1),
    "body": _str(minLength=1, maxLength=12000),
}, req=["id", "title", "body"])

REQUIREMENT = _obj({
    "id": _str(pattern=r"R\d+"),
    "requirement": _str(minLength=1),
    "observable": _str(),
    "cites": _arr(_str()),
}, req=["id", "requirement", "observable"])

CONSTRAINT = _obj({
    "id": _str(pattern=r"C\d+"),
    "constraint": _str(minLength=1),
    "observable": _str(),
}, req=["id", "constraint", "observable"])

CRITERION = _obj({
    "id": _str(pattern=r"V\d+"),
    "criterion": _str(minLength=1),
    "procedure": _str(minLength=1),
    "cites": _arr(_str()),
}, req=["id", "criterion", "procedure"])

# A task id inside its plan is T plus exactly two digits: it becomes a
# directory name, and the layout grammar admits no other shape.
TASK_LOCAL = r"T\d{2}"

TASK = _obj({
    "id": _str(pattern=TASK_LOCAL),
    "title": _str(minLength=1),
    "goal": _str(minLength=1),
    "files": _arr(_str(minLength=1), minItems=1),
    "accepts": _arr(_str(minLength=1), minItems=1),
    "provides": _arr(_str()),
    "consumes": _arr(_str()),
    "depends_on": _arr(_str(pattern=TASK_LOCAL)),
}, req=["id", "title", "goal", "files", "accepts"])

FINDING = _obj({
    "id": _str(minLength=1),
    "severity": _enum("critical", "important", "minor", "info"),
    "claim": _str(minLength=1),
    "evidence": _str(),
    "fix_scope": _enum("instance", "class"),
    "class_hint": _str(),
    "status": _enum("open", "fixed", "waived", "routed"),
}, req=["id", "severity", "claim"])


def artifact_schema(artifact_kind: str) -> dict:
    """Per-artifact body schema. Shared skeleton: id/title/summary/sections;
    heavier kinds add their typed collections. The id's segment is tied to the
    kind (a charter is CHTR, never SPEC), and a plan is a plan id."""
    props = {
        "id": _str(pattern=artifact_pattern(artifact_kind)),
        "title": _str(minLength=1),
        "summary": _str(minLength=1),
        "sections": _arr(SECTION),
        "cites": _arr(_str()),
    }
    req = ["id", "title", "summary", "sections"]
    if artifact_kind in ("spec", "charter"):
        props.update({
            "requirements": _arr(REQUIREMENT),
            "constraints": _arr(CONSTRAINT),
            "risks": _arr(_str()),
        })
    if artifact_kind == "vrfy":
        # Verification is driven by these rows: a VRFY without any would make
        # the verification gate pass with nothing proven.
        props["criteria"] = _arr(CRITERION, minItems=1)
        req.append("criteria")
    if artifact_kind == "plan":
        props.update({
            "plan_id": _str(pattern=PLAN_ID),
            "objective": _str(minLength=1),
            "tasks": _arr(TASK, minItems=1),
            "gates": _arr(_str()),
            "more_plans": {"type": "boolean"},
        })
        req += ["plan_id", "objective", "tasks", "more_plans"]
    if artifact_kind in ("arch", "design"):
        props.update({
            "adrs": _arr(_obj({
                "id": _str(minLength=1), "title": _str(minLength=1),
                "decision": _str(minLength=1), "why": _str(minLength=1),
                "cost_if_wrong": _str(),
                "alternatives": _arr(_str()),
            }, req=["id", "title", "decision", "why"])),
            "ifces": _arr(_obj({
                "id": _str(minLength=1), "title": _str(minLength=1),
                "provides": _arr(_str()), "consumes": _arr(_str()),
            }, req=["id", "title"])),
        })
    if artifact_kind == "risk":
        props["risks"] = _arr(_obj({
            "id": _str(minLength=1), "risk": _str(minLength=1),
            "likelihood": _enum("high", "medium", "low"),
            "impact": _enum("high", "medium", "low"),
            "mitigation": _str(minLength=1),
        }, req=["id", "risk", "likelihood", "impact", "mitigation"]))
    return _obj({**_base(artifact_kind), **props}, req=["kind", "v", *req])


ARTIFACT_KINDS = ["charter", "options", "brainstorm", "arch", "adr", "ifce",
                  "design", "spec", "risk", "vrfy", "plan"]

# The target of an audit or repair: any artifact, or a plan.
ARTIFACT_OR_PLAN = ARTIFACT_ID + "|" + PLAN_ID


# ------------------------------------------------------------ runtime

REPORT = _obj({
    **_base("report"),
    "task": _str(pattern=TASK_ID),
    "result": _enum("DONE", "DONE_WITH_CONCERNS", "BLOCKED", "PARTIAL"),
    "summary": _str(minLength=1),
    "commits": _arr(_str(minLength=1)),
    "concerns": _arr(_str()),
    "tests": _arr(_obj({
        "name": _str(minLength=1), "ran": {"type": "boolean"},
        "passed": {"type": "boolean"}, "detail": _str(),
    }, req=["name", "ran", "passed"])),
    "model_actual": _str(),
}, req=["kind", "v", "task", "result", "summary", "commits"])

VERDICT = _obj({
    **_base("verdict"),
    "task": _str(pattern=TASK_ID),
    "round": _int(minimum=1),
    "spec_verdict": _enum("PASS", "FAIL"),
    "quality_verdict": _enum("APPROVED", "NEEDS_FIXES",
                             "APPROVED_WITH_ROUTED_RESIDUALS"),
    "findings": _arr(FINDING),
    "model_actual": _str(),
    "commit_base": _str(minLength=4),
    "commit_head": _str(minLength=4),
    "reviewed_package_sha": _str(minLength=4),
}, req=["kind", "v", "task", "round", "spec_verdict",
        "quality_verdict", "commit_base", "commit_head",
        "reviewed_package_sha"])

HEARTBEAT = _obj({
    **_base("heartbeat"),
    "task": _str(pattern=TASK_ID),
    "note": _str(maxLength=400),
}, req=["kind", "v", "task"])

EVIDENCE = _obj({
    **_base("evidence"),
    "criterion": _str(pattern=r"V\d+"),
    "command": _str(minLength=1),
    "observed": _str(minLength=1),
    "verdict": _enum("proven", "unavailable", "failed"),
    "state_commit": _str(minLength=4),
    "artifacts": _arr(_str()),
}, req=["kind", "v", "criterion", "command", "observed",
        "verdict", "state_commit"])

GATE_DECISION = _obj({
    **_base("gate_decision"),
    "phase": _enum(*PHASES),
    "decision": _enum("approved", "rejected", "waived"),
    "by": _enum("human", "auto"),
    "note": _str(),
}, req=["kind", "v", "phase", "decision", "by"])

RULING = _obj({
    **_base("ruling"),
    "decision": _str(minLength=1),
    "why": _str(minLength=1),
    "cost_if_wrong": _str(),
    "answered": _str(),
    "unsolicited": _str(),
    "stop": {"type": "boolean"},
    "for_task": _str(pattern=f"(?:{TASK_ID}|{PLAN_ID})"),
}, req=["kind", "v", "decision", "why"])

AUDIT = _obj({
    **_base("audit"),
    "target": _str(pattern=ARTIFACT_OR_PLAN),
    "round": _int(minimum=1),
    "verdict": _enum("PASS", "FAIL"),
    "findings": _arr(FINDING),
}, req=["kind", "v", "target", "round", "verdict", "findings"])


HALT = _obj({
    **_base("halt"),
    "reason": _str(minLength=1),
}, req=["kind", "v", "reason"])

SPAWN_ERROR = _obj({
    **_base("spawn_error"),
    "error_class": _enum("rate_limit", "auth", "network", "session",
                         "other"),
    "detail": _str(),
}, req=["kind", "v", "dispatch_id", "error_class"])

NEEDS_CONTEXT = _obj({
    **_base("needs_context"),
    "task": _str(pattern=TASK_ID),
    "question": _str(minLength=1),
    "for_role": _str(),
}, req=["kind", "v", "task", "question"])

MERGE = _obj({
    **_base("merge"),
    "plan": _str(pattern=PLAN_ID),
    "merge_sha": _str(minLength=4),
    "branch": _str(),
}, req=["kind", "v", "plan", "merge_sha"])

RESUME = _obj({
    **_base("resume"),
    "reason": _str(minLength=1),
}, req=["kind", "v", "reason"])


SCHEMAS = {
    "report": REPORT,
    "verdict": VERDICT,
    "heartbeat": HEARTBEAT,
    "evidence": EVIDENCE,
    "gate_decision": GATE_DECISION,
    "ruling": RULING,
    "halt": HALT,
    "spawn_error": SPAWN_ERROR,
    "needs_context": NEEDS_CONTEXT,
    "audit": AUDIT,
    "merge": MERGE,
    "resume": RESUME,
}


def schema_for(kind: str) -> dict:
    if kind in ARTIFACT_KINDS:
        return artifact_schema(kind)
    if kind in SCHEMAS:
        return SCHEMAS[kind]
    raise Rejection("unknown_kind", "$.kind",
                    "|".join(sorted(SCHEMAS) + ARTIFACT_KINDS), repr(kind))
