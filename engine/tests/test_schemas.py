# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""schemas.py: what a worker is allowed to say.

Four layers. The validator is driven branch by branch with small schemas of
its own. Every payload kind is pinned as a literal contract (required keys,
the closed vocabulary) and then attacked with generated variants: drop a key,
add a key, wrong type, wrong kind. The registry is checked for internal
consistency. A seeded fuzzer proves the validator can only ever answer with
a typed Rejection, never a crash.

Defects this file pins that the first implementation had: patterns matched
anywhere in the string (so `xT1y` was a task id), a VRFY without criteria was
valid (the verification gate then passed with nothing proven), and an audit
or ruling could name a target that is not an id.
"""
from __future__ import annotations

import copy
import random
import re
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from executor import paths as P, schemas as S  # noqa: E402
from executor.store import PHASES, Rejection  # noqa: E402

validate, schema_for = S.validate, S.schema_for

from _payloads import GOOD, INIT, PLAN, TASK

BASE_KEYS = {"kind", "v", "engine_version", "dispatch_id"}
ART_KEYS = BASE_KEYS | {"id", "title", "summary", "sections", "cites"}


# The contract: what each kind must carry, and everything it may carry.
REQUIRED = {
    **{k: {"kind", "v", "id", "title", "summary", "sections"}
       for k in ("charter", "options", "brainstorm", "arch", "adr", "ifce",
                 "design", "spec", "risk")},
    "vrfy": {"kind", "v", "id", "title", "summary", "sections", "criteria"},
    "plan": {"kind", "v", "id", "title", "summary", "sections", "plan_id",
             "objective", "tasks"},
    "report": {"kind", "v", "task", "result", "summary", "commits"},
    "verdict": {"kind", "v", "task", "round", "spec_verdict",
                "quality_verdict", "commit_base", "commit_head",
                "reviewed_package_sha"},
    "heartbeat": {"kind", "v", "task"},
    "evidence": {"kind", "v", "criterion", "command", "observed", "verdict",
                 "state_commit"},
    "gate_decision": {"kind", "v", "phase", "decision", "by"},
    "ruling": {"kind", "v", "decision", "why"},
    "audit": {"kind", "v", "target", "round", "verdict", "findings"},
    "repair": {"kind", "v", "target", "round"},
    "halt": {"kind", "v", "reason"},
    "spawn_error": {"kind", "v", "dispatch_id", "error_class"},
    "needs_context": {"kind", "v", "task", "question"},
    "merge": {"kind", "v", "plan", "merge_sha"},
}
EXTRA_KEYS = {
    **{k: ART_KEYS for k in ("options", "brainstorm", "adr", "ifce")},
    "charter": ART_KEYS | {"requirements", "constraints", "risks"},
    "spec": ART_KEYS | {"requirements", "constraints", "risks"},
    "arch": ART_KEYS | {"adrs", "ifces"},
    "design": ART_KEYS | {"adrs", "ifces"},
    "risk": ART_KEYS | {"risks"},
    "vrfy": ART_KEYS | {"criteria"},
    "plan": ART_KEYS | {"plan_id", "objective", "tasks", "gates"},
    "report": BASE_KEYS | {"task", "result", "summary", "commits", "concerns",
                           "tests", "model_actual"},
    "verdict": BASE_KEYS | {"task", "round", "spec_verdict",
                            "quality_verdict", "findings", "model_actual",
                            "commit_base", "commit_head",
                            "reviewed_package_sha"},
    "heartbeat": BASE_KEYS | {"task", "note"},
    "evidence": BASE_KEYS | {"criterion", "command", "observed", "verdict",
                             "state_commit", "artifacts"},
    "gate_decision": BASE_KEYS | {"phase", "decision", "by", "note"},
    "ruling": BASE_KEYS | {"decision", "why", "cost_if_wrong", "answered",
                           "unsolicited", "stop", "for_task"},
    "audit": BASE_KEYS | {"target", "round", "verdict", "findings"},
    "repair": BASE_KEYS | {"target", "round", "fixed", "introduced", "note"},
    "halt": BASE_KEYS | {"reason"},
    "spawn_error": BASE_KEYS | {"error_class", "detail"},
    "needs_context": BASE_KEYS | {"task", "question", "for_role"},
    "merge": BASE_KEYS | {"plan", "merge_sha", "branch"},
}
RUNTIME_KINDS = ["report", "verdict", "heartbeat", "evidence",
                 "gate_decision", "ruling", "audit", "repair", "halt",
                 "spawn_error", "needs_context", "merge"]


class SchemaCase(unittest.TestCase):
    def rejects(self, obj, schema, code, field=None) -> Rejection:
        with self.assertRaises(Rejection) as ctx:
            validate(obj, schema)
        err = ctx.exception
        self.assertEqual(err.code, code, str(err))
        if field is not None:
            self.assertEqual(err.field, field, str(err))
        return err

    def accepts(self, obj, schema) -> None:
        validate(obj, schema)

    def kind_rejects(self, payload, code, field=None) -> Rejection:
        return self.rejects(payload, schema_for(payload["kind"]), code, field)


# --------------------------------------------------------------- validator

class TypeTests(SchemaCase):
    GOOD_VALUES = {"object": {}, "array": [], "string": "x", "integer": 3,
                   "number": 2.5, "boolean": True, "null": None}

    def test_every_type_accepts_its_own_value_and_rejects_the_others(self):
        for stype, ok in self.GOOD_VALUES.items():
            self.accepts(ok, {"type": stype})
            for other, bad in self.GOOD_VALUES.items():
                if other == stype:
                    continue
                if stype == "number" and other == "integer":
                    continue          # an integer is a valid number
                with self.subTest(expected=stype, got=other):
                    err = self.rejects(bad, {"type": stype}, "type")
                    self.assertEqual(err.expected, stype)
                    self.assertEqual(err.got, other)

    def test_rejections_name_json_types_not_python_ones(self):
        for bad, name in ((None, "null"), (True, "boolean"), (False, "boolean"),
                          (3, "integer"), (2.5, "number"), ("s", "string"),
                          ([], "array"), ({}, "object")):
            with self.subTest(got=name):
                self.assertEqual(S.json_type(bad), name)
        self.assertEqual(S.json_type(b"raw"), "bytes")     # not JSON: as is

    def test_a_boolean_is_never_an_integer_or_a_number(self):
        for stype in ("integer", "number"):
            for flag in (True, False):
                with self.subTest(stype=stype, value=flag):
                    err = self.rejects(flag, {"type": stype}, "type")
                    self.assertEqual(err.got, "boolean")

    def test_a_float_is_not_an_integer_but_an_integer_is_a_number(self):
        self.rejects(1.5, {"type": "integer"}, "type")
        self.accepts(7, {"type": "number"})

    def test_a_schema_without_a_type_accepts_any_value(self):
        for value in (None, 1, "x", [], {}):
            self.accepts(value, {})

    def test_a_non_dict_schema_is_no_constraint(self):
        for schema in (True, None, "string"):
            self.accepts({"anything": 1}, schema)


class EnumTests(SchemaCase):
    def test_a_member_is_accepted_and_a_stranger_is_not(self):
        schema = S._enum("PASS", "FAIL")
        self.accepts("PASS", schema)
        err = self.rejects("MAYBE", schema, "enum", "$")
        self.assertEqual((err.expected, err.got), ("PASS|FAIL", "'MAYBE'"))

    def test_membership_is_exact_not_case_folded_or_coerced(self):
        for bad in ("pass", "PASS ", 1, None, ["PASS"]):
            with self.subTest(value=bad):
                self.rejects(bad, S._enum("PASS", "FAIL"), "enum")

    def test_an_enum_applies_to_non_strings_too(self):
        self.accepts(2, {"enum": [1, 2]})
        self.rejects(3, {"enum": [1, 2]}, "enum")


class StringTests(SchemaCase):
    def test_min_and_max_length_are_inclusive_boundaries(self):
        schema = S._str(minLength=2, maxLength=4)
        for ok in ("ab", "abc", "abcd"):
            self.accepts(ok, schema)
        err = self.rejects("a", schema, "minLength")
        self.assertEqual((err.expected, err.got), ("len>=2", "len=1"))
        err = self.rejects("abcde", schema, "maxLength")
        self.assertEqual((err.expected, err.got), ("len<=4", "len=5"))

    def test_length_counts_characters_not_bytes(self):
        self.accepts("éé", S._str(maxLength=2))
        self.rejects("é", S._str(minLength=2), "minLength")

    def test_a_pattern_must_match_the_whole_string(self):
        schema = S._str(pattern=r"T\d{2}")
        self.accepts("T01", schema)
        for bad in ("xT01", "T01x", "xT01y", "T1", "T001", "t01", ""):
            with self.subTest(value=bad):
                self.rejects(bad, schema, "pattern")

    def test_an_alternation_pattern_still_means_one_whole_alternative(self):
        schema = S._str(pattern=r"A|B")
        self.accepts("A", schema)
        self.accepts("B", schema)
        self.rejects("AB", schema, "pattern")
        self.rejects("xA", schema, "pattern")

    def test_the_pattern_error_truncates_a_huge_value(self):
        err = self.rejects("x" * 500, S._str(pattern=r"y"), "pattern")
        self.assertEqual(len(err.got), 60)
        self.assertEqual(err.expected, "y")

    def test_string_constraints_do_not_apply_to_other_types(self):
        with self.assertRaises(Rejection) as ctx:
            validate(5, S._str(minLength=1))
        self.assertEqual(ctx.exception.code, "type")


class IntegerTests(SchemaCase):
    def test_minimum_is_an_inclusive_boundary(self):
        schema = S._int(minimum=1)
        self.accepts(1, schema)
        self.accepts(99, schema)
        err = self.rejects(0, schema, "minimum")
        self.assertEqual((err.expected, err.got), (">=1", "0"))
        self.rejects(-4, schema, "minimum")


class ObjectTests(SchemaCase):
    SCHEMA = S._obj({"a": S._str(), "b": S._int()}, req=["a"])

    def test_a_required_key_must_be_present(self):
        self.accepts({"a": "x"}, self.SCHEMA)
        err = self.rejects({"b": 1}, self.SCHEMA, "required", "$.a")
        self.assertEqual((err.expected, err.got), ("present", "missing"))

    def test_an_optional_key_may_be_absent_but_is_checked_when_present(self):
        self.accepts({"a": "x", "b": 2}, self.SCHEMA)
        self.rejects({"a": "x", "b": "two"}, self.SCHEMA, "type", "$.b")

    def test_objects_are_closed_by_default(self):
        err = self.rejects({"a": "x", "zzz": 1}, self.SCHEMA,
                           "additionalProperties", "$.zzz")
        self.assertEqual(err.got, "extra key")

    def test_an_open_object_allows_extra_keys(self):
        self.accepts({"a": "x", "zzz": [1]}, S._obj({"a": S._str()},
                                                    extra=True))
        self.accepts({"zzz": 1}, {"type": "object"})

    def test_a_schema_valued_additional_properties_checks_every_extra(self):
        schema = {"type": "object", "properties": {"a": S._str()},
                  "additionalProperties": S._int(minimum=0)}
        self.accepts({"a": "x", "n": 3, "m": 0}, schema)
        self.rejects({"n": "no"}, schema, "type", "$.n")
        self.rejects({"n": -1}, schema, "minimum", "$.n")
        self.accepts({"a": "x"}, schema)

    def test_declared_properties_are_not_checked_as_extras(self):
        schema = {"type": "object", "properties": {"a": S._str()},
                  "additionalProperties": S._int()}
        self.accepts({"a": "text"}, schema)

    def test_field_paths_name_the_full_location(self):
        schema = S._obj({"a": S._arr(S._obj({"b": S._arr(S._str())}))})
        self.rejects({"a": [{"b": ["ok"]}, {"b": ["ok", 5]}]}, schema,
                     "type", "$.a[1].b[1]")

    def test_required_is_checked_before_the_properties(self):
        err = self.rejects({"b": "wrong type"}, self.SCHEMA, "required")
        self.assertEqual(err.field, "$.a")


class ArrayTests(SchemaCase):
    def test_min_items_is_an_inclusive_boundary(self):
        schema = S._arr(S._str(), minItems=2)
        self.accepts(["a", "b"], schema)
        err = self.rejects(["a"], schema, "minItems")
        self.assertEqual((err.expected, err.got), (">=2 items", "1 items"))

    def test_every_item_is_validated_and_the_index_is_reported(self):
        self.rejects(["a", "b", 3], S._arr(S._str()), "type", "$[2]")

    def test_an_empty_array_is_valid_without_min_items(self):
        self.accepts([], S._arr(S._str()))

    def test_an_array_without_items_accepts_anything_inside(self):
        self.accepts([1, "x", None], {"type": "array"})


class OneOfTests(SchemaCase):
    SCHEMA = {"oneOf": [S._str(minLength=3), S._int(minimum=10)]}

    def test_any_matching_variant_is_enough(self):
        self.accepts("abc", self.SCHEMA)
        self.accepts(12, self.SCHEMA)

    def test_no_matching_variant_is_one_typed_rejection(self):
        for bad in ("ab", 3, None, []):
            with self.subTest(value=bad):
                err = self.rejects(bad, self.SCHEMA, "oneOf", "$")
                self.assertEqual(err.got, "no variant matched")


# ------------------------------------------------------------ contracts

class BuilderTests(SchemaCase):
    def test_base_keys_are_the_shared_envelope(self):
        self.assertEqual(set(S.BASE), BASE_KEYS)

    def test_the_dispatch_echo_is_optional_and_must_be_a_dispatch_id(self):
        for kind in RUNTIME_KINDS:
            if kind == "spawn_error":
                continue
            payload = {**GOOD[kind], "dispatch_id": "D00042"}
            with self.subTest(kind=kind, echo="good"):
                validate(payload, schema_for(kind))
            with self.subTest(kind=kind, echo="verbose"):
                bad = {**GOOD[kind],
                       "dispatch_id": "d-00042-INIT-0001-CHTR-01-charter"}
                self.rejects(bad, schema_for(kind), "pattern",
                             "$.dispatch_id")

    def test_the_engine_version_stamp_is_an_optional_string(self):
        validate({**GOOD["halt"], "engine_version": "2.0.0"},
                 schema_for("halt"))
        self.rejects({**GOOD["halt"], "engine_version": 2}, schema_for("halt"),
                     "type", "$.engine_version")

    def test_every_schema_pins_its_own_kind(self):
        for kind in RUNTIME_KINDS + S.ARTIFACT_KINDS:
            with self.subTest(kind=kind):
                props = schema_for(kind)["properties"]
                self.assertEqual(props["kind"], {"enum": [kind]})


class RegistryTests(SchemaCase):
    def test_artifact_kinds_and_id_segments_agree(self):
        self.assertEqual(set(P.ARTIFACT_SEGMENTS) | {"plan"},
                         set(S.ARTIFACT_KINDS))
        self.assertEqual(len(S.ARTIFACT_KINDS), len(set(S.ARTIFACT_KINDS)))

    def test_the_runtime_registry_is_exactly_the_documented_kinds(self):
        self.assertEqual(sorted(S.SCHEMAS), sorted(RUNTIME_KINDS))

    def test_good_payloads_cover_every_kind(self):
        self.assertEqual(sorted(GOOD),
                         sorted(RUNTIME_KINDS + S.ARTIFACT_KINDS))

    def test_every_kind_resolves_to_its_schema(self):
        for kind in RUNTIME_KINDS:
            self.assertIs(schema_for(kind), S.SCHEMAS[kind])
        for kind in S.ARTIFACT_KINDS:
            self.assertEqual(schema_for(kind), S.artifact_schema(kind))

    def test_artifact_schemas_are_built_fresh_each_time(self):
        first = schema_for("charter")
        first["properties"]["title"]["minLength"] = 99
        self.assertEqual(schema_for("charter")["properties"]["title"]
                         ["minLength"], 1)

    def test_an_unknown_kind_lists_what_is_known(self):
        with self.assertRaises(Rejection) as ctx:
            schema_for("nonsense")
        err = ctx.exception
        self.assertEqual((err.code, err.field), ("unknown_kind", "$.kind"))
        self.assertEqual(err.got, "'nonsense'")
        for kind in RUNTIME_KINDS + S.ARTIFACT_KINDS:
            self.assertIn(kind, err.expected)

    def test_required_keys_are_pinned_per_kind(self):
        for kind, want in REQUIRED.items():
            with self.subTest(kind=kind):
                self.assertEqual(set(schema_for(kind)["required"]), want)

    def test_the_vocabulary_is_closed_and_pinned_per_kind(self):
        for kind, want in EXTRA_KEYS.items():
            with self.subTest(kind=kind):
                self.assertEqual(set(schema_for(kind)["properties"]), want)

    def test_every_schema_object_is_closed_and_satisfiable(self):
        def walk(node, where):
            if node.get("type") == "object":
                with self.subTest(where=where):
                    self.assertIs(node["additionalProperties"], False)
                    self.assertLessEqual(set(node["required"]),
                                         set(node["properties"]))
            for key, sub in node.get("properties", {}).items():
                walk(sub, f"{where}.{key}")
            if "items" in node:
                walk(node["items"], f"{where}[]")

        for kind in RUNTIME_KINDS + S.ARTIFACT_KINDS:
            walk(schema_for(kind), kind)

    def test_every_pattern_compiles_and_every_enum_is_populated(self):
        def walk(node):
            if "pattern" in node:
                re.compile(node["pattern"])
            if "enum" in node:
                self.assertTrue(node["enum"])
                self.assertEqual(len(node["enum"]), len(set(node["enum"])))
            for sub in node.get("properties", {}).values():
                walk(sub)
            if "items" in node:
                walk(node["items"])

        for kind in RUNTIME_KINDS + S.ARTIFACT_KINDS:
            walk(schema_for(kind))


# ----------------------------------------------------- generated variants

class EveryKindTests(SchemaCase):
    def test_the_good_payload_for_every_kind_is_accepted(self):
        for kind, payload in GOOD.items():
            with self.subTest(kind=kind):
                validate(payload, schema_for(kind))

    def test_key_order_does_not_matter(self):
        for kind, payload in GOOD.items():
            shuffled = dict(reversed(list(payload.items())))
            with self.subTest(kind=kind):
                validate(shuffled, schema_for(kind))

    def test_dropping_any_required_key_is_rejected_at_that_key(self):
        for kind, keys in REQUIRED.items():
            for key in keys:
                with self.subTest(kind=kind, dropped=key):
                    payload = {k: v for k, v in GOOD[kind].items() if k != key}
                    err = self.rejects(payload, schema_for(kind),
                                       "required", f"$.{key}")
                    self.assertEqual(err.expected, "present")

    def test_an_unknown_top_level_key_is_rejected_at_that_key(self):
        for kind in GOOD:
            with self.subTest(kind=kind):
                payload = {**GOOD[kind], "bogus": 1}
                self.kind_rejects(payload, "additionalProperties", "$.bogus")

    def test_a_payload_stamped_with_another_kind_is_rejected(self):
        for kind in GOOD:
            other = "halt" if kind != "halt" else "merge"
            with self.subTest(kind=kind):
                payload = {**GOOD[kind], "kind": other}
                self.rejects(payload, schema_for(kind), "enum", "$.kind")

    def test_every_present_key_enforces_its_type(self):
        for kind, payload in GOOD.items():
            for key, value in payload.items():
                if key == "kind":
                    continue                  # an enum, covered above
                wrong = 12345 if isinstance(value, str) else "not-that-type"
                with self.subTest(kind=kind, key=key):
                    with self.assertRaises(Rejection) as ctx:
                        validate({**payload, key: wrong}, schema_for(kind))
                    self.assertEqual(ctx.exception.field, f"$.{key}")

    def test_a_non_object_payload_is_a_type_rejection(self):
        for kind in GOOD:
            for bad in ([], "x", 3, None):
                with self.subTest(kind=kind, payload=bad):
                    self.rejects(bad, schema_for(kind), "type", "$")

    def test_validation_never_mutates_its_input(self):
        for kind, payload in GOOD.items():
            before = copy.deepcopy(payload)
            validate(payload, schema_for(kind))
            self.assertEqual(payload, before)


class EnvelopeTests(SchemaCase):
    def test_the_schema_version_stamp_is_not_blank(self):
        self.kind_rejects({**GOOD["halt"], "v": ""}, "minLength", "$.v")


class IdAnchoringTests(SchemaCase):
    """Ids become directory names and graph keys: they must match exactly."""

    def test_task_ids_are_full_task_ids_everywhere_they_appear(self):
        cases = {"report": "task", "verdict": "task", "heartbeat": "task",
                 "needs_context": "task", "ruling": "for_task"}
        for kind, key in cases.items():
            payload = {**GOOD[kind], key: TASK}
            validate(payload, schema_for(kind))
            for bad in ("T01", "P01-T01", f"x{TASK}", f"{TASK}x",
                        f"{INIT}-P01-T1", f"{INIT}-P01-T001", PLAN, ""):
                with self.subTest(kind=kind, value=bad):
                    self.kind_rejects({**payload, key: bad}, "pattern",
                                      f"$.{key}")

    def test_criterion_ids_are_anchored(self):
        for good in ("V1", "V12", "V007"):
            validate({**GOOD["evidence"], "criterion": good},
                     schema_for("evidence"))
        for bad in ("V", "xV1", "V1x", "v1", "1", ""):
            with self.subTest(value=bad):
                self.kind_rejects({**GOOD["evidence"], "criterion": bad},
                                  "pattern", "$.criterion")

    def test_plan_ids_in_a_merge_are_full_plan_ids(self):
        for bad in ("P01", f"{INIT}-P1", f"{PLAN}-T01", f"x{PLAN}", TASK):
            with self.subTest(value=bad):
                self.kind_rejects({**GOOD["merge"], "plan": bad}, "pattern",
                                  "$.plan")

    def test_audit_and_repair_targets_are_an_artifact_or_a_plan(self):
        for kind in ("audit", "repair"):
            for good in (f"{INIT}-CHTR-01", f"{INIT}-ADR-07", PLAN):
                with self.subTest(kind=kind, target=good):
                    validate({**GOOD[kind], "target": good}, schema_for(kind))
            for bad in (TASK, "INIT-0001", "charter", f"{INIT}-FOO-01",
                        f"x{PLAN}", f"{PLAN}x", ""):
                with self.subTest(kind=kind, target=bad):
                    self.kind_rejects({**GOOD[kind], "target": bad},
                                      "pattern", "$.target")

    def test_a_dispatch_id_is_required_and_exact_for_a_spawn_error(self):
        for bad in ("D1", "d00001", "D00001x", "x", ""):
            with self.subTest(value=bad):
                self.kind_rejects({**GOOD["spawn_error"], "dispatch_id": bad},
                                  "pattern", "$.dispatch_id")
        validate({**GOOD["spawn_error"], "dispatch_id": "D123456"},
                 schema_for("spawn_error"))


class RuntimePayloadTests(SchemaCase):
    def test_report_result_and_summary(self):
        for result in ("DONE", "DONE_WITH_CONCERNS", "BLOCKED", "PARTIAL"):
            validate({**GOOD["report"], "result": result},
                     schema_for("report"))
        self.kind_rejects({**GOOD["report"], "result": "OK"}, "enum",
                          "$.result")
        self.kind_rejects({**GOOD["report"], "summary": ""}, "minLength",
                          "$.summary")

    def test_report_commits_are_non_empty_strings(self):
        validate({**GOOD["report"], "commits": []}, schema_for("report"))
        self.kind_rejects({**GOOD["report"], "commits": [""]}, "minLength",
                          "$.commits[0]")
        self.kind_rejects({**GOOD["report"], "commits": [7]}, "type",
                          "$.commits[0]")

    def test_report_tests_need_name_ran_and_passed(self):
        row = {"name": "unit", "ran": True, "passed": False, "detail": "x"}
        validate({**GOOD["report"], "tests": [row]}, schema_for("report"))
        for key in ("name", "ran", "passed"):
            bad = {k: v for k, v in row.items() if k != key}
            with self.subTest(missing=key):
                self.kind_rejects({**GOOD["report"], "tests": [bad]},
                                  "required", f"$.tests[0].{key}")
        self.kind_rejects({**GOOD["report"], "tests": [{**row, "ran": "yes"}]},
                          "type", "$.tests[0].ran")

    def test_report_concerns_and_model_are_optional(self):
        validate({**GOOD["report"], "concerns": ["slow"],
                  "model_actual": "m"}, schema_for("report"))

    def test_verdict_round_is_a_positive_integer(self):
        for good in (1, 2, 99):
            validate({**GOOD["verdict"], "round": good},
                     schema_for("verdict"))
        for bad in (0, -1):
            self.kind_rejects({**GOOD["verdict"], "round": bad}, "minimum",
                              "$.round")
        for bad in (1.0, "1", True):
            with self.subTest(round=bad):
                self.kind_rejects({**GOOD["verdict"], "round": bad}, "type",
                                  "$.round")

    def test_verdict_enums(self):
        for q in ("APPROVED", "NEEDS_FIXES", "APPROVED_WITH_ROUTED_RESIDUALS"):
            validate({**GOOD["verdict"], "quality_verdict": q},
                     schema_for("verdict"))
        self.kind_rejects({**GOOD["verdict"], "quality_verdict": "LGTM"},
                          "enum", "$.quality_verdict")
        self.kind_rejects({**GOOD["verdict"], "spec_verdict": "pass"}, "enum",
                          "$.spec_verdict")

    def test_verdict_revisions_need_at_least_four_characters(self):
        for key in ("commit_base", "commit_head", "reviewed_package_sha"):
            validate({**GOOD["verdict"], key: "abcd"}, schema_for("verdict"))
            with self.subTest(key=key):
                self.kind_rejects({**GOOD["verdict"], key: "abc"},
                                  "minLength", f"$.{key}")

    def test_finding_shape(self):
        finding = {"id": "F1", "severity": "important", "claim": "bug",
                   "evidence": "a.py:3", "fix_scope": "class",
                   "class_hint": "all callers", "status": "open"}
        validate({**GOOD["verdict"], "findings": [finding]},
                 schema_for("verdict"))
        validate({**GOOD["verdict"], "findings": [
            {"id": "F1", "severity": "info", "claim": "c"}]},
            schema_for("verdict"))
        for key, bad, code in (("severity", "huge", "enum"),
                               ("fix_scope", "global", "enum"),
                               ("status", "done", "enum"),
                               ("claim", "", "minLength"),
                               ("id", "", "minLength")):
            with self.subTest(key=key):
                self.kind_rejects({**GOOD["verdict"], "findings": [
                    {**finding, key: bad}]}, code, f"$.findings[0].{key}")
        for key in ("id", "severity", "claim"):
            with self.subTest(missing=key):
                row = {k: v for k, v in finding.items() if k != key}
                self.kind_rejects({**GOOD["verdict"], "findings": [row]},
                                  "required", f"$.findings[0].{key}")

    def test_heartbeat_note_is_capped_at_four_hundred_characters(self):
        validate({**GOOD["heartbeat"], "note": "n" * 400},
                 schema_for("heartbeat"))
        self.kind_rejects({**GOOD["heartbeat"], "note": "n" * 401},
                          "maxLength", "$.note")

    def test_evidence_verdict_and_free_text(self):
        for verdict in ("proven", "unavailable", "failed"):
            validate({**GOOD["evidence"], "verdict": verdict},
                     schema_for("evidence"))
        self.kind_rejects({**GOOD["evidence"], "verdict": "passed"}, "enum",
                          "$.verdict")
        for key in ("command", "observed"):
            self.kind_rejects({**GOOD["evidence"], key: ""}, "minLength",
                              f"$.{key}")
        self.kind_rejects({**GOOD["evidence"], "state_commit": "abc"},
                          "minLength", "$.state_commit")
        validate({**GOOD["evidence"], "artifacts": ["a.log", "b.png"]},
                 schema_for("evidence"))

    def test_a_gate_decision_names_a_real_phase_and_who_decided(self):
        for phase in PHASES:
            validate({**GOOD["gate_decision"], "phase": phase},
                     schema_for("gate_decision"))
        self.kind_rejects({**GOOD["gate_decision"], "phase": "bogus"}, "enum",
                          "$.phase")
        for decision in ("approved", "rejected", "waived"):
            validate({**GOOD["gate_decision"], "decision": decision},
                     schema_for("gate_decision"))
        self.kind_rejects({**GOOD["gate_decision"], "decision": "yes"},
                          "enum", "$.decision")
        for by in ("human", "auto"):
            validate({**GOOD["gate_decision"], "by": by},
                     schema_for("gate_decision"))
        self.kind_rejects({**GOOD["gate_decision"], "by": "robot"}, "enum",
                          "$.by")
        validate({**GOOD["gate_decision"], "note": "ok"},
                 schema_for("gate_decision"))

    def test_ruling_optional_fields(self):
        validate({**GOOD["ruling"], "cost_if_wrong": "x", "answered": "q",
                  "unsolicited": "u", "stop": True, "for_task": TASK},
                 schema_for("ruling"))
        self.kind_rejects({**GOOD["ruling"], "stop": "yes"}, "type",
                          "$.stop")
        for key in ("decision", "why"):
            self.kind_rejects({**GOOD["ruling"], key: ""}, "minLength",
                              f"$.{key}")

    def test_audit_findings_and_verdict(self):
        self.kind_rejects({**GOOD["audit"], "verdict": "MAYBE"}, "enum",
                          "$.verdict")
        self.kind_rejects({**GOOD["audit"], "round": 0}, "minimum",
                          "$.round")
        validate({**GOOD["audit"], "verdict": "FAIL", "findings": [
            {"id": "F1", "severity": "critical", "claim": "c"}]},
            schema_for("audit"))
        self.kind_rejects({**GOOD["audit"], "findings": [{"id": "F1"}]},
                          "required", "$.findings[0].severity")

    def test_repair_optional_fields(self):
        validate({**GOOD["repair"], "fixed": ["F1"], "note": "n",
                  "introduced": [{"id": "F2", "severity": "minor",
                                  "claim": "c"}]}, schema_for("repair"))
        self.kind_rejects({**GOOD["repair"], "round": 0}, "minimum",
                          "$.round")
        self.kind_rejects({**GOOD["repair"], "fixed": [1]}, "type",
                          "$.fixed[0]")

    def test_halt_needs_a_reason(self):
        self.kind_rejects({**GOOD["halt"], "reason": ""}, "minLength",
                          "$.reason")

    def test_spawn_error_classes(self):
        for cls in ("rate_limit", "auth", "network", "session", "other"):
            validate({**GOOD["spawn_error"], "error_class": cls},
                     schema_for("spawn_error"))
        self.kind_rejects({**GOOD["spawn_error"], "error_class": "ENOENT"},
                          "enum", "$.error_class")
        validate({**GOOD["spawn_error"], "detail": "429"},
                 schema_for("spawn_error"))

    def test_needs_context_and_merge_fields(self):
        self.kind_rejects({**GOOD["needs_context"], "question": ""},
                          "minLength", "$.question")
        validate({**GOOD["needs_context"], "for_role": "supervisor"},
                 schema_for("needs_context"))
        self.kind_rejects({**GOOD["merge"], "merge_sha": "abc"}, "minLength",
                          "$.merge_sha")
        validate({**GOOD["merge"], "branch": "task/P01"}, schema_for("merge"))


class ArtifactPayloadTests(SchemaCase):
    def test_each_artifact_id_must_carry_its_own_kind_segment(self):
        for kind, seg in P.ARTIFACT_SEGMENTS.items():
            for other in set(P.ARTIFACT_SEGMENTS.values()) - {seg}:
                with self.subTest(kind=kind, wrong=other):
                    payload = {**GOOD[kind], "id": f"{INIT}-{other}-01"}
                    self.kind_rejects(payload, "pattern", "$.id")

    def test_an_artifact_id_must_match_exactly(self):
        for bad in ("INIT-0001-CHTR-01-x", "xINIT-0001-CHTR-01",
                    "INIT-0001-CHTR-1", "INIT-0001-CHTR-001",
                    "INIT-0001-chtr-01", PLAN, ""):
            with self.subTest(value=bad):
                self.kind_rejects({**GOOD["charter"], "id": bad}, "pattern",
                                  "$.id")

    def test_a_plan_is_identified_by_a_plan_id_not_an_artifact_id(self):
        self.kind_rejects({**GOOD["plan"], "id": f"{INIT}-CHTR-01"},
                          "pattern", "$.id")
        self.kind_rejects({**GOOD["plan"], "plan_id": f"{INIT}-CHTR-01"},
                          "pattern", "$.plan_id")

    def test_sections_are_validated_row_by_row(self):
        row = {"id": "s", "title": "t", "body": "b"}
        for key in row:
            with self.subTest(missing=key):
                bad = {k: v for k, v in row.items() if k != key}
                self.kind_rejects({**GOOD["charter"], "sections": [bad]},
                                  "required", f"$.sections[0].{key}")
        self.kind_rejects({**GOOD["charter"], "sections": [{**row,
                                                            "body": ""}]},
                          "minLength", "$.sections[0].body")

    def test_a_section_body_is_capped_at_twelve_thousand_characters(self):
        validate({**GOOD["charter"], "sections": [
            {"id": "s", "title": "t", "body": "b" * 12000}]},
            schema_for("charter"))
        self.kind_rejects({**GOOD["charter"], "sections": [
            {"id": "s", "title": "t", "body": "b" * 12001}]},
            "maxLength", "$.sections[0].body")

    def test_title_and_summary_are_not_blank(self):
        for key in ("title", "summary"):
            self.kind_rejects({**GOOD["charter"], key: ""}, "minLength",
                              f"$.{key}")

    def test_a_kind_rejects_collections_that_belong_to_other_kinds(self):
        self.kind_rejects({**GOOD["options"], "requirements": []},
                          "additionalProperties", "$.requirements")
        self.kind_rejects({**GOOD["charter"], "criteria": []},
                          "additionalProperties", "$.criteria")
        self.kind_rejects({**GOOD["spec"], "tasks": []},
                          "additionalProperties", "$.tasks")

    def test_requirements_and_constraints(self):
        for kind in ("charter", "spec"):
            req = {"id": "R1", "requirement": "r", "observable": "o",
                   "cites": ["x"]}
            con = {"id": "C1", "constraint": "c", "observable": "o"}
            validate({**GOOD[kind], "requirements": [req],
                      "constraints": [con], "risks": ["slow"]},
                     schema_for(kind))
            for bad in ("R", "xR1", "R1x", "r1"):
                with self.subTest(kind=kind, requirement_id=bad):
                    self.kind_rejects({**GOOD[kind], "requirements": [
                        {**req, "id": bad}]}, "pattern",
                        "$.requirements[0].id")
            for bad in ("C", "xC1", "C1x"):
                with self.subTest(kind=kind, constraint_id=bad):
                    self.kind_rejects({**GOOD[kind], "constraints": [
                        {**con, "id": bad}]}, "pattern",
                        "$.constraints[0].id")
            for key in ("id", "requirement", "observable"):
                with self.subTest(kind=kind, missing=key):
                    row = {k: v for k, v in req.items() if k != key}
                    self.kind_rejects({**GOOD[kind], "requirements": [row]},
                                      "required",
                                      f"$.requirements[0].{key}")

    def test_a_vrfy_must_carry_at_least_one_criterion(self):
        without = {k: v for k, v in GOOD["vrfy"].items() if k != "criteria"}
        self.kind_rejects(without, "required", "$.criteria")
        self.kind_rejects({**GOOD["vrfy"], "criteria": []}, "minItems",
                          "$.criteria")

    def test_vrfy_criteria_rows(self):
        row = {"id": "V2", "criterion": "c", "procedure": "p",
               "cites": ["INIT-0001-SPEC-01"]}
        validate({**GOOD["vrfy"], "criteria": [row]}, schema_for("vrfy"))
        for bad in ("V", "xV1", "V1x", "v1"):
            with self.subTest(criterion_id=bad):
                self.kind_rejects({**GOOD["vrfy"], "criteria": [
                    {**row, "id": bad}]}, "pattern", "$.criteria[0].id")
        for key in ("criterion", "procedure"):
            self.kind_rejects({**GOOD["vrfy"], "criteria": [
                {**row, key: ""}]}, "minLength", f"$.criteria[0].{key}")

    def test_a_plan_needs_an_objective_and_at_least_one_task(self):
        self.kind_rejects({**GOOD["plan"], "tasks": []}, "minItems",
                          "$.tasks")
        self.kind_rejects({**GOOD["plan"], "objective": ""}, "minLength",
                          "$.objective")
        validate({**GOOD["plan"], "gates": ["tests"]}, schema_for("plan"))

    def test_plan_task_rows(self):
        task = {"id": "T02", "title": "t", "goal": "g", "files": ["a"],
                "accepts": ["x"], "provides": ["p"], "consumes": ["c"],
                "depends_on": ["T01"]}
        validate({**GOOD["plan"], "tasks": [task]}, schema_for("plan"))
        for bad in ("T1", "T001", "xT01", "T01x", "t01", "", "01"):
            with self.subTest(task_id=bad):
                self.kind_rejects({**GOOD["plan"], "tasks": [
                    {**task, "id": bad}]}, "pattern", "$.tasks[0].id")
            with self.subTest(depends_on=bad):
                self.kind_rejects({**GOOD["plan"], "tasks": [
                    {**task, "depends_on": [bad]}]}, "pattern",
                    "$.tasks[0].depends_on[0]")
        for key in ("files", "accepts"):
            self.kind_rejects({**GOOD["plan"], "tasks": [
                {**task, key: []}]}, "minItems", f"$.tasks[0].{key}")
            self.kind_rejects({**GOOD["plan"], "tasks": [
                {**task, key: [""]}]}, "minLength", f"$.tasks[0].{key}[0]")
        for key in ("id", "title", "goal", "files", "accepts"):
            row = {k: v for k, v in task.items() if k != key}
            with self.subTest(missing=key):
                self.kind_rejects({**GOOD["plan"], "tasks": [row]},
                                  "required", f"$.tasks[0].{key}")

    def test_arch_and_design_decisions_and_interfaces(self):
        adr = {"id": "A1", "title": "t", "decision": "d", "why": "w",
               "cost_if_wrong": "c", "alternatives": ["x"]}
        ifce = {"id": "I1", "title": "t", "provides": ["p"],
                "consumes": ["c"]}
        for kind in ("arch", "design"):
            validate({**GOOD[kind], "adrs": [adr], "ifces": [ifce]},
                     schema_for(kind))
            for key in ("id", "title", "decision", "why"):
                with self.subTest(kind=kind, missing_adr=key):
                    row = {k: v for k, v in adr.items() if k != key}
                    self.kind_rejects({**GOOD[kind], "adrs": [row]},
                                      "required", f"$.adrs[0].{key}")
            for key in ("id", "title"):
                with self.subTest(kind=kind, missing_ifce=key):
                    row = {k: v for k, v in ifce.items() if k != key}
                    self.kind_rejects({**GOOD[kind], "ifces": [row]},
                                      "required", f"$.ifces[0].{key}")

    def test_risk_register_rows(self):
        row = {"id": "K1", "risk": "r", "likelihood": "low",
               "impact": "high", "mitigation": "m"}
        validate({**GOOD["risk"], "risks": [row]}, schema_for("risk"))
        for key in ("likelihood", "impact"):
            for level in ("high", "medium", "low"):
                validate({**GOOD["risk"], "risks": [{**row, key: level}]},
                         schema_for("risk"))
            with self.subTest(enum=key):
                self.kind_rejects({**GOOD["risk"], "risks": [
                    {**row, key: "extreme"}]}, "enum", f"$.risks[0].{key}")
        for key in ("id", "risk", "likelihood", "impact", "mitigation"):
            with self.subTest(missing=key):
                bad = {k: v for k, v in row.items() if k != key}
                self.kind_rejects({**GOOD["risk"], "risks": [bad]},
                                  "required", f"$.risks[0].{key}")

    def test_cites_are_a_list_of_strings(self):
        validate({**GOOD["charter"], "cites": [f"{INIT}-CHTR-01"]},
                 schema_for("charter"))
        self.kind_rejects({**GOOD["charter"], "cites": [1]}, "type",
                          "$.cites[0]")


# ------------------------------------------------- keyword scope and bounds

class KeywordScopeTests(SchemaCase):
    """A keyword only constrains the type it belongs to (JSON Schema). A stray
    one on another type must be ignored: neither a crash nor a rejection."""

    def test_string_keywords_ignore_other_types(self):
        for kw in ({"minLength": 3}, {"maxLength": 1}, {"pattern": "x"}):
            with self.subTest(keyword=kw):
                self.accepts(5, {"type": "integer", **kw})

    def test_integer_keywords_ignore_other_types(self):
        self.accepts("a", {"type": "string", "minimum": 5})

    def test_object_keywords_ignore_other_types(self):
        self.accepts([], {"type": "array", "required": ["a"]})

    def test_array_keywords_ignore_other_types(self):
        self.accepts({}, {"type": "object", "minItems": 2})
        self.accepts({"x": 1}, {"type": "object", "items": S._str(minLength=9)})


# The numeric contract of the vocabulary, pinned as literals so that a changed
# bound cannot hide behind a test that reads the very schema it is checking.
# Rows are (group, path, constraint) -> value. Group "artifact" covers every
# artifact kind, "*" the envelope every payload carries.
BOUNDS = {
    ("*", "v", "minLength"): 1,
    ("artifact", "title", "minLength"): 1,
    ("artifact", "summary", "minLength"): 1,
    ("artifact", "sections[].id", "minLength"): 1,
    ("artifact", "sections[].title", "minLength"): 1,
    ("artifact", "sections[].body", "minLength"): 1,
    ("artifact", "sections[].body", "maxLength"): 12000,
    ("artifact", "requirements[].requirement", "minLength"): 1,
    ("artifact", "constraints[].constraint", "minLength"): 1,
    ("artifact", "criteria", "minItems"): 1,
    ("artifact", "criteria[].criterion", "minLength"): 1,
    ("artifact", "criteria[].procedure", "minLength"): 1,
    ("artifact", "objective", "minLength"): 1,
    ("artifact", "tasks", "minItems"): 1,
    ("artifact", "tasks[].title", "minLength"): 1,
    ("artifact", "tasks[].goal", "minLength"): 1,
    ("artifact", "tasks[].files", "minItems"): 1,
    ("artifact", "tasks[].files[]", "minLength"): 1,
    ("artifact", "tasks[].accepts", "minItems"): 1,
    ("artifact", "tasks[].accepts[]", "minLength"): 1,
    ("artifact", "adrs[].id", "minLength"): 1,
    ("artifact", "adrs[].title", "minLength"): 1,
    ("artifact", "adrs[].decision", "minLength"): 1,
    ("artifact", "adrs[].why", "minLength"): 1,
    ("artifact", "ifces[].id", "minLength"): 1,
    ("artifact", "ifces[].title", "minLength"): 1,
    ("artifact", "risks[].id", "minLength"): 1,
    ("artifact", "risks[].risk", "minLength"): 1,
    ("artifact", "risks[].mitigation", "minLength"): 1,
    ("report", "summary", "minLength"): 1,
    ("report", "commits[]", "minLength"): 1,
    ("report", "tests[].name", "minLength"): 1,
    ("verdict", "round", "minimum"): 1,
    ("verdict", "findings[].id", "minLength"): 1,
    ("verdict", "findings[].claim", "minLength"): 1,
    ("verdict", "commit_base", "minLength"): 4,
    ("verdict", "commit_head", "minLength"): 4,
    ("verdict", "reviewed_package_sha", "minLength"): 4,
    ("heartbeat", "note", "maxLength"): 400,
    ("evidence", "command", "minLength"): 1,
    ("evidence", "observed", "minLength"): 1,
    ("evidence", "state_commit", "minLength"): 4,
    ("ruling", "decision", "minLength"): 1,
    ("ruling", "why", "minLength"): 1,
    ("audit", "round", "minimum"): 1,
    ("audit", "findings[].id", "minLength"): 1,
    ("audit", "findings[].claim", "minLength"): 1,
    ("repair", "round", "minimum"): 1,
    ("repair", "introduced[].id", "minLength"): 1,
    ("repair", "introduced[].claim", "minLength"): 1,
    ("halt", "reason", "minLength"): 1,
    ("needs_context", "question", "minLength"): 1,
    ("merge", "merge_sha", "minLength"): 4,
}
ALL_KINDS = RUNTIME_KINDS + S.ARTIFACT_KINDS
CONSTRAINTS = ("minLength", "maxLength", "minItems", "minimum")

# One valid example per pattern in use. A new pattern with no sample here
# fails test_every_pattern_in_use_has_a_sample_value.
PATTERN_SAMPLES = {
    P.TASK_ID: TASK, P.PLAN_ID: PLAN, P.DISPATCH_ID: "D00001",
    S.ARTIFACT_OR_PLAN: PLAN, S.TASK_LOCAL: "T01",
    r"R\d+": "R1", r"C\d+": "C1", r"V\d+": "V1",
    **{P.artifact_pattern(k): f"{INIT}-{seg}-01"
       for k, seg in P.ARTIFACT_SEGMENTS.items()},
}


def walk(node, path=()):
    """(path, constraint, value) for every bound in a schema, depth first."""
    for c in CONSTRAINTS:
        if c in node:
            yield path, c, node[c]
    for key, sub in node.get("properties", {}).items():
        yield from walk(sub, path + (key,))
    if "items" in node:
        yield from walk(node["items"], path + ("[]",))


def dotted(path) -> str:
    out = ""
    for step in path:
        out += "[]" if step == "[]" else ("." if out else "") + step
    return out


def steps_of(text: str) -> list[str]:
    return re.findall(r"[^.\[\]]+|\[\]", text)


def observed_bounds():
    """The bounds the schemas actually carry, grouped like BOUNDS, with a
    kind that owns each one and any two kinds that disagree."""
    rows, home, clashes = {}, {}, []
    groups = [("artifact", S.ARTIFACT_KINDS)] + \
             [(k, [k]) for k in RUNTIME_KINDS]
    for group, kinds in groups:
        for kind in kinds:
            for path, c, v in walk(schema_for(kind)):
                d = dotted(path)
                key = ("*", d, c) if d == "v" else (group, d, c)
                if key in rows and rows[key] != v:
                    clashes.append((key, rows[key], v))
                rows[key] = v
                home.setdefault(key, kind)
    return rows, home, clashes


def minimal(node: dict) -> Any:
    """The smallest value a schema accepts."""
    if "enum" in node:
        return node["enum"][0]
    kind = node["type"]
    if kind == "string":
        if "pattern" in node:
            return PATTERN_SAMPLES[node["pattern"]]
        return "x" * node.get("minLength", 0)
    if kind == "integer":
        return node.get("minimum", 0)
    if kind == "boolean":
        return False
    if kind == "array":
        return [minimal(node["items"]) for _ in range(node.get("minItems", 0))]
    return {k: minimal(node["properties"][k]) for k in node.get("required", [])}


def inject(node: dict, steps: list[str], value: Any) -> Any:
    """minimal(node) with `value` placed at `steps`, creating optional
    properties and array items on the way down."""
    if not steps:
        return value
    head, rest = steps[0], steps[1:]
    if head == "[]":
        return [inject(node["items"], rest, value)]
    obj = minimal(node)
    obj[head] = inject(node["properties"][head], rest, value)
    return obj


def node_at(schema: dict, steps: list[str]) -> dict:
    for step in steps:
        schema = schema["items"] if step == "[]" else \
            schema["properties"][step]
    return schema


def boundary(constraint: str, value: int, node: dict) -> tuple[Any, Any]:
    """(an accepted value, the nearest rejected one) at the literal bound."""
    if constraint == "minLength":
        return "x" * value, "x" * (value - 1)
    if constraint == "maxLength":
        return "x" * value, "x" * (value + 1)
    if constraint == "minItems":
        item = minimal(node["items"])
        return [item] * value, [item] * (value - 1)
    return value, value - 1                     # minimum


class BoundsContractTests(SchemaCase):
    def test_every_bound_in_every_schema_is_pinned_and_nothing_else_is(self):
        rows, _home, clashes = observed_bounds()
        self.assertEqual(clashes, [])               # kinds agree on a path
        self.assertEqual(rows, BOUNDS)

    def test_every_pattern_in_use_has_a_sample_value(self):
        used: set[str] = set()

        def collect(node):
            if "pattern" in node:
                used.add(node["pattern"])
            for sub in node.get("properties", {}).values():
                collect(sub)
            if "items" in node:
                collect(node["items"])

        for kind in ALL_KINDS:
            collect(schema_for(kind))
        self.assertEqual(used - set(PATTERN_SAMPLES), set())
        for pattern in used:
            with self.subTest(pattern=pattern):
                self.assertIsNotNone(
                    re.fullmatch(pattern, PATTERN_SAMPLES[pattern]))

    def test_the_minimal_instance_of_every_schema_is_valid(self):
        for kind in ALL_KINDS:
            with self.subTest(kind=kind):
                validate(minimal(schema_for(kind)), schema_for(kind))

    def test_each_pinned_bound_is_enforced_at_exactly_its_value(self):
        _rows, home, _clashes = observed_bounds()
        self.assertGreater(len(BOUNDS), 50)
        for (group, path, constraint), value in BOUNDS.items():
            schema = schema_for(home[(group, path, constraint)])
            steps = steps_of(path)
            ok, bad = boundary(constraint, value, node_at(schema, steps))
            field = "$" + "".join("[0]" if s == "[]" else f".{s}"
                                  for s in steps)
            with self.subTest(group=group, path=path, bound=constraint):
                validate(inject(schema, steps, ok), schema)
                self.rejects(inject(schema, steps, bad), schema, constraint,
                             field)


# ----------------------------------------------------------------- fuzzing

def random_json(rng: random.Random, depth: int = 0):
    pick = rng.randrange(8 if depth < 3 else 5)
    if pick == 0:
        return None
    if pick == 1:
        return rng.random() < 0.5
    if pick == 2:
        return rng.randrange(-5, 10**6)
    if pick == 3:
        return rng.random() * 100
    if pick == 4:
        return rng.choice(["", "x", f"{INIT}-CHTR-01", "T01", "V1",
                           "D00001", "é" * 3, "a" * 13000, TASK, PLAN])
    if pick == 5:
        return [random_json(rng, depth + 1) for _ in range(rng.randrange(3))]
    return {rng.choice(["id", "kind", "x", "round", "task"]):
            random_json(rng, depth + 1) for _ in range(rng.randrange(3))}


def paths_of(node, prefix=()):
    """Every addressable location in a JSON tree."""
    yield prefix
    if isinstance(node, dict):
        for k, v in node.items():
            yield from paths_of(v, prefix + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from paths_of(v, prefix + (i,))


def mutate(rng: random.Random, payload: dict) -> dict:
    out = copy.deepcopy(payload)
    where = rng.choice(list(paths_of(out)))
    if not where:
        return random_json(rng)  # type: ignore[return-value]
    parent = out
    for step in where[:-1]:
        parent = parent[step]
    last = where[-1]
    action = rng.randrange(3)
    if action == 0:
        parent[last] = random_json(rng)
    elif action == 1 and isinstance(parent, dict):
        del parent[last]
    elif isinstance(parent, dict):
        parent[rng.choice(["extra", "id", "round"])] = random_json(rng)
    else:
        parent[last] = random_json(rng)
    return out


class FuzzTests(SchemaCase):
    ROUNDS = 400

    def test_mutated_payloads_are_accepted_or_typed_rejections_never_crashes(
            self):
        rng = random.Random(0xC0FFEE)
        checked = rejected = 0
        for kind, payload in sorted(GOOD.items()):
            schema = schema_for(kind)
            for i in range(self.ROUNDS):
                mutant = mutate(rng, payload)
                before = copy.deepcopy(mutant)
                try:
                    validate(mutant, schema)
                except Rejection as r:
                    rejected += 1
                    d = r.to_dict()
                    self.assertEqual(set(d), {"code", "field", "expected",
                                              "got", "hint"})
                    self.assertTrue(all(isinstance(v, str)
                                        for v in d.values()), d)
                    self.assertTrue(d["field"].startswith("$"), d)
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"{kind} mutation #{i} crashed the validator "
                              f"with {type(exc).__name__}: {exc}\n{mutant!r}")
                self.assertEqual(mutant, before, "validate mutated input")
                checked += 1
        self.assertEqual(checked, self.ROUNDS * len(GOOD))
        self.assertGreater(rejected, checked // 2)   # the fuzzer has teeth

    def test_arbitrary_json_against_every_schema_never_crashes(self):
        rng = random.Random(1234)
        for kind in sorted(GOOD):
            schema = schema_for(kind)
            for _ in range(200):
                value = random_json(rng)
                try:
                    validate(value, schema)
                except Rejection:
                    pass


if __name__ == "__main__":
    unittest.main()
