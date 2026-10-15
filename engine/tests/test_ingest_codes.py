# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""ingest rejection codes: each code is reached by a payload a worker could
plausibly send, and a refused payload leaves the journal as it was."""
from __future__ import annotations

import unittest

import _payloads as PL
from _live import Live
from executor.engine import fold, ingest, open_dispatches
from executor.store import Rejection

INIT = PL.INIT


class LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def assertRefused(self, code: str, payload, actor: str = "worker") -> Rejection:
        before = len(self.live.events())
        with self.assertRaises(Rejection) as r:
            ingest(self.init, payload, actor=actor)
        self.assertEqual(r.exception.code, code)
        self.assertEqual(len(self.live.events()), before,
                         "a refused payload must not reach the journal")
        return r.exception


class Envelope(LiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.live.act()  # enter intake

    def test_a_payload_that_is_not_an_object_is_a_type_rejection(self):
        self.assertRefused("type", ["a", "list"])

    def test_a_payload_without_a_kind_is_a_required_rejection(self):
        self.assertRefused("required", {"v": "v1"})

    def test_a_kind_that_is_not_a_string_is_a_type_rejection(self):
        self.assertRefused("type", {"kind": 3, "v": "v1"})

    def test_an_unknown_kind_is_refused_by_name(self):
        exc = self.assertRefused("unknown_kind", {"kind": "mystery", "v": "v1"})
        self.assertIn("mystery", exc.got)

    def test_a_spawn_error_for_a_dispatch_that_is_not_open_is_refused(self):
        self.live.run(lambda a: a["action"] == "DISPATCH")
        self.assertRefused("no_open_slot", PL.spawn_error(dispatch_id="D99999"))


class PlanCodes(LiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")

    def test_a_plan_whose_id_and_plan_id_disagree_is_a_mismatch(self):
        self.assertRefused("mismatch", {**PL.plan_payload(), "plan_id": f"{INIT}-P09"})

    def test_repeated_task_ids_are_a_duplicate(self):
        self.assertRefused("duplicate", PL.plan_payload(
            tasks=[PL.task_row("T01"), PL.task_row("T01")]))

    def test_a_dependency_outside_the_plan_is_a_dangling_ref(self):
        exc = self.assertRefused("dangling_ref", PL.plan_payload(
            tasks=[PL.task_row("T01", depends_on=["T09"])]))
        self.assertEqual(exc.field, "$.tasks.T01.depends_on")


class CriteriaCodes(LiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "vrfy")

    def test_repeated_criterion_ids_are_a_duplicate(self):
        self.assertRefused("duplicate", PL.vrfy_payload(("V1", "a"), ("V1", "b")))


class HeartbeatCodes(LiveCase):
    def test_a_heartbeat_keeps_the_dispatch_open_and_records_the_beat(self):
        impl = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        ingest(self.init, PL.heartbeat(task=impl["entity"]))
        self.assertEqual([d["dispatch_id"] for d in open_dispatches(self.init)],
                         [impl["dispatch_id"]])
        self.assertIn("last_beat", fold(self.live.events())["dispatches"][impl["dispatch_id"]])


class ReviewCodes(LiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.review = self.live.run(lambda a: a["action"] == "DISPATCH"
                                    and a["role"] == "review")

    def test_a_finding_that_cites_a_missing_path_is_refused(self):
        ctx = self.review["context"]
        self.assertRefused("missing_evidence", PL.verdict(
            task=self.review["entity"], rnd=ctx["round"], base=ctx["base"],
            head=ctx["head"], reviewed_package_sha=ctx["package_sha"],
            findings=[PL.finding(evidence="see src/nowhere/x.py")]))


class EvidenceCodes(LiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.criterion = self.live.run(
            lambda a: a["action"] == "DISPATCH" and a["role"] == "evidence")["entity"]

    def test_evidence_naming_no_commit_is_an_unknown_rev(self):
        self.assertRefused("unknown_rev", PL.evidence(criterion=self.criterion,
                                                     commit="0" * 40))

    def test_evidence_citing_an_artifact_missing_at_its_commit_is_refused(self):
        self.assertRefused("missing_evidence", PL.evidence(
            criterion=self.criterion, commit=self.live.git("rev-parse", "HEAD"),
            artifacts=["docs/nope.md"]))


class GateCodes(LiveCase):
    def test_a_gate_decision_for_a_phase_not_awaiting_one_is_refused(self):
        self.live.run(lambda a: a["action"] == "GATE")
        self.assertRefused("no_open_gate", PL.gate(phase="design"), actor="human")


if __name__ == "__main__":
    unittest.main()
