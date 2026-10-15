# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""emit_next, state by state: what the pump is told, and what each answer does
to the next instruction."""
from __future__ import annotations

import unittest

import _payloads as PL
from _live import Live
from executor.engine import ingest, open_dispatches
from executor.policy import DEFAULTS
from executor.store import append_event, make_event

MAX_EVIDENCE_TRIES = DEFAULTS["max_evidence_tries"]


class LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def impl(self) -> dict:
        return self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")


class Questions(LiveCase):
    def test_a_question_holds_the_task_until_a_human_rules(self):
        impl = self.impl()
        ingest(self.init, PL.needs_context(task=impl["entity"],
                                           question="which database?"))
        asked = self.live.act()
        self.assertEqual((asked["action"], asked["topic"]), ("ASK", "which database?"))
        ingest(self.init, PL.ruling(decision="postgres", why="client standard",
                                    for_task=impl["entity"]), actor="human")
        resumed = self.live.act()
        self.assertEqual((resumed["action"], resumed["role"]), ("DISPATCH", "impl"))
        self.assertNotEqual(resumed["dispatch_id"], impl["dispatch_id"])

    def test_a_blocked_report_asks_and_a_ruling_reopens_the_task(self):
        impl = self.impl()
        ingest(self.init, PL.report(task=impl["entity"], commits=(), result="BLOCKED",
                                    summary="no schema yet"))
        self.assertEqual(self.live.act()["action"], "ASK")
        ingest(self.init, PL.ruling(decision="create the schema", why="needed",
                                    for_task=impl["entity"]), actor="human")
        again = self.live.act()
        self.assertEqual((again["action"], again["role"]), ("DISPATCH", "impl"))


class Gates(LiveCase):
    def test_a_rejected_gate_halts_and_only_a_resume_continues(self):
        self.live.run(lambda a: a["action"] == "GATE")
        ingest(self.init, PL.gate(phase="intake", decision="rejected",
                                  note="charter too vague"), actor="human")
        self.assertEqual(self.live.act()["action"], "HALT")
        ingest(self.init, {"kind": "resume", "v": "v1", "reason": "charter reworked"},
               actor="human")
        self.assertEqual(self.live.act()["action"], "GATE")

    def test_a_waived_gate_passes_the_phase(self):
        self.live.run(lambda a: a["action"] == "GATE")
        ingest(self.init, PL.gate(phase="intake", decision="waived"), actor="human")
        self.assertEqual(self.live.act()["phase"], "discovery")


class Evidence(LiveCase):
    def test_evidence_that_never_proves_escalates_at_the_attempt_cap(self):
        act = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "evidence")
        for _ in range(MAX_EVIDENCE_TRIES):
            ingest(self.init, PL.evidence(criterion=act["entity"],
                                          commit=self.live.git("rev-parse", "HEAD"),
                                          verdict="failed"))
            act = self.live.act()
        self.assertEqual(act["action"], "ESCALATE")
        self.assertIn("not proven", act["reason"])


class Plans(LiveCase):
    def test_a_cyclic_plan_escalates_instead_of_waiting_forever(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")
        cyclic = [PL.task_row("T01", depends_on=["T02"]),
                  PL.task_row("T02", depends_on=["T01"])]
        ingest(self.init, PL.plan_payload(tasks=cyclic))
        act = self.live.run(lambda a: a["action"] == "ESCALATE")
        self.assertIn("no dispatchable work", act["reason"])


class Journal(LiveCase):
    def test_a_dispatch_answered_behind_the_engines_back_escalates(self):
        impl = self.impl()
        raw = make_event(self.init.idir, "tamper", "evidence", "V1",
                         {"criterion": "V1", "verdict": "failed"},
                         dispatch_id=impl["dispatch_id"], payload_sha="0" * 64)
        append_event(self.init.idir, raw)
        act = self.live.act()
        self.assertEqual(act["action"], "ESCALATE")
        self.assertIn("dispatched with no open", act["reason"])
        self.assertEqual(open_dispatches(self.init), [])


class QuietPolls(LiveCase):
    def test_polls_that_wait_on_a_human_write_nothing(self):
        impl = self.impl()
        ingest(self.init, PL.needs_context(task=impl["entity"],
                                           question="which database?"))
        self.live.act()
        before = len(self.live.events())
        for _ in range(3):
            self.assertEqual(self.live.act()["action"], "ASK")
        self.assertEqual(len(self.live.events()), before)

    def test_polls_after_done_write_nothing(self):
        self.live.run(lambda a: a["action"] == "DONE")
        before = len(self.live.events())
        self.assertEqual(self.live.act()["action"], "DONE")
        self.assertEqual(len(self.live.events()), before)


if __name__ == "__main__":
    unittest.main()
