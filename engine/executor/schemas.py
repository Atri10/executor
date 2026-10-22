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

from .paths import (ARTIFACT_ID, CHANGE_ID, DISPATCH_ID, PLAN_ID, TASK_ID,
                    artifact_pattern)
from .store import PHASES, Rejection

# Inner ids an artifact declares. They are citable (audit D06, D15).
REQUIREMENT_ID = r"R\d+"
CONSTRAINT_ID = r"C\d+"
CRITERION_ID = r"V\d+"

# A branch a task or plan may own: task/<TASK-ID>, plan/<PLAN-ID>,
# initiative/<INIT-ID>, side/<slug>, hotfix/<slug>. The git rules read it.
BRANCH_NAME = (r"(?:task|plan|initiative|side|hotfix)/[A-Za-z0-9._/-]+")

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
            # A nullable field accepts None for a real absent state, so a
            # document never has to write a string that means "no value".
            if not (schema.get("nullable") and obj is None):
                raise Rejection("type", field, stype, json_type(obj))
        # The value constraints below (length, pattern) describe a string;
        # on a nullable None there is nothing to measure.
        if stype == "string" and obj is None:
            return
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
        if "notMatch" in schema:
            for rule in schema["notMatch"]:
                if re.search(rule, obj):
                    raise Rejection("notMatch", field,
                                    f"no match for {rule}", obj[:60])
        if schema.get("nonBlank") and not obj.strip():
            # Whitespace is not content: it passes minLength and renders
            # an empty paragraph, a list item with no text, or a blank
            # table cell — a payload that looks answered and is not.
            raise Rejection("nonBlank", field, "non-whitespace text",
                            repr(obj[:20]))
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
        # An object-level invariant no per-property check can express: the
        # named function reads several fields at once and rejects with the
        # field path of the offending member.
        shape = schema.get("shape")
        if shape:
            SHAPES[shape](obj, field)
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


def _obj(props, req=None, extra=False, shape=None):
    d = {"type": "object", "properties": props,
         "required": req or [], "additionalProperties": extra}
    if shape:
        d["shape"] = shape
    return d


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

# A payload carries DATA; the engine renders markdown. These patterns exist
# so a payload cannot become a second renderer: a pipe table, a fence, or a
# heading inside a string is formatting the caller was supposed to leave to
# views._render_doc, and two renderers drift.
MD_TABLE = r"(?m)^\s*\|"
MD_FENCE = r"```"
MD_HEAD = r"(?m)^#{1,6}\s"
MD_BULLET = r"(?m)^\s*[-*+]\s"
MD_RULE = r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$"
# What any prose-ish string may not contain: the three markdown constructs
# that have a structured home in the payload.
NO_MD = [MD_TABLE, MD_FENCE, MD_HEAD]
# A table cell becomes one rendered cell: a pipe would end the row early and
# a newline would end the table, so neither is data.
NO_CELL_MD = [r"\|", r"[\r\n]"]


def _table_rows_match_columns(obj: dict, field: str) -> None:
    """Every row carries one cell per column: a short row renders a table
    whose cells shift under a reader's eye, and a long one is silently
    truncated by the renderer. Neither is acceptable in the thinking store."""
    width = len(obj["columns"])
    for i, row in enumerate(obj.get("rows", [])):
        if len(row) != width:
            raise Rejection(
                "row_width", f"{field}.rows[{i}]",
                f"{width} cells (one per column)", f"{len(row)} cells")


def _section_has_content(obj: dict, field: str) -> None:
    """A section with no shape is a heading promising text that is not
    there: prose, bullets, tables, or code — at least one, or it is a
    title with nothing under it."""
    if not any(obj.get(k) for k in ("prose", "bullets", "tables", "code")):
        raise Rejection("empty_section", field,
                        "prose, bullets, tables, or code", "none present")


def _section_ids_unique(obj: dict, field: str) -> None:
    """A reviewer cites `§<section id>`, so an id must name one section.
    Two sections sharing an id make the citation ambiguous — and the
    prompt promises the citation."""
    seen: set[str] = set()
    for i, sec in enumerate(obj.get("sections", [])):
        sid = sec.get("id")
        if sid in seen:
            raise Rejection("duplicate", f"{field}.sections[{i}].id",
                            "a section id used once", sid)
        seen.add(sid)


SHAPES = {"table": _table_rows_match_columns,
          "section": _section_has_content,
          "artifact": _section_ids_unique}


def _prose(**kw):
    """Paragraph text: content, not formatting."""
    return _str(nonBlank=True, notMatch=NO_MD, **kw)


def _cell(**kw):
    """One rendered table cell."""
    return _str(nonBlank=True, notMatch=NO_CELL_MD, **kw)


def _bullet_list(**kw):
    return _arr(_str(nonBlank=True, notMatch=NO_MD + [MD_BULLET], **kw))


TABLE = _obj({
    "caption": _str(maxLength=200),
    "columns": _arr(_cell(minLength=1), minItems=1),
    "rows": _arr(_arr(_cell(minLength=1), minItems=1), minItems=1),
}, req=["columns", "rows"], shape="table")

CODE = _obj({
    "lang": _str(),
    "source": _str(minLength=1),
}, req=["source"])

# A section is structured content: prose paragraphs, bullet items, tables,
# and code blocks are four shapes, each with a typed home, so the renderer
# never guesses. At least one shape must be present — an empty section is a
# heading in the store promising text that is not there.
SECTION = _obj({
    "id": _str(minLength=1),
    "title": _str(minLength=1),
    "prose": _prose(minLength=1, maxLength=12000),
    "bullets": _bullet_list(minLength=1),
    "tables": _arr(TABLE, minItems=1),
    "code": _arr(CODE, minItems=1),
}, req=["id", "title"], shape="section")

REQUIREMENT = _obj({
    "id": _str(pattern=REQUIREMENT_ID),
    "requirement": _prose(minLength=1),
    "observable": _prose(),
    "cites": _arr(_str()),
}, req=["id", "requirement", "observable"])

CONSTRAINT = _obj({
    "id": _str(pattern=CONSTRAINT_ID),
    "constraint": _prose(minLength=1),
    "observable": _prose(),
}, req=["id", "constraint", "observable"])

CRITERION = _obj({
    "id": _str(pattern=r"V\d+"),
    "criterion": _prose(minLength=1),
    "procedure": _prose(minLength=1),
    "cites": _arr(_str()),
}, req=["id", "criterion", "procedure"])

# A task id inside its plan is T plus exactly two digits: it becomes a
# directory name, and the layout grammar admits no other shape.
TASK_LOCAL = r"T\d{2}"

TASK = _obj({
    "id": _str(pattern=TASK_LOCAL),
    "title": _str(minLength=1),
    "goal": _prose(minLength=1),
    "files": _arr(_str(minLength=1), minItems=1),
    "accepts": _arr(_str(minLength=1), minItems=1),
    "provides": _arr(_str()),
    "consumes": _arr(_str()),
    "depends_on": _arr(_str(pattern=TASK_LOCAL)),
    # The structured link between a task and the contract it implements. A
    # regression pass reads these; prose is never parsed (audit D06).
    "requirements": _arr(_str(pattern=REQUIREMENT_ID)),
    "constraints": _arr(_str(pattern=CONSTRAINT_ID)),
}, req=["id", "title", "goal", "files", "accepts"])

FINDING = _obj({
    "id": _str(minLength=1),
    "severity": _enum("critical", "important", "minor", "info"),
    "claim": _prose(minLength=1),
    "evidence": _prose(),
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
        "summary": _prose(minLength=1),
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
    if artifact_kind == "arch":
        # Per-component design artifacts: the engine mints one design instance
        # per component (audit D05). Optional, so every stored arch payload
        # still validates and still yields exactly one design.
        props["components"] = _arr(_obj({
            "id": _str(minLength=1), "title": _str(minLength=1),
            "responsibility": _str(),
        }, req=["id", "title"]))
    if artifact_kind == "design":
        props["component"] = _str(minLength=1)
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
        # `mitigation` is nullable because "accepted without mitigation"
        # is a real disposition the human must be able to overrule; forcing
        # the string "none" would hide it.
        props["risks"] = _arr(_obj({
            "id": _str(minLength=1), "risk": _str(minLength=1),
            "likelihood": _enum("high", "medium", "low"),
            "impact": _enum("high", "medium", "low"),
            "mitigation": _prose(nullable=True),
        }, req=["id", "risk", "likelihood", "impact", "mitigation"]))
    return _obj({**_base(artifact_kind), **props},
                req=["kind", "v", *req], shape="artifact")




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
    "branch": _str(pattern=BRANCH_NAME),
    "concerns": _arr(_str()),
    "tests": _arr(_obj({
        "name": _str(minLength=1), "ran": {"type": "boolean"},
        "passed": {"type": "boolean"}, "detail": _str(),
    }, req=["name", "ran", "passed"])),
    "model_actual": _str(),
}, req=["kind", "v", "task", "result", "summary", "commits"])

QUALITY_VERDICTS = ("APPROVED", "NEEDS_FIXES", "APPROVED_WITH_ROUTED_RESIDUALS")


VERDICT = _obj({
    **_base("verdict"),
    "task": _str(pattern=TASK_ID),
    "round": _int(minimum=1),
    "spec_verdict": _enum("PASS", "FAIL"),
    "quality_verdict": _enum(*QUALITY_VERDICTS),
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
    "for_task": _str(pattern=f"(?:{TASK_ID}|{PLAN_ID}|{CHANGE_ID})"),
}, req=["kind", "v", "decision", "why"])

# A mid-run change: the ids that changed, who asked, why. The blast radius is
# computed from the fold, never declared here.
CHANGE_REQUEST = _obj({
    **_base("change_request"),
    "title": _str(minLength=1),
    "requested_by": _str(minLength=1),
    "why": _prose(minLength=1),
    "change": _obj({
        "requirements": _arr(_str(pattern=REQUIREMENT_ID)),
        "constraints": _arr(_str(pattern=CONSTRAINT_ID)),
        "criteria": _arr(_str(pattern=CRITERION_ID)),
        "artifacts": _arr(_str(pattern=ARTIFACT_OR_PLAN)),
        "tasks": _arr(_str(pattern=TASK_ID)),
    }, req=[]),
    "note": _prose(),
}, req=["kind", "v", "title", "requested_by", "why", "change"])

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
    "branch": _str(pattern=BRANCH_NAME),
}, req=["kind", "v", "plan", "merge_sha", "branch"])

RESUME = _obj({
    **_base("resume"),
    "reason": _str(minLength=1),
}, req=["kind", "v", "reason"])


POLICY = _obj({
    "v": _enum("v1"),
    "max_fix_rounds": _int(),
    "max_audit_rounds": _int(),
    "max_evidence_tries": _int(),
    "max_plans": _int(),
    "spawn_retry_cap": _int(),
    "suspect_s": _int(),
    "deadline_s": _int(),
    "clean_quality": _arr(_enum(*QUALITY_VERDICTS), minItems=1),
}, req=["v"])


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
    "change_request": CHANGE_REQUEST,
}


def schema_for(kind: str) -> dict:
    if kind in ARTIFACT_KINDS:
        return artifact_schema(kind)
    if kind in SCHEMAS:
        return SCHEMAS[kind]
    raise Rejection("unknown_kind", "$.kind",
                    "|".join(sorted(SCHEMAS) + ARTIFACT_KINDS), repr(kind))
