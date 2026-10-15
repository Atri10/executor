# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Projections: the committed records and views are deterministic functions of
the payloads and the folded state. Each renderer is checked on what it says."""
from __future__ import annotations

import unittest

import _payloads as PL
from _live import Live
from executor.engine import fold
from executor.paths import views_dir
from executor.views import (render_handoff_index, render_handoff_md,
                            render_report_md, render_verdict_md, status_card)

INIT = PL.INIT
CHARTER = f"{INIT}-CHTR-01"


class Records(unittest.TestCase):
    def test_a_report_record_lists_commits_and_concerns_only_when_present(self):
        bare = render_report_md(PL.report(commits=(), result="BLOCKED"), "D00001")
        self.assertIn("- none", bare)
        self.assertNotIn("concerns", bare)
        full = render_report_md(PL.report(concerns=["timeout risk"]), "D00002")
        self.assertIn("- `abc1234`", full)
        self.assertIn("**concerns:**", full)

    def test_a_verdict_record_sorts_findings_by_severity(self):
        verdict = PL.verdict(findings=[PL.finding("F2", "minor", "nit"),
                                       PL.finding("F1", "critical", "crash")])
        text = render_verdict_md(verdict)
        self.assertLess(text.index("F1"), text.index("F2"))
        self.assertIn("- none", render_verdict_md(PL.verdict()))

    def test_renderers_are_deterministic(self):
        verdict = PL.verdict(findings=[PL.finding()])
        self.assertEqual(render_verdict_md(verdict), render_verdict_md(verdict))


class GateCard(unittest.TestCase):
    def test_a_gate_card_is_plain_ascii_and_names_the_open_gate(self):
        live = Live()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "GATE")
        card = status_card(live.init, fold(live.events()))
        self.assertIn("-> GATE intake", card)
        card.encode("ascii")


class FinishedRun(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.live.run(lambda a: a["action"] == "DONE")
        self.state = fold(self.live.events())

    def test_the_handoff_index_reports_the_final_state_of_every_entity(self):
        index = render_handoff_index(INIT, self.state)
        by_id = {a["id"]: a for a in index["artifacts"]}
        self.assertEqual(by_id[CHARTER]["status"], "cleared")
        self.assertEqual(index["plans"], [{"id": PL.PLAN, "status": "merged",
                                           "tasks": [PL.TASK]}])
        self.assertEqual(index["tasks"], {PL.TASK: "complete"})
        self.assertEqual(index["evidence"], {"V1": "proven"})

    def test_the_handoff_markdown_renders_each_table_from_the_same_facts(self):
        md = render_handoff_md(INIT, self.state)
        self.assertIn(f"| {CHARTER} | charter | cleared | 1 |", md)
        self.assertIn(f"| {PL.TASK} | complete |", md)
        self.assertIn("- V1: proven", md)

    def test_every_projection_file_is_written_next_to_the_journal(self):
        names = {p.name for p in views_dir(self.live.init.idir).iterdir()}
        self.assertIn("graph.json", names)


class EmptyState(unittest.TestCase):
    def test_an_empty_run_renders_its_empty_sections_as_none(self):
        md = render_handoff_md(INIT, fold([]))
        self.assertEqual(md.count("- none"), 2)  # plans and evidence; no task rows


if __name__ == "__main__":
    unittest.main()
