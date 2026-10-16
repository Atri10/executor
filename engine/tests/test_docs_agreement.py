# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The rejection reference must match the engine, both directions.

`skills/executor/references/rejections.md` is the document a controller
reads when a payload is refused. A code the engine raises but the
reference omits leaves the reader with no resolution path; a row with no
raise site documents a rejection that cannot happen. Both are drift, so
this test walks the engine source for every raise site and the reference
for every documented code and compares the two sets.

The codes are read from source text, not from importing the modules, so
a raise inside a branch no test exercises still counts.
"""
from __future__ import annotations

import ast
import json
import re
import unittest

from _scripts import REPO
import sys

sys.path.insert(0, str(REPO / "engine"))
from executor import schemas as S

ENGINE = REPO / "engine" / "executor"
REFERENCE = (REPO / "skills" / "executor" / "references" / "rejections.md")


def _code_of(node: ast.Call) -> str | None:
    """The code a refusal carries: a Rejection names it first, an
    ExecError last, after its message."""
    args = [a for a in node.args if isinstance(a, ast.Constant)
            and isinstance(a.value, str)]
    if not args:
        return None
    name = node.func.id if isinstance(node.func, ast.Name) else ""
    return (args[0].value if name == "Rejection" else args[-1].value)


def engine_codes() -> set[str]:
    """Every code the engine can raise, read from the AST so a code inside
    a branch no test exercises still counts."""
    codes: set[str] = set()
    for f in sorted(ENGINE.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"), str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ("Rejection", "ExecError"):
                code = _code_of(node)
                if code:
                    codes.add(code)
    return codes


# A backticked code in the reference's first table column; a cell may list
# several, separated by slashes (the structural bounds share one row).
# The validator's own codes are camelCase (`additionalProperties`), so the
# pattern allows an interior capital.
DOC_ROW_CODE = re.compile(r"`([A-Za-z][A-Za-z_]{2,})`")
# The mini-validator in schemas.py raises these from its own statements,
# spelled as schema keywords rather than as the validator's raise calls.
VALIDATOR_CODES = {
    "type", "required", "enum", "pattern", "minLength", "maxLength",
    "minItems", "minimum", "notMatch", "oneOf",
}


def documented_codes() -> set[str]:
    """The first column of every table row: a code is `snake_case`, which
    keeps field paths (`$.plan`), kind names, and prose out."""
    codes = set()
    for line in REFERENCE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        codes.update(DOC_ROW_CODE.findall(line.split("|")[1]))
    return codes


class RejectionReferenceAgrees(unittest.TestCase):
    def test_the_reference_exists(self):
        self.assertTrue(REFERENCE.exists(), REFERENCE)

    def test_every_implemented_code_is_documented(self):
        missing = engine_codes() - documented_codes() - VALIDATOR_CODES
        self.assertEqual(missing, set(),
                         f"undocumented rejection codes: {sorted(missing)}")

    def test_every_documented_code_is_implemented(self):
        # The structural codes come from the mini-validator in
        # schemas.py, whose raise sites spell them the same way.
        extra = documented_codes() - engine_codes() - VALIDATOR_CODES
        self.assertEqual(extra, set(),
                         f"documented but never raised: {sorted(extra)}")

    def test_the_documented_set_is_substantial(self):
        """A reference documenting only the two codes someone remembered is
        worse than none, because it looks authoritative."""
        self.assertGreater(len(documented_codes()), 25)


class IdExamplesAreReal(unittest.TestCase):
    """Every ID the skills tree shows an agent must be one the engine
    accepts. A phantom segment (`RSCH`) or a retired shape (`…-T03-R02`)
    teaches a reader to emit a `pattern` rejection and then wonder why."""

    SEEN = re.compile(r"INIT-\d{4}-[A-Z]{3,4}-\d{2}")

    def engine_segments(self) -> set[str]:
        import sys
        sys.path.insert(0, str(REPO / "engine"))
        from executor.paths import ARTIFACT_SEGMENTS
        return set(ARTIFACT_SEGMENTS.values())

    def test_every_id_example_uses_a_declared_segment(self):
        declared = self.engine_segments()
        bad = {}
        for f in sorted((REPO / "skills").rglob("*.md")):
            for i, line in enumerate(f.read_text(encoding="utf-8")
                                     .splitlines(), 1):
                for token in self.SEEN.findall(line):
                    seg = token.split("-")[2]
                    if seg not in declared:
                        bad.setdefault(token, []).append(f"{f}:{i}")
        self.assertEqual(bad, {}, f"IDs with no declared segment: {bad}")


def _fill(obj, schema):
    """Replace a placeholder token in a value with the smallest value the
    schema accepts, so a skeleton written for a reader (`[D<NNNNN>]`) is
    still checked for shape: the keys it carries, the types they hold, and
    the patterns and bounds it claims. A value whose shape the schema does
    not allow is returned untouched — `validate` rejects it, which is the
    point of the check."""
    if not isinstance(schema, dict):
        return obj
    if "enum" in schema and obj not in schema["enum"]:
        # "A | B | C" is the vocabulary written out for a reader: any member
        # satisfies it. A plain wrong value ("MAYBE") is a doc defect, so it
        # is left for `validate` to reject.
        if isinstance(obj, str) and "|" in obj:
            return schema["enum"][0]
        return obj
    stype = schema.get("type")
    if stype == "object":
        props = schema.get("properties", {})
        if not isinstance(obj, dict):
            return obj
        return {k: (_fill(v, props[k]) if k in props else v)
                for k, v in obj.items()}
    if stype == "array" and isinstance(obj, list):
        return [_fill(v, schema.get("items", {})) for v in obj]
    if stype == "string" and isinstance(obj, str) and (
            "[" in obj or "<" in obj):
        node = {k: v for k, v in schema.items() if k in
                ("minLength", "maxLength", "pattern", "enum", "notMatch")}
        node["type"] = "string"
        from test_schemas import minimal
        return minimal(node)
    return obj


class PayloadSkeletonsValidate(unittest.TestCase):
    """Every JSON payload the skills show an agent must be one the engine
    accepts. A skeleton with a field the schema deleted, a criterion ID
    that fails its pattern, or a required field missing teaches a worker
    to emit a rejection — and the worker has no way to tell the document
    wrong from the engine wrong."""

    def skeletons(self) -> list[tuple[str, dict]]:
        out = []
        for p in sorted((REPO / "skills").rglob("*.md")):
            for m in re.finditer(r"```json\n(.*?)```", p.read_text(), re.S):
                block = m.group(1)
                depth, start = 0, None
                for i, ch in enumerate(block):
                    if ch == "{":
                        if depth == 0:
                            start = i
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0 and start is not None:
                            chunk = block[start:i + 1]
                            if '"kind"' in chunk:
                                try:
                                    obj = json.loads(chunk)
                                except ValueError:
                                    obj = None
                                if isinstance(obj, dict) and "kind" in obj:
                                    out.append((p.name, obj))
                            start = None
        return out

    def test_every_skeleton_parses(self):
        for name, obj in self.skeletons():
            with self.subTest(file=name):
                self.assertIsInstance(obj, dict)

    def test_a_skeleton_naming_a_real_kind_validates(self):
        kinds = set(S.ARTIFACT_KINDS) | {
            "report", "verdict", "heartbeat", "evidence", "gate_decision",
            "ruling", "halt", "spawn_error", "needs_context", "audit",
            "merge", "resume"}
        checked = 0
        for name, obj in self.skeletons():
            if obj["kind"] not in kinds:
                continue
            schema = S.schema_for(obj["kind"])
            with self.subTest(file=name, kind=obj["kind"]):
                S.validate(_fill(obj, schema), schema)
            checked += 1
        self.assertGreater(checked, 10)


if __name__ == "__main__":
    unittest.main()
