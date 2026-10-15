# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""scripts/validate_skills.py: the structural contract every skill must meet.

Each check is driven in isolation against a tiny skills tree built in a temp
directory, so a failure points at one rule. The checks matter because the
payload of this repository is prompts: a malformed frontmatter hides a skill
from routing, an unbalanced fence swallows the next section, and an
unregistered prompt template is dispatched by nothing.
"""
from __future__ import annotations

import io
import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _scripts import load, run_as_main

vs = load("validate_skills.py")

# The glyphs the validator bans, built from code points: this file must not
# itself contain them (a repo-wide rule covers every markdown-producing write).
BOX_CHARS = "".join(map(chr, (
    0x251C, 0x2514, 0x2502, 0x250C, 0x2510, 0x2518, 0x252C, 0x2534, 0x253C,
    0x256D, 0x256E, 0x256F, 0x2570, 0x2550, 0x2551, 0x2554, 0x2557, 0x255A,
    0x255D)))
TEE, ELBOW, DASHES = chr(0x251C), chr(0x2514), chr(0x2500) * 2

GOOD_SKILL = textwrap.dedent("""\
    ---
    name: demo
    description: Does a thing. Use when the thing is needed.
    ---
    # Demo

    ## Self-Critique
    ok

    ## Verification
    ok
""")


class TreeCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def put(self, rel: str, text: str = "") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def run_check(self, check, path: Path) -> list[str]:
        fail: list[str] = []
        check(path, str(path.relative_to(self.root)), fail)
        return fail

    def main_result(self, *argv: str):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.argv", ["validate_skills.py", *argv]), \
                redirect_stdout(out), redirect_stderr(err):
            rc = vs.main()
        return rc, out.getvalue(), err.getvalue()


class FrontmatterTests(TreeCase):
    def check(self, text: str) -> list[str]:
        return self.run_check(vs.check_frontmatter,
                              self.put("a/SKILL.md", text))

    def test_a_complete_frontmatter_passes(self):
        self.assertEqual(self.check(GOOD_SKILL), [])

    def test_no_frontmatter_at_all(self):
        for text in ("", "# Title\n", "name: x\n"):
            with self.subTest(text=text):
                self.assertEqual(self.check(text),
                                 ["FAIL a/SKILL.md: no frontmatter block"])

    def test_an_unterminated_frontmatter(self):
        self.assertEqual(
            self.check("---\nname: x\ndescription: Use when y\n"),
            ["FAIL a/SKILL.md: unterminated frontmatter"])

    def test_a_missing_name_is_reported_alone(self):
        self.assertEqual(
            self.check("---\ndescription: Use when y\n---\n"),
            ["FAIL a/SKILL.md: no name: field"])

    def test_a_missing_description_also_loses_the_use_when_trigger(self):
        self.assertEqual(
            self.check("---\nname: x\n---\n"),
            ["FAIL a/SKILL.md: no description: field (routing depends on "
             "it)",
             "FAIL a/SKILL.md: description lacks a 'Use when' trigger"])

    def test_a_description_without_a_trigger(self):
        self.assertEqual(
            self.check("---\nname: x\ndescription: Does things.\n---\n"),
            ["FAIL a/SKILL.md: description lacks a 'Use when' trigger"])

    def test_a_folded_multiline_description_still_counts(self):
        self.assertEqual(self.check(
            "---\nname: x\ndescription: >\n  Does things.\n"
            "  Use when needed.\n---\n"), [])

    def test_fields_must_start_a_line(self):
        self.assertEqual(
            len(self.check("---\n  name: x\n  description: Use when y\n---\n")),
            2)

    def test_the_trigger_is_only_looked_for_inside_the_frontmatter(self):
        text = "---\nname: x\ndescription: nothing\n---\nUse when later\n"
        self.assertEqual(self.check(text),
                         ["FAIL a/SKILL.md: description lacks a 'Use when' "
                          "trigger"])


class FenceTests(TreeCase):
    def check(self, text: str) -> list[str]:
        return self.run_check(vs.check_fences, self.put("a/x.md", text))

    def test_balanced_fences_pass(self):
        self.assertEqual(self.check("```\ncode\n```\n\n```py\nx\n```\n"), [])

    def test_no_fences_pass(self):
        self.assertEqual(self.check("plain text\n"), [])

    def test_an_odd_count_is_reported_with_the_count(self):
        self.assertEqual(self.check("```\ncode\n"),
                         ["FAIL a/x.md: unbalanced code fences (1)"])
        self.assertEqual(self.check("```\na\n```\n```\nb\n"),
                         ["FAIL a/x.md: unbalanced code fences (3)"])

    def test_only_lines_that_start_a_fence_count(self):
        self.assertEqual(self.check("use ``` inline\n"), [])

    def test_an_indented_fence_counts(self):
        self.assertEqual(self.check("  ```\ncode\n  ```\n"), [])
        self.assertEqual(self.check("  ```\ncode\n"),
                         ["FAIL a/x.md: unbalanced code fences (1)"])


class HtmlCommentTests(TreeCase):
    def check(self, text: str) -> list[str]:
        return self.run_check(vs.check_html_comments,
                              self.put("a/x.md", text))

    def test_a_comment_in_prose_is_reported_with_its_line(self):
        self.assertEqual(self.check("ok\nbad <!-- hidden --> text\n"),
                         ["FAIL a/x.md:2: HTML comment in markdown"])

    def test_a_comment_inside_a_code_span_is_just_text(self):
        self.assertEqual(self.check("write `<!-- x -->` to comment\n"), [])

    def test_a_comment_in_a_markup_fence_is_the_sampled_language(self):
        for lang in ("html", "xml", "svg", "HTML", "Svg"):
            with self.subTest(lang=lang):
                self.assertEqual(
                    self.check(f"```{lang}\n<!-- sample -->\n```\n"), [])

    def test_a_comment_in_any_other_fence_is_still_reported(self):
        for opener in ("```", "```python", "```md"):
            with self.subTest(opener=opener):
                self.assertEqual(
                    self.check(f"{opener}\n<!-- x -->\n```\n"),
                    ["FAIL a/x.md:2: HTML comment in markdown"])

    def test_the_markup_exemption_ends_with_the_fence(self):
        self.assertEqual(
            self.check("```html\n<!-- a -->\n```\n<!-- b -->\n"),
            ["FAIL a/x.md:4: HTML comment in markdown"])

    def test_every_comment_line_is_reported(self):
        self.assertEqual(
            len(self.check("<!-- a -->\ntext\n<!-- b -->\n")), 2)


class SectionTests(TreeCase):
    def check(self, text: str) -> list[str]:
        return self.run_check(vs.check_sections, self.put("a/SKILL.md", text))

    def test_exactly_one_of_each_passes(self):
        self.assertEqual(self.check(GOOD_SKILL), [])

    def test_a_missing_section_is_named_with_the_count(self):
        self.assertEqual(
            self.check("## Self-Critique\nx\n"),
            ["FAIL a/SKILL.md: expected exactly one '## Verification' "
             "section, found 0"])

    def test_a_duplicated_section_is_named_with_the_count(self):
        text = GOOD_SKILL + "\n## Verification\nagain\n"
        self.assertEqual(
            self.check(text),
            ["FAIL a/SKILL.md: expected exactly one '## Verification' "
             "section, found 2"])

    def test_both_missing_gives_two_findings(self):
        self.assertEqual(len(self.check("# nothing\n")), 2)

    def test_only_a_level_two_heading_on_its_own_line_counts(self):
        text = ("### Self-Critique\n## Self-Critique extra\n"
                "text ## Verification\n")
        self.assertEqual(len(self.check(text)), 2)

    def test_trailing_whitespace_after_the_heading_is_fine(self):
        self.assertEqual(
            self.check("## Self-Critique  \nx\n## Verification\t\ny\n"), [])


REGISTRY = textwrap.dedent("""\
    # Layout

    ## Dispatch registry

    | Template | Used by |
    |---|---|
    | `executor/author-prompt.md` | author |
    | `executor-review/task-reviewer-prompt.md` | review |

    ## Next section

    | `executor/ignored-prompt.md` | not in the registry |
""")
PROMPT = "respond_to dispatch_id kind\n"
REGISTERED = {"executor/author-prompt.md": PROMPT,
              "executor-review/task-reviewer-prompt.md": PROMPT}


class RegistryTests(TreeCase):
    def build(self, *, layout: str | None = REGISTRY,
              prompts: dict[str, str] | None = None) -> list[str]:
        if layout is not None:
            self.put("executor/references/layout.md", layout)
        for rel, body in (REGISTERED if prompts is None else prompts).items():
            self.put(rel, body)
        fail: list[str] = []
        vs.check_registry(self.root, fail)
        return fail

    def test_a_consistent_registry_passes(self):
        self.assertEqual(self.build(), [])

    def test_without_a_layout_file_there_is_nothing_to_check(self):
        self.assertEqual(self.build(layout=None, prompts={}), [])

    def test_a_registry_naming_no_templates_is_reported(self):
        out = self.build(layout="## Dispatch registry\n\n| nothing |\n",
                         prompts={})
        self.assertEqual(len(out), 1)
        self.assertIn("no prompt templates under ## Dispatch registry",
                      out[0])

    def test_a_template_named_only_after_the_next_heading_is_unregistered(self):
        out = self.build(prompts={**REGISTERED,
                                  "executor/ignored-prompt.md": PROMPT})
        self.assertEqual(out, ["FAIL executor/ignored-prompt.md: prompt on "
                               "disk not in Dispatch registry"])

    def test_a_template_named_after_the_next_heading_is_not_missing(self):
        self.assertEqual(self.build(), [])

    def test_only_table_rows_register_a_template(self):
        layout = ("## Dispatch registry\n\n"
                  "Mentions `executor/prose-prompt.md` in prose.\n"
                  "| `executor/author-prompt.md` | x |\n")
        self.assertEqual(
            self.build(layout=layout,
                       prompts={"executor/author-prompt.md": PROMPT}), [])

    def test_a_registered_template_that_does_not_exist(self):
        out = self.build(prompts={"executor/author-prompt.md": PROMPT})
        self.assertEqual(len(out), 1)
        self.assertIn("registered prompt missing: "
                      "executor-review/task-reviewer-prompt.md", out[0])

    def test_each_missing_dispatch_token_is_named(self):
        for token in ("respond_to", "dispatch_id", "kind"):
            with self.subTest(token=token):
                out = self.build(prompts={
                    **REGISTERED,
                    "executor/author-prompt.md": PROMPT.replace(token, "")})
                self.assertEqual(
                    out, [f"FAIL executor/author-prompt.md: prompt lacks "
                          f"dispatch contract token `{token}`"])

    def test_a_template_missing_every_token_gets_three_findings(self):
        out = self.build(prompts={**REGISTERED,
                                  "executor/author-prompt.md": "nothing\n"})
        self.assertEqual(len(out), 3)

    def test_an_unregistered_template_on_disk_is_reported(self):
        out = self.build(prompts={**REGISTERED,
                                  "executor-spec/stray-prompt.md": PROMPT})
        self.assertEqual(out, ["FAIL executor-spec/stray-prompt.md: prompt "
                               "on disk not in Dispatch registry"])


class BoxDrawingTests(TreeCase):
    def check(self, text: str) -> list[str]:
        return self.run_check(vs.check_box_drawing, self.put("a/x.md", text))

    def test_the_banned_set_is_exactly_the_documented_one(self):
        self.assertEqual(set(BOX_CHARS), set(vs.BOX.pattern[1:-1]))
        self.assertEqual(len(BOX_CHARS), 19)

    def test_plain_markdown_passes(self):
        self.assertEqual(self.check("| a | b |\n|---|---|\n"), [])

    def test_every_box_character_is_reported_with_its_line(self):
        for ch in BOX_CHARS:
            with self.subTest(codepoint=hex(ord(ch))):
                out = self.check(f"ok\nline {ch} here\n")
                self.assertEqual(len(out), 1)
                self.assertIn("a/x.md:2: box-drawing character", out[0])

    def test_a_character_inside_a_code_span_is_allowed(self):
        self.assertEqual(self.check(f"the glyph `{TEE}` is banned\n"), [])

    def test_a_fenced_tree_is_not_exempt(self):
        text = f"```\n{TEE}{DASHES} a\n{ELBOW}{DASHES} b\n```\n"
        self.assertEqual(len(self.check(text)), 2)


class StripSpanTests(unittest.TestCase):
    def test_spans_are_removed_and_text_around_them_kept(self):
        self.assertEqual(vs._strip_spans("a `b` c `d` e"), "a  c  e")
        self.assertEqual(vs._strip_spans("no spans"), "no spans")
        self.assertEqual(vs._strip_spans("unclosed ` tick"),
                         "unclosed ` tick")


class MainTests(TreeCase):
    def good_tree(self) -> None:
        self.put("demo/SKILL.md", GOOD_SKILL)

    def test_a_clean_tree_passes(self):
        self.good_tree()
        rc, out, err = self.main_result(str(self.root))
        self.assertEqual((rc, out.strip(), err),
                         (0, "skill validation: all clean", ""))

    def test_findings_go_to_stderr_with_a_failure_banner(self):
        self.put("demo/SKILL.md", "no frontmatter\n")
        rc, out, err = self.main_result(str(self.root))
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no frontmatter block", err)
        self.assertIn("skill validation: FAILURES", err)

    def test_duplicate_skill_names_are_reported(self):
        self.put("one/SKILL.md", GOOD_SKILL)
        self.put("two/SKILL.md", GOOD_SKILL)
        rc, _, err = self.main_result(str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("duplicate skill name 'demo'", err)

    def test_distinct_names_are_not_duplicates(self):
        self.put("one/SKILL.md", GOOD_SKILL)
        self.put("two/SKILL.md", GOOD_SKILL.replace("name: demo",
                                                    "name: other"))
        self.assertEqual(self.main_result(str(self.root))[0], 0)

    def test_every_markdown_file_gets_the_text_checks(self):
        self.good_tree()
        self.put("demo/notes.md", "```\nunclosed\n")
        self.put("demo/more.md", "<!-- c -->\n")
        self.put("demo/tree.md", f"{TEE}{DASHES} a\n")
        rc, _, err = self.main_result(str(self.root))
        self.assertEqual(rc, 1)
        for want in ("unbalanced code fences", "HTML comment",
                     "box-drawing character"):
            self.assertIn(want, err)

    def test_the_registry_and_visual_guards_run_too(self):
        self.good_tree()
        self.put("executor/references/layout.md",
                 "## Dispatch registry\n\n| none |\n")
        self.put("demo/page.html", "")
        rc, _, err = self.main_result(str(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("no prompt templates", err)
        self.assertIn("visual-companion asset", err)

    def test_the_default_root_is_skills_in_the_working_directory(self):
        self.put("skills/demo/SKILL.md", GOOD_SKILL)
        old = os.getcwd()
        self.addCleanup(os.chdir, old)
        os.chdir(self.root)
        self.assertEqual(self.main_result()[0], 0)

    def test_an_empty_tree_is_clean(self):
        self.assertEqual(self.main_result(str(self.root))[0], 0)

    def test_the_entry_point_exits_with_the_result(self):
        self.good_tree()
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(run_as_main("validate_skills.py",
                                         str(self.root)), 0)
        self.assertIn("all clean", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
