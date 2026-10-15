# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The skills tree ships no HTML and no visual companion, ever again.

`scripts/validate_skills.py::check_no_visual_material` is the guard. These
tests pin both halves: the guard fires on every shape the companion took
(prose, a fenced launcher, an HTML or JS asset), and the real repository is
clean today.
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _scripts import REPO, load

vs = load("validate_skills.py")

MARKERS = ["Visual Companion", "visual-companion", "visualcompanion",
           "visual mode", "server.cjs", "frame-template", "screen_dir",
           "events_file", "start-server", "stop-server"]
ASSETS = ["a/frame.html", "a/page.HTM", "a/helper.js", "a/server.cjs",
          "a/mod.mjs"]


class VisualGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def put(self, rel: str, text: str = "") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def findings(self) -> list[str]:
        fail: list[str] = []
        vs.check_no_visual_material(self.root, fail)
        return fail

    def run_main(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.argv", ["validate_skills.py", str(self.root)]), \
                redirect_stdout(out), redirect_stderr(err):
            rc = vs.main()
        return rc, out.getvalue(), err.getvalue()

    def test_clean_tree_has_no_findings(self):
        self.put("executor/SKILL.md", "# Executor\nplain prose\n")
        self.assertEqual(self.findings(), [])

    def test_prose_reference_is_flagged_with_file_and_line(self):
        p = self.put("a/SKILL.md", "ok\nOffer the visual companion now.\n")
        (finding,) = self.findings()
        self.assertIn(f"{p}:2", finding)

    def test_fenced_launcher_is_flagged(self):
        self.put("a/x.md", "```bash\n./start-server.sh --open\n```\n")
        self.assertEqual(len(self.findings()), 1)

    def test_every_marker_spelling_is_flagged(self):
        for i, marker in enumerate(MARKERS):
            with self.subTest(marker=marker):
                self.put(f"m{i}.md", f"see {marker}\n")
                self.assertTrue(any(f"m{i}.md:1" in f
                                    for f in self.findings()))

    def test_html_and_js_assets_are_flagged_whatever_their_content(self):
        for name in ASSETS:
            with self.subTest(asset=name):
                p = self.put(name, "")
                self.assertTrue(any(str(p) in f and "asset" in f
                                    for f in self.findings()))

    def test_files_that_are_neither_markdown_nor_assets_are_ignored(self):
        self.put("a/notes.txt", "visual companion")
        self.put("a/data.json", '{"x": "visual companion"}')
        self.assertEqual(self.findings(), [])

    def test_directories_are_skipped_not_read(self):
        (self.root / "a" / "dir.md").mkdir(parents=True)
        self.assertEqual(self.findings(), [])

    def test_main_fails_and_names_the_violation(self):
        self.put("a/notes.md", "see the visual companion\n")
        rc, _, err = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("visual-companion reference", err)

    def test_main_passes_on_a_clean_tree(self):
        self.put("a/notes.md", "nothing visual here\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("all clean", out)


class RepositoryIsCleanTests(unittest.TestCase):
    def test_skills_tree_ships_no_visual_material(self):
        fail: list[str] = []
        vs.check_no_visual_material(REPO / "skills", fail)
        self.assertEqual(fail, [])

    def test_readme_contributing_and_ci_do_not_mention_the_companion(self):
        targets = [REPO / "README.md", REPO / "CONTRIBUTING.md",
                   *sorted((REPO / ".github").rglob("*.yml")),
                   *sorted((REPO / ".github").rglob("*.yaml"))]
        for f in targets:
            with self.subTest(file=f.name):
                lines = f.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines, 1):
                    self.assertIsNone(vs.VISUAL_MARKERS.search(line),
                                      f"{f.name}:{i}: {line}")


if __name__ == "__main__":
    unittest.main()
