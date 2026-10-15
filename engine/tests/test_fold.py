# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""engine.fold: the one interpretation of the journal.

fold is pure, so these tests build events by hand, exactly as `ingest` and the
engine store them (the payload's `kind`, `v` and `dispatch_id` are stripped from
`data`; the dispatch id lives on the event), and check what state results. They
pin one event kind at a time, then the properties that make a journal
trustworthy: replay is deterministic, input is never mutated, and an event the
fold cannot apply never reaches the journal in the first place.

Defects this suite caught in the first implementation:
 * a spawn_error event crashed the fold after it was committed, poisoning every
   later read of the journal (the dispatch id was read from `data`, where it
   never is);
 * a waived gate was accepted by the schema and ignored by the fold, leaving
   the phase stuck;
 * critiques were keyed by target alone, so plan_regression found the audit
   planning had already cleared and audited nothing;
 * a PASS audit left the critique round behind, so the next round number was
   minted twice;
 * "reviews" and "proves" edges pointed from an entity to itself.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from executor import engine  # noqa: E402
from executor.paths import ARTIFACT_SEGMENTS  # noqa: E402
from executor.store import PHASES  # noqa: E402

import _payloads as PL  # noqa: E402
from _payloads import INIT, PLAN, TASK  # noqa: E402

fold = engine.fold
T0 = "2026-01-01T00:00:00Z"


def ev(kind: str, entity: str, data: dict | None = None, *,
       did: str | None = None, ts: str = T0, sha: str | None = None) -> dict:
    return {"seq": 0, "ts": ts, "v": "v1", "actor": "test", "kind": kind,
            "entity": entity, "dispatch_id": did, "payload_sha": sha,
            "data": data if data is not None else {}}


def journal(*events: dict) -> list[dict]:
    """Number the events as the store would."""
    for i, e in enumerate(events, 1):
        e["seq"] = i
    return list(events)


def data_of(payload: dict) -> dict:
    """What the engine stores for a payload."""
    return {k: v for k, v in payload.items()
            if k not in ("kind", "v", "engine_version", "dispatch_id")}


def created() -> dict:
    return ev("created", INIT, {"title": "t"})


def entered(phase: str) -> dict:
    return ev("phase_entered", INIT, {"phase": phase})


def with_plan(tasks: list[dict] | None = None, *extra: dict) -> dict:
    """State of an initiative in execution with one plan authored."""
    return fold(journal(created(), entered("execution"),
                        ev("plan", PLAN, data_of(PL.plan_payload(tasks=tasks))),
                        *extra))


def dispatched(entity: str, role: str, schema: str, did: str = "D00005",
               **extra) -> dict:
    data = {"role": role, "schema": schema,
            "respond_to": f"/x/{did}/payload.json", **extra}
    return ev("task_dispatched", entity, data, did=did)


class InitialStateTests(unittest.TestCase):
    def test_an_empty_journal_is_the_start_of_an_initiative(self):
        s = fold([])
        self.assertEqual((s["phase"], s["phase_state"], s["halt"], s["done"],
                          s["seq"]), ("intake", {}, None, False, 0))
        for key in ("artifacts", "critiques", "plans", "tasks", "verdicts",
                    "reports", "evidence", "dispatches", "answered",
                    "entities"):
            self.assertEqual(s[key], {}, key)
        for key in ("plan_order", "rulings", "edges", "needs_ruling",
                    "questions"):
            self.assertEqual(s[key], [], key)

    def test_seq_is_the_number_of_events_folded(self):
        self.assertEqual(fold(journal(created(), entered("intake")))["seq"], 2)

    def test_created_registers_the_initiative_as_an_entity(self):
        s = fold(journal(created()))
        self.assertEqual(s["entities"], {INIT: {"type": "initiative"}})
        self.assertEqual(s["phase"], "intake")


class PhaseTests(unittest.TestCase):
    def test_entering_a_phase_makes_it_current_and_in_progress(self):
        s = fold(journal(created(), entered("discovery")))
        self.assertEqual(s["phase"], "discovery")
        self.assertEqual(s["phase_state"], {"discovery": "in_progress"})

    def test_earlier_phases_keep_their_state(self):
        s = fold(journal(created(), entered("intake"),
                         ev("gate_opened", INIT, {"phase": "intake"}),
                         ev("gate_decision", "intake",
                            {"phase": "intake", "decision": "approved",
                             "by": "human"}),
                         entered("discovery")))
        self.assertEqual(s["phase_state"], {"intake": "passed",
                                            "discovery": "in_progress"})

    def test_re_entering_a_phase_resets_it_to_in_progress(self):
        s = fold(journal(entered("intake"),
                         ev("gate_opened", INIT, {"phase": "intake"}),
                         entered("intake")))
        self.assertEqual(s["phase_state"]["intake"], "in_progress")

    def test_opening_a_gate_marks_the_phase_gate_pending(self):
        s = fold(journal(entered("intake"),
                         ev("gate_opened", INIT, {"phase": "intake"})))
        self.assertEqual(s["phase_state"]["intake"], "gate_pending")


class GateDecisionTests(unittest.TestCase):
    def decide(self, phase: str, decision: str, note: str | None = None):
        data = {"phase": phase, "decision": decision, "by": "human"}
        if note is not None:
            data["note"] = note
        return fold(journal(created(), entered(phase),
                            ev("gate_opened", INIT, {"phase": phase}),
                            ev("gate_decision", phase, data)))

    def test_approval_passes_the_phase(self):
        self.assertEqual(self.decide("intake", "approved")["phase_state"]
                         ["intake"], "passed")

    def test_a_waived_gate_passes_the_phase_too(self):
        """The schema accepts decision=waived; the fold once ignored it, so a
        waived phase never advanced."""
        self.assertEqual(self.decide("intake", "waived")["phase_state"]
                         ["intake"], "passed")

    def test_a_rejected_gate_halts_the_run_with_the_note(self):
        s = self.decide("intake", "rejected", "scope is wrong")
        self.assertEqual(s["halt"], "gate intake rejected: scope is wrong")
        self.assertEqual(s["phase_state"]["intake"], "gate_pending")

    def test_a_rejection_without_a_note_still_says_why_it_halted(self):
        self.assertEqual(self.decide("intake", "rejected")["halt"],
                         "gate intake rejected: no note")

    def test_approving_the_handoff_gate_finishes_the_initiative(self):
        self.assertTrue(self.decide("handoff", "approved")["done"])
        self.assertTrue(self.decide("handoff", "waived")["done"])

    def test_approving_any_other_gate_does_not(self):
        for phase in PHASES[:-1]:
            with self.subTest(phase=phase):
                self.assertFalse(self.decide(phase, "approved")["done"])

    def test_rejecting_the_handoff_gate_does_not_finish_it(self):
        self.assertFalse(self.decide("handoff", "rejected")["done"])


class HaltTests(unittest.TestCase):
    def test_a_halt_records_its_reason(self):
        self.assertEqual(fold(journal(ev("halt", INIT, {"reason": "stop"})))
                         ["halt"], "stop")

    def test_a_halt_without_a_reason_says_halted(self):
        self.assertEqual(fold(journal(ev("halt", INIT, {}))) ["halt"],
                         "halted")

    def test_a_resume_clears_the_halt(self):
        s = fold(journal(ev("halt", INIT, {"reason": "stop"}),
                         ev("resume", INIT, {})))
        self.assertIsNone(s["halt"])

    def test_a_later_halt_wins_over_an_earlier_resume(self):
        s = fold(journal(ev("halt", INIT, {"reason": "a"}),
                         ev("resume", INIT, {}),
                         ev("halt", INIT, {"reason": "b"})))
        self.assertEqual(s["halt"], "b")


class ArtifactTests(unittest.TestCase):
    KINDS = sorted(ARTIFACT_SEGMENTS)

    def test_every_artifact_kind_is_drafted_on_first_sight(self):
        for kind in self.KINDS:
            payload = PL.art(kind)
            with self.subTest(kind=kind):
                s = fold(journal(ev(kind, payload["id"], data_of(payload))))
                a = s["artifacts"][payload["id"]]
                self.assertEqual((a["kind"], a["status"], a["round"]),
                                 (kind, "drafted", 1))
                self.assertEqual(a["data"], data_of(payload))
                self.assertEqual(s["entities"][payload["id"]],
                                 {"type": "artifact"})

    def test_redrafting_bumps_the_round_replaces_the_data_and_reopens_it(self):
        first = PL.art("charter")
        second = PL.art("charter", title="v2")
        aid = first["id"]
        s = fold(journal(
            ev("charter", aid, data_of(first)),
            ev("audit", aid, data_of(PL.audit(aid, 1, "PASS"))),
            ev("charter", aid, data_of(second))))
        a = s["artifacts"][aid]
        self.assertEqual((a["round"], a["status"], a["data"]["title"]),
                         (2, "drafted", "v2"))

    def test_cites_become_edges(self):
        payload = PL.art("options", cites=[f"{INIT}-CHTR-01"])
        s = fold(journal(ev("options", payload["id"], data_of(payload))))
        self.assertEqual(s["edges"], [{"from": payload["id"],
                                       "to": f"{INIT}-CHTR-01",
                                       "kind": "cites"}])

    def test_redrafting_does_not_repeat_an_edge(self):
        payload = PL.art("options", cites=[f"{INIT}-CHTR-01"])
        first = ev("options", payload["id"], data_of(payload))
        s = fold(journal(first, dict(first)))
        self.assertEqual(len(s["edges"]), 1)


class PlanTests(unittest.TestCase):
    def test_a_plan_registers_itself_and_its_tasks(self):
        rows = [PL.task_row("T01"), PL.task_row("T02", depends_on=["T01"])]
        s = with_plan(rows)
        self.assertEqual(s["plan_order"], [PLAN])
        self.assertEqual(s["plans"][PLAN], {"status": "draft"})
        t2 = s["tasks"][f"{PLAN}-T02"]
        self.assertEqual((t2["state"], t2["round"], t2["fix_rounds"]),
                         ("pending", 0, 0))
        self.assertEqual((t2["plan"], t2["title"], t2["goal"], t2["files"],
                          t2["accepts"], t2["depends_on"]),
                         (PLAN, "task T02", "g", ["a.py"], ["it works"],
                          ["T01"]))
        self.assertEqual(s["entities"][f"{PLAN}-T02"], {"type": "task"})
        self.assertIn({"from": PLAN, "to": f"{PLAN}-T02", "kind": "contains"},
                      s["edges"])

    def test_a_task_without_dependencies_depends_on_nothing(self):
        self.assertEqual(with_plan()["tasks"][TASK]["depends_on"], [])

    def test_redrafting_a_plan_neither_duplicates_it_nor_resets_its_tasks(self):
        s = with_plan(None, dispatched(TASK, "impl", "report"),
                      ev("plan", PLAN, data_of(PL.plan_payload(
                          tasks=[PL.task_row("T01"), PL.task_row("T02")]))))
        self.assertEqual(s["plan_order"], [PLAN])
        self.assertEqual(s["tasks"][TASK]["state"], "dispatched")
        self.assertEqual(s["tasks"][f"{PLAN}-T02"]["state"], "pending")

    def test_plans_keep_the_order_they_were_authored_in(self):
        p2 = f"{INIT}-P02"
        s = fold(journal(ev("plan", PLAN, data_of(PL.plan_payload())),
                         ev("plan", p2, data_of(PL.plan_payload(pid=p2)))))
        self.assertEqual(s["plan_order"], [PLAN, p2])

    def test_redrafting_updates_unstarted_tasks_and_drops_removed_ones(self):
        first = PL.plan_payload(tasks=[PL.task_row("T01"),
                                       PL.task_row("T02")])
        second = PL.plan_payload(tasks=[PL.task_row(
            "T01", title="renamed", files=["b.py"], accepts=["new"])])
        s = fold(journal(ev("plan", PLAN, data_of(first)),
                         ev("plan", PLAN, data_of(second))))
        self.assertEqual(sorted(s["tasks"]), [TASK])
        t = s["tasks"][TASK]
        self.assertEqual((t["title"], t["files"], t["accepts"]),
                         ("renamed", ["b.py"], ["new"]))

    def test_a_task_under_way_keeps_its_contract_when_the_plan_changes(self):
        s = with_plan(None, dispatched(TASK, "impl", "report"),
                      ev("plan", PLAN, data_of(PL.plan_payload(
                          tasks=[PL.task_row("T01", title="changed")]))))
        t = s["tasks"][TASK]
        self.assertEqual((t["title"], t["state"]),
                         ("task T01", "dispatched"))

    def test_a_task_under_way_survives_being_dropped_from_the_plan(self):
        s = with_plan(None, dispatched(TASK, "impl", "report"),
                      ev("plan", PLAN, data_of(PL.plan_payload(
                          tasks=[PL.task_row("T02")]))))
        self.assertEqual(sorted(s["tasks"]), [TASK, f"{PLAN}-T02"])


class AuditTests(unittest.TestCase):
    AID = f"{INIT}-CHTR-01"

    def state(self, phase: str, *events: dict) -> dict:
        payload = PL.art("charter")
        return fold(journal(created(), entered(phase),
                            ev("charter", self.AID, data_of(payload)),
                            *events))

    def audit(self, rnd: int, verdict: str, *findings: dict) -> dict:
        return ev("audit", self.AID,
                  data_of(PL.audit(self.AID, rnd, verdict, findings)))

    def test_a_failing_audit_opens_a_critique_with_its_open_findings(self):
        keep = PL.finding("F1")
        done = PL.finding("F2", status="fixed")
        waived = PL.finding("F3", status="waived")
        s = self.state("intake", self.audit(1, "FAIL", keep, done, waived))
        c = s["critiques"][f"intake:{self.AID}"]
        self.assertEqual((c["round"], c["status"]), (1, "fail"))
        self.assertEqual([f["id"] for f in c["open"]], ["F1"])
        self.assertEqual(s["artifacts"][self.AID]["status"], "under_audit")

    def test_a_finding_without_a_status_counts_as_open(self):
        s = self.state("intake", self.audit(1, "FAIL", PL.finding("F1")))
        self.assertEqual(len(s["critiques"][f"intake:{self.AID}"]["open"]), 1)

    def test_a_passing_audit_clears_the_critique_and_the_artifact(self):
        s = self.state("intake", self.audit(1, "FAIL", PL.finding()),
                       self.audit(2, "PASS"))
        c = s["critiques"][f"intake:{self.AID}"]
        self.assertEqual((c["status"], c["open"]), ("clean", []))
        self.assertEqual(s["artifacts"][self.AID]["status"], "cleared")

    def test_a_passing_audit_records_its_round(self):
        """A PASS once left the round behind, so round 2 would be minted again."""
        s = self.state("intake", self.audit(1, "FAIL", PL.finding()),
                       self.audit(2, "PASS"))
        self.assertEqual(s["critiques"][f"intake:{self.AID}"]["round"], 2)
        s = self.state("intake", self.audit(1, "PASS"))
        self.assertEqual(s["critiques"][f"intake:{self.AID}"]["round"], 1)

    def test_critiques_are_scoped_to_the_phase_they_happened_in(self):
        """plan_regression re-audits what planning cleared: the two audits are
        different critiques of the same plan."""
        plan = PL.plan_payload()
        s = fold(journal(
            created(), entered("planning"),
            ev("plan", PLAN, data_of(plan)),
            ev("audit", PLAN, data_of(PL.audit(PLAN, 1, "PASS"))),
            entered("plan_regression"),
            ev("audit", PLAN, data_of(PL.audit(PLAN, 1, "FAIL",
                                               (PL.finding(),))))))
        self.assertEqual(s["critiques"][f"planning:{PLAN}"]["status"], "clean")
        self.assertEqual(s["critiques"][f"plan_regression:{PLAN}"]["status"],
                         "fail")

    def test_an_audit_of_an_unknown_target_leaves_the_artifacts_alone(self):
        s = fold(journal(created(), entered("intake"),
                         ev("audit", "INIT-0001-GHOST-01",
                            data_of(PL.audit("INIT-0001-GHOST-01", 1)))))
        self.assertEqual(s["artifacts"], {})
        self.assertIn("intake:INIT-0001-GHOST-01", s["critiques"])

    def test_a_redrafted_artifact_marks_the_failed_critique_repaired(self):
        s = self.state("intake", self.audit(1, "FAIL", PL.finding()),
                       ev("charter", self.AID, data_of(PL.art("charter"))))
        self.assertEqual(s["critiques"][f"intake:{self.AID}"]["status"],
                         "repaired")

    def test_a_redraft_in_another_phase_does_not_touch_this_critique(self):
        s = self.state("intake", self.audit(1, "FAIL", PL.finding()),
                       entered("discovery"),
                       ev("charter", self.AID, data_of(PL.art("charter"))))
        self.assertEqual(s["critiques"][f"intake:{self.AID}"]["status"],
                         "fail")

    def test_a_redraft_of_an_unaudited_artifact_leaves_no_critique(self):
        s = self.state("intake", ev("charter", self.AID,
                                    data_of(PL.art("charter"))))
        self.assertEqual(s["critiques"], {})

    def test_audits_and_redrafts_draw_no_self_referential_edges(self):
        s = self.state("intake", self.audit(1, "PASS"),
                       ev("charter", self.AID, data_of(PL.art("charter"))))
        self.assertEqual([e for e in s["edges"] if e["from"] == e["to"]], [])


class DispatchTests(unittest.TestCase):
    def test_a_dispatch_is_recorded_for_any_entity(self):
        s = fold(journal(created(), entered("intake"),
                         dispatched(f"{INIT}-CHTR-01", "author", "charter",
                                    did="D00003")))
        self.assertEqual(s["dispatches"]["D00003"], {
            "entity": f"{INIT}-CHTR-01", "role": "author",
            "schema": "charter", "at": T0, "base": None, "context": {},
            "respond_to": "/x/D00003/payload.json"})
        self.assertIn({"from": "D00003", "to": f"{INIT}-CHTR-01",
                       "kind": "dispatched"}, s["edges"])
        self.assertEqual(s["tasks"], {})

    def test_dispatching_a_task_moves_it_to_dispatched(self):
        s = with_plan(None, dispatched(TASK, "impl", "report", "D00007",
                                       base="abc1234"))
        t = s["tasks"][TASK]
        self.assertEqual((t["state"], t["role"], t["dispatch_id"], t["base"]),
                         ("dispatched", "impl", "D00007", "abc1234"))
        self.assertEqual(s["dispatches"]["D00007"]["at"], T0)

    def test_the_task_clock_starts_at_the_dispatch(self):
        s = with_plan(None, dispatched(TASK, "impl", "report", "D00004"))
        self.assertEqual(s["dispatches"]["D00004"]["at"], T0)
        self.assertNotIn("last_beat", s["dispatches"]["D00004"])

    def test_an_authoring_dispatch_registers_the_artifact_it_will_produce(
            self):
        """Otherwise the dispatch edge points at nothing until the artifact
        exists, and `check` reports a dangling edge for every open dispatch."""
        aid = f"{INIT}-CHTR-01"
        s = fold(journal(created(), entered("intake"),
                         dispatched(aid, "author", "charter")))
        self.assertEqual(s["entities"][aid], {"type": "artifact"})


class ReportTests(unittest.TestCase):
    def reported(self, **extra):
        payload = PL.report(**extra)
        return with_plan(None, dispatched(TASK, "impl", "report", "D00005"),
                         ev("report", TASK, data_of(payload), did="D00005"))

    def test_a_report_moves_the_task_to_reported_and_is_kept(self):
        s = self.reported()
        self.assertEqual(s["tasks"][TASK]["state"], "reported")
        self.assertEqual(s["reports"][TASK]["summary"], "done")

    def test_a_blocked_report_blocks_the_task_and_asks_for_a_ruling(self):
        s = self.reported(result="BLOCKED")
        self.assertEqual(s["tasks"][TASK]["state"], "blocked")
        self.assertEqual([(n["task"], n["ruled"]) for n in s["needs_ruling"]],
                         [(TASK, False)])
        self.assertIn("BLOCKED", s["needs_ruling"][0]["concern"])

    def test_each_concern_needs_its_own_ruling(self):
        s = self.reported(result="DONE_WITH_CONCERNS",
                          concerns=["slow", "flaky"])
        self.assertEqual([n["concern"] for n in s["needs_ruling"]],
                         ["slow", "flaky"])
        self.assertEqual(s["tasks"][TASK]["state"], "reported")

    def test_a_report_for_an_unknown_task_is_kept_but_changes_no_task(self):
        s = fold(journal(ev("report", "INIT-0001-P09-T09",
                            data_of(PL.report("INIT-0001-P09-T09")))))
        self.assertIn("INIT-0001-P09-T09", s["reports"])
        self.assertEqual(s["tasks"], {})


class HeartbeatTests(unittest.TestCase):
    def test_a_heartbeat_moves_the_dispatch_clock(self):
        later = "2026-01-01T00:20:00Z"
        s = with_plan(None, dispatched(TASK, "impl", "report", "D00004"),
                      ev("heartbeat", TASK, {"task": TASK}, ts=later, did="D00004"))
        self.assertEqual(s["dispatches"]["D00004"]["last_beat"], later)
        self.assertEqual(s["tasks"][TASK]["state"], "dispatched")

    def test_a_heartbeat_for_an_unknown_task_is_ignored(self):
        s = fold(journal(ev("heartbeat", "INIT-0001-P09-T09", {})))
        self.assertEqual(s["tasks"], {})


class VerdictTests(unittest.TestCase):
    def judged(self, **kw):
        payload = PL.verdict(**kw)
        return with_plan(None, ev("verdict", TASK, data_of(payload)))

    def test_a_clean_verdict_completes_the_task(self):
        for quality in ("APPROVED", "APPROVED_WITH_ROUTED_RESIDUALS"):
            with self.subTest(quality=quality):
                t = self.judged(quality=quality)["tasks"][TASK]
                self.assertEqual((t["state"], t["round"], t["fix_rounds"]),
                                 ("complete", 1, 0))

    def test_an_unclean_verdict_sends_the_task_to_a_fix_and_counts_it(self):
        for kw in ({"spec": "FAIL"}, {"quality": "NEEDS_FIXES"},
                   {"spec": "FAIL", "quality": "NEEDS_FIXES"}):
            with self.subTest(kw=kw):
                t = self.judged(**kw)["tasks"][TASK]
                self.assertEqual((t["state"], t["fix_rounds"]),
                                 ("fix_needed", 1))

    def test_fix_rounds_accumulate_across_failing_verdicts(self):
        s = with_plan(None,
                      ev("verdict", TASK, data_of(PL.verdict(rnd=1,
                                                             spec="FAIL"))),
                      ev("verdict", TASK, data_of(PL.verdict(rnd=2,
                                                             spec="FAIL"))))
        t = s["tasks"][TASK]
        self.assertEqual((t["round"], t["fix_rounds"]), (2, 2))

    def test_verdicts_are_kept_by_task_and_zero_padded_round(self):
        s = self.judged(rnd=3)
        self.assertEqual(list(s["verdicts"]), [f"{TASK}-R03"])

    def test_verdicts_draw_no_self_referential_edges(self):
        self.assertEqual([e for e in self.judged()["edges"]
                          if e["from"] == e["to"]], [])


class SpawnErrorTests(unittest.TestCase):
    def failed(self):
        return with_plan(None, dispatched(TASK, "impl", "report", "D00005"),
                         ev("spawn_error", TASK,
                            {"error_class": "rate_limit"}, did="D00005"))

    def test_a_spawn_error_marks_the_dispatch_and_returns_the_task(self):
        """The dispatch id is on the event, not in data: reading it from data
        crashed the fold after the event was already committed. The task goes
        back to the state it was dispatched from, and the loss is counted."""
        s = self.failed()
        self.assertEqual(s["dispatches"]["D00005"]["spawn_error"], "rate_limit")
        self.assertEqual(s["tasks"][TASK]["state"], "pending")
        self.assertEqual(s["lost"], {f"{TASK}:report": 1})

    def test_a_spawn_error_for_an_unknown_dispatch_is_ignored(self):
        s = fold(journal(created(), ev("spawn_error", TASK,
                                       {"error_class": "other"},
                                       did="D99999")))
        self.assertEqual(s["dispatches"], {})
        self.assertEqual(s["tasks"], {})


class NeedsContextTests(unittest.TestCase):
    def asked(self):
        return with_plan(None, dispatched(TASK, "impl", "report"),
                         ev("needs_context", TASK,
                            {"task": TASK, "question": "which db?"}))

    def test_a_question_parks_the_task_and_is_remembered(self):
        s = self.asked()
        self.assertEqual((s["tasks"][TASK]["state"],
                          s["tasks"][TASK]["question"]),
                         ("needs_context", "which db?"))
        self.assertEqual(s["questions"], [{"task": TASK,
                                           "question": "which db?",
                                           "ruled": False}])

    def test_a_question_about_an_unknown_task_is_still_recorded(self):
        s = fold(journal(ev("needs_context", "INIT-0001-P09-T09",
                            {"task": "INIT-0001-P09-T09", "question": "q"})))
        self.assertEqual(len(s["questions"]), 1)
        self.assertEqual(s["tasks"], {})


class RulingTests(unittest.TestCase):
    def ruling(self, **kw):
        return ev("ruling", INIT, data_of(PL.ruling(**kw)))

    def test_a_ruling_is_recorded(self):
        s = fold(journal(self.ruling()))
        self.assertEqual([r["decision"] for r in s["rulings"]], ["use X"])
        self.assertIsNone(s["halt"])

    def test_a_stopping_ruling_halts_with_its_decision(self):
        self.assertEqual(fold(journal(self.ruling(decision="stop now",
                                                  stop=True)))["halt"],
                         "stop now")

    def test_a_ruling_for_a_task_settles_its_concerns_and_questions(self):
        s = with_plan(None, dispatched(TASK, "impl", "report"),
                      ev("report", TASK, data_of(PL.report(
                          result="DONE_WITH_CONCERNS", concerns=["c"]))),
                      ev("needs_context", TASK,
                         {"task": TASK, "question": "q"}),
                      self.ruling(for_task=TASK))
        self.assertTrue(all(n["ruled"] for n in s["needs_ruling"]))
        self.assertTrue(all(q["ruled"] for q in s["questions"]))

    def test_a_ruling_for_another_task_settles_nothing(self):
        other = f"{PLAN}-T02"
        s = with_plan([PL.task_row("T01"), PL.task_row("T02")],
                      ev("report", TASK, data_of(PL.report(
                          result="DONE_WITH_CONCERNS", concerns=["c"]))),
                      self.ruling(for_task=other))
        self.assertFalse(s["needs_ruling"][0]["ruled"])

    def test_a_ruling_frees_a_blocked_or_questioning_task(self):
        for state_event in (
                ev("report", TASK, data_of(PL.report(result="BLOCKED"))),
                ev("needs_context", TASK, {"task": TASK, "question": "q"})):
            with self.subTest(via=state_event["kind"]):
                s = with_plan(None, state_event, self.ruling(for_task=TASK))
                self.assertEqual(s["tasks"][TASK]["state"], "pending")

    def test_a_ruling_leaves_other_task_states_alone(self):
        s = with_plan(None, dispatched(TASK, "impl", "report"),
                      self.ruling(for_task=TASK))
        self.assertEqual(s["tasks"][TASK]["state"], "dispatched")

    def test_a_ruling_without_a_task_settles_nothing(self):
        s = with_plan(None, ev("report", TASK, data_of(PL.report(
            result="DONE_WITH_CONCERNS", concerns=["c"]))), self.ruling())
        self.assertFalse(s["needs_ruling"][0]["ruled"])

    def test_a_ruling_that_quotes_a_question_settles_it_and_frees_its_task(
            self):
        s = with_plan(None, dispatched(TASK, "impl", "report"),
                      ev("needs_context", TASK,
                         {"task": TASK, "question": "which database?"}),
                      self.ruling(answered="which database"))
        self.assertTrue(s["questions"][0]["ruled"])
        self.assertEqual(s["tasks"][TASK]["state"], "pending")

    def test_a_ruling_quoting_a_different_question_settles_nothing(self):
        s = with_plan(None, dispatched(TASK, "impl", "report"),
                      ev("needs_context", TASK,
                         {"task": TASK, "question": "which database?"}),
                      self.ruling(answered="which cache"))
        self.assertFalse(s["questions"][0]["ruled"])
        self.assertEqual(s["tasks"][TASK]["state"], "needs_context")


class EvidenceTests(unittest.TestCase):
    def test_evidence_is_kept_in_order_per_criterion(self):
        first = PL.evidence("V1", verdict="failed")
        second = PL.evidence("V1", verdict="proven")
        other = PL.evidence("V2")
        s = fold(journal(ev("evidence", "V1", data_of(first)),
                         ev("evidence", "V2", data_of(other)),
                         ev("evidence", "V1", data_of(second))))
        self.assertEqual([e["verdict"] for e in s["evidence"]["V1"]],
                         ["failed", "proven"])
        self.assertEqual(len(s["evidence"]["V2"]), 1)

    def test_evidence_draws_no_self_referential_edge(self):
        s = fold(journal(ev("evidence", "V1", data_of(PL.evidence()))))
        self.assertEqual([e for e in s["edges"] if e["from"] == e["to"]], [])


class MergeTests(unittest.TestCase):
    def test_a_merge_marks_the_plan_merged_with_its_sha(self):
        s = with_plan(None, ev("merge", PLAN, {"plan": PLAN,
                                               "merge_sha": "abc1234"}))
        self.assertEqual(s["plans"][PLAN]["status"], "merged")
        self.assertEqual(s["plans"][PLAN]["merge_sha"], "abc1234")

    def test_a_merge_of_an_unplanned_plan_still_records_it(self):
        s = fold(journal(ev("merge", "INIT-0001-P09",
                            {"plan": "INIT-0001-P09", "merge_sha": "abc1234"})))
        self.assertEqual(s["plans"]["INIT-0001-P09"]["status"], "merged")


class AnsweredTests(unittest.TestCase):
    """A dispatch is open until an event answers it; the journal says which."""

    def state(self, *events: dict) -> dict:
        return with_plan(None, dispatched(TASK, "impl", "report", "D00005"),
                         *events)

    def test_a_fresh_dispatch_is_unanswered(self):
        self.assertEqual(self.state()["answered"], {})

    def test_an_answering_event_records_the_payload_digest_by_dispatch(self):
        s = self.state(ev("report", TASK, data_of(PL.report()),
                          did="D00005", sha="feedface"))
        self.assertEqual(s["answered"], {"D00005": "feedface"})

    def test_every_answering_kind_closes_its_dispatch(self):
        for kind, data in (("verdict", data_of(PL.verdict())),
                           ("spawn_error", {"error_class": "other"}),
                           ("needs_context", {"task": TASK, "question": "q"})):
            with self.subTest(kind=kind):
                s = self.state(ev(kind, TASK, data, did="D00005", sha="x"))
                self.assertIn("D00005", s["answered"])

    def test_a_heartbeat_never_closes_a_dispatch(self):
        s = self.state(ev("heartbeat", TASK, {"task": TASK}, did="D00005"))
        self.assertEqual(s["answered"], {})

    def test_the_dispatch_event_itself_is_not_an_answer(self):
        self.assertNotIn("D00005", self.state()["answered"])

    def test_an_event_without_a_dispatch_answers_nothing(self):
        s = self.state(ev("report", TASK, data_of(PL.report())))
        self.assertEqual(s["answered"], {})


class PurityTests(unittest.TestCase):
    def long_journal(self) -> list[dict]:
        aid = f"{INIT}-CHTR-01"
        return journal(
            created(), entered("intake"),
            ev("charter", aid, data_of(PL.art("charter"))),
            ev("audit", aid, data_of(PL.audit(aid, 1, "FAIL",
                                              (PL.finding(),)))),
            ev("charter", aid, data_of(PL.art("charter"))),
            ev("audit", aid, data_of(PL.audit(aid, 2, "PASS"))),
            entered("planning"),
            ev("plan", PLAN, data_of(PL.plan_payload())),
            dispatched(TASK, "impl", "report", "D00009"),
            ev("report", TASK, data_of(PL.report()), did="D00009",
               sha="aa"))

    def test_folding_twice_gives_the_same_state(self):
        events = self.long_journal()
        self.assertEqual(fold(events), fold(events))

    def test_folding_never_mutates_the_events(self):
        events = self.long_journal()
        before = copy.deepcopy(events)
        fold(events)
        self.assertEqual(events, before)

    def test_states_do_not_share_structure_between_calls(self):
        events = self.long_journal()
        a, b = fold(events), fold(events)
        a["tasks"][TASK]["state"] = "tampered"
        a["edges"].clear()
        self.assertEqual(b["tasks"][TASK]["state"], "reported")
        self.assertTrue(b["edges"])

    def test_a_prefix_folds_to_the_state_at_that_point(self):
        events = self.long_journal()
        self.assertEqual(fold(events[:2])["phase"], "intake")
        self.assertEqual(fold(events[:7])["phase"], "planning")
        self.assertEqual(fold(events)["seq"], len(events))

    def test_every_prefix_of_a_realistic_journal_folds_without_error(self):
        events = self.long_journal()
        for n in range(len(events) + 1):
            with self.subTest(prefix=n):
                fold(events[:n])


if __name__ == "__main__":
    unittest.main()
