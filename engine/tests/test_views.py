# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Projections: the committed records and views are deterministic functions of
the payloads and the folded state. Each renderer is checked on what it says."""
from __future__ import annotations

import unittest

import _payloads as PL
from _live import Live
from executor.engine import _render_doc, fold, ingest
from executor.paths import views_dir
from executor.views import (evidence_counts, render_handoff_index,
                            render_handoff_md,
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


    def test_the_card_reports_open_critiques_and_unruled_concerns(self):
        live = Live()
        self.addCleanup(live.close)
        drafted = live.run(lambda a: a["action"] == "DISPATCH"
                           and a["role"] == "author")
        ingest(live.init, live.answer(drafted))
        audit = live.act()
        ingest(live.init, PL.audit(target=audit["entity"], rnd=1, verdict="FAIL",
                                   findings=(PL.finding(),)))
        # Read the card before the repair dispatch is issued: the fixture would
        # answer it and close the critique again.
        card = status_card(live.init, fold(live.events()))
        self.assertIn("open critique findings", card)
        impl = live.run(lambda a: a["action"] == "DISPATCH"
                        and a["role"] == "impl")
        ingest(live.init, PL.report(task=impl["entity"], commits=(),
                                    result="BLOCKED",
                                    concerns=["no schema yet"]))
        card = status_card(live.init, fold(live.events()))
        self.assertIn("awaiting rulings", card)

    def test_a_halted_run_says_so_on_the_card(self):
        live = Live()
        self.addCleanup(live.close)
        live.act()
        ingest(live.init, {"kind": "halt", "v": "v1", "reason": "client stop"})
        card = status_card(live.init, fold(live.events()))
        self.assertIn("HALTED: client stop", card)

    def test_the_card_counts_evidence_outcomes_and_unanswered_criteria(self):
        """A criterion nobody ran is unproven however obviously it 'must'
        work, so the card counts it rather than letting it be absorbed
        into a sentence about the ones that ran."""
        live = Live()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "GATE")
        # Author the verification strategy, then land one evidence payload
        # against a criterion and leave the rest unanswered.
        vrfy = live.run(lambda a: a["action"] == "DISPATCH"
                        and a["role"] == "author" and a["schema"] == "vrfy")
        ingest(live.init, live.answer(vrfy))
        act = live.run(lambda a: a["action"] == "DISPATCH"
                       and a["role"] == "evidence")
        if act is not None:
            head = live.land_change()
            payload = PL.evidence(criterion=act["entity"], commit=head,
                                  verdict="proven")
            ingest(live.init, payload)
        card = status_card(live.init, fold(live.events()))
        self.assertRegex(card, r"evidence: \d+ proven")
        self.assertIn("unanswered", card)

    def test_the_card_omits_evidence_until_a_vrfy_exists(self):
        """The counts describe a verification strategy that exists; before
        one is authored there is nothing to count, and a zero line would
        read as 'nothing proven' when nothing was even planned."""
        live = Live()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "GATE")
        card = status_card(live.init, fold(live.events()))
        self.assertNotIn("evidence:", card)

    def test_the_card_omits_quiet_sections_entirely(self):
        """A line that reads 'open critique findings: 0' is noise a reader
        learns to skip — and that reader then skips the line that matters."""
        live = Live()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "GATE")
        card = status_card(live.init, fold(live.events()))
        self.assertNotIn("open critique findings", card)
        self.assertNotIn("awaiting rulings", card)
        self.assertNotIn("HALTED", card)

    def test_the_gate_line_appears_only_at_a_gate(self):
        """The line points at a decision that is waiting; printed at any
        other time it trains the reader to ignore it — and then a real gate
        goes unanswered."""
        live = Live()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "DISPATCH"
                 and a["role"] == "author")
        card = status_card(live.init, fold(live.events()))
        self.assertNotIn("-> GATE", card)

    def test_the_evidence_counts_separate_every_outcome(self):
        """The counts a reader acts on: proven, failed, unavailable, and the
        ones nobody ran. Collapsing two of them hides the difference
        between a failing criterion and an unobserved one."""
        self.assertEqual(evidence_counts(fold([])),
                         {"proven": 0, "failed": 0, "unavailable": 0,
                          "unanswered": 0})
        s = {"evidence": {"V1": [{"verdict": "proven"}],
                          "V2": [{"verdict": "failed"}],
                          "V3": [{"verdict": "unavailable"},
                                 {"verdict": "failed"}],
                          "V4": [{"verdict": "proven"}]},
             "artifacts": {"A": {"kind": "vrfy", "data": {"criteria": [
                 {"id": "V1"}, {"id": "V2"}, {"id": "V3"}, {"id": "V4"},
                 {"id": "V5"}, {"id": "V6"}]}}}}
        # A criterion's state is its latest verdict: V3 ran twice and the
        # second run is the one that counts, so `unavailable` is 0.
        self.assertEqual(evidence_counts(s),
                         {"proven": 2, "failed": 2, "unavailable": 0,
                          "unanswered": 2})

    def test_an_unknown_verdict_does_not_crash_the_counts(self):
        """The schema pins `verdict` to three values, so an out-of-set one
        means the journal was edited by hand. Counting it as unanswered is
        honest; raising KeyError from `executor status` is a crash on a
        store the reader must be able to inspect."""
        s = {"evidence": {"V1": [{"verdict": "maybe"}],
                          "V2": [{"verdict": "proven"}]},
             "artifacts": {"A": {"kind": "vrfy", "data": {"criteria": [
                 {"id": "V1"}, {"id": "V2"}]}}}}
        self.assertEqual(evidence_counts(s),
                         {"proven": 1, "failed": 0, "unavailable": 0,
                          "unanswered": 1})


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


class EmptyState(unittest.TestCase):
    def test_an_empty_run_renders_its_empty_sections_as_none(self):
        md = render_handoff_md(INIT, fold([]))
        self.assertEqual(md.count("- none"), 2)  # plans and evidence; no task rows


class DocumentRendering(unittest.TestCase):
    """The payload is data; this is the only place markdown is written. A
    table in the store is rows plus columns, and the reader gets the same
    table every time because nothing but this code formats it."""

    def doc(self, **sections):
        base = {"id": "INIT-0001-CHTR-01", "title": "Cells",
                "summary": "One line."}
        base.update(sections)
        return _render_doc(base)

    def test_a_section_renders_each_shape_in_order(self):
        md = self.doc(sections=[{
            "id": "s", "title": "Bounds",
            "prose": "First paragraph.",
            "bullets": ["one", "two"],
            "tables": [{"caption": "Costs", "columns": ["A", "B"],
                        "rows": [["x", "y"]]}],
            "code": [{"lang": "ts", "source": "let a = 1"}],
        }])
        self.assertIn("## Bounds", md)
        self.assertLess(md.index("First paragraph."), md.index("- one"))
        self.assertLess(md.index("- one"), md.index("*Costs*"))
        self.assertLess(md.index("*Costs*"), md.index("| A | B |"))
        self.assertLess(md.index("| A | B |"), md.index("```ts"))
        self.assertIn("| x | y |", md)
        self.assertIn("| --- |", md)
        self.assertIn("let a = 1", md)

    def test_a_shape_that_is_absent_renders_nothing(self):
        md = self.doc(sections=[{"id": "s", "title": "Only",
                                 "prose": "Just text."}])
        self.assertNotIn("| ", md)
        self.assertNotIn("```", md)
        self.assertNotIn("- ", md)

    def test_a_code_block_with_no_language_still_fences(self):
        md = self.doc(sections=[{"id": "s", "title": "C",
                                 "code": [{"source": "raw"}]}])
        self.assertIn("```\nraw\n```", md)

    def test_rendering_is_deterministic(self):
        payload = {"id": "INIT-0001-SPEC-01", "title": "S",
                   "summary": "sum",
                   "sections": [{"id": "r", "title": "Rows",
                                 "tables": [{"columns": ["A"],
                                             "rows": [["1"]]}]}],
                   "requirements": [{"id": "R1", "requirement": "must",
                                     "observable": "seen"}]}
        self.assertEqual(_render_doc(payload), _render_doc(payload))

    def test_a_rich_section_renders_exactly_these_bytes(self):
        """Every shape's contribution is pinned to the byte: a dropped blank
        line, a lost bullet, or a missing fence closes changes the document a
        reader sees, and only an exact assertion notices."""
        payload = {"id": "X", "title": "T", "summary": "s",
                   "sections": [{"id": "a", "title": "A",
                                 "prose": "p",
                                 "bullets": ["b1", "b2"],
                                 "tables": [{"caption": "cap",
                                             "columns": ["A", "B"],
                                             "rows": [["1", "2"],
                                                      ["3", "4"]]}],
                                 "code": [{"lang": "ts", "source": "x"}]}]}
        self.assertEqual(_render_doc(payload),
                         "# X — T\n\n"
                         "*s*\n\n"
                         "## A\n"
                         "p\n\n"
                         "- b1\n"
                         "- b2\n\n"
                         "*cap*\n\n"
                         "| A | B |\n"
                         "| --- | --- |\n"
                         "| 1 | 2 |\n"
                         "| 3 | 4 |\n\n"
                         "```ts\nx\n```\n\n")

    def test_a_table_only_section_has_no_stray_paragraph(self):
        payload = {"id": "X", "title": "T", "summary": "s",
                   "sections": [{"id": "a", "title": "A",
                                 "tables": [{"columns": ["A"],
                                             "rows": [["1"]]}]}]}
        self.assertEqual(_render_doc(payload),
                         "# X — T\n\n*s*\n\n"
                         "## A\n\n| A |\n| --- |\n| 1 |\n\n")

    def test_a_payload_never_needs_its_own_markdown(self):
        """Every construct the old `body` string carried has a typed home:
        a heading is the title, a list is bullets, a grid is tables, and a
        sample is code. The rendered doc is fully built from data."""
        md = self.doc(sections=[
            {"id": "a", "title": "T", "prose": "p", "bullets": ["b"],
             "tables": [{"columns": ["c"], "rows": [["d"]]}],
             "code": [{"source": "e"}]}])
        self.assertNotIn("body", md)
        for construct in ("#", "-", "|", "```"):
            self.assertIn(construct, md)


if __name__ == "__main__":
    unittest.main()
