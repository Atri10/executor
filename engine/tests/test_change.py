# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The mid-run change protocol: a journaled change request, a blast radius
computed from the fold, and a regression lane that re-dispatches the work it
affects (audit D06)."""
import unittest

import _payloads as PL
from _live import Live
from executor.engine import fold, ingest
from executor.store import Rejection


class Bound(Live):
    """A run whose spec binds C1 and whose plan says so: the structured link the
    radius reads. `Live`'s generic artifacts carry no ids, which is the coarse
    case."""

    def answer(self, act: dict) -> dict:
        role, schema = act["role"], act["schema"]
        if role in ("author", "repair") and schema == "spec":
            return PL.art("spec",
                          requirements=[{"id": "R1", "requirement": "r",
                                         "observable": "o"}],
                          constraints=[{"id": "C1", "constraint": "c",
                                        "observable": "o"}])
        if role in ("author", "repair") and schema == "vrfy":
            # V1 cites the constraint that changed, so the radius reaches it
            return PL.art("vrfy", criteria=[{"id": "V1", "criterion": "works",
                                            "procedure": "run it",
                                            "cites": ["C1"]}])
        if role in ("author", "repair") and schema == "plan":
            return PL.plan_payload(pid=act["entity"], tasks=[
                PL.task_row("T01", constraints=["C1"], requirements=["R1"])])
        return super().answer(act)


def to_impl(live: Live) -> dict:
    """Drive to the first implementation dispatch: the run is in `execution`."""
    return live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")


class Scoping(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Bound()
        self.addCleanup(self.live.close)
        self.init = self.live.init
        to_impl(self.live)

    def file_change(self, **change) -> dict:
        payload = {"kind": "change_request", "v": "v1",
                   "title": "C1 tightened", "requested_by": "owner",
                   "why": "the bootstrap proved the old wording unsafe",
                   "change": change or {"constraints": ["C1"]}}
        return ingest(self.init, payload, actor="human")

    def test_the_request_is_journaled_with_a_minted_id(self):
        ev = self.file_change()
        self.assertEqual(ev["kind"], "change_request")
        self.assertEqual(ev["entity"], "CR-0001")
        self.assertEqual(fold(self.init.events)["changes"]["CR-0001"]["state"],
                         "requested")

    def test_the_radius_is_computed_from_the_task_links(self):
        self.file_change()
        act = self.live.act()
        self.assertEqual(act["action"], "CHANGE-SCOPE")
        radius = act["radius"]
        self.assertFalse(radius["coarse"])
        self.assertEqual(radius["tasks"], ["INIT-0001-P01-T01"])
        self.assertEqual(radius["reasons"]["tasks"]["INIT-0001-P01-T01"], "binds")
        self.assertIn("INIT-0001-SPEC-01", radius["artifacts"])
        self.assertEqual(radius["reasons"]["artifacts"]
                         ["INIT-0001-SPEC-01"], "owns")

    def test_polling_twice_returns_the_same_step_and_writes_nothing(self):
        """The lane journals the scope once; after that a repeated poll returns
        the same dispatch and writes nothing (the request is idempotent)."""
        self.file_change()
        self.assertEqual(self.live.act()["action"], "CHANGE-SCOPE")
        first = self.live.act()
        n = len(self.init.events)
        second = self.live.act()
        self.assertEqual(first, second)
        self.assertEqual(n, len(self.init.events))

    def test_the_lane_runs_to_a_close(self):
        self.file_change()
        self.live.run(lambda a: a["action"] == "CHANGE-DONE")
        s = fold(self.init.events)
        self.assertEqual(s["changes"]["CR-0001"]["state"], "applied")
        self.assertEqual(s["changes"]["CR-0001"]["reason"], "absorbed")
        # the spec was revised and re-audited, the task redone, the criterion
        # re-proven: all three are visible in the fold
        self.assertGreaterEqual(s["artifacts"]["INIT-0001-SPEC-01"]["round"], 2)
        self.assertEqual(s["tasks"]["INIT-0001-P01-T01"]["state"], "complete")
        self.assertEqual(s["evidence"]["V1"][-1]["verdict"], "proven")

    def test_an_unknown_seed_id_is_refused(self):
        with self.assertRaises(Rejection) as err:
            self.file_change(constraints=["C99"])
        self.assertEqual(err.exception.code, "dangling_ref")

    def test_a_worker_cannot_file_a_change(self):
        with self.assertRaises(Rejection) as err:
            ingest(self.init, {"kind": "change_request", "v": "v1",
                               "title": "t", "requested_by": "w", "why": "w",
                               "change": {"constraints": ["C1"]}})
        self.assertEqual(err.exception.code, "unauthorized")

    def test_a_ruling_naming_the_change_withdraws_it(self):
        self.file_change()
        self.live.act()                       # scope it
        ingest(self.init, PL.ruling("stop this change", for_task="CR-0001"),
               actor="human")
        self.assertEqual(fold(self.init.events)["changes"]["CR-0001"]["state"],
                         "withdrawn")
        # the lane is empty: the next action is ordinary execution work
        act = self.live.act()
        self.assertNotEqual(act["action"], "CHANGE-SCOPE")



class Citing(Live):
    """A plan that cites the spec, the shape the corpus actually has."""

    def answer(self, act: dict) -> dict:
        if act["role"] in ("author", "repair") and act["schema"] == "plan":
            return PL.plan_payload(pid=act["entity"],
                                   cites=["INIT-0001-SPEC-01"])
        return super().answer(act)


class Chained(Bound):
    """Two tasks, the second depending on the first."""

    def answer(self, act: dict) -> dict:
        if act["role"] in ("author", "repair") and act["schema"] == "plan":
            return PL.plan_payload(pid=act["entity"], tasks=[
                PL.task_row("T01", id="T01", constraints=["C1"]),
                PL.task_row("T02", id="T02", depends_on=["T01"])])
        return Bound.answer(self, act)


class BlockedByADependency(unittest.TestCase):
    def test_a_task_whose_dependency_is_open_is_not_redispatched(self):
        live = Chained()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        # name only T02: its dependency T01 is in flight, so the lane must not
        # dispatch T02 out of order
        ingest(live.init, {"kind": "change_request", "v": "v1", "title": "t",
                           "requested_by": "o", "why": "w",
                           "change": {"tasks": ["INIT-0001-P01-T02"]}},
               actor="human")
        live.act()                                  # CHANGE-SCOPE
        act = live.act()
        self.assertEqual(act["entity"], "INIT-0001-P01-T01")
        self.assertEqual(fold(live.init.events)["tasks"]
                         ["INIT-0001-P01-T02"]["state"], "pending")


class Rework(unittest.TestCase):
    def test_a_completed_task_is_redone_when_the_contract_changes(self):
        """Step 4 of the lane: a task that finished before the change has an
        old report, so it is dispatched again with the change in context."""
        live = Bound()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "MERGE")      # T01 complete
        self.assertEqual(fold(live.init.events)["tasks"]
                         ["INIT-0001-P01-T01"]["state"], "complete")
        ingest(live.init, {"kind": "change_request", "v": "v1", "title": "t",
                           "requested_by": "o", "why": "w",
                           "change": {"constraints": ["C1"]}}, actor="human")
        live.run(lambda a: a["action"] == "CHANGE-DONE")
        act = [e for e in live.init.events
               if e["kind"] == "task_dispatched"
               and e["data"].get("context", {}).get("change") == "CR-0001"]
        self.assertTrue(act, "the rework was dispatched with the change")
        self.assertEqual(fold(live.init.events)["changes"]["CR-0001"]["state"],
                         "applied")


class Coarse(unittest.TestCase):
    def test_a_plan_without_task_links_is_reported_coarse(self):
        live = Citing()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        ingest(live.init, {"kind": "change_request", "v": "v1",
                           "title": "t", "requested_by": "o", "why": "w",
                           "change": {"artifacts": ["INIT-0001-SPEC-01"]}},
               actor="human")
        act = live.act()
        self.assertEqual(act["action"], "CHANGE-SCOPE")
        self.assertTrue(act["radius"]["coarse"])
        self.assertEqual(act["radius"]["reasons"]["tasks"]
                         ["INIT-0001-P01-T01"], "plan")


class NoImpact(unittest.TestCase):
    def test_a_change_that_names_nothing_closes_without_a_dispatch(self):
        """An empty request is legal and honest: it scopes to nothing and says
        so, instead of dispatching work nobody asked for."""
        live = Live()
        self.addCleanup(live.close)
        live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")
        ingest(live.init, {"kind": "change_request", "v": "v1",
                           "title": "t", "requested_by": "o", "why": "w",
                           "change": {}},
               actor="human")
        self.assertEqual(live.act()["action"], "CHANGE-SCOPE")
        act = live.run(lambda a: a["action"] == "CHANGE-DONE")
        self.assertEqual(act["reason"], "no_impact")
        self.assertEqual(fold(live.init.events)["changes"]["CR-0001"]["state"],
                         "applied")


if __name__ == "__main__":
    unittest.main()


class AtGate(unittest.TestCase):
    def test_a_change_waits_for_a_pending_gate(self):
        """A gate is about to pass; re-running work under it would invalidate
        the decision. The lane starts once the gate is decided."""
        live = Live()
        self.addCleanup(live.close)
        act = live.run(lambda a: a["action"] == "GATE")
        ingest(live.init, {"kind": "change_request", "v": "v1", "title": "t",
                           "requested_by": "o", "why": "w", "change": {}},
               actor="human")
        self.assertEqual(live.act()["action"], "GATE")
        ingest(live.init, PL.gate(phase=act["phase"]), actor="human")
        self.assertEqual(live.act()["action"], "CHANGE-SCOPE")
