# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The engine ships inside the skill, and the two copies cannot drift.

The skills call `executor <verb>` and nothing installs a command, so the
engine travels inside the router skill and the launcher resolves it from
its own directory. These tests pin the three properties that make that
true for a user who only ran `npx skills add`:

1. the bundle is byte-identical to `engine/executor/` — one package, two
   copies, no drift;
2. the launcher runs from a copied skill directory in an unrelated working
   directory, with no `PYTHONPATH`, which is what an install produces;
3. every `engine/executor/...` path a skill document cites resolves
   inside the installed skill, never to a clone the user does not have.
"""
from __future__ import annotations

import io
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _scripts import REPO, load

sync_engine = load("sync_engine.py")
SKILL = REPO / "skills" / "executor"
LAUNCHER = SKILL / "scripts" / "executor"


class BundleMatchesSource(unittest.TestCase):
    """The bundled copy is generated, so a hand edit to either side is the
    failure this catches: the repository would test one engine and ship
    another."""

    def test_the_bundle_is_in_sync(self):
        self.assertEqual(sync_engine.drift(), [],
                         "run python scripts/sync_engine.py")

    def test_the_launcher_is_executable(self):
        self.assertTrue(os.access(LAUNCHER, os.X_OK),
                        "the launcher lost its exec bit")

    def test_the_bundle_carries_every_module(self):
        shipped = set(sync_engine.modules(sync_engine.BUNDLE))
        source = set(sync_engine.modules(sync_engine.SOURCE))
        self.assertEqual(shipped, source)

    def test_drift_names_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, dst = root / "engine", root / "bundle"
            for d in (src, dst):
                d.mkdir()
            (src / "a.py").write_text("A = 1\n", encoding="utf-8")
            (src / "b.py").write_text("B = 1\n", encoding="utf-8")
            (dst / "a.py").write_text("A = 2\n", encoding="utf-8")
            (dst / "c.py").write_text("C = 1\n", encoding="utf-8")
            with mock.patch.object(sync_engine, "SOURCE", src), \
                 unittest.mock.patch.object(sync_engine, "BUNDLE", dst):
                problems = sync_engine.drift()
        text = "\n".join(problems)
        self.assertIn("stale in the bundle: a.py", text)
        self.assertIn("missing from the bundle: b.py", text)
        self.assertIn("not in the engine source: c.py", text)

    def test_sync_rewrites_a_stale_bundle_and_drops_orphans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, dst = root / "engine", root / "bundle"
            for d in (src, dst):
                d.mkdir()
            (src / "a.py").write_text("A = 1\n", encoding="utf-8")
            (dst / "a.py").write_text("A = 2\n", encoding="utf-8")
            (dst / "orphan.py").write_text("X = 1\n", encoding="utf-8")
            with mock.patch.object(sync_engine, "SOURCE", src), \
                 unittest.mock.patch.object(sync_engine, "BUNDLE", dst):
                changed = sync_engine.sync()
                self.assertEqual(sync_engine.drift(), [])
            self.assertEqual(sorted(changed), ["-orphan.py", "a.py"])
            self.assertEqual((dst / "a.py").read_text(encoding="utf-8"),
                             "A = 1\n")


class SyncEngineCli(unittest.TestCase):
    """`sync_engine.py` is the only writer of the bundle, so its own exit
    codes are what CI depends on: 0 in sync, 1 drifted, 2 no source."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.src, self.dst = root / "engine", root / "bundle"
        self.src.mkdir()
        (self.src / "a.py").write_text("A = 1\n", encoding="utf-8")
        patcher = unittest.mock.patch.object(sync_engine, "SOURCE", self.src)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = unittest.mock.patch.object(sync_engine, "BUNDLE", self.dst)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = sync_engine.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_check_passes_on_a_mirrored_bundle(self):
        sync_engine.sync()
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("in sync", out)

    def test_check_fails_and_names_the_drift(self):
        self.dst.mkdir()
        (self.dst / "a.py").write_text("A = 2\n", encoding="utf-8")
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("stale in the bundle: a.py", err)
        self.assertIn("python scripts/sync_engine.py", err)

    def test_write_reports_what_it_changed(self):
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("a.py", out)
        self.assertEqual((self.dst / "a.py").read_text(encoding="utf-8"),
                         "A = 1\n")

    def test_write_says_so_when_nothing_changed(self):
        self.run_main()
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("already in sync", out)

    def test_a_missing_source_is_an_error_not_a_silent_empty_bundle(self):
        shutil.rmtree(self.src)
        code, _, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("engine source missing", err)

    def test_the_module_guard_exits_with_mains_code(self):
        with mock.patch("sys.argv", ["sync_engine.py", "--check"]), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as se:
                runpy.run_path(str(Path(sync_engine.__file__)),
                               run_name="__main__")
        self.assertEqual(se.exception.code, 0)


class InstalledSkillRuns(unittest.TestCase):
    """The install path, exercised as an install: copy the skill directory
    somewhere unrelated, drop `PYTHONPATH`, and run the launcher from a
    project that is not the repository."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.skills = self.root / "agent" / "skills"
        self.skills.mkdir(parents=True)
        self.installed = self.skills / "executor"
        shutil.copytree(SKILL, self.installed)
        self.project = self.root / "project"
        self.project.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if k != "PYTHONPATH"}

    def run_launcher(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.installed / "scripts" / "executor"),
             *argv],
            cwd=self.project, env=self.env, capture_output=True, text=True)

    def test_version_runs_with_no_pythonpath_and_no_clone(self):
        proc = self.run_launcher("--version")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout.strip(), r"^\d+\.\d+\.\d+$")

    def test_help_lists_the_command_surface(self):
        proc = self.run_launcher("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("executor new", proc.stdout)
        self.assertIn("executor next", proc.stdout)

    def test_a_full_command_runs_in_a_fresh_git_repo(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        proc = self.run_launcher("new", "Installed run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("INIT-0001", proc.stdout)
        status = self.run_launcher("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("INIT-0001", status.stdout)

    def test_the_exec_bit_runs_it_directly(self):
        """Where the exec bit survived the copy, the bare form works."""
        proc = subprocess.run(
            [str(self.installed / "scripts" / "executor"), "--version"],
            cwd=self.project, env=self.env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout.strip(), r"^\d+\.\d+\.\d+$")

    def test_a_launcher_with_no_bundle_fails_loudly(self):
        shutil.rmtree(self.installed / "scripts" / "lib")
        proc = self.run_launcher("--version")
        self.assertEqual(proc.returncode, 127)
        self.assertIn("bundled engine is missing", proc.stderr)


class SkillPathsResolveInstalled(unittest.TestCase):
    """A skill document that cites `engine/executor/x.py` teaches a reader to
    open a path an install does not have. The engine is cited under the
    skill's own scripts/lib/, which exists wherever the skill was copied."""

    def test_no_skill_document_cites_the_repository_engine_path(self):
        offenders = []
        for f in sorted((REPO / "skills").rglob("*.md")):
            for i, line in enumerate(
                    f.read_text(encoding="utf-8").splitlines(), 1):
                if "engine/executor/" in line:
                    offenders.append(f"{f.relative_to(REPO)}:{i}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
