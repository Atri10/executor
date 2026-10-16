# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Layout: every canonical file lands at its canonical path, and the decisions
that choose what a file holds (review packages, preflight, repairs, plans)."""
from __future__ import annotations

import unittest
from pathlib import Path

import _payloads as PL
from _live import Live
from executor.engine import check, fold, ingest
from executor.policy import DEFAULTS
from executor.paths import (artifact_file, audit_file, docs_artifact_file,
                            docs_export_journal, docs_artifact_md, docs_index_file,
                            docs_index_md,
                            docs_plan_file, docs_report_file, docs_verdict_file,
                            journal_file, plan_audit_file, plan_file,
                            preflight_file, repair_file, review_package_file,
                            task_impl_report, verdict_file)
from executor.store import read_json, sha256

MAX_PLANS = DEFAULTS["max_plans"]

INIT = PL.INIT
CHARTER = f"{INIT}-CHTR-01"


def _json(path: Path) -> dict:
    data = read_json(path)
    assert data is not None, f"{path} is missing or unreadable"
    return data


class LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def impl_dispatch_id(self) -> str:
        return next(e["dispatch_id"] for e in self.live.events()
                    if e["kind"] == "task_dispatched" and e["data"]["role"] == "impl")


class CanonicalLayout(LiveCase):
    def test_a_full_run_writes_each_canonical_file_and_the_check_is_clean(self):
        self.live.run(lambda a: a["action"] == "DONE")
        idir, root = self.init.idir, self.live.root
        did = self.impl_dispatch_id()
        expected = [
            artifact_file(idir, CHARTER), audit_file(idir, CHARTER, 1),
            plan_file(idir, PL.PLAN), plan_audit_file(idir, PL.PLAN, 1),
            plan_audit_file(idir, PL.PLAN, 2), preflight_file(idir, PL.PLAN),
            task_impl_report(idir, PL.TASK, did),
            review_package_file(idir, PL.TASK, 1), verdict_file(idir, PL.TASK, 1),
            docs_artifact_file(root, INIT, CHARTER),
            docs_plan_file(root, INIT, PL.PLAN),
            docs_report_file(root, INIT, PL.TASK, did),
            docs_verdict_file(root, INIT, PL.TASK, 1),
            docs_index_file(root, INIT), docs_index_md(root, INIT),
            docs_export_journal(root, INIT),
        ]
        for path in expected:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), path)
        self.assertEqual(check(self.init)["problems"], [])

    def test_the_committed_journal_export_is_a_byte_copy_of_the_journal(self):
        self.live.run(lambda a: a["action"] == "DONE")
        self.assertEqual(docs_export_journal(self.live.root, INIT).read_bytes(),
                         journal_file(self.init.idir).read_bytes())

    def test_a_spec_document_renders_its_requirements_and_constraints(self):
        """The committed markdown is generated from the payload: a spec's
        requirement and constraint sections appear in it."""
        draft = self.live.run(lambda a: a["action"] == "DISPATCH"
                              and a["role"] == "author"
                              and a["schema"] == "spec")
        spec = {**PL.art("spec"),
                "requirements": [{"id": "R1", "requirement": "log in",
                                  "observable": "session cookie"}],
                "constraints": [{"id": "C1", "constraint": "under 200ms",
                                 "observable": "p99"}]}
        ingest(self.init, spec)
        md = docs_artifact_md(self.live.root, INIT, spec["id"]).read_text()
        self.assertIn("### R1", md)
        self.assertIn("**C1**", md)


class ReviewPackages(LiveCase):
    def test_a_second_review_round_is_given_the_prior_findings_and_the_diff(self):
        review = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        ctx = review["context"]
        finding = PL.finding("F1", "important", "the loop never ends")
        ingest(self.init, PL.verdict(task=PL.TASK, rnd=ctx["round"], base=ctx["base"],
                                     head=ctx["head"],
                                     reviewed_package_sha=ctx["package_sha"],
                                     spec="FAIL", findings=[finding]))
        again = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        package = _json(review_package_file(self.init.idir, PL.TASK, 2))
        self.assertEqual(package["prior_findings"], [finding])
        self.assertTrue(package["changed_files"])
        self.assertEqual(again["context"]["package_sha"], package["package_sha"])


class Preflight(LiveCase):
    def test_overlapping_unordered_tasks_are_ruled_on_before_the_first_dispatch(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")
        ingest(self.init, PL.plan_payload(tasks=[PL.task_row("T01"), PL.task_row("T02")]))
        ask = self.live.run(lambda a: a["action"] == "ASK")
        self.assertEqual(ask["task"], PL.PLAN)
        self.assertIn("file ownership", ask["topic"])
        self.assertEqual(_json(preflight_file(self.init.idir, PL.PLAN))["verdict"],
                         "conflict")
        ingest(self.init, PL.ruling(decision="run T01 first", why="both touch a.py",
                                    for_task=PL.PLAN), actor="human")
        impl = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        self.assertEqual(impl["entity"], f"{PL.PLAN}-T01")


class RepairRecords(LiveCase):
    def test_a_repair_is_recorded_against_the_findings_the_redraft_answers(self):
        drafted = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        draft = self.live.answer(drafted)
        ingest(self.init, draft)
        self.assertEqual(self.live.act()["role"], "audit")
        finding = PL.finding("F1")
        ingest(self.init, PL.audit(target=CHARTER, rnd=1, verdict="FAIL",
                                   findings=(finding,)))
        self.assertEqual(self.live.act()["role"], "repair")
        ingest(self.init, draft)
        self.assertEqual(read_json(repair_file(self.init.idir, CHARTER, 1)),
                         {"target": CHARTER, "round": 1, "addressed": [finding],
                          "artifact_sha256": sha256(draft)})


class Plans(LiveCase):
    def test_the_planner_says_when_another_plan_is_needed_and_every_plan_runs(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")
        ingest(self.init, PL.plan_payload(pid=f"{INIT}-P01", more_plans=True))
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")
        self.live.run(lambda a: a["action"] == "DONE")
        s = fold(self.live.events())
        self.assertEqual(s["plan_order"], [f"{INIT}-P01", f"{INIT}-P02"])
        self.assertEqual(sorted(s["tasks"]), [f"{INIT}-P01-T01", f"{INIT}-P02-T01"])
        self.assertEqual(check(self.init)["problems"], [])

    def test_a_planner_that_never_says_enough_is_stopped_at_the_plan_cap(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")
        act: dict = {}
        for n in range(1, MAX_PLANS + 1):
            ingest(self.init, PL.plan_payload(pid=f"{INIT}-P{n:02d}", more_plans=True))
            act = self.live.act()
        self.assertEqual(act["action"], "ESCALATE")
        self.assertIn(str(MAX_PLANS), act["reason"])


if __name__ == "__main__":
    unittest.main()
