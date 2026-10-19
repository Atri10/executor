# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The CLI, in process: every command, every exit code, and the authority
boundary that keeps a worker from approving its own gate."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import runpy
from pathlib import Path
from unittest import mock

import _payloads as PL
from _live import Live
from executor import cli
from executor.paths import meta_file
from executor.store import ExecError, Rejection, read_json, write_json


def run(argv: list[str], cwd: Path, stdin: bytes | None = None) -> tuple[int, str, str]:
    """Run the CLI in process inside `cwd`. Returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    stdin_obj = io.TextIOWrapper(io.BytesIO(stdin or b""), encoding="utf-8")
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(Path, "cwd", return_value=cwd))
        stack.enter_context(mock.patch("sys.argv", ["executor", *argv]))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        stack.enter_context(mock.patch("sys.stdin", stdin_obj))
        code = cli.main(["executor", *argv])
    return code, out.getvalue(), err.getvalue()


class CliCase(unittest.TestCase):
    def setUp(self) -> None:
        self.live = Live()
        self.addCleanup(self.live.close)
        self.root = self.live.root
        self.payloads = Path(tempfile.mkdtemp(prefix="exec-cli-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.payloads, ignore_errors=True))

    def payload_file(self, doc: dict) -> str:
        path = self.payloads / f"{doc['kind']}-{os.getpid()}.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def cli(self, *argv: str, stdin: bytes | None = None):
        return run(list(argv), self.root, stdin)


class Usage(CliCase):
    def test_help_and_version_exit_zero(self):
        code, out, _ = run(["help"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("executor new", out)
        code, out, _ = run(["--version"], self.root)
        self.assertEqual((code, out.strip() != ""), (0, True))

    def test_an_unknown_command_is_a_usage_error(self):
        code, _, err = run(["bogus"], self.root)
        self.assertEqual(code, 2)
        self.assertIn("unknown command", err)

    def test_no_arguments_prints_the_help(self):
        code, out, _ = run([], self.root)
        self.assertEqual(code, 0)
        self.assertIn("executor new", out)

    def test_the_module_guard_exits_with_mains_code(self):
        """`python cli.py --version` reaches the __main__ guard and exits 0."""
        with mock.patch("sys.argv", ["cli.py", "--version"]), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as se:
                runpy.run_path(str(Path(cli.__file__)), run_name="__main__")
        self.assertEqual(se.exception.code, 0)

    def test_the_package_guard_exits_with_mains_code(self):
        """`python -m executor` reaches executor/__main__.py and exits 0,
        with the same argv convention cli.py's own guard uses."""
        pkg_main = Path(cli.__file__).parent / "__main__.py"
        self.assertTrue(pkg_main.exists(), "executor/__main__.py is the -m entry")
        out = io.StringIO()
        with mock.patch("sys.argv", ["executor", "--version"]), \
             contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as se:
                runpy.run_path(str(pkg_main), run_name="__main__")
        self.assertEqual(se.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), cli.__version__)

    def test_importing_the_package_entry_does_not_run_it(self):
        """A plain import of `executor.__main__` is inert: the CLI runs only
        under the `__main__` guard, so importing never fires a command."""
        import importlib
        module = importlib.import_module("executor.__main__")
        self.assertTrue(hasattr(module, "main"))


class Stdio(unittest.TestCase):
    """Windows pipes use the locale code page, which cannot encode the help
    arrow or a non-Latin title; the streams are reconfigured to UTF-8 where
    they support it."""

    def test_a_stream_that_can_reconfigure_is_switched_to_utf8(self):
        fake = mock.Mock()
        with mock.patch.object(cli.sys, "stdout", fake), \
             mock.patch.object(cli.sys, "stderr", io.StringIO()):
            cli._utf8_stdio()
        fake.reconfigure.assert_called_once_with(encoding="utf-8")

    def test_a_stream_without_reconfigure_is_left_alone(self):
        out = io.StringIO()
        with mock.patch.object(cli.sys, "stdout", out), \
             mock.patch.object(cli.sys, "stderr", out):
            cli._utf8_stdio()
        self.assertEqual(out.getvalue(), "")


class NewCommand(CliCase):
    def test_new_creates_an_initiative_through_the_engine(self):
        code, out, _ = self.cli("new", "Mobility", "exam", "portal")
        self.assertEqual(code, 0)
        created = json.loads(out)
        self.assertEqual(created["title"], "Mobility exam portal")
        self.assertTrue(created["created"].startswith("INIT-"))
        meta = read_json(meta_file(Path(created["store"])))
        self.assertIsNotNone(meta)
        self.assertEqual(meta["engine_version"], cli.__version__)

    def test_new_without_a_title_is_a_usage_error(self):
        code, _, err = self.cli("new", "  ")
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class NextAndStatus(CliCase):
    def test_next_returns_one_typed_action(self):
        code, out, _ = self.cli("next")
        self.assertEqual(code, 0)
        act = json.loads(out)
        self.assertEqual(act["action"], "PHASE-ENTER")
        self.assertIn("resume", act)


class Autonomy(CliCase):
    def test_the_policy_in_force_is_deny_for_every_phase_by_default(self):
        code, out, _ = self.cli("autonomy")
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(out)["autonomy"].values()), {"deny"})

    def test_setting_a_known_phase_to_a_known_mode_is_accepted(self):
        code, out, _ = self.cli("autonomy", "intake", "gate")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["set"], {"intake": "gate"})
        self.assertEqual(json.loads(out)["autonomy"]["intake"], "gate")

    def test_a_mode_outside_the_three_words_is_refused_and_writes_nothing(self):
        before = self.live.init.idir.joinpath("meta", "autonomy.json").read_bytes()
        code, _, err = self.cli("autonomy", "intake", "allow-all")
        self.assertEqual((code, json.loads(err)["code"]), (2, "unknown_mode"))
        self.assertEqual(self.live.init.idir.joinpath("meta", "autonomy.json").read_bytes(),
                         before)

    def test_an_unknown_phase_is_refused(self):
        code, _, err = self.cli("autonomy", "bogusphase", "gate")
        self.assertEqual((code, json.loads(err)["code"]), (2, "unknown_phase"))

    def test_a_phase_without_a_mode_is_a_usage_error(self):
        code, _, err = self.cli("autonomy", "intake")
        self.assertEqual((code, json.loads(err)["code"]), (2, "usage"))


class StatusAndId(CliCase):
    def test_status_prints_the_gate_card(self):
        self.live.run(lambda a: a["action"] == "GATE")
        code, out, _ = self.cli("status")
        self.assertEqual(code, 0)
        self.assertIn("-> GATE intake", out)

    def test_an_explicit_initiative_id_is_honoured(self):
        code, out, _ = self.cli("status", self.live.init.id)
        self.assertEqual(code, 0)
        self.assertIn(self.live.init.id, out)

    def test_an_unknown_initiative_id_is_an_engine_error(self):
        code, _, err = self.cli("status", "INIT-9999")
        self.assertEqual(code, 2)
        self.assertIn("no_initiative", err)


class IngestAuthority(CliCase):
    def test_a_worker_payload_is_accepted_from_a_file(self):
        drafted = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        code, out, _ = self.cli("ingest", self.payload_file(self.live.answer(drafted)))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["accepted"], "charter")

    def test_a_payload_read_from_stdin_is_accepted(self):
        drafted = self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        code, out, _ = self.cli("ingest", "-",
                                stdin=json.dumps(self.live.answer(drafted)).encode("utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["accepted"], "charter")

    def test_a_human_decision_cannot_be_ingested_by_a_worker(self):
        self.live.run(lambda a: a["action"] == "GATE")
        code, _, err = self.cli("ingest", self.payload_file(PL.gate(phase="intake")))
        self.assertEqual(code, 2)
        self.assertIn("unauthorized", err)
        self.assertEqual(self.live.events()[-1]["kind"], "gate_opened",
                         "the gate must stay open")

    def test_a_refused_payload_exits_two_with_the_typed_rejection(self):
        code, _, err = self.cli("ingest", self.payload_file(PL.art("charter")))
        self.assertEqual(code, 2)
        self.assertIn("no_open_slot", err)

    def test_malformed_json_is_a_typed_rejection(self):
        path = self.payloads / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        code, _, err = self.cli("ingest", str(path))
        self.assertEqual(code, 2)
        self.assertIn("not_json", err)

    def test_an_ingest_without_a_path_is_a_usage_error(self):
        code, _, err = run(["ingest"], self.root)
        self.assertEqual(code, 2)
        self.assertIn("usage", err)

    def test_a_missing_payload_file_is_reported_not_raised(self):
        code, _, err = self.cli("ingest", str(self.payloads / "absent.json"))
        self.assertEqual(code, 2)
        self.assertIn("missing_file", err)

    def test_a_non_utf8_payload_file_is_refused_on_every_platform(self):
        path = self.payloads / "latin.json"
        path.write_bytes('{"kind": "charter", "t": "caf\xe9"}'.encode("latin-1"))
        with self.assertRaises(UnicodeDecodeError):
            run(["ingest", str(path)], self.root)


class DecideCommand(CliCase):
    def test_a_human_decision_is_accepted_through_decide(self):
        self.live.run(lambda a: a["action"] == "GATE")
        code, out, _ = self.cli("decide", self.payload_file(PL.gate(phase="intake")))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["accepted"], "gate_decision")

    def test_a_worker_payload_cannot_be_decided(self):
        code, _, err = self.cli("decide", self.payload_file(PL.art("charter")))
        self.assertEqual(code, 2)
        self.assertIn("unauthorized", err)

    def test_decide_without_a_path_is_a_usage_error(self):
        code, _, err = run(["decide"], self.root)
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class Checks(CliCase):
    def test_check_is_clean_on_a_fresh_run(self):
        code, out, _ = self.cli("check")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["chain"], "ok")

    def test_check_exits_one_when_it_finds_a_problem(self):
        path = self.live.init.idir / "stray.txt"
        path.write_text("x", encoding="utf-8")
        code, out, _ = self.cli("check")
        self.assertEqual(code, 1)
        self.assertTrue(any("non-canonical" in p for p in json.loads(out)["problems"]))

    def test_doctor_reports_the_policy_in_force_and_open_dispatches(self):
        self.live.run(lambda a: a["action"] == "DISPATCH" and a["role"] == "author")
        code, out, _ = self.cli("doctor")
        report = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(report["policy"]["values"]["deadline_s"], 3600)
        self.assertEqual(len(report["open_dispatch_ids"]), 1)

    def test_doctor_exits_one_on_a_problem(self):
        (self.live.init.idir / "stray.txt").write_text("x", encoding="utf-8")
        code, _, _ = self.cli("doctor")
        self.assertEqual(code, 1)


class Graph(CliCase):
    def test_graph_json_lists_nodes_and_edges(self):
        code, out, _ = self.cli("graph")
        doc = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIn(self.live.init.id, doc["nodes"])

    def test_graph_mermaid_is_a_flowchart(self):
        self.live.run(lambda a: a["action"] == "DISPATCH")
        code, out, _ = self.cli("graph", "--format", "mermaid")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("flowchart LR"))
        self.assertIn("dispatched", out)

    def test_an_unknown_graph_format_is_a_usage_error(self):
        code, _, err = self.cli("graph", "--format", "dot")
        self.assertEqual(code, 2)
        self.assertIn("unknown graph format", err)

    def test_a_format_flag_with_no_value_is_a_usage_error(self):
        code, _, err = self.cli("graph", "--format")
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


class Migrate(CliCase):
    def test_a_current_store_reports_no_action_needed(self):
        code, out, _ = self.cli("migrate", "--dry-run")
        report = json.loads(out)
        self.assertEqual((code, report["verdict"], report["action"]),
                         (0, "current", "none"))
        self.assertTrue(report["dry_run"])

    def test_an_outdated_store_is_reported_and_never_edited(self):
        meta = read_json(meta_file(self.live.init.idir))
        self.assertIsNotNone(meta)
        write_json(meta_file(self.live.init.idir), {**meta, "engine_version": "0.0.1"})
        before = meta_file(self.live.init.idir).read_bytes()
        code, out, _ = self.cli("migrate")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["verdict"], "store_outdated")
        self.assertEqual(meta_file(self.live.init.idir).read_bytes(), before)

    def test_an_explicit_initiative_id_is_accepted(self):
        code, out, _ = self.cli("migrate", self.live.init.id, "--dry-run")
        self.assertEqual((code, json.loads(out)["verdict"]), (0, "current"))


class Secrets(CliCase):
    def test_secrets_scan_finds_a_secret_without_printing_it(self):
        key = "-----BEGIN " + " ".join(("RSA", "PRIVATE", "KEY")) + "-----"
        leak = self.live.init.idir / "meta" / "leak.txt"
        leak.write_text(f"x\n{key}\n", encoding="utf-8")
        code, out, _ = self.cli("check", "--secrets")
        self.assertEqual(code, 1)
        self.assertIn("private_key", out)
        self.assertIn("leak.txt", out)
        self.assertNotIn(key, out)

    def test_secrets_scan_on_a_clean_store_exits_zero(self):
        code, out, _ = self.cli("check", "--secrets")
        self.assertEqual(json.loads(out)["findings"], [])

    def test_stray_args_are_usage_under_secrets_too(self):
        code, _, err = self.cli("check", "--secrets", "extra-arg")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "usage")


class Errors(CliCase):
    def fail_status(self, error) -> tuple[int, str, str]:
        """Run `status` with its handler replaced in the real dispatch table, so
        main()'s error mapping is what is under test."""
        with mock.patch.dict(cli.COMMANDS, {"status": mock.Mock(side_effect=error)}):
            return run(["status"], self.root)

    def test_a_keyboard_interrupt_exits_130(self):
        self.assertEqual(self.fail_status(KeyboardInterrupt)[0], 130)

    def test_an_engine_error_is_printed_as_json_with_its_code(self):
        code, _, err = self.fail_status(ExecError("boom", "x_code"))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err), {"error": "boom", "code": "x_code"})

    def test_a_rejection_is_printed_as_json_with_its_fields(self):
        code, _, err = self.fail_status(Rejection("some_code", "$.f", "a", "b", "hint text"))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["rejected"]["hint"], "hint text")

    def test_a_missing_file_is_mapped_to_a_typed_error(self):
        code, _, err = self.fail_status(FileNotFoundError("gone.json"))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "missing_file")


if __name__ == "__main__":
    unittest.main()
