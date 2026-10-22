# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""ingest: which payloads land, which are refused, and that a refusal writes
nothing. Every case runs against a real initiative in a real git repository."""
from __future__ import annotations

import unittest

import _payloads as PL
from _live import Live
from executor.engine import ingest
from executor.paths import artifact_file
from executor.store import Rejection


class LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def assertRefused(self, code: str, payload: dict, actor: str = "worker"):
        before = len(self.live.events())
        with self.assertRaises(Rejection) as r:
            ingest(self.init, payload, actor=actor)
        self.assertEqual(r.exception.code, code)
        self.assertEqual(len(self.live.events()), before,
                         "a refused payload must not reach the journal")
        return r.exception


class Binding(LiveCase):
    def test_a_payload_that_answers_no_open_dispatch_is_refused(self):
        exc = self.assertRefused("no_open_slot", PL.art("charter"))
        self.assertIn("charter", exc.got)
        self.assertFalse(artifact_file(self.init.idir, f"{self.init.id}-CHTR-01").exists())

    def test_a_dangling_cite_is_refused_once_the_dispatch_is_open(self):
        self.live.act()
        self.live.act()
        exc = self.assertRefused("dangling_ref", PL.art(
            "charter", cites=["INIT-0001-NOPE-01"]))
        self.assertEqual(exc.field, "$.cites")
        self.assertFalse(artifact_file(self.init.idir, f"{self.init.id}-CHTR-01").exists())

    def test_a_payload_cannot_cite_itself(self):
        """A self-citation is an artifact arguing from itself: the reference
        adds nothing a reader can check, and it would also make a redraft
        look like it cited its predecessor."""
        self.live.act()
        self.live.act()
        exc = self.assertRefused("dangling_ref", PL.art(
            "charter", cites=["INIT-0001-CHTR-01"]))
        self.assertEqual(exc.field, "$.cites")
        self.assertIn("itself", exc.hint or "")


class Redelivery(LiveCase):
    def test_an_identical_redelivery_of_an_accepted_answer_is_a_no_op(self):
        drafted = self.live.run(
            lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        payload = self.live.answer(drafted)
        ingest(self.init, payload)
        before = len(self.live.events())
        self.assertEqual(ingest(self.init, payload), {"deduplicated": True})
        self.assertEqual(len(self.live.events()), before)

    def test_an_identical_repair_of_an_accepted_draft_is_accepted(self):
        drafted = self.live.run(
            lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        draft = self.live.answer(drafted)
        ingest(self.init, draft)
        audit = self.live.act()
        ingest(self.init, PL.audit(target=audit["entity"], rnd=1, verdict="FAIL",
                                   findings=(PL.finding(),)))
        self.assertEqual(self.live.act()["role"], "repair")
        event = ingest(self.init, draft)
        self.assertEqual(event["kind"], "charter")
        self.assertNotIn("deduplicated", event)


class Authority(LiveCase):
    def test_gate_decisions_need_the_human_actor(self):
        self.live.run(lambda a: a["action"] == "GATE")
        self.assertRefused("unauthorized", PL.gate(phase="intake"))
        ingest(self.init, PL.gate(phase="intake"), actor="human")
        self.assertEqual(self.live.act()["phase"], "discovery")

    def test_rulings_need_the_human_actor(self):
        self.assertRefused("unauthorized", PL.ruling(), actor="worker")


class ReportContract(LiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.impl = self.live.run(
            lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")

    def test_a_report_that_moved_nothing_is_an_empty_range(self):
        for commits in ((self.impl["base"],), ()):
            with self.subTest(commits=commits):
                self.assertRefused("empty_range", PL.report(
                    task=self.impl["entity"], commits=commits))

    def test_an_unknown_commit_is_refused(self):
        self.assertRefused("unknown_rev", PL.report(
            task=self.impl["entity"], commits=("0" * 40,)))

    def test_a_blocked_report_needs_no_commit_and_opens_a_question(self):
        ingest(self.init, PL.report(task=self.impl["entity"], commits=(),
                                    result="BLOCKED"))
        self.assertEqual(self.live.act()["action"], "ASK")


class VerdictContract(LiveCase):
    def test_a_verdict_must_echo_the_minted_round_package_and_range(self):
        review = self.live.run(
            lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        ctx = review["context"]
        good = {"task": review["entity"], "rnd": ctx["round"],
                "base": ctx["base"], "head": ctx["head"],
                "reviewed_package_sha": ctx["package_sha"]}
        cases = (({"rnd": ctx["round"] + 1}, "round_mismatch"),
                 ({"reviewed_package_sha": "f" * 40}, "package_mismatch"),
                 ({"base": ctx["head"], "head": ctx["base"]}, "range_mismatch"))
        for change, code in cases:
            with self.subTest(code=code):
                self.assertRefused(code, PL.verdict(**{**good, **change}))
        ingest(self.init, PL.verdict(**good))
        self.assertEqual(self.live.events()[-1]["kind"], "verdict")


class Halting(LiveCase):
    def test_a_halted_run_refuses_work_and_clears_only_on_resume(self):
        self.live.act()
        ingest(self.init, PL.halt("hold for the client"), actor="human")
        self.assertRefused("halted", PL.art("charter"))
        self.assertEqual(self.live.act()["action"], "HALT")
        ingest(self.init, {"kind": "resume", "v": "v1",
                           "reason": "client confirmed"}, actor="human")
        self.assertNotEqual(self.live.act()["action"], "HALT")

    def test_a_resume_is_refused_when_the_run_is_not_halted(self):
        self.assertRefused("not_halted", {"kind": "resume", "v": "v1",
                                          "reason": "nothing to resume"},
                           actor="human")

    def test_a_ruling_for_an_unknown_task_is_refused(self):
        self.assertRefused("unknown_entity",
                           PL.ruling(for_task="INIT-0001-P09-T09"), actor="human")


class MergeContract(LiveCase):
    def test_a_merge_waits_for_every_task_and_is_accepted_once(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        head = self.live.git("rev-parse", "HEAD")
        self.assertRefused("incomplete", PL.merge(plan=PL.PLAN, sha=head))
        merge = self.live.run(lambda a: a["action"] == "MERGE")
        self.assertEqual(merge["plan"], PL.PLAN)
        head = self.live.git("rev-parse", "HEAD")
        # merge direction: the merge lands on the plan branch (rule G5)
        self.live.branch_at(f"plan/{PL.PLAN}")
        ingest(self.init, PL.merge(plan=PL.PLAN, sha=head))
        self.assertRefused("already_merged", PL.merge(plan=PL.PLAN, sha=head))


if __name__ == "__main__":
    unittest.main()
