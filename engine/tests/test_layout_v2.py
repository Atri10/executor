# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The v2 store layout: a plan index with a file per task, a view tree with one
leaf per entity, a committed index written mid-run, and a migration that is
deterministic and byte-idempotent (audit D03, D04, D08, D11, D12, D16)."""
import hashlib
import unittest
from pathlib import Path

import _payloads as PL
from _live import Live
from executor import migrate as M
from executor import views as V
from executor.engine import check, emit_next, fold, ingest
from executor.paths import (docs_index_file, docs_plan_file, docs_plan_md,
                            docs_task_md, plan_file, prompt_file,
                            task_spec_file, view_file, view_plan_file,
                            view_task_file)
from executor.store import read_json, write_json


def digests(root: Path) -> dict[str, str]:
    return {f.relative_to(root).as_posix(): hashlib.sha256(f.read_bytes())
            .hexdigest() for f in sorted(root.rglob("*")) if f.is_file()}


class Excel(Live):
    """A run driven to its second implementation dispatch: one plan authored,
    one task started."""

    def __init__(self) -> None:
        super().__init__()
        self.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")


class PlanProjections(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Excel()
        self.addCleanup(self.live.close)
        self.init = self.live.init
        self.plan = "INIT-0001-P01"

    def test_the_plan_index_carries_no_task_bodies(self):
        idx = read_json(plan_file(self.init.idir, self.plan))
        self.assertEqual(sorted(idx["tasks"][0]), ["depends_on", "id", "title"])
        self.assertNotIn("goal", idx["tasks"][0])
        self.assertEqual(idx["tasks"][0]["id"], "T01")

    def test_every_task_has_its_own_contract_before_it_runs(self):
        spec = read_json(task_spec_file(self.init.idir,
                                        f"{self.plan}-T01"))
        self.assertEqual(spec["id"], f"{self.plan}-T01")
        self.assertEqual(spec["plan"], self.plan)
        self.assertEqual(spec["files"], ["a.py"])
        for key in ("goal", "accepts", "depends_on", "provides", "consumes",
                    "requirements", "constraints"):
            self.assertIn(key, spec)

    def test_the_committed_store_has_the_same_breakdown(self):
        self.assertEqual(read_json(docs_plan_file(self.live.root, "INIT-0001",
                                                  self.plan)),
                         read_json(plan_file(self.init.idir, self.plan)))
        text = docs_plan_md(self.live.root, "INIT-0001", self.plan).read_text(
            encoding="utf-8")
        self.assertIn("## Tasks", text)
        task_md = docs_task_md(self.live.root, "INIT-0001",
                               f"{self.plan}-T01").read_text(encoding="utf-8")
        self.assertIn("**accepts:**", task_md)


class ViewTree(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Excel()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def test_the_root_index_names_every_leaf(self):
        text = view_file(self.init.idir, "index.md").read_text(encoding="utf-8")
        self.assertIn("[progress](progress.md)", text)
        self.assertIn("plans/INIT-0001-P01/plan.md", text)
        self.assertIn("tasks/INIT-0001-P01-T01/task.md", text)
        self.assertIn("dispatch ids are journal sequence numbers", text)

    def test_a_task_has_one_leaf_however_many_rounds_it_has(self):
        for rnd in (1, 2, 3):
            act = self.live.run(lambda a: a["action"] == "DISPATCH"
                                and a["role"] == "review")
            ingest(self.init, PL.verdict(
                task=act["entity"], rnd=act["context"]["round"],
                base=act["context"]["base"], head=act["context"]["head"],
                reviewed_package_sha=act["context"]["package_sha"],
                spec="FAIL", findings=[PL.finding(f"F{rnd}")]))
            self.live.run(lambda a: a["action"] == "DISPATCH"
                          and a["role"] in ("impl", "fix"))
        text = view_task_file(self.init.idir,
                              "INIT-0001-P01-T01").read_text(encoding="utf-8")
        self.assertIn("### R01 findings", text)
        self.assertIn("### R02 findings", text)
        leaves = [p for p in (self.init.idir / "views").rglob("*")
                  if p.is_file() and "R0" in p.name and p.suffix == ".md"]
        self.assertEqual(leaves, [])          # no flat per-round file survives

    def test_a_plan_view_carries_its_tasks(self):
        text = view_plan_file(self.init.idir,
                              "INIT-0001-P01").read_text(encoding="utf-8")
        self.assertIn("| INIT-0001-P01-T01 |", text)

    def test_an_abandoned_dispatch_is_not_reported_as_answered(self):
        act = self.live.run(lambda a: a["action"] == "DISPATCH")
        s = fold(self.init.events)
        s["dispatches"][act["dispatch_id"]]["abandoned"] = "no heartbeat"
        text = V.dispatches_md(self.init, s, "stamp")
        row = [ln for ln in text.splitlines() if act["dispatch_id"] in ln][0]
        self.assertIn("abandoned", row)

    def test_progress_renders_the_rulings_in_order(self):
        ingest(self.init, PL.ruling("first", for_task="INIT-0001-P01-T01"),
               actor="human")
        ingest(self.init, PL.ruling("second", for_task="INIT-0001-P01-T01"),
               actor="human")
        text = view_file(self.init.idir, "progress.md").read_text(encoding="utf-8")
        self.assertIn("## Rulings", text)
        self.assertLess(text.index("first"), text.index("second"))

    def test_the_status_card_shows_the_policy_and_its_source(self):
        write_json(self.init.root / "docs" / "executor" / "INIT-0001" / "meta"
                   / "policy.json", {"v": "v1", "max_fix_rounds": 7})
        emit_next(self.init)          # the policy is folded on the next poll
        card = V.status_card(self.init, fold(self.init.events))
        self.assertIn("policy: audit<=", card)
        self.assertIn("fix<=7", card)


class Reproducible(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Excel()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def test_two_renders_of_one_journal_are_byte_identical(self):
        """A projection is a function of the journal, not of the clock: this is
        what makes the drift check and an idempotent migration possible."""
        self.assertEqual(V.render_plan(self.init), V.render_plan(self.init))

    def test_the_committed_index_matches_a_fresh_render(self):
        s = fold(self.init.events)
        self.assertEqual(read_json(docs_index_file(self.live.root, "INIT-0001")),
                         V.render_handoff_index("INIT-0001", s))

    def test_a_tampered_committed_index_is_reported(self):
        path = docs_index_file(self.live.root, "INIT-0001")
        bad = read_json(path)
        bad["phase"] = "COMPLETELY-WRONG"
        write_json(path, bad)
        problems = check(self.init)["problems"]
        self.assertTrue(any("committed index stale" in p and "index.json" in p
                            for p in problems), problems)

    def test_a_missing_canonical_file_is_reported(self):
        prompt_file(self.init.idir,
                    self.live.run(lambda a: a["action"] == "DISPATCH")
                    ["dispatch_id"]).unlink()
        problems = check(self.init)["problems"]
        self.assertTrue(any("missing canonical file" in p and "prompt.md" in p
                            for p in problems), problems)

    def test_a_missing_task_contract_is_reported(self):
        task_spec_file(self.init.idir, "INIT-0001-P01-T01").unlink()
        problems = check(self.init)["problems"]
        self.assertTrue(any("task.json" in p for p in problems), problems)


class Components(unittest.TestCase):
    """An artifact kind is not capped at one instance (audit D05)."""

    def test_one_design_artifact_per_declared_component(self):
        live = Live()
        self.addCleanup(live.close)

        class Arch(Live):
            def answer(self, act):
                if act["role"] in ("author", "repair") and act["schema"] == "arch":
                    return PL.art("arch", components=[
                        {"id": "CMP-01", "title": "chassis"},
                        {"id": "CMP-02", "title": "gateway"}])
                if act["role"] in ("author", "repair") and act["schema"] == "design":
                    return PL.art("design", id=act["entity"],
                                  component=act["context"]["component"])
                return Live.answer(self, act)

        run = Arch()
        self.addCleanup(run.close)
        act = run.run(lambda a: a["action"] == "DISPATCH"
                      and a["role"] == "author" and a["schema"] == "design"
                      and a["entity"].endswith("DSGN-02"))
        self.assertEqual(act["context"]["component"], "CMP-02")
        ingest(run.init, run.answer(act))
        s = fold(run.init.events)
        designs = {a: v.get("component") for a, v in s["artifacts"].items()
                   if v["kind"] == "design"}
        self.assertEqual(sorted(designs), ["INIT-0001-DSGN-01",
                                           "INIT-0001-DSGN-02"])
        self.assertEqual(sorted(designs.values()), ["CMP-01", "CMP-02"])


class Migration(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Excel()
        self.addCleanup(self.live.close)
        self.init = self.live.init
        # a v1-shaped tree: no per-task projections, a flat per-round view,
        # and a store stamp the engine refuses to write into
        for f in self.init.idir.glob("plans/*/tasks/*/task.json"):
            f.unlink()
        for f in self.live.root.glob("docs/executor/INIT-0001/plans/*/tasks/*/task.md"):
            f.unlink()
        write_json(self.init.idir / "meta" / "meta.json",
                   {"engine_version": "2.1.0", "schema_version": "v1",
                    "store_version": "v1"})

    def test_a_v1_tree_is_refused_by_the_writer_and_readable_by_migrate(self):
        from executor.store import check_store_version
        with self.assertRaises(Exception) as err:
            check_store_version(self.init.idir)
        self.assertEqual(getattr(err.exception, "code", ""), "store_outdated")
        # migrate opens it ungated: a skewed store is what it must explain
        self.assertIn("writes", M.migrate_layout(self.init, dry_run=True))

    def test_dry_run_touches_nothing(self):
        before = digests(self.live.root)
        res = M.migrate_layout(self.init, dry_run=True)
        self.assertEqual(before, digests(self.live.root))
        self.assertFalse(res["already_current"])
        self.assertTrue(any(p.endswith("task.json") for p in res["writes"]))

    def test_a_change_request_is_part_of_the_migration(self):
        live = Excel()
        self.addCleanup(live.close)
        ingest(live.init, {"kind": "change_request", "v": "v1", "title": "t",
                           "requested_by": "o", "why": "w", "change": {}},
               actor="human")
        work = M.plan(live.init)
        self.assertTrue(any(p.name == "change.json" for p in work["writes"]))

    def test_apply_writes_verifies_and_is_byte_idempotent(self):
        first = M.migrate_layout(self.init, dry_run=False)
        self.assertTrue(first["verified"], first["problems"])
        after_one = digests(self.live.root)
        second = M.migrate_layout(self.init, dry_run=False)
        self.assertTrue(second["already_current"])
        self.assertEqual(after_one, digests(self.live.root),
                         "a second apply must write identical bytes")
        self.assertEqual(check(self.init)["problems"], [])


if __name__ == "__main__":
    unittest.main()
