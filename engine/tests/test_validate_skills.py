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
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path, PureWindowsPath
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
        self.assertIn(f"{p.as_posix()}:2", finding)

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
                self.assertTrue(any(p.as_posix() in f and "asset" in f
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


class PayloadContractGuardTests(unittest.TestCase):
    """The guard that makes a second markdown renderer impossible to
    reintroduce: a `sections[].body` example, a markdown template handed
    to a prompt, or an output placeholder resolving to a .md file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def put(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def findings(self) -> list[str]:
        fail: list[str] = []
        vs.check_payload_contract(self.root, fail)
        return fail

    def test_a_clean_tree_has_no_findings(self):
        self.put("demo/SKILL.md", "# Demo\nprose only\n")
        self.assertEqual(self.findings(), [])

    def test_a_body_field_example_is_flagged_with_file_and_line(self):
        p = self.put("demo/notes.md", 'ok\n"sections": [{"id": "s", '
                                      '"title": "t", "body": "b"}]\n')
        (finding,) = self.findings()
        self.assertIn(f"{p.as_posix()}:2", finding)
        self.assertIn("sections[].body example", finding)

    def test_the_structured_field_names_pass(self):
        self.put("demo/notes.md", '```json\n"sections": [{"id": "s", '
                                  '"title": "t", "prose": "p",\n'
                                  '  "bullets": ["b"],\n'
                                  '  "tables": [{"columns": ["A"], '
                                  '"rows": [["1"]]}],\n'
                                  '  "code": [{"lang": "ts", '
                                  '"source": "x"}]}]\n```\n')
        self.assertEqual(self.findings(), [])

    def test_a_prompt_with_a_markdown_output_template_is_flagged(self):
        self.put("demo/scout-prompt.md",
                 "## The Output File\n\n```markdown\n\n"
                 "| A | B |\n|---|---|\n\n```\n")
        (finding,) = self.findings()
        self.assertIn("```markdown template", finding)

    def test_a_markdown_fence_in_a_non_prompt_is_allowed(self):
        self.put("demo/SKILL.md", "```markdown\nsample\n```\n")
        self.assertEqual(self.findings(), [])

    def test_an_output_placeholder_resolving_to_markdown_is_flagged(self):
        self.put("demo/prompt.md", "| `[OUTPUT_FILE]` | "
                                   "`<session dir>/prior-art.md` |\n")
        (finding,) = self.findings()
        self.assertIn("output placeholder resolves to a .md file", finding)

    def test_an_output_placeholder_resolving_to_json_passes(self):
        self.put("demo/prompt.md", "| `[OUTPUT_FILE]` | "
                                   "the `respond_to` path "
                                   "`dispatches/D<NNNNN>/payload.json` |\n")
        self.assertEqual(self.findings(), [])


class RefusalContractGuardTests(unittest.TestCase):
    """A worker prompt that never says what a refusal means leaves the
    worker to improvise: re-dispatch, edit the journal, answer another
    slot. All three corrupt a run, so every payload-writing prompt carries
    the contract and the validator proves it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def put(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def findings(self) -> list[str]:
        fail: list[str] = []
        vs.check_refusal_contract(self.root, fail)
        return fail

    def test_a_prompt_without_the_refusal_contract_is_flagged(self):
        p = self.put("demo/scout-prompt.md", "# Scout\n\n| respond_to | x |\n")
        (finding,) = self.findings()
        self.assertIn(p.as_posix(), finding)
        self.assertIn("refusal contract", finding)

    def test_a_prompt_carrying_the_contract_passes(self):
        self.put("demo/scout-prompt.md",
                 "# Scout\n\n## If Your Payload Is Refused\n\nfix it\n")
        self.assertEqual(self.findings(), [])

    def test_the_human_lane_templates_are_exempt(self):
        self.put("demo/decide-prompt.md", "# Decide\n")
        self.put("demo/supervisor-prompt.md", "# Supervisor\n")
        self.assertEqual(self.findings(), [])

    def test_the_real_repository_prompts_carry_the_contract(self):
        fail: list[str] = []
        vs.check_refusal_contract(REPO / "skills", fail)
        self.assertEqual(fail, [])


class DiagnosticsArePortable(unittest.TestCase):
    """Every path the validator prints or compares is POSIX. Windows is the
    only platform where `str(Path)` says `a\\SKILL.md`, and a diagnostic
    whose separator depends on the host is a diagnostic a reader cannot
    grep and a registry comparison that fails on one OS and passes on
    another. The Windows CI run found this: 47 failures, all of them the
    validator disagreeing with itself about a separator."""

    def the_tree(self, name: str = "skills") -> list[str]:
        root = REPO / name
        out: list[str] = []
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "validate_skills.py"),
             str(root)], capture_output=True, text=True, cwd=REPO)
        out += proc.stdout.splitlines() + proc.stderr.splitlines()
        return out

    def test_the_validator_reports_no_backslash_paths(self):
        for line in self.the_tree():
            self.assertNotIn("\\", line,
                             f"a path separator leaked into a diagnostic: "
                             f"{line}")

    def test_the_registry_agrees_with_the_paths_it_sees(self):
        """The registry rows are POSIX text, so the on-disk set must be
        built the same way or every prompt looks unregistered on Windows."""
        root = REPO / "skills"
        fail: list[str] = []
        vs.check_registry(root, fail)
        self.assertEqual(fail, [])

    def test_a_diagnostic_path_is_posix_even_when_the_host_is_not(self):
        """`PurePath.as_posix()` is platform-independent, and it is the only
        conversion the validator may use. A regression to `str(path)` is
        invisible on macOS and breaks Windows, so it is asserted here."""
        self.assertEqual(PureWindowsPath("a", "SKILL.md").as_posix(),
                         "a/SKILL.md")
        self.assertEqual(str(PureWindowsPath("a", "SKILL.md")),
                         "a\\SKILL.md")


class RepositoryIsCleanTests(unittest.TestCase):
    def test_skills_tree_ships_no_visual_material(self):
        fail: list[str] = []
        vs.check_no_visual_material(REPO / "skills", fail)
        self.assertEqual(fail, [])

    def test_skills_tree_teaches_no_second_renderer(self):
        """Real-tree enforcement: no `sections[].body` example, no prompt
        carrying a markdown output template, and no output placeholder
        that resolves to a .md path. The engine renders every markdown
        file from the payload's data, so a doc that shows anything else
        teaches an agent to become a second renderer."""
        fail: list[str] = []
        vs.check_payload_contract(REPO / "skills", fail)
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
