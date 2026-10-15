# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Engine tunables come from files, per project and per initiative. The files
are validated, the effective values are journaled when they change, and the
journal alone decides what a run does."""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

import _payloads as PL
from _live import Live
from executor.engine import check, emit_next, fold, ingest
from executor.paths import initiative_policy_file, project_policy_file
from executor.policy import DEFAULTS, load_policy
from executor.store import ExecError

INIT = PL.INIT


class PolicyCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def write(self, path: Path, doc) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")

    def project(self, doc) -> None:
        self.write(project_policy_file(self.live.root), doc)

    def initiative(self, doc) -> None:
        self.write(initiative_policy_file(self.live.root, INIT), doc)

    def policy_events(self) -> list[dict]:
        return [e for e in self.live.events() if e["kind"] == "policy"]


class Layers(PolicyCase):
    def test_with_no_files_the_built_in_defaults_apply(self):
        values, sources = load_policy(self.live.root, INIT)
        self.assertEqual(values, DEFAULTS)
        self.assertEqual(set(sources.values()), {"default"})

    def test_an_empty_policy_file_is_valid_and_changes_nothing(self):
        self.project({"v": "v1"})
        self.assertEqual(load_policy(self.live.root, INIT)[0], DEFAULTS)

    def test_the_project_file_overrides_the_defaults_key_by_key(self):
        self.project({"v": "v1", "max_fix_rounds": 3})
        values, sources = load_policy(self.live.root, INIT)
        self.assertEqual(values["max_fix_rounds"], 3)
        self.assertEqual(sources["max_fix_rounds"], "project")
        self.assertEqual(sources["max_plans"], "default")

    def test_the_initiative_file_overrides_the_project_file(self):
        self.project({"v": "v1", "deadline_s": 600})
        self.initiative({"v": "v1", "suspect_s": 60, "deadline_s": 300})
        values, sources = load_policy(self.live.root, INIT)
        self.assertEqual((values["deadline_s"], sources["deadline_s"]), (300, "initiative"))
        self.assertEqual((values["suspect_s"], sources["suspect_s"]), (60, "initiative"))


class Refusals(PolicyCase):
    BAD = (
        ({"v": "v1", "bogus": 1}, "unknown key"),
        ({"v": "v2"}, "unknown version"),
        ({}, "missing version"),
        ({"v": "v1", "max_plans": "nine"}, "wrong type"),
        ({"v": "v1", "max_plans": True}, "boolean for an integer"),
        ({"v": "v1", "max_plans": 100}, "above the bound"),
        ({"v": "v1", "spawn_retry_cap": -1}, "below the bound"),
        ({"v": "v1", "suspect_s": 3600, "deadline_s": 3600}, "suspect not below deadline"),
        ({"v": "v1", "clean_quality": ["MAYBE"]}, "unknown quality verdict"),
        ({"v": "v1", "clean_quality": []}, "empty clean set"),
    )

    def test_every_malformed_or_out_of_range_document_is_refused(self):
        for doc, why in self.BAD:
            with self.subTest(why=why):
                self.project(doc)
                with self.assertRaises(ExecError) as ctx:
                    load_policy(self.live.root, INIT)
                self.assertEqual(ctx.exception.code, "policy_invalid")

    def test_unreadable_json_and_non_objects_are_refused(self):
        for raw in ("{not json", "[1, 2]"):
            with self.subTest(raw=raw):
                self.project(raw)
                with self.assertRaises(ExecError) as ctx:
                    load_policy(self.live.root, INIT)
                self.assertEqual(ctx.exception.code, "policy_invalid")


class Journaling(PolicyCase):
    def test_creation_journals_the_effective_policy(self):
        events = self.policy_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["data"]["values"], DEFAULTS)

    def test_a_changed_file_is_journaled_at_the_next_poll_and_an_unchanged_one_is_not(self):
        before = len(self.policy_events())
        self.project({"v": "v1", "max_fix_rounds": 3})
        self.live.act()
        self.assertEqual(len(self.policy_events()), before + 1)
        self.live.act()
        self.assertEqual(len(self.policy_events()), before + 1)
        last = self.policy_events()[-1]["data"]
        self.assertEqual((last["values"]["max_fix_rounds"], last["sources"]["max_fix_rounds"]),
                         (3, "project"))


class LiveEffects(PolicyCase):
    def test_a_lowered_deadline_abandons_a_silent_dispatch_at_the_next_poll(self):
        impl = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        self.project({"v": "v1", "suspect_s": 60, "deadline_s": 120})
        again = self.live.act(now=time.time() + 121)
        self.assertEqual(again["action"], "DISPATCH")
        self.assertNotEqual(again["dispatch_id"], impl["dispatch_id"])
        self.assertEqual([e["kind"] for e in self.live.events()[-3:]],
                         ["policy", "abandon", "task_dispatched"])

    def test_a_lowered_fix_cap_escalates_after_one_failed_review(self):
        self.project({"v": "v1", "max_fix_rounds": 1})
        review = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        ctx = review["context"]
        ingest(self.init, PL.verdict(task=PL.TASK, rnd=ctx["round"], base=ctx["base"],
                                     head=ctx["head"], reviewed_package_sha=ctx["package_sha"],
                                     spec="FAIL", findings=[PL.finding()]))
        act = self.live.act()
        self.assertEqual(act["action"], "ESCALATE")
        self.assertIn("fix-round cap (1)", act["reason"])

    def test_the_clean_quality_set_is_read_from_the_journaled_policy(self):
        self.project({"v": "v1", "clean_quality": ["APPROVED", "NEEDS_FIXES"]})
        review = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        ctx = review["context"]
        ingest(self.init, PL.verdict(task=PL.TASK, rnd=ctx["round"], base=ctx["base"],
                                     head=ctx["head"], reviewed_package_sha=ctx["package_sha"],
                                     quality="NEEDS_FIXES"))
        self.assertEqual(fold(self.live.events())["tasks"][PL.TASK]["state"], "complete")

    def test_an_invalid_policy_file_stops_the_engine_rather_than_deciding_from_it(self):
        self.write(project_policy_file(self.live.root), "{bad")
        with self.assertRaises(ExecError) as ctx:
            emit_next(self.init)
        self.assertEqual(ctx.exception.code, "policy_invalid")


class Drift(PolicyCase):
    def test_check_reports_drift_until_the_next_write_records_it(self):
        self.live.act()
        self.project({"v": "v1", "max_fix_rounds": 3})
        self.assertTrue(any(p.startswith("policy drift")
                            for p in check(self.init)["problems"]))
        self.live.act()
        self.assertFalse(any(p.startswith("policy drift")
                             for p in check(self.init)["problems"]))

    def test_check_reports_an_invalid_policy_file_without_writing(self):
        self.write(project_policy_file(self.live.root), "{bad")
        before = len(self.live.events())
        self.assertTrue(any(p.startswith("policy invalid")
                            for p in check(self.init)["problems"]))
        self.assertEqual(len(self.live.events()), before)


if __name__ == "__main__":
    unittest.main()
