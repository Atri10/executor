# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The branches the larger suites do not reach: helper failure paths, the
change lane's edge cases, the CLI verbs added for changes and migration, and
the two repository scripts (which the coverage floor measures like the rest)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _payloads as PL
from _live import Live
from executor import engine as E
from executor import migrate as M
from executor import store as S
from executor import views as V
from executor.engine import fold, ingest
from executor.paths import docs_init_dir, run_root
from executor.store import ExecError, Rejection, write_json

REPO = Path(__file__).resolve().parents[2]


def ev(kind: str, entity: str = "INIT-0001", data: dict | None = None,
       seq: int = 1) -> dict:
    return {"kind": kind, "entity": entity, "data": data or {}, "seq": seq,
            "ts": "2026-01-01T00:00:00Z", "actor": "engine"}


class Helpers(unittest.TestCase):
    def test_git_helpers_fail_closed_outside_a_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(E._branches_containing(root, "abc"), set())
            self.assertEqual(E._commit_subjects(root, "a", "b"), [])
            self.assertEqual(E._branch(root), "")

    def test_a_change_id_is_the_first_free_number(self):
        self.assertEqual(E._next_change_id({"changes": {}}), "CR-0001")
        self.assertEqual(E._next_change_id(
            {"changes": {"CR-0001": {}, "CR-0003": {}}}), "CR-0002")

    def test_the_next_artifact_instance_skips_taken_and_odd_tails(self):
        s = {"artifacts": {"INIT-0001-DSGN-01": {}, "INIT-0001-DSGN-xx": {}}}
        init = type("I", (), {"id": "INIT-0001"})()
        self.assertEqual(E._next_artifact_id(init, s, "design"),
                         "INIT-0001-DSGN-02")

    def test_the_initiative_id_space_is_refused_not_widened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (run_root(root) / "INIT-9999").mkdir(parents=True)
            with self.assertRaises(ExecError) as err:
                E._next_init_id(root)
            self.assertEqual(err.exception.code, "id_exhausted")

    def test_a_layout_version_is_parsed_or_zero(self):
        self.assertEqual(S.layout_major("v2"), 2)
        self.assertEqual(S.layout_major("garbage"), 0)

    def test_an_event_for_an_unknown_change_is_ignored(self):
        s = fold([ev("change_scoped", "CR-0009",
                     {"id": "CR-0009", "radius": {}, "baselines": {}}),
                  ev("change_applied", "CR-0009", {"id": "CR-0009"})])
        self.assertEqual(s["changes"], {})

    def test_a_change_note_and_the_gates_reach_the_render(self):
        text = E._render_change({"id": "CR-0001", "title": "t", "state": "scoped",
                                 "requested_by": "o", "why": "w",
                                 "note": "read this first", "change": {},
                                 "radius": None, "reason": ""})
        self.assertIn("read this first", text)
        plan = PL.plan_payload(tasks=[PL.task_row("T01", provides=["p"],
                                                  consumes=["c"])],
                               gates=["intake approved"])
        self.assertIn("## Gates", E._render_plan_index(plan))
        spec = E._render_task_spec("INIT-0001-P01-T01", plan["tasks"][0])
        self.assertIn("**provides:** p", spec)
        self.assertIn("**consumes:** c", spec)


class Radius(unittest.TestCase):
    def state(self) -> dict:
        return {
            "artifacts": {"INIT-0001-SPEC-01": {"kind": "spec",
                                                "ids": ["C1"], "cites": []},
                          "INIT-0001-P01": {"kind": "plan",
                                            "cites": ["INIT-0001-SPEC-01"],
                                            "ids": []}},
            "edges": [],
            "plan_order": ["INIT-0001-P01"],
            "tasks": {
                "INIT-0001-P01-T01": {"plan": "INIT-0001-P01",
                                      "depends_on": [],
                                      "requirements": [], "constraints": ["C1"]},
                "INIT-0001-P01-T02": {"plan": "INIT-0001-P01",
                                      "depends_on": ["T01"],
                                      "requirements": [], "constraints": []},
                "INIT-0001-P01-T03": {"plan": "INIT-0001-P01",
                                      "depends_on": ["T02"],
                                      "requirements": [], "constraints": []}},
        }

    def test_a_binding_task_pulls_its_dependents_transitively(self):
        radius = E._blast_radius(self.state(), {"constraints": ["C1"]})
        self.assertFalse(radius["coarse"])
        self.assertEqual(radius["reasons"]["tasks"]["INIT-0001-P01-T01"], "binds")
        self.assertEqual(radius["reasons"]["tasks"]["INIT-0001-P01-T02"],
                         "depends")
        self.assertEqual(radius["reasons"]["tasks"]["INIT-0001-P01-T03"],
                         "depends")

    def test_a_named_task_that_left_the_fold_is_ignored(self):
        radius = E._blast_radius(self.state(),
                                 {"tasks": ["INIT-0001-P01-T02",
                                            "INIT-0001-P01-T99"]})
        self.assertIn("INIT-0001-P01-T02", radius["tasks"])
        self.assertNotIn("INIT-0001-P01-T99", radius["tasks"])

    def test_named_tasks_are_added_one_by_one(self):
        radius = E._blast_radius(self.state(),
                                 {"tasks": ["INIT-0001-P01-T02",
                                            "INIT-0001-P01-T03"]})
        self.assertEqual(radius["reasons"]["tasks"]["INIT-0001-P01-T02"],
                         "named")
        self.assertEqual(radius["reasons"]["tasks"]["INIT-0001-P01-T03"],
                         "named")

    def test_a_dependency_that_is_not_complete_blocks_a_task(self):
        s = self.state()
        s["tasks"]["INIT-0001-P01-T01"]["state"] = "pending"
        self.assertFalse(E._ready(s, s["tasks"]["INIT-0001-P01-T02"]))
        s["tasks"]["INIT-0001-P01-T01"]["state"] = "complete"
        self.assertTrue(E._ready(s, s["tasks"]["INIT-0001-P01-T02"]))

    def test_a_task_that_left_the_fold_does_not_block_a_close(self):
        change = {"id": "CR-0001", "state": "scoped", "seq": 5, "title": "t",
                  "note": "", "change": {},
                  "radius": {"artifacts": [], "plans": [], "tasks": ["GONE"],
                             "criteria": [], "docs": [], "coarse": False,
                             "reasons": {}},
                  "baselines": {"artifact_round": {}, "critique_round": {},
                                "task_report": {}, "criteria": {}}}
        s = {"changes": {"CR-0001": change}, "tasks": {}, "artifacts": {},
             "evidence": {}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(E, "_record"):
            act = E._change_advance(
                type("I", (), {"id": "INIT-0001", "root": Path(tmp),
                               "idir": Path(tmp) / "i"})(), s, change, 0.0)
        # no task to redo, no criterion to prove: the lane closes
        self.assertIsNotNone(act)
        self.assertEqual(act["action"], "CHANGE-DONE")

    def test_a_criterion_without_evidence_holds_the_lane_open(self):
        change = {"id": "CR-0001", "state": "scoped", "seq": 5, "title": "t",
                  "note": "", "change": {},
                  "radius": {"artifacts": [], "plans": [], "tasks": [],
                             "criteria": ["V1"], "docs": [], "coarse": False,
                             "reasons": {}},
                  "baselines": {"artifact_round": {}, "critique_round": {},
                                "task_report": {}, "criteria": {"V1": 0}}}
        with tempfile.TemporaryDirectory() as tmp:
            s = {"changes": {}, "tasks": {}, "artifacts": {}, "evidence": {},
                 "dispatches": {}, "answered": {}, "entities": {}, "edges": [],
                 "changes": {}, "lost": {}, "plan_order": [], "plans": {},
                 "policy": {"values": {"spawn_retry_cap": 2,
                                       "max_evidence_tries": 3}}}
            with mock.patch.object(E, "_record"):
                # no evidence yet: the lane dispatches a re-proof, never closes
                act = E._change_advance(
                    type("I", (), {"id": "INIT-0001", "root": Path(tmp),
                                   "idir": Path(tmp) / "i",
                                   "events": []})(), s, change, 0.0)
        self.assertIsNotNone(act)
        self.assertEqual(act["role"], "evidence")


class Checks(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def test_a_charter_may_cite_another_initiative_but_a_spec_may_not(self):
        s = fold(self.init.events)
        E._check_artifact(s, {"kind": "charter", "id": "INIT-0001-CHTR-01",
                              "cites": ["INIT-0009-CHTR-01"]})
        with self.assertRaises(Rejection) as err:
            E._check_artifact(s, {"kind": "spec", "id": "INIT-0001-SPEC-01",
                                  "cites": ["INIT-0009-SPEC-01"]})
        self.assertEqual(err.exception.code, "dangling_ref")

    def test_a_plan_task_may_not_bind_an_unknown_id(self):
        s = fold(self.init.events)
        payload = PL.plan_payload(tasks=[PL.task_row("T01",
                                                     constraints=["C99"])])
        with self.assertRaises(Rejection) as err:
            E._check_artifact(s, payload)
        self.assertEqual(err.exception.code, "dangling_ref")

    def test_a_report_with_no_commits_skips_the_git_rules(self):
        act = self.live.run(lambda a: a["action"] == "DISPATCH"
                            and a["role"] == "impl")
        ingest(self.init, PL.report(task=act["entity"], commits=(),
                                    result="BLOCKED",
                                    concerns=["need the chassis contract"]))
        self.assertIn(act["dispatch_id"],
                      fold(self.init.events)["answered"])

    def test_the_git_rules_skip_a_dispatch_without_a_base(self):
        act = self.live.run(lambda a: a["action"] == "DISPATCH"
                            and a["role"] == "impl")
        sha = self.live.land_change(f"task/{act['entity']}")
        sl = {"base": "", "context": {"rules": E.RULES_VERSION,
                                      "base_branch": ""}}
        E._check_git_discipline(self.init, {"task": act["entity"],
                                           "commits": [sha]}, sl)

    def test_a_draft_that_answers_a_missing_change_is_not_checked(self):
        E._check_change_absorbed({"changes": {}}, {"constraints": []},
                                 {"context": {"change": "CR-0009"}})

    def test_a_draft_that_drops_a_changed_id_is_refused(self):
        s = {"changes": {"CR-0001": {"change": {"constraints": ["C1"]}}}}
        with self.assertRaises(Rejection) as err:
            E._check_change_absorbed(s, {"constraints": []},
                                     {"context": {"change": "CR-0001"}})
        self.assertEqual(err.exception.code, "change_not_applied")


class Cards(unittest.TestCase):
    def test_a_long_ruling_is_truncated(self):
        s = fold([ev("ruling", "INIT-0001",
                     {"decision": "x" * 200, "why": "w"})])
        text = V.progress_md(type("I", (), {"id": "INIT-0001", "events": []})(),
                             s, "stamp")
        self.assertIn("…", text)

    def test_a_task_view_survives_a_task_with_no_files_and_no_rounds(self):
        s = fold([])
        s["tasks"] = {"INIT-0001-P01-T01": {"state": "pending", "plan": "INIT-0001-P01",
                                            "title": "t", "round": 0,
                                            "fix_rounds": 0}}
        text = V.task_view_md(type("I", (), {"id": "INIT-0001", "events": []})(),
                              s, "INIT-0001-P01-T01", "stamp")
        self.assertIn("state: **pending**", text)

    def test_a_card_without_a_vrfy_artifact_and_with_an_open_change(self):
        s = fold([ev("change_request", "CR-0001",
                     {"title": "t", "requested_by": "o", "why": "w",
                      "change": {}})])
        card = V.status_card(type("I", (), {"id": "INIT-0001",
                                            "meta": {}})(), s)
        self.assertIn("change: CR-0001 requested", card)
        self.assertNotIn("evidence:", card)

    def test_a_card_shows_only_the_open_changes(self):
        s = fold([ev("change_request", "CR-0001",
                     {"title": "open", "requested_by": "o", "why": "w",
                      "change": {}}),
                  ev("change_request", "CR-0002",
                     {"title": "done", "requested_by": "o", "why": "w",
                      "change": {}}, seq=2),
                  ev("change_applied", "CR-0002", {"id": "CR-0002"}, seq=3)])
        card = V.status_card(type("I", (), {"id": "INIT-0001",
                                            "meta": {}})(), s)
        self.assertIn("change: CR-0001 requested", card)
        self.assertNotIn("CR-0002", card)


class Cli(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")

    def run_cli(self, *args: str) -> tuple[int, str]:
        """Run the CLI in process, in the fixture's repository."""
        import contextlib
        import io
        from executor import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(Path, "cwd",
                                                  return_value=self.live.root))
            stack.enter_context(mock.patch("sys.argv", ["executor", *args]))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            stack.enter_context(mock.patch(
                "sys.stdin", io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8")))
            code = cli.main(["executor", *args])
        return code, out.getvalue() + err.getvalue()

    def write_change(self) -> Path:
        path = Path(self.live.root) / "change.json"
        path.write_text(json.dumps({
            "kind": "change_request", "v": "v1", "title": "t",
            "requested_by": "o", "why": "w",
            "change": {"artifacts": ["INIT-0001-SPEC-01"]}}), encoding="utf-8")
        return path

    def test_change_files_a_request_and_lists_it(self):
        code, out = self.run_cli("change", str(self.write_change()), self.init.id)
        self.assertEqual(code, 0)
        self.assertIn("CR-0001", out)
        code, out = self.run_cli("change", "--list", self.init.id)
        self.assertEqual(code, 0)
        self.assertIn("CR-0001", out)

    def test_change_without_arguments_is_a_usage_error(self):
        code, out = self.run_cli("change")
        self.assertEqual(code, 2)
        self.assertIn("executor change", out)

    def test_migrate_dry_run_and_apply(self):
        code, out = self.run_cli("migrate", self.init.id, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn('"writes"', out)
        code, out = self.run_cli("migrate", self.init.id, "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn('"verified": true', out)


class Scripts(unittest.TestCase):
    """The two repository scripts are measured like the engine: one run each."""

    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "impl")

    def test_the_migration_script_dry_runs_and_applies(self):
        import _scripts
        import contextlib
        import io
        for flag in ("--dry-run", "--apply"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = _scripts.run_as_main("migrate_layout.py",
                                            str(self.live.root), "INIT-0001", flag)
            self.assertEqual(code, 0)
            self.assertIn('"mode"', buf.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(_scripts.run_as_main("migrate_layout.py"), 2)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(_scripts.run_as_main("migrate_layout.py", "-h"), 0)
            self.assertIn("Usage:", buf.getvalue())

    def test_the_migration_script_reports_a_skewed_store(self):
        import _scripts
        import contextlib
        import io
        from executor.paths import meta_file
        # a 1.x store predates the layout field: its shape is unknown
        write_json(meta_file(self.live.init.idir),
                   {"engine_version": "1.0.0", "schema_version": "v1"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _scripts.run_as_main("migrate_layout.py", str(self.live.root),
                                        "INIT-0001", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("store_outdated", buf.getvalue())

    def test_the_measure_script_prints_the_curve(self):
        import _scripts
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _scripts.run_as_main("measure_store.py",
                                        str(run_root(self.live.root) / "INIT-0001"))
        self.assertEqual(code, 0)
        self.assertIn("cumulative state bytes", buf.getvalue())
        self.assertIn("journal bytes", buf.getvalue())

    def test_both_scripts_import_cleanly(self):
        import _scripts
        for name in ("migrate_layout.py", "measure_store.py"):
            self.assertTrue(callable(_scripts.load(name).main))

    def test_a_blank_journal_line_does_not_break_the_measure(self):
        import _scripts
        import contextlib
        import io
        idir = Path(tempfile.mkdtemp())
        (idir / "journal").mkdir(parents=True)
        source = (run_root(self.live.root) / "INIT-0001" / "journal"
                  / "events.v1.jsonl").read_bytes()
        first = source.splitlines()[0]
        (idir / "journal" / "events.v1.jsonl").write_bytes(first + b"\n\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _scripts.run_as_main("measure_store.py", str(idir))
        self.assertEqual(code, 0)
        self.assertIn("journal bytes", buf.getvalue())

    def test_the_measure_script_prints_its_usage(self):
        import _scripts
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(_scripts.run_as_main("measure_store.py", "-h"), 0)
        self.assertIn("Usage:", buf.getvalue())

    def test_the_measure_script_refuses_an_empty_store(self):
        import _scripts
        import contextlib
        import io
        empty = Path(tempfile.mkdtemp())
        (empty / "journal").mkdir(parents=True)
        (empty / "journal" / "events.v1.jsonl").write_text("", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _scripts.run_as_main("measure_store.py", str(empty))
        self.assertEqual(code, 1)
        self.assertIn("no events", buf.getvalue())


class MigrationFailure(unittest.TestCase):
    def test_a_failed_verification_names_the_problem_and_leaves_the_store(self):
        live = Live()
        self.addCleanup(live.close)
        before = {p for p in docs_init_dir(live.root, "INIT-0001").rglob("*")}
        with mock.patch.object(M.E, "_projection_problems",
                               return_value=["committed index stale: x"]):
            with self.assertRaises(ExecError) as err:
                M.migrate_layout(live.init, dry_run=False)
        self.assertEqual(err.exception.code, "migration_failed")
        self.assertIn("committed index stale", str(err.exception))
        after = {p for p in docs_init_dir(live.root, "INIT-0001").rglob("*")}
        self.assertTrue(before <= after)      # nothing deleted on a failure

    def test_a_store_without_a_committed_tree_still_plans_its_writes(self):
        live = Live()
        self.addCleanup(live.close)
        docs = docs_init_dir(live.root, "INIT-0001")
        for f in sorted(docs.rglob("*"), reverse=True):
            f.unlink() if f.is_file() else f.rmdir()
        docs.rmdir()
        work = M.plan(live.init)
        # the docs directory is gone, so nothing under it can be removed and
        # every committed write is still planned
        self.assertFalse(any("docs/" in p.as_posix() for p in work["removes"]))
        self.assertTrue(any(p.name == "index.json" for p in work["writes"]))

    def test_a_stray_projection_is_removed_by_the_apply(self):
        live = Live()
        self.addCleanup(live.close)
        stray = live.init.idir / "views" / "INIT-0001-P01-T01-R01-verdict.md"
        stray.write_text("old layout", encoding="utf-8")
        result = M.migrate_layout(live.init, dry_run=False)
        self.assertIn(".executor/INIT-0001/views/INIT-0001-P01-T01-R01-verdict.md",
                      result["removes"])
        self.assertFalse(stray.exists())


if __name__ == "__main__":
    unittest.main()


class MoreChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.init = self.live.init

    def test_rendering_a_section_covers_bullets_tables_and_code(self):
        payload = PL.art("charter", sections=[
            {"id": "s", "title": "S", "prose": "p", "bullets": ["b"],
             "tables": [{"caption": "c", "columns": ["a", "b"],
                         "rows": [["1", "2"]]}],
             "code": [{"lang": "py", "source": "x = 1"}]}])
        text = E._render_doc(payload)
        self.assertIn("| a | b |", text)
        self.assertIn("```py", text)
        self.assertIn("- b", text)

    def test_a_tampered_committed_markdown_index_is_reported(self):
        from executor.paths import docs_index_md
        path = docs_index_md(self.live.root, "INIT-0001")
        path.write_text("hand edited\n", encoding="utf-8")
        problems = E.check(self.init)["problems"]
        self.assertTrue(any("index.md" in p for p in problems), problems)

    def test_a_policy_that_cannot_be_read_is_reported(self):
        from executor.paths import docs_init_dir
        policy = docs_init_dir(self.live.root, "INIT-0001") / "meta" / "policy.json"
        policy.write_text("{not json", encoding="utf-8")
        problems = E.check(self.init)["problems"]
        self.assertTrue(any("policy" in p for p in problems), problems)


class Prompts(unittest.TestCase):
    """The prompt carries the rules it was minted under, the change it exists to
    absorb, and the component it designs — and stays quiet when it has none."""

    def slot(self, **ctx) -> dict:
        return {"role": "repair", "entity": "INIT-0001-SPEC-01",
                "schema": "spec", "dispatch_id": "D00001",
                "respond_to": "x", "base": "", "context": ctx}

    def test_a_prompt_without_rules_or_change_stays_quiet(self):
        live = Live()
        self.addCleanup(live.close)
        text = E._render_prompt(live.init, fold(live.init.events),
                                self.slot())
        self.assertNotIn("rules:", text)
        self.assertNotIn("## Change", text)

    def test_a_prompt_carries_the_rules_the_change_and_the_component(self):
        live = Live()
        self.addCleanup(live.close)
        text = E._render_prompt(live.init, fold(live.init.events), self.slot(
            rules=E.RULES_VERSION, change="CR-0001", change_summary="tighten C1",
            change_targets={"constraints": ["C1"]}, note="read the RFC",
            component="CMP-01", component_title="chassis"))
        self.assertIn(f"rules: {E.RULES_VERSION}", text)
        self.assertIn("## Change CR-0001", text)
        self.assertIn("read the RFC", text)
        self.assertIn("CMP-01", text)
