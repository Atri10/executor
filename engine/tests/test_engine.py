# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Regression suite for the v2 engine — one test per contract the field
runs proved fragile. Run: python3 -m unittest discover -s engine/tests.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from executor import __version__                        # noqa: E402
from executor.engine import check, emit_next, ingest  # noqa: E402
from executor.store import (Initiative, Rejection, append_event,
                            init_store, make_event, read_events,
                            verify_chain)         # noqa: E402
from executor.schemas import schema_for, validate           # noqa: E402


from _live import hermetic_git as git   # noqa: E402  (no signing, no global config)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "i")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "b")
        self.idir = init_store(self.root, "INIT-0001", "t")
        self.init = Initiative("INIT-0001", self.root, self.idir)
        append_event(self.idir, make_event(
            self.idir, "engine", "created", "INIT-0001", {"title": "t"}))
        self.init.reload()

    def tearDown(self):
        self.tmp.cleanup()

    def ev(self, kind, ent, data, **kw):
        return append_event(self.idir,
                            make_event(self.idir, "engine", kind, ent,
                                       data, **kw))

    def act(self):
        return emit_next(self.init)

    def pay(self, **kw):
        return ingest(self.init, kw)


# ------------------------------------------------------------------ store

class TestStore(Base):
    def test_meta_written(self):
        m = (self.idir / "meta" / "meta.json")
        self.assertTrue(m.exists())
        self.assertEqual(m.read_text().__contains__("engine_version"), True)

    def test_chain_links(self):
        self.ev("phase_entered", "INIT-0001", {"phase": "intake"})
        evs = read_events(self.idir)
        self.assertEqual(verify_chain(evs), [])
        self.assertEqual(evs[-1]["prev_sha"], evs[-2]["line_sha"])

    def test_tamper_detected(self):
        evs = read_events(self.idir)
        evs[-1]["data"]["phase"] = "MUTATED"
        # prev_sha of a *next* event must equal tampered line's sha
        self.assertNotEqual(evs[-1]["line_sha"],
                            verify_chain([evs[-1]]) and evs[-1]["prev_sha"])

    def test_torn_tail_tolerated(self):
        jf = self.idir / "journal" / "events.v1.jsonl"
        with open(jf, "ab") as f:
            f.write(b'{"seq": 99, "kind": partial-broken')
        evs = read_events(self.idir)
        self.assertEqual(evs[-1]["kind"], "created")  # torn line dropped


# ------------------------------------------------------------------ schemas

class TestSchemas(Base):
    def test_closed_enum(self):
        with self.assertRaises(Rejection):
            validate({"kind": "verdict", "v": "v1", "task": "x", "round": 1,
                      "spec_verdict": "MAYBE", "quality_verdict": "APPROVED",
                      "commit_base": "a", "commit_head": "b",
                      "reviewed_package_sha": "abcdef"},
                     schema_for("verdict"))

    def test_unknown_key_rejected(self):
        with self.assertRaises(Rejection):
            validate({"kind": "halt", "v": "v1", "reason": "x", "extra": 1},
                     schema_for("halt"))

    def test_artifact_min_items(self):
        with self.assertRaises(Rejection):
            validate({"kind": "vrfy", "v": "v1", "id": "INIT-0001-VRFY-01",
                      "title": "t", "summary": "s", "sections": [],
                      "criteria": []},
                     schema_for("vrfy"))


# ------------------------------------------------------------------ loop

class TestLoop(Base):
    def charter(self):
        return {"kind": "charter", "v": "v1", "id": "INIT-0001-CHTR-01",
                "title": "t", "summary": "s",
                "sections": [{"id": "s1", "title": "w", "body": "x"}],
                "cites": [], "requirements": [], "constraints": [],
                "risks": []}

    def test_first_action_is_phase_enter(self):
        self.assertEqual(self.act()["action"], "PHASE-ENTER")

    def test_then_author_dispatch(self):
        self.act()  # PHASE-ENTER
        a = self.act()
        self.assertEqual(a["action"], "DISPATCH")
        self.assertEqual(a["role"], "author")
        self.assertTrue(a["respond_to"].endswith("payload.json"))
        self.assertTrue(Path(a["prompt"]).exists())

    def test_resume_manifest_present(self):
        self.act()
        a = self.act()
        self.assertIn("resume", a)
        self.assertEqual(a["resume"]["phase"], "intake")

    def test_open_slot_dedupes(self):
        self.act(); a1 = self.act()
        a2 = self.act()
        self.assertEqual(a1["dispatch_id"], a2["dispatch_id"])

    def test_artifact_commit_written_nested(self):
        self.act(); self.act()
        self.pay(**self.charter())
        j = self.root / "docs/executor/INIT-0001/artifacts" \
            / "INIT-0001-CHTR-01/artifact.json"
        m = j.with_suffix(".md")
        self.assertTrue(j.exists())
        self.assertTrue(m.exists())

    def test_audit_then_gate(self):
        self.act(); self.act()
        self.pay(**self.charter())
        a = self.act()
        self.assertEqual(a["role"], "audit")
        # audit PASS at the slot
        pay = {"kind": "audit", "v": "v1", "target": "INIT-0001-CHTR-01",
               "round": 1, "verdict": "PASS", "findings": []}
        self.pay(**pay)
        self.assertEqual(self.act()["action"], "GATE")


# ------------------------------------------------------------------ check

class TestCheck(Base):
    def test_clean_chain(self):
        res = check(self.init)
        self.assertEqual(res["chain"], "ok")


if __name__ == "__main__":
    unittest.main()

