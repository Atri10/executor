# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Autonomy: a phase gate clears without a human only when the per-phase policy
permits it. The policy fails closed: a missing or malformed file, an unlisted
phase or a misspelled mode all mean deny. Pick-class phases (design and
specification, where a human chooses between options) and handoff (the human's
sign-off on the finished run) never clear unattended. An automatic pass is
journaled as automatic, so it can never be mistaken for a human decision."""
from __future__ import annotations

import unittest

from _live import Live
from executor.engine import NEVER_AUTO, PICK_PHASES, fold, ingest
from executor.paths import autonomy_file
from executor.store import PHASES, read_json, write_json

# Phases whose structural gate the engine can verify without a human. Every phase
# outside NEVER_AUTO qualifies; the test derives them from the same set so a
# change shows up here, not silently.
STRUCTURAL = tuple(p for p in PHASES if p not in NEVER_AUTO)


class AutonomyCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def set_policy(self, **modes: object) -> None:
        current = read_json(autonomy_file(self.init.idir)) or {}
        write_json(autonomy_file(self.init.idir), {**current, **modes})
    def phase_decisions(self, phase: str) -> list[dict]:
        """The gate decisions recorded for one phase, in journal order."""
        return [e for e in self.gate_decisions() if e["data"]["phase"] == phase]
    def run_to_gate(self, phase: str) -> dict:
        """Drive the real pump until `phase` is awaiting its gate, or until the run
        cannot get there without a human."""
        return self.live.run(lambda a: a["action"] == "GATE" and a.get("phase") == phase)

    def gate_decisions(self) -> list[dict]:
        return [e for e in self.live.events() if e["kind"] == "gate_decision"]


class FailClosed(AutonomyCase):
    def test_a_missing_policy_file_means_every_gate_waits_for_a_human(self):
        autonomy_file(self.init.idir).unlink()
        self.run_to_gate("intake")
        self.assertEqual(self.live.act()["action"], "GATE")
        self.assertEqual(self.gate_decisions(), [])

    def test_a_misspelled_mode_means_deny(self):
        self.set_policy(intake="alow")
        self.run_to_gate("intake")
        self.assertEqual(self.live.act()["action"], "GATE")
        self.assertEqual(self.gate_decisions(), [])

    def test_an_unlisted_phase_is_denied_even_when_the_file_is_otherwise_permissive(self):
        policy = {p: "gate" for p in STRUCTURAL}
        policy.pop("intake")
        autonomy_file(self.init.idir).write_text("{}", encoding="utf-8")
        write_json(autonomy_file(self.init.idir), policy)
        self.run_to_gate("intake")
        self.assertEqual(self.live.act()["action"], "GATE")


class Deny(AutonomyCase):
    def test_deny_never_clears_the_gate_unattended(self):
        self.set_policy(intake="deny")
        self.run_to_gate("intake")
        self.assertEqual(self.live.act()["action"], "GATE")
        self.assertEqual(self.gate_decisions(), [])


class GateAndAllow(AutonomyCase):
    def test_gate_clears_a_structural_phase_and_journals_it_as_automatic(self):
        self.set_policy(intake="gate")
        self.run_to_gate("intake")
        self.assertEqual(self.phase_decisions("intake")[0]["data"]["by"], "auto")
        self.assertEqual(self.phase_decisions("intake")[0]["data"]["decision"], "approved")
        self.assertEqual(fold(self.live.events())["phase_state"]["intake"], "passed")

    def test_allow_clears_a_structural_phase_the_same_way(self):
        self.set_policy(intake="allow")
        self.run_to_gate("intake")
        self.assertEqual(self.phase_decisions("intake")[0]["data"]["by"], "auto")

    def test_a_pick_class_phase_is_never_cleared_by_the_engine(self):
        """Under allow, a structural phase may clear automatically; a pick-class phase
        may not. Every pick-class gate that is decided must be decided by a human:
        the journaled decision for it carries by == 'human', never 'auto'."""
        self.assertEqual(set(PICK_PHASES), {"design", "specification"})
        for phase in PICK_PHASES:
            with self.subTest(phase=phase):
                self.set_policy(**{phase: "allow"})
                self.live.run(lambda a: a["action"] == "DONE")
                decided = [d["data"] for d in self.gate_decisions()
                           if d["data"]["phase"] == phase]
                self.assertTrue(decided, f"{phase} should have reached its gate")
                self.assertEqual({d["by"] for d in decided}, {"human"})

    def test_an_automatic_pass_never_clears_a_halted_run(self):
        self.set_policy(intake="gate")
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        ingest(self.init, {"kind": "halt", "v": "v1", "reason": "client stop"},
               actor="human")
        self.assertEqual(self.live.act()["action"], "HALT")
        self.assertEqual(self.gate_decisions(), [])

    def test_handoff_is_never_cleared_by_the_engine(self):
        """The final gate is the human's sign-off on the run: even under allow,
        handoff waits for a decision, and none is journaled automatically."""
        self.assertIn("handoff", NEVER_AUTO)
        self.set_policy(handoff="allow")
        act = self.run_to_gate("handoff")
        self.assertEqual((act["action"], act["phase"]), ("GATE", "handoff"))
        self.assertEqual(self.phase_decisions("handoff"), [])

    def test_a_resumed_run_still_clears_its_automatic_gates(self):
        """Resume clears the halt latch only: the journaled policy still decides
        every gate afterward, so an automatic gate keeps passing unattended."""
        self.set_policy(intake="gate")
        ingest(self.init, {"kind": "halt", "v": "v1", "reason": "client stop"},
               actor="human")
        self.assertEqual(self.live.act()["action"], "HALT")
        ingest(self.init, {"kind": "resume", "v": "v1", "reason": "client ok"},
               actor="human")
        act = self.run_to_gate("discovery")
        self.assertEqual((act["action"], act["phase"]), ("GATE", "discovery"))
        self.assertEqual(self.phase_decisions("intake")[0]["data"]["by"], "auto")


class PolicyShape(AutonomyCase):
    def test_a_fresh_initiative_denies_every_phase(self):
        policy = read_json(autonomy_file(self.init.idir))
        self.assertEqual(sorted(policy), sorted(PHASES))
        self.assertEqual(set(policy.values()), {"deny"})


if __name__ == "__main__":
    unittest.main()
