# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""check: what it reports when the journal or the store is wrong. Each case
tampers with the store the way a hand edit or a crash would, then asserts on
the report. check never writes, so the tampering stays visible afterwards."""
from __future__ import annotations

import time
import unittest

import _payloads as PL
from _live import Live
from executor.engine import DEADLINE_S, SUSPECT_S, check
from executor.paths import docs_init_dir, journal_file
from executor.store import append_event, make_event

INIT = PL.INIT


class LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def problems(self, **kw) -> list[str]:
        return check(self.init, **kw)["problems"]

    def tamper(self, kind: str, entity: str, data: dict) -> None:
        append_event(self.init.idir, make_event(self.init.idir, "tamper", kind,
                                                entity, data))


class Journal(LiveCase):
    def test_a_clean_run_checks_clean(self):
        self.live.run(lambda a: a["action"] == "DONE")
        report = check(self.init)
        self.assertEqual((report["chain"], report["problems"]), ("ok", []))

    def test_an_edited_event_breaks_the_chain(self):
        path = journal_file(self.init.idir)
        path.write_bytes(path.read_bytes().replace(b"live", b"LIVE", 1))
        self.assertEqual(check(self.init)["chain"], "broken")

    def test_a_torn_trailing_line_is_counted_and_reported(self):
        with journal_file(self.init.idir).open("ab") as fh:
            fh.write(b'{"seq": 9, "ki')
        self.assertTrue(any("unparseable journal line" in p for p in self.problems()))

    def test_an_event_of_an_unknown_kind_is_reported(self):
        self.tamper("mystery", INIT, {})
        self.assertIn("unknown event kind(s): mystery", self.problems())

    def test_an_event_the_fold_cannot_apply_is_reported_not_raised(self):
        self.tamper("phase_entered", INIT, {})
        self.assertTrue(any(p.startswith("fold failed") for p in self.problems()))

    def test_a_citation_to_nothing_is_a_dangling_edge(self):
        self.tamper("charter", f"{INIT}-CHTR-01",
                    {"kind": "charter", "cites": ["INIT-0001-NOPE-01"]})
        self.assertIn("dangling edge cites: INIT-0001-NOPE-01", self.problems())


class StateCache(LiveCase):
    def test_a_write_that_bypassed_the_projection_leaves_the_cache_stale(self):
        self.tamper("resume", INIT, {"reason": "x"})
        for _ in range(2):
            self.assertTrue(any(p.startswith("state cache stale")
                                for p in self.problems()))


class Liveness(LiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")

    def test_a_fresh_dispatch_is_not_reported_as_silent(self):
        self.assertFalse(any("silent" in p for p in self.problems()))

    def test_silence_past_the_suspect_threshold_is_reported(self):
        problems = self.problems(now=time.time() + SUSPECT_S + 60)
        self.assertTrue(any(p.startswith("suspect dispatch") for p in problems))

    def test_silence_past_the_deadline_is_reported_as_dead(self):
        problems = self.problems(now=time.time() + DEADLINE_S + 60)
        self.assertTrue(any(p.startswith("dead dispatch") for p in problems))


class StoreFiles(LiveCase):
    def test_a_stray_run_file_and_an_orphan_dispatch_directory_are_reported(self):
        (self.init.idir / "stray.txt").write_text("x", encoding="utf-8")
        (self.init.idir / "dispatches" / "D99999").mkdir(parents=True)
        problems = self.problems()
        self.assertIn(f"non-canonical file: {INIT}/stray.txt", problems)
        self.assertIn("orphan dispatch directory D99999: never journaled", problems)

    def test_a_stray_committed_file_is_reported(self):
        docs = docs_init_dir(self.live.root, INIT)
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "stray.md").write_text("x", encoding="utf-8")
        self.assertIn(f"non-canonical committed file: {INIT}/stray.md", self.problems())


if __name__ == "__main__":
    unittest.main()
