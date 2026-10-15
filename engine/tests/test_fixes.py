# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Fix rounds: a failing review sends the task back to a fix, a fix is recorded
at its canonical paths, and the fix cap ends the run instead of looping."""
from __future__ import annotations

import unittest
from pathlib import Path

import _payloads as PL
from _live import Live
from executor.engine import MAX_FIX_ROUNDS, ingest
from executor.paths import fix_package_file, fix_report_file
from executor.store import read_json


def _json(path: Path) -> dict:
    data = read_json(path)
    assert data is not None, f"{path} is missing or unreadable"
    return data


class Fixes(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def fail_review(self, review: dict) -> None:
        ctx = review["context"]
        ingest(self.init, PL.verdict(task=review["entity"], rnd=ctx["round"],
                                     base=ctx["base"], head=ctx["head"],
                                     reviewed_package_sha=ctx["package_sha"],
                                     spec="FAIL", findings=[PL.finding()]))

    def test_a_failing_review_sends_the_task_back_to_a_fix_until_the_cap(self):
        review = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        act: dict = {}
        for fix_round in range(1, MAX_FIX_ROUNDS + 1):
            self.fail_review(review)
            act = self.live.act()
            if fix_round == MAX_FIX_ROUNDS:
                break
            self.assertEqual((act["role"], act["context"]["round"]), ("fix", fix_round))
            ingest(self.init, self.live.answer(act))
            review = self.live.act()
            self.assertEqual(review["role"], "review")
        self.assertEqual(act["action"], "ESCALATE")
        self.assertIn("fix-round cap", act["reason"])

    def test_a_fix_is_recorded_at_its_canonical_paths(self):
        review = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        self.fail_review(review)
        fix = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "fix")
        ingest(self.init, self.live.answer(fix))
        package = _json(fix_package_file(self.init.idir, PL.TASK, 1))
        self.assertEqual(package["task"], PL.TASK)
        report = _json(fix_report_file(self.init.idir, PL.TASK, 1))
        self.assertEqual(report["commits"], [self.live.git("rev-parse", "HEAD")])


if __name__ == "__main__":
    unittest.main()
