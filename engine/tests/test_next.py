# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""emit_next: what the pump is told, and the only moments the engine writes."""
from __future__ import annotations

import threading
import time
import unittest

import _payloads as PL
from _live import Live
from executor.engine import check, ingest, open_dispatches
from executor.policy import DEFAULTS
from executor.store import PHASES, verify_chain

DEADLINE_S = DEFAULTS["deadline_s"]
MAX_AUDIT_ROUNDS = DEFAULTS["max_audit_rounds"]
SPAWN_RETRY_CAP = DEFAULTS["spawn_retry_cap"]


class LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init


class PollingIsIdempotent(LiveCase):
    def test_a_repeated_poll_returns_the_open_dispatch_and_writes_nothing(self):
        self.live.act()
        first = self.live.act()
        before = len(self.live.events())
        again = self.live.act()
        self.assertEqual(first["action"], "DISPATCH")
        self.assertEqual(again["dispatch_id"], first["dispatch_id"])
        self.assertEqual(len(self.live.events()), before)

    def test_every_action_carries_a_resume_manifest(self):
        act = self.live.act()
        self.assertEqual(act["resume"]["phase"], "intake")
        self.assertEqual(act["resume"]["last_seq"], len(self.live.events()))
        self.assertEqual(act["resume"]["open_slots"], 0)


class HappyPath(LiveCase):
    def test_a_cooperative_worker_drives_every_phase_to_done(self):
        final = self.live.run(lambda a: a["action"] == "DONE")
        self.assertEqual(final["action"], "DONE")
        entered = [e["data"]["phase"] for e in self.live.events()
                   if e["kind"] == "phase_entered"]
        self.assertEqual(entered, list(PHASES))
        report = check(self.init)
        self.assertEqual((report["chain"], report["problems"], report["open_slots"]),
                         ("ok", [], 0))


class SpawnErrors(LiveCase):
    def test_a_lost_worker_is_redispatched_until_the_retry_cap_then_escalates(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        for _ in range(SPAWN_RETRY_CAP + 1):
            act = self.live.act()
            self.assertEqual(act["action"], "DISPATCH")
            ingest(self.init, PL.spawn_error(dispatch_id=act["dispatch_id"]))
        self.assertEqual(self.live.act()["action"], "ESCALATE")
        self.assertEqual(self.live.act()["action"], "HALT")


class SilentWorkers(LiveCase):
    def test_a_dispatch_silent_past_the_deadline_is_abandoned_and_reissued(self):
        first = self.live.run(lambda a: a["action"] == "DISPATCH")
        again = self.live.act(now=time.time() + DEADLINE_S + 1)
        self.assertEqual(again["action"], "DISPATCH")
        self.assertNotEqual(again["dispatch_id"], first["dispatch_id"])
        self.assertEqual([e["kind"] for e in self.live.events()[-2:]],
                         ["abandon", "task_dispatched"])

    def test_a_dispatch_inside_the_deadline_is_kept(self):
        first = self.live.run(lambda a: a["action"] == "DISPATCH")
        kept = self.live.act(now=time.time() + DEADLINE_S - 60)
        self.assertEqual(kept["dispatch_id"], first["dispatch_id"])


class AuditRounds(LiveCase):
    def test_an_artifact_that_never_clears_escalates_at_the_round_cap(self):
        drafted = self.live.run(
            lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        ingest(self.init, self.live.answer(drafted))
        for rnd in range(1, MAX_AUDIT_ROUNDS + 1):
            audit = self.live.act()
            self.assertEqual((audit["role"], audit["context"]["round"]),
                             ("audit", rnd))
            ingest(self.init, PL.audit(target=audit["entity"], rnd=rnd,
                                       verdict="FAIL",
                                       findings=(PL.finding(),)))
            repair = self.live.act()
            self.assertEqual(repair["role"], "repair")
            ingest(self.init, self.live.answer(repair))
        self.assertEqual(self.live.act()["action"], "ESCALATE")


class Concurrency(LiveCase):
    def test_racing_polls_commit_one_phase_entry_and_one_dispatch(self):
        results: list[dict] = []
        threads = [threading.Thread(target=lambda: results.append(self.live.act()))
                   for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        events = self.live.events()
        kinds = [e["kind"] for e in events]
        self.assertEqual(kinds.count("phase_entered"), 1)
        self.assertEqual(kinds.count("task_dispatched"), 1)
        opened = next(e["dispatch_id"] for e in events
                      if e["kind"] == "task_dispatched")
        dispatched = {r["dispatch_id"] for r in results
                      if r["action"] == "DISPATCH"}
        self.assertEqual(dispatched, {opened})
        self.assertEqual(verify_chain(events), [])


class OpenDispatches(LiveCase):
    def test_the_journal_lists_what_a_worker_may_still_answer(self):
        self.assertEqual(open_dispatches(self.init), [])
        act = self.live.run(lambda a: a["action"] == "DISPATCH")
        self.assertEqual([d["dispatch_id"] for d in open_dispatches(self.init)],
                         [act["dispatch_id"]])
        ingest(self.init, self.live.answer(act))
        self.assertEqual(open_dispatches(self.init), [])


if __name__ == "__main__":
    unittest.main()
