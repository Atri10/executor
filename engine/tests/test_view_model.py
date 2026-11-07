# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The view model is what both pages show, so these tests pin what a reader
would see: dependencies that resolve, the attention list, evidence and dispatch
counts, phase durations, the parent index order, and privacy (no payloads,
home directory masked)."""
from __future__ import annotations

import json
import unittest

from executor.view_model import (initiative_model, initiative_row, mask_home,
                                 root_model)

PLAN = "INIT-1-P01"
STORE = {"engine": "2.1.1", "store_version": "v2", "verdict": "current"}


def _folded(**overrides) -> dict:
    folded = {
        "phase": "execution",
        "phase_state": {"intake": "complete", "execution": "in_progress"},
        "done": False,
        "seq": 5,
        "last_ts": "2026-01-01T00:05:00Z",
        "tasks": {
            f"{PLAN}-T01": {"title": "Schema", "state": "complete", "plan": PLAN,
                            "depends_on": [], "files": ["engine/a.py"], "goal": "g"},
            f"{PLAN}-T02": {"title": "Store", "state": "blocked", "plan": PLAN,
                            "depends_on": ["T01"], "fix_rounds": 2},
            f"{PLAN}-T03": {"title": "View", "state": "pending", "plan": PLAN,
                            "depends_on": ["T02", "T99"]},
        },
        "dispatches": {
            "D1": {"role": "impl", "entity": f"{PLAN}-T01", "at": "2026-01-01T00:01:00Z"},
            "D2": {"role": "review", "entity": f"{PLAN}-T02", "at": "2026-01-01T00:02:00Z"},
            "D3": {"role": "fix", "entity": f"{PLAN}-T02", "at": "2026-01-01T00:03:00Z",
                   "abandoned": True},
        },
        "answered": {"D1": "digest"},
        "evidence": {"V1": [{"verdict": "proven", "state_commit": "abcdef1234567890"}]},
        "critiques": {f"{PLAN}-T02": {"open": ["fix the store"], "round": 1, "status": "open"}},
        "entities": {
            "INIT-1": {"type": "initiative"},
            f"{PLAN}-T01": {"type": "task"},
            f"{PLAN}-T02": {"type": "task"},
            f"{PLAN}-T03": {"type": "task"},
            "A1": {"type": "artifact"},
        },
        "edges": [
            {"from": "INIT-1", "to": f"{PLAN}-T01", "kind": "contains"},
            {"from": f"{PLAN}-T01", "to": "A1", "kind": "cites"},
            {"from": "D1", "to": f"{PLAN}-T01", "kind": "dispatched"},
        ],
        "artifacts": {"A1": {"kind": "design", "title": "Design note", "status": "draft",
                             "summary": "see /Users/someone/work/x", "round": 1,
                             "cites": [f"{PLAN}-T01"]}},
        "changes": {"C1": {"title": "Add field", "state": "withdrawn", "reason": "scope",
                           "why": "w", "radius": {"artifacts": ["A1"], "tasks": []}}},
        "rulings": [{"decision": "use sqlite", "why": "local", "cost_if_wrong": "migrate"}],
        "needs_ruling": [{"task": f"{PLAN}-T02", "concern": "retry policy", "ruled": False}],
        "policy": {"max_fix_rounds": 3},
    }
    folded.update(overrides)
    return folded


def _event(seq: int, ts: str, kind: str, data=None) -> dict:
    return {"seq": seq, "ts": ts, "kind": kind, "actor": "engine", "entity": "",
            "dispatch_id": "", "data": data or {}}


def _model(folded=None, events=None, criteria=None, home=""):
    return initiative_model(init_id="INIT-1", title="Demo", folded=folded or _folded(),
                            events=events or [], criteria=criteria or [{"id": "V1",
                            "criterion": "tests pass", "cites": ["A1"]}],
                            store=STORE, home=home)


class Dependencies(unittest.TestCase):
    def test_a_local_dependency_resolves_through_its_plan_prefix(self):
        tasks = {t["short"]: t for t in _model()["tasks"]}
        self.assertEqual(tasks["T03"]["depends_on"], [f"{PLAN}-T02"])

    def test_a_dependency_that_matches_nothing_is_reported_not_dropped(self):
        tasks = {t["short"]: t for t in _model()["tasks"]}
        self.assertEqual(tasks["T03"]["unresolved"], ["T99"])

    def test_dependents_are_the_inverse_of_depends_on(self):
        tasks = {t["short"]: t for t in _model()["tasks"]}
        self.assertEqual(tasks["T02"]["dependents"], [f"{PLAN}-T03"])

    def test_the_dag_has_one_node_per_task_and_one_edge_per_resolved_dependency(self):
        dag = _model()["dag"]
        self.assertEqual(len(dag["nodes"]), 3)
        self.assertEqual(sorted((e["from"], e["to"]) for e in dag["edges"]),
                         [(f"{PLAN}-T01", f"{PLAN}-T02"), (f"{PLAN}-T02", f"{PLAN}-T03")])


class Dispatches(unittest.TestCase):
    def test_each_dispatch_is_answered_open_or_abandoned(self):
        outcomes = {d["id"]: d["outcome"] for d in _model()["dispatches"]}
        self.assertEqual(outcomes, {"D1": "answered", "D2": "open", "D3": "abandoned"})

    def test_a_task_counts_the_dispatches_aimed_at_it(self):
        tasks = {t["short"]: t for t in _model()["tasks"]}
        self.assertEqual(tasks["T02"]["dispatches"], 2)


class Attention(unittest.TestCase):
    def test_blocked_work_ranks_above_open_findings_and_rulings(self):
        kinds = [(a["kind"], a["severity"]) for a in _model()["attention"]]
        self.assertEqual(kinds[0], ("task", "bad"))
        self.assertLess(kinds.index(("critique", "warn")), kinds.index(("dispatch", "info")))

    def test_a_proven_criterion_raises_no_attention(self):
        kinds = {a["kind"] for a in _model()["attention"]}
        self.assertNotIn("evidence", kinds)

    def test_a_withdrawn_change_is_terminal_and_raises_no_attention(self):
        kinds = {a["kind"] for a in _model()["attention"]}
        self.assertNotIn("change", kinds)

    def test_a_criterion_with_no_run_is_unanswered_and_unproven(self):
        model = _model(criteria=[{"id": "V1", "criterion": "a"}, {"id": "V2", "criterion": "b"}])
        evidence = {e["id"]: e for e in model["evidence"]}
        self.assertEqual(evidence["V2"]["verdict"], "unanswered")
        self.assertEqual(model["kpis"]["evidence"]["unproven"], 1)


class Graph(unittest.TestCase):
    def test_entity_edges_keep_containment_and_citation_between_known_entities_only(self):
        kinds = sorted(e["kind"] for e in _model()["entity_edges"])
        self.assertEqual(kinds, ["cites", "contains"])

    def test_the_kpis_count_every_fold_edge_including_dispatch_links(self):
        self.assertEqual(_model()["kpis"]["edges"],
                         {"contains": 1, "cites": 1, "dispatched": 1})

    def test_an_artifact_lists_what_cites_it(self):
        (artifact,) = _model()["artifacts"]
        self.assertEqual(artifact["cited_by"], [f"{PLAN}-T01"])


class Phases(unittest.TestCase):
    def test_a_phase_lasts_until_the_next_phase_is_entered(self):
        events = [_event(1, "2026-01-01T00:00:00Z", "phase_entered", {"phase": "intake"}),
                  _event(2, "2026-01-01T00:02:00Z", "phase_entered", {"phase": "execution"})]
        phases = {p["name"]: p for p in _model(events=events)["phases"]}
        self.assertEqual(phases["intake"]["seconds"], 120)
        self.assertEqual(phases["execution"]["seconds"], 180)
        self.assertTrue(phases["execution"]["current"])

    def test_a_phase_never_entered_is_pending_with_no_duration(self):
        phases = {p["name"]: p for p in _model()["phases"]}
        self.assertEqual(phases["handoff"]["state"], "pending")
        self.assertIsNone(phases["handoff"]["seconds"])


class Privacy(unittest.TestCase):
    def test_journal_payloads_never_reach_the_model(self):
        events = [_event(1, "2026-01-01T00:00:00Z", "ruling", {"text": "PAYLOAD-SECRET"})]
        self.assertNotIn("PAYLOAD-SECRET", json.dumps(_model(events=events)))

    def test_the_home_directory_is_masked_in_every_string(self):
        model = _model(home="/Users/someone")
        self.assertNotIn("/Users/someone", json.dumps(model))
        self.assertEqual(model["artifacts"][0]["summary"], "see ~/work/x")

    def test_either_separator_style_of_a_windows_home_is_masked(self):
        self.assertEqual(mask_home("C:\\Users\\me\\x", "C:\\Users\\me"), "~\\x")
        self.assertEqual(mask_home("C:/Users/me/x", "C:\\Users\\me"), "~/x")

    def test_a_degenerate_home_is_never_masked(self):
        self.assertEqual(mask_home("/a/b", "/"), "/a/b")


class ParentIndex(unittest.TestCase):
    def _row(self, init_id: str, last_ts: str, done: bool = False) -> dict:
        folded = _folded(last_ts=last_ts, done=done)
        model = initiative_model(init_id=init_id, title=init_id, folded=folded, events=[],
                                 criteria=[], store=STORE)
        return initiative_row(model, href=f"../{init_id}/views/index.html")

    def test_the_most_recent_initiative_comes_first_and_ties_break_by_id(self):
        rows = [self._row("INIT-2", "2026-01-01T00:00:00Z"),
                self._row("INIT-3", "2026-01-03T00:00:00Z"),
                self._row("INIT-1", "2026-01-01T00:00:00Z")]
        order = [r["id"] for r in root_model(rows, STORE)["initiatives"]]
        self.assertEqual(order, ["INIT-3", "INIT-1", "INIT-2"])

    def test_the_totals_add_up_across_initiatives(self):
        rows = [self._row("INIT-1", "2026-01-01T00:00:00Z", done=True),
                self._row("INIT-2", "2026-01-02T00:00:00Z")]
        totals = root_model(rows, STORE)["totals"]
        self.assertEqual((totals["initiatives"], totals["done"], totals["active"]), (2, 1, 1))
        self.assertEqual(totals["tasks_total"], 6)

    def test_the_same_fold_always_gives_the_same_model(self):
        self.assertEqual(_model(), _model())


class Robustness(unittest.TestCase):
    """A damaged journal entry must degrade one row, never break the page."""

    def test_a_malformed_phase_timestamp_gives_no_duration_instead_of_a_crash(self):
        events = [_event(1, "not-a-time", "phase_entered", {"phase": "intake"}),
                  _event(2, "2026-01-01T00:02:00Z", "phase_entered", {"phase": "execution"})]
        phases = {p["name"]: p for p in _model(events=events)["phases"]}
        self.assertIsNone(phases["intake"]["seconds"])

    def test_a_dispatch_whose_spawn_failed_is_reported_as_a_spawn_error(self):
        folded = _folded()
        folded["dispatches"]["D4"] = {"role": "impl", "entity": f"{PLAN}-T03",
                                      "at": "2026-01-01T00:04:00Z", "spawn_error": True}
        outcomes = {d["id"]: d["outcome"] for d in _model(folded=folded)["dispatches"]}
        self.assertEqual(outcomes["D4"], "spawn_error")

    def test_a_full_task_id_in_depends_on_resolves_directly(self):
        folded = _folded()
        folded["tasks"][f"{PLAN}-T03"]["depends_on"] = [f"{PLAN}-T01"]
        tasks = {t["short"]: t for t in _model(folded=folded)["tasks"]}
        self.assertEqual(tasks["T03"]["depends_on"], [f"{PLAN}-T01"])

    def test_a_reference_to_a_task_that_does_not_exist_is_never_guessed(self):
        tasks = {t["short"]: t for t in _model()["tasks"]}
        self.assertNotIn("T99", str(tasks["T03"]["depends_on"]))
        self.assertEqual(tasks["T03"]["unresolved"], ["T99"])

    def test_a_phase_entered_twice_keeps_its_first_timestamp(self):
        events = [_event(1, "2026-01-01T00:00:00Z", "phase_entered", {"phase": "intake"}),
                  _event(2, "2026-01-01T00:03:00Z", "phase_entered", {"phase": "intake"})]
        phases = {p["name"]: p for p in _model(events=events)["phases"]}
        self.assertEqual(phases["intake"]["entered"], "2026-01-01T00:00:00Z")

    def test_a_ruling_already_answered_raises_no_attention(self):
        folded = _folded()
        folded["needs_ruling"] = [{"task": f"{PLAN}-T02", "concern": "retry policy", "ruled": True}]
        kinds = {a["kind"] for a in _model(folded=folded)["attention"]}
        self.assertNotIn("ruling", kinds)


if __name__ == "__main__":
    unittest.main()
