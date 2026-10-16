# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The mutation tool is only worth trusting if it is itself tested: every
operator produces the code it claims, every mutant is distinct and valid, and
on a toy project a strong suite kills everything while a weak one is caught
leaking exactly where it is weak.
"""
from __future__ import annotations

import ast
import io
import json
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _scripts import load, run_as_main

M = load("mutate.py")

SRC = textwrap.dedent('''
    def f(a, b, c):
        if a == b and not c:
            return a + b
        raise ValueError("x")
''')

LOOP = textwrap.dedent('''
    def g(xs):
        n = 5
        ok = True
        total = 0
        while ok:
            for x in xs:
                if x:
                    continue
                if x is None:
                    break
                total += x
            ok = False
        print(total)
        return total
''')


def norm(source: str) -> str:
    return ast.unparse(ast.parse(source))


class SiteTests(unittest.TestCase):
    def test_sites_come_in_a_fixed_traversal_order(self):
        self.assertEqual([s.desc for s in M.list_sites(SRC)], [
            "== -> !=", "drop 'not'", "and -> or", "+ -> -",
            "return -> return None", "if-test -> True", "if-test -> False",
            "raise -> pass"])

    def test_sites_carry_the_original_line_numbers(self):
        lines = {s.desc: s.lineno for s in M.list_sites(SRC)}
        self.assertEqual(lines["== -> !="], 3)
        self.assertEqual(lines["+ -> -"], 4)
        self.assertEqual(lines["raise -> pass"], 5)

    def test_loops_constants_and_statements_have_their_own_operators(self):
        descs = [s.desc for s in M.list_sites(LOOP)]
        for want in ("5 -> 6", "True -> False", "0 -> 1", "while-test -> False",
                     "continue -> pass", "break -> pass", "is -> is not",
                     "+= -> -=", "delete call statement",
                     "return -> return None"):
            self.assertIn(want, descs)
        self.assertNotIn("None -> ", " ".join(descs))

    def test_every_comparison_and_arithmetic_operator_flips(self):
        pairs = {"==": "!=", "!=": "==", "<": ">=", "<=": ">", ">": "<=",
                 ">=": "<", "is": "is not", "is not": "is", "in": "not in",
                 "not in": "in"}
        for op, flipped in pairs.items():
            src = f"def f(a, b):\n    return a {op} b\n"
            with self.subTest(op=op):
                out = M.mutate_source(src, 0)
                self.assertIn(f"a {flipped} b", out)
        self.assertIn("a - b", M.mutate_source("x = a + b", 0))
        self.assertIn("a + b", M.mutate_source("x = a - b", 0))

    def test_or_flips_to_and_and_a_bare_return_is_left_alone(self):
        self.assertIn("a and b", M.mutate_source("x = a or b", 0))
        self.assertEqual(M.list_sites("def f():\n    return\n"), [])
        self.assertEqual(M.list_sites("def f():\n    return None\n"), [])

    def test_a_multi_operator_comparison_flips_only_its_first_operator(self):
        out = M.mutate_source("x = a < b < c", 0)
        self.assertIn("a >= b < c", out)

    def test_unmapped_operators_and_docstrings_are_not_sites(self):
        self.assertEqual(M.list_sites('"""doc"""\nx = a * b\ny = "s"\n'), [])
        self.assertEqual(M.list_sites("x = a @ b"), [])
        self.assertEqual(M.list_sites("x = a % b"), [])


class MutantTests(unittest.TestCase):
    def test_each_mutant_is_valid_python_and_differs_from_the_original(self):
        base = norm(SRC)
        mutants = [M.mutate_source(SRC, i)
                   for i in range(len(M.list_sites(SRC)))]
        for i, m in enumerate(mutants):
            with self.subTest(site=i):
                compile(m, "x", "exec")
                self.assertNotEqual(norm(m), base)
        self.assertEqual(len(set(mutants)), len(mutants))      # all distinct

    def test_each_mutation_produces_exactly_the_code_it_names(self):
        want = {
            0: "a != b", 1: "if a == b and c", 2: "a == b or not c",
            3: "return a - b", 4: "return None", 5: "if True:",
            6: "if False:", 7: "pass",
        }
        for i, snippet in want.items():
            with self.subTest(site=i):
                self.assertIn(snippet, M.mutate_source(SRC, i))

    def test_a_mutation_replaces_only_its_own_site(self):
        out = M.mutate_source(SRC, 3)
        self.assertIn("a == b and (not c)", out)     # unparse parenthesises
        self.assertIn("raise ValueError('x')", out)

    def test_statement_deletions_leave_a_valid_pass(self):
        for i, s in enumerate(M.list_sites(LOOP)):
            if s.desc.endswith("-> pass") or s.desc.startswith("delete"):
                with self.subTest(site=s.desc):
                    out = M.mutate_source(LOOP, i)
                    self.assertIn("pass", out)
                    compile(out, "x", "exec")

    def test_an_if_can_be_forced_either_way_independently(self):
        a = M.mutate_source("if x:\n    pass\n", 0)
        b = M.mutate_source("if x:\n    pass\n", 1)
        self.assertIn("if True", a)
        self.assertIn("if False", b)


TOY = textwrap.dedent('''
    def small(n):
        """True for n below ten."""
        if n < 10:
            return True
        return False
''')
HEAD = textwrap.dedent('''
    import sys, unittest
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from executor import toy

    class T(unittest.TestCase):
        def test_boundary(self):
''')


def suite(*statements: str) -> str:
    """A toy test module whose single test runs `statements`. Built line by
    line on purpose: patching a template with str.replace is silent when the
    target text does not match, which would turn a 'weak suite' into a copy
    of the strong one and make the leak tests pass vacuously."""
    return HEAD + "".join(f"        {s}\n" for s in statements)


STRONG = suite("self.assertIs(toy.small(9), True)",
               "self.assertIs(toy.small(10), False)",
               "self.assertIs(toy.small(0), True)",
               "self.assertIs(toy.small(11), False)")
WEAK = suite("self.assertTrue(toy.small(1))")
BROKEN = suite("self.assertIs(toy.small(9), False)")
HANGING = suite("import time", "time.sleep(30)")


class ToyCase(unittest.TestCase):
    """A throwaway project to mutate. Owns no tests, so the classes built on
    it do not run each other's tests twice."""

    def project(self, test_source: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "engine" / "executor").mkdir(parents=True)
        (root / "engine" / "tests").mkdir()
        (root / "engine" / "executor" / "__init__.py").write_text("")
        (root / "engine" / "executor" / "toy.py").write_text(TOY)
        (root / "engine" / "tests" / "test_toy.py").write_text(test_source)
        return root

    def snapshot(self, root: Path) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        M._snapshot(root, Path(tmp.name))
        return Path(tmp.name)

    def results(self, root: Path):
        return M.run(root, ["engine/executor/toy.py"], workers=2,
                     timeout=30)


class ToyProject(ToyCase):
    """The tool run end to end against a toy project."""

    def test_a_strong_suite_kills_every_mutant(self):
        res = self.results(self.project(STRONG))
        self.assertTrue(res)
        self.assertEqual({r.status for r in res} - {"invalid"}, {"killed"})

    def test_a_weak_suite_is_caught_leaking_at_the_boundary(self):
        res = self.results(self.project(WEAK))
        survivors = {r.site.desc for r in res if r.status == "survived"}
        self.assertIn("10 -> 11", survivors)        # n < 11 passes small(1)
        self.assertIn("if-test -> True", survivors)
        killed = {r.site.desc for r in res if r.status == "killed"}
        self.assertIn("< -> >=", killed)            # flips small(1): caught

    def test_a_suite_that_fails_before_mutation_is_refused(self):
        with self.assertRaises(M.BaselineFailure):
            self.results(self.project(BROKEN))

    def test_missing_tests_for_a_target_are_a_clear_error(self):
        root = self.project(STRONG)
        with self.assertRaises(SystemExit) as err:
            M.run(root, ["engine/executor/__init__.py"], workers=1)
        self.assertIn("no tests found", str(err.exception))

    def test_the_default_tests_are_the_modules_own(self):
        root = self.project(STRONG)
        (root / "engine" / "tests" / "test_toy_more.py").write_text("")
        (root / "engine" / "tests" / "test_other.py").write_text("")
        self.assertEqual(M.default_tests(root, "engine/executor/toy.py"),
                         ["test_toy", "test_toy_more"])

    def test_a_hanging_mutant_counts_as_detected(self):
        copy = self.snapshot(self.project(HANGING))
        self.assertEqual(M._run_tests(copy, ["test_toy"], timeout=0.5),
                         "timeout")

    def test_the_four_toy_suites_are_genuinely_different(self):
        self.assertEqual(len({STRONG, WEAK, BROKEN, HANGING}), 4)

    def test_the_limit_caps_the_number_of_mutants(self):
        res = M.run(self.project(STRONG), ["engine/executor/toy.py"],
                    workers=1, timeout=30, limit=2)
        self.assertEqual(len(res), 2)

    def test_a_mutation_that_cannot_compile_is_invalid_not_scored(self):
        real = M.mutate_source
        M.mutate_source = lambda *_args: "def (:\n"   # type: ignore
        self.addCleanup(setattr, M, "mutate_source", real)
        res = M.run(self.project(STRONG), ["engine/executor/toy.py"],
                    workers=1, timeout=30, limit=1)
        self.assertEqual([r.status for r in res], ["invalid"])


class ReportTests(unittest.TestCase):
    SITE = M.Site(7, "== -> !=")

    def result(self, status="survived", rel="a.py"):
        return M.Result(rel, self.SITE, "if x == y:", status)

    def test_a_survivor_is_unexplained_without_an_allowlist_entry(self):
        text, n = M.report([self.result()], [])
        self.assertEqual(n, 1)
        self.assertIn("SURVIVED a.py:7 == -> !=  | if x == y:", text)

    def test_an_allowlisted_survivor_shows_its_reason_and_does_not_fail(self):
        allow = [{"file": "a.py", "code": "if x == y:",
                  "mutation": "== -> !=", "why": "x and y are the same obj"}]
        text, n = M.report([self.result()], allow)
        self.assertEqual(n, 0)
        self.assertIn("why: x and y are the same obj", text)

    def test_the_allowlist_matches_on_text_not_line_number(self):
        shifted = M.Result("a.py", M.Site(99, "== -> !="), "if x == y:",
                           "survived")
        allow = [{"file": "a.py", "code": "if x == y:",
                  "mutation": "== -> !=", "why": "same"}]
        self.assertEqual(M.report([shifted], allow)[1], 0)

    def test_the_score_counts_timeouts_as_caught_and_ignores_invalid(self):
        res = [self.result("killed"), self.result("timeout"),
               self.result("survived"), self.result("invalid")]
        text, _ = M.report(res, [])
        self.assertIn("3 mutants, 2 caught (1 by timeout), 1 survived, "
                      "1 invalid: score 66.7%", text)

    def test_a_file_with_no_scored_mutants_scores_one_hundred(self):
        text, n = M.report([self.result("invalid")], [])
        self.assertIn("score 100.0%", text)
        self.assertEqual(n, 0)

    def test_files_are_reported_separately_and_in_order(self):
        text, _ = M.report([self.result("killed", "b.py"),
                            self.result("killed", "a.py")], [])
        self.assertLess(text.index("a.py:"), text.index("b.py:"))

    def test_loading_the_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "allow.json"
            self.assertEqual(M.load_allow(path), [])
            self.assertEqual(M.load_allow(None), [])
            good = [{"file": "a", "code": "b", "mutation": "c", "why": "d"}]
            path.write_text(json.dumps(good), encoding="utf-8")
            self.assertEqual(M.load_allow(path), good)
            path.write_text(json.dumps([{"file": "a"}]), encoding="utf-8")
            with self.assertRaises(SystemExit):
                M.load_allow(path)


class MainTests(ToyCase):
    def main(self, root: Path, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = M.main(["engine/executor/toy.py", "--root", str(root),
                         "--workers", "2", "--timeout", "30", *extra])
        return rc, out.getvalue(), err.getvalue()

    def test_exit_zero_when_everything_is_killed(self):
        rc, out, _ = self.main(self.project(STRONG))
        self.assertEqual(rc, 0)
        self.assertIn("score 100.0%", out)

    def test_exit_one_and_the_survivors_listed_for_a_weak_suite(self):
        rc, out, _ = self.main(self.project(WEAK))
        self.assertEqual(rc, 1)
        self.assertIn("SURVIVED engine/executor/toy.py", out)

    def test_exit_two_when_the_baseline_fails(self):
        rc, _, err = self.main(self.project(BROKEN))
        self.assertEqual(rc, 2)
        self.assertIn("baseline failure", err)

    def test_an_allowlist_can_explain_every_survivor(self):
        root = self.project(WEAK)
        _, out, _ = self.main(root)
        entries = []
        for line in out.splitlines():
            if line.startswith("  SURVIVED"):
                head, _, code = line.partition("  | ")
                entries.append({
                    "file": "engine/executor/toy.py", "code": code,
                    "mutation": head.split(" ", 4)[-1].strip(),
                    "why": "toy"})
        allow = root / "allow.json"
        allow.write_text(json.dumps(entries), encoding="utf-8")
        rc, _, _ = self.main(root, "--allow", str(allow))
        self.assertEqual(rc, 0)


def site(source: str, desc: str) -> int:
    """The traversal index of the mutation named `desc` in `source`."""
    return [s.desc for s in M.list_sites(source)].index(desc)


class RemainingBranchTests(ToyCase):
    """Branches the toy-project runs never reach."""

    def test_an_augmented_assignment_flips_in_both_directions(self):
        for src, desc, want in (("x += y", "+= -> -=", "x -= y"),
                                ("x -= y", "-= -> +=", "x += y")):
            with self.subTest(src=src):
                self.assertEqual(M.mutate_source(src, site(src, desc)), want)

    def test_a_while_loop_can_be_skipped_entirely(self):
        src = "while c:\n    y = 1\n"
        out = M.mutate_source(src, site(src, "while-test -> False"))
        self.assertIn("while False:", out)
        self.assertIn("y = 1", out)

    def test_a_snapshot_copies_files_and_directories_but_not_bytecode(self):
        root = self.project(STRONG)
        (root / "README.md").write_text("readme", encoding="utf-8")
        (root / "pyproject.toml").write_text("[x]", encoding="utf-8")
        cache = root / "engine" / "executor" / "__pycache__"
        cache.mkdir()
        (cache / "toy.pyc").write_bytes(b"x")
        (root / "engine" / "executor" / "stale.pyc").write_bytes(b"x")
        dest = self.snapshot(root)
        self.assertEqual((dest / "README.md").read_text(encoding="utf-8"),
                         "readme")
        self.assertTrue((dest / "pyproject.toml").is_file())
        self.assertTrue((dest / "engine" / "executor" / "toy.py").is_file())
        self.assertFalse((dest / "engine" / "executor" / "__pycache__").exists())
        self.assertFalse((dest / "engine" / "executor" / "stale.pyc").exists())
        self.assertFalse((dest / "scripts").exists())     # absent: skipped

    def test_default_tests_normalise_hyphens_in_the_script_name(self):
        root = self.project(STRONG)
        (root / "engine" / "tests" / "test_lint_thing.py").write_text("")
        self.assertEqual(M.default_tests(root, "scripts/lint-thing.py"),
                         ["test_lint_thing"])

    def test_the_entry_point_reports_a_usage_error(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(run_as_main("mutate.py"), 2)
        self.assertIn("targets", err.getvalue())


if __name__ == "__main__":
    unittest.main()
