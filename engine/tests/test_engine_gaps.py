# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Engine behaviour the other suites do not reach: locking across threads, audit
and verdict outcomes, preflight conflicts, report and evidence checks, and the
liveness of dispatches with unreadable timestamps."""
import json
import re
import threading

import time
import unittest

import _payloads as PL
from _live import Live
from executor import engine
from executor.engine import _iso2epoch, _silent_for, check, fold, ingest
from executor.paths import dispatches_dir, docs_init_dir, journal_file, state_file
from executor.store import ExecError, Rejection, read_json, write_json


class LiveCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init


class Locking(LiveCase):
    def test_a_nested_lock_on_the_same_store_in_one_thread_does_not_deadlock(self):
        with engine._exclusive(self.init.idir):
            with engine._exclusive(self.init.idir):
                self.assertEqual(engine._held.key, str(self.init.idir))
        self.assertIsNone(engine._held.key)

    def test_a_writer_in_another_thread_waits_for_the_holder_to_finish(self):
        entered, release = threading.Event(), threading.Event()
        order: list[str] = []

        def holder():
            with engine._exclusive(self.init.idir):
                entered.set()
                release.wait(timeout=5)
                order.append("holder")

        t = threading.Thread(target=holder)
        t.start()
        entered.wait(timeout=5)
        threading.Timer(0.05, release.set).start()
        with engine._exclusive(self.init.idir):
            order.append("waiter")
        t.join(timeout=5)
        self.assertEqual(order, ["holder", "waiter"])


class AuditOutcomes(LiveCase):
    def drafted(self) -> str:
        """Drive the run to its first audit. The audit is the engine's next
        dispatch, so the test answers it through the real pump."""
        return self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "audit")["entity"]

    def test_a_failing_audit_leaves_the_artifact_under_audit(self):
        target = self.drafted()
        ingest(self.init, PL.audit(target=target, rnd=1, verdict="FAIL",
                                   findings=(PL.finding("F1"),)))
        self.assertEqual(fold(self.live.events())["artifacts"][target]["status"], "under_audit")

    def test_a_passing_audit_clears_the_artifact(self):
        target = self.drafted()
        ingest(self.init, PL.audit(target=target, rnd=1, verdict="PASS"))
        self.assertEqual(fold(self.live.events())["artifacts"][target]["status"], "cleared")

    def test_an_audit_of_a_plan_records_its_critique_without_an_artifact_row(self):
        s = fold([])
        engine._apply_audit(s, PL.audit(target=PL.PLAN, rnd=1, verdict="FAIL",
                                        findings=(PL.finding("F9"),)))
        self.assertEqual(s["critiques"][f"intake:{PL.PLAN}"]["status"], "fail")
        self.assertNotIn(PL.PLAN, s["artifacts"])

    def test_only_open_findings_remain_on_a_failed_critique(self):
        s = fold([])
        findings = (PL.finding("F1"), {**PL.finding("F2"), "status": "fixed"})
        engine._apply_audit(s, PL.audit(target="X", rnd=1, verdict="FAIL", findings=findings))
        self.assertEqual([f["id"] for f in s["critiques"]["intake:X"]["open"]], ["F1"])


class VerdictOutcomes(LiveCase):
    def test_a_verdict_for_an_unknown_task_is_recorded_and_creates_no_task(self):
        s = fold([])
        engine._apply_verdict(s, "INIT-0001-P09-T09", PL.verdict(task="INIT-0001-P09-T09"))
        self.assertIn("INIT-0001-P09-T09-R01", s["verdicts"])
        self.assertEqual(s["tasks"], {})


class PreflightOrdering(unittest.TestCase):
    def tasks(self, b_depends: list[str]) -> dict:
        return {f"{PL.PLAN}-T01": {"plan": PL.PLAN, "files": ["a.py"], "depends_on": []},
                f"{PL.PLAN}-T02": {"plan": PL.PLAN, "files": ["a.py"],
                                   "depends_on": b_depends}}

    def test_unordered_tasks_are_not_ordered(self):
        self.assertFalse(engine._ordered(self.tasks([]), f"{PL.PLAN}-T01", f"{PL.PLAN}-T02"))

    def test_a_dependency_orders_tasks_in_either_direction(self):
        self.assertTrue(engine._ordered(self.tasks(["T01"]), f"{PL.PLAN}-T01", f"{PL.PLAN}-T02"))
        self.assertTrue(engine._ordered(self.tasks(["T01"]), f"{PL.PLAN}-T02", f"{PL.PLAN}-T01"))

    def test_reachability_follows_chains_and_terminates_on_a_cycle(self):
        cyclic = {"P-T1": {"plan": "P", "depends_on": ["T2"]},
                  "P-T2": {"plan": "P", "depends_on": ["T3"]},
                  "P-T3": {"plan": "P", "depends_on": ["T1"]}}
        self.assertTrue(engine._reaches(cyclic, "P-T1", "P-T3"))
        self.assertFalse(engine._reaches(cyclic, "P-T1", "P-T9"))


class PlanAndCriteriaRefusals(LiveCase):
    def test_a_plan_whose_plan_id_disagrees_is_refused_as_a_mismatch(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")
        with self.assertRaises(Rejection) as r:
            ingest(self.init, {**PL.plan_payload(), "plan_id": "INIT-0001-P77"})
        self.assertEqual(r.exception.code, "mismatch")

    def test_a_plan_depending_on_a_task_outside_it_is_refused(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "plan")
        with self.assertRaises(Rejection) as r:
            ingest(self.init, PL.plan_payload(tasks=[PL.task_row("T01", depends_on=["T77"])]))
        self.assertEqual(r.exception.code, "dangling_ref")

    def test_a_criterion_listed_twice_is_refused(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author"
                      and a["schema"] == "vrfy")
        with self.assertRaises(Rejection) as r:
            ingest(self.init, PL.vrfy_payload(("V1", "a"), ("V1", "b")))
        self.assertEqual(r.exception.code, "duplicate")


class ReportRefusals(LiveCase):
    def test_a_report_with_no_commits_is_refused_as_an_empty_range(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        with self.assertRaises(Rejection) as r:
            ingest(self.init, PL.report(task=PL.TASK, commits=()))
        self.assertEqual(r.exception.code, "empty_range")

    def test_a_fix_report_that_only_repeats_the_prior_head_is_refused(self):
        impl = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        ingest(self.init, self.live.answer(impl))
        review = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "review")
        ctx = review["context"]
        ingest(self.init, PL.verdict(task=PL.TASK, rnd=ctx["round"], base=ctx["base"],
                                     head=ctx["head"], reviewed_package_sha=ctx["package_sha"],
                                     spec="FAIL", findings=[PL.finding()]))
        fix = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "fix")
        prior_head = self.live.git("rev-parse", "HEAD")
        with self.assertRaises(Rejection) as r:
            ingest(self.init, PL.report(task=PL.TASK, commits=(prior_head,)))
        self.assertEqual(r.exception.code, "empty_range")
        self.assertEqual(fold(self.live.events())["tasks"][PL.TASK]["state"], "dispatched")


class EvidenceAndAudit(LiveCase):
    def test_evidence_citing_an_artifact_present_at_its_commit_is_accepted(self):
        crit = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "evidence")
        (self.live.root / "proof.txt").write_text("ok\n", encoding="utf-8")
        self.live.git("add", "-A")
        self.live.git("commit", "-q", "-m", "proof")
        head = self.live.git("rev-parse", "HEAD")
        ingest(self.init, PL.evidence(criterion=crit["entity"], commit=head,
                                      artifacts=["proof.txt"]))
        self.assertEqual(fold(self.live.events())["evidence"][crit["entity"]][-1]["verdict"],
                         "proven")

    def test_an_audit_round_the_engine_did_not_mint_is_refused(self):
        draft = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        ingest(self.init, self.live.answer(draft))
        audit = self.live.act()
        with self.assertRaises(Rejection) as r:
            ingest(self.init, PL.audit(target=audit["entity"],
                                       rnd=audit["context"]["round"] + 4))
        self.assertEqual(r.exception.code, "round_mismatch")


class Timestamps(LiveCase):
    def test_an_unreadable_timestamp_is_refused_not_read_as_the_epoch(self):
        with self.assertRaises(ExecError) as r:
            _iso2epoch("2026-10-15T14:00:00")
        self.assertEqual(r.exception.code, "bad_timestamp")

    def test_an_open_dispatch_with_an_unreadable_stamp_escalates_instead_of_stalling(self):
        """Before the fix, a poll on an open dispatch whose stamp could not be read
        re-emitted the same dispatch forever: no abandon, no escalation, no progress.
        The stamp is corrupted through the store, so the chain stays valid and the
        only fault is the unreadable time."""
        act = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        dispatch_ev = next(e for e in self.live.events()
                           if e["kind"] == "task_dispatched"
                           and e.get("dispatch_id") == act["dispatch_id"])
        self.assertIsNotNone(dispatch_ev)
        bad = self.live.dispatch_with_stamp(act, "not a timestamp")
        self.assertEqual(bad["dispatch_id"], act["dispatch_id"])
        follow = self.live.act(now=time.time() + 10**6)
        self.assertEqual(follow["action"], "ESCALATE")
        self.assertIn("unreadable timestamp", follow["reason"])

    def test_check_reports_an_unreadable_dispatch_stamp_and_does_not_judge_it_dead(self):
        """check must name the unreadable stamp and must not call the dispatch dead:
        liveness cannot be judged from a time that cannot be read. Driven through the
        store with a valid chain, so the only fault is the stamp."""
        act = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        self.live.dispatch_with_stamp(act, "not a timestamp")
        report = check(self.init, now=time.time() + 10**6)
        self.assertEqual(report["chain"], "ok")
        self.assertTrue(any(p.startswith(f"unreadable timestamp on dispatch {act['dispatch_id']}")
                            for p in report["problems"]))
        self.assertFalse(any(p.startswith("dead dispatch") for p in report["problems"]))

    def test_a_missing_state_cache_is_reported_stale_not_raised(self):
        state_file(self.init.idir).unlink()
        self.assertTrue(any(p.startswith("state cache stale")
                            for p in check(self.init)["problems"]))

    def test_a_git_failure_is_an_exec_error_named_git_error(self):
        """When git itself fails, the caller gets the engine's error contract:
        an ExecError carrying the command's stderr and the code git_error —
        never a raw subprocess exception."""
        with self.assertRaises(ExecError) as ctx:
            engine._git(self.live.root, "rev-parse", "--verify",
                        "refs/executor-test-does-not-exist")
        self.assertEqual(ctx.exception.code, "git_error")
        self.assertIn("rev-parse", str(ctx.exception))

    def test_a_stale_state_cache_names_the_journal_length(self):
        cache = read_json(state_file(self.init.idir))
        cache["last_seq"] = 0
        write_json(state_file(self.init.idir), cache)
        problems = check(self.init)["problems"]
        self.assertTrue(any("last_seq 0" in p for p in problems))


class Internals(LiveCase):
    def test_an_unreadable_stamp_counts_as_no_silence(self):
        """A dispatch is judged dead on evidence, never on a stamp that cannot
        be read: an unreadable one contributes zero seconds of silence."""
        self.assertEqual(_silent_for({"at": "not a timestamp"}, 10**9), 0.0)

    def test_entity_for_falls_back_to_the_dispatch_id_for_unknown_kinds(self):
        """Slot-bearing kinds map to their natural entity; a kind the mapper
        does not know yet still identifies itself by dispatch_id."""
        self.assertEqual(engine._entity_for({"kind": "mystery",
                                             "dispatch_id": "D00007"}),
                         "D00007")
        self.assertEqual(engine._entity_for({"kind": "mystery"}), "-")

    def test_open_for_scans_past_a_slot_for_another_entity(self):
        """The first open slot is not assumed to be the one a payload answers:
        slots are scanned until entity and schema match."""
        s = {"dispatches": {
            "D00001": {"entity": "INIT-0001-CHTR-01", "schema": "charter",
                       "role": "author", "respond_to": "", "base": "", "context": {}},
            "D00002": {"entity": "INIT-0001-P01-T01", "schema": "report",
                       "role": "impl", "respond_to": "", "base": "", "context": {}}},
            "answered": set()}
        self.assertIsNone(engine._open_for(s, "INIT-0001-CHTR-01", "report"))
        self.assertEqual(engine._open_for(s, "INIT-0001-P01-T01")["dispatch_id"],
                         "D00002")

    def test_check_survives_a_store_missing_its_optional_directories(self):
        """A store that has never dispatched or exported still audits cleanly:
        missing dispatches/ and docs dirs are not problems."""
        docs_init_dir(self.live.root, self.init.id).rmdir()
        dispatches_dir(self.init.idir).rmdir()
        report = check(self.init)
        self.assertEqual((report["chain"], report["problems"]), ("ok", []))

    def test_a_stray_file_in_the_committed_store_is_named(self):
        """The committed side of the store is audited as strictly as the run
        side: a file the grammar does not describe is reported by path."""
        stray = docs_init_dir(self.live.root, self.init.id) / "meta" / "stray.txt"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("x", encoding="utf-8")
        problems = check(self.init)["problems"]
        self.assertTrue(any("non-canonical committed file" in p and
                            "stray.txt" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
