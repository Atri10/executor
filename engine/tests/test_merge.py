# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Merge records are pump-driven and slot-free, so they are checked on what
they name: a known plan, and a commit that exists."""
from __future__ import annotations

import unittest

import _payloads as PL
from _live import Live
from executor.engine import ingest
from executor.store import Rejection


class Merges(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def test_a_merge_of_a_plan_that_does_not_exist_is_an_unknown_entity(self):
        before = len(self.live.events())
        with self.assertRaises(Rejection) as r:
            ingest(self.init, PL.merge(plan=PL.PLAN, sha=self.live.git("rev-parse", "HEAD")))
        self.assertEqual(r.exception.code, "unknown_entity")
        self.assertEqual(len(self.live.events()), before)

    def test_a_merge_naming_no_commit_is_an_unknown_rev(self):
        self.live.run(lambda a: a["action"] == "MERGE")
        before = len(self.live.events())
        with self.assertRaises(Rejection) as r:
            ingest(self.init, PL.merge(plan=PL.PLAN, sha="0" * 40))
        self.assertEqual(r.exception.code, "unknown_rev")
        self.assertEqual(len(self.live.events()), before)


if __name__ == "__main__":
    unittest.main()
