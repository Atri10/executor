#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Mutation testing with the standard library only.

Line coverage proves a line RAN; it does not prove a test would notice if the
line were wrong. This tool changes the code one small way at a time (flip a
comparison, swap and/or, drop a `not`, delete a call, turn a `raise` into
`pass`, change a constant, force an `if` one way) and runs the tests against
each change. A mutant the tests still pass is a SURVIVOR: a behavior nobody
asserts. Survivors are either missing assertions (add one) or genuinely
equivalent changes (record them in the allowlist with the reason).

    python scripts/mutate.py engine/executor/store.py
    python scripts/mutate.py engine/executor/paths.py --tests test_paths
    python scripts/mutate.py engine/executor/store.py --allow scripts/mutation-allow.json

Tests default to `test_<module>*` for each target, the strictest reading: a
module's own suite must stand on its own. Pure Python, threads over private
copies of the tree, no shell: identical on macOS, Linux and Windows.
Exit 0 when nothing unexplained survives, 1 otherwise, 2 on bad input.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# What a mutant's private copy needs so every test module can import and run.
COPY = ("engine", "scripts", "skills", "README.md", "CONTRIBUTING.md",
        ".github", "pyproject.toml")

_SYM = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
        ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not",
        ast.In: "in", ast.NotIn: "not in", ast.Add: "+", ast.Sub: "-"}
_CMP_FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE,
             ast.LtE: ast.Gt, ast.Gt: ast.LtE, ast.GtE: ast.Lt,
             ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn,
             ast.NotIn: ast.In}
_ARITH_FLIP = {ast.Add: ast.Sub, ast.Sub: ast.Add}


class BaselineFailure(Exception):
    """The unmodified tests fail, so no mutant result would mean anything."""


@dataclass(frozen=True)
class Site:
    lineno: int
    desc: str


@dataclass(frozen=True)
class Result:
    rel: str
    site: Site
    code: str          # the original source line, stripped
    status: str        # killed | survived | timeout | invalid


class _Mutator(ast.NodeTransformer):
    """One traversal both lists every mutation site and, when `target` is the
    running index, applies exactly that one. Children are visited before their
    parent decides, so the index order is identical in both uses."""

    def __init__(self, target: int | None = None):
        self.target = target
        self.sites: list[Site] = []

    def _at(self, node: ast.AST, desc: str) -> bool:
        idx = len(self.sites)
        self.sites.append(Site(getattr(node, "lineno", 0), desc))
        return idx == self.target

    def visit_Compare(self, node):
        self.generic_visit(node)
        flip = _CMP_FLIP.get(type(node.ops[0]))
        if flip and self._at(node, f"{_SYM[type(node.ops[0])]} -> "
                                   f"{_SYM[flip]}"):
            node.ops[0] = flip()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        was_and = isinstance(node.op, ast.And)
        if self._at(node, "and -> or" if was_and else "or -> and"):
            node.op = ast.Or() if was_and else ast.And()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._at(node, "drop 'not'"):
            return node.operand
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        flip = _ARITH_FLIP.get(type(node.op))
        if flip and self._at(node, f"{_SYM[type(node.op)]} -> {_SYM[flip]}"):
            node.op = flip()
        return node

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        flip = _ARITH_FLIP.get(type(node.op))
        if flip and self._at(node, f"{_SYM[type(node.op)]}= -> "
                                   f"{_SYM[flip]}="):
            node.op = flip()
        return node

    def visit_Constant(self, node):
        value = node.value
        if isinstance(value, bool):
            if self._at(node, f"{value} -> {not value}"):
                node.value = not value
        elif isinstance(value, int):
            if self._at(node, f"{value} -> {value + 1}"):
                node.value = value + 1
        return node

    def visit_Return(self, node):
        self.generic_visit(node)
        v = node.value
        bare_none = isinstance(v, ast.Constant) and v.value is None
        if v is not None and not bare_none and \
                self._at(node, "return -> return None"):
            node.value = ast.Constant(value=None)
        return node

    def visit_If(self, node):
        self.generic_visit(node)
        always = self._at(node, "if-test -> True")
        never = self._at(node, "if-test -> False")
        if always:
            node.test = ast.Constant(value=True)
        if never:
            node.test = ast.Constant(value=False)
        return node

    def visit_While(self, node):
        self.generic_visit(node)
        if self._at(node, "while-test -> False"):
            node.test = ast.Constant(value=False)
        return node

    def _to_pass(self, node, desc):
        self.generic_visit(node)
        if self._at(node, desc):
            return ast.copy_location(ast.Pass(), node)
        return node

    def visit_Raise(self, node):
        return self._to_pass(node, "raise -> pass")

    def visit_Continue(self, node):
        return self._to_pass(node, "continue -> pass")

    def visit_Break(self, node):
        return self._to_pass(node, "break -> pass")

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call):
            return self._to_pass(node, "delete call statement")
        self.generic_visit(node)
        return node


def list_sites(source: str) -> list[Site]:
    m = _Mutator(None)
    m.visit(ast.parse(source))
    return m.sites


def mutate_source(source: str, index: int) -> str:
    tree = ast.parse(source)
    _Mutator(index).visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


# ------------------------------------------------------------- execution

def _snapshot(root: Path, dest: Path) -> None:
    skip = shutil.ignore_patterns("__pycache__", "*.pyc")
    for name in COPY:
        src = root / name
        if src.is_dir():
            shutil.copytree(src, dest / name, ignore=skip)
        elif src.is_file():
            shutil.copy2(src, dest / name)


def _run_tests(workdir: Path, modules: list[str], timeout: float) -> str:
    """killed | survived | timeout, for the tests as they stand in `workdir`."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "-f", *modules],
            cwd=workdir / "engine" / "tests", env=env, timeout=timeout,
            capture_output=True)
    except subprocess.TimeoutExpired:
        return "timeout"
    return "survived" if r.returncode == 0 else "killed"


def default_tests(root: Path, rel: str) -> list[str]:
    stem = Path(rel).stem.replace("-", "_")
    return sorted(p.stem for p in (root / "engine" / "tests").glob(
        f"test_{stem}*.py"))


def run(root: Path, targets: list[str], tests: list[str] | None = None,
        workers: int = 4, timeout: float = 60.0,
        limit: int | None = None) -> list[Result]:
    """Mutate every site of every target and report what the tests did."""
    plan: list[tuple[str, str, list[str]]] = []
    for rel in targets:
        modules = tests or default_tests(root, rel)
        if not modules:
            raise SystemExit(f"no tests found for {rel}: pass --tests")
        plan.append((rel, (root / rel).read_text(encoding="utf-8"), modules))

    with tempfile.TemporaryDirectory() as tmp:
        copies: queue.Queue[Path] = queue.Queue()
        for i in range(workers):
            dest = Path(tmp) / f"w{i}"
            dest.mkdir()
            _snapshot(root, dest)
            copies.put(dest)

        probe = copies.get()
        for rel, _, modules in plan:
            if _run_tests(probe, modules, timeout) != "survived":
                raise BaselineFailure(
                    f"tests {modules} fail before any mutation for {rel}")
        copies.put(probe)

        jobs = [(rel, src, modules, i, site)
                for rel, src, modules in plan
                for i, site in enumerate(list_sites(src))]
        if limit:
            jobs = jobs[:limit]

        def work(job) -> Result:
            rel, src, modules, index, site = job
            code = src.splitlines()[site.lineno - 1].strip()
            try:
                mutated = mutate_source(src, index)
                compile(mutated, rel, "exec")
            except SyntaxError:
                return Result(rel, site, code, "invalid")
            wd = copies.get()
            try:
                (wd / rel).write_text(mutated, encoding="utf-8")
                return Result(rel, site, code,
                              _run_tests(wd, modules, timeout))
            finally:
                (wd / rel).write_text(src, encoding="utf-8")
                copies.put(wd)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(work, jobs))


# ------------------------------------------------------------- reporting

def load_allow(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    for e in entries:
        if not (e.get("file") and e.get("code") and e.get("mutation")
                and e.get("why")):
            raise SystemExit(f"{path}: every entry needs file, code, "
                             f"mutation and why: {e}")
    return entries


def _allowed(r: Result, allow: list[dict]) -> dict | None:
    for e in allow:
        if (e["file"], e["code"], e["mutation"]) == \
                (r.rel, r.code, r.site.desc):
            return e
    return None


def report(results: list[Result], allow: list[dict]) -> tuple[str, int]:
    """(text, unexplained survivor count)."""
    lines: list[str] = []
    unexplained = 0
    for rel in sorted({r.rel for r in results}):
        mine = [r for r in results if r.rel == rel]
        count = {s: sum(r.status == s for r in mine)
                 for s in ("killed", "survived", "timeout", "invalid")}
        scored = len(mine) - count["invalid"]
        caught = count["killed"] + count["timeout"]
        score = 100.0 * caught / scored if scored else 100.0
        lines.append(f"{rel}: {scored} mutants, {caught} caught "
                     f"({count['timeout']} by timeout), "
                     f"{count['survived']} survived, "
                     f"{count['invalid']} invalid: score {score:.1f}%")
        for r in mine:
            if r.status != "survived":
                continue
            why = _allowed(r, allow)
            if why:
                lines.append(f"  allowed  {rel}:{r.site.lineno} "
                             f"{r.site.desc}  | {r.code}\n"
                             f"           why: {why['why']}")
            else:
                unexplained += 1
                lines.append(f"  SURVIVED {rel}:{r.site.lineno} "
                             f"{r.site.desc}  | {r.code}")
    return "\n".join(lines), unexplained


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+", help="source files to mutate")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--tests", nargs="+", default=None,
                    help="test modules (default: test_<module>*)")
    ap.add_argument("--workers", type=int,
                    default=min(8, os.cpu_count() or 2))
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--limit", type=int, default=None,
                    help="only the first N mutants (smoke runs)")
    ap.add_argument("--allow", type=Path, default=None,
                    help="JSON list of explained equivalent survivors")
    args = ap.parse_args(argv)
    try:
        results = run(args.root, args.targets, args.tests, args.workers,
                      args.timeout, args.limit)
    except BaselineFailure as e:
        print(f"baseline failure: {e}", file=sys.stderr)
        return 2
    text, unexplained = report(results, load_allow(args.allow))
    print(text)
    return 1 if unexplained else 0


if __name__ == "__main__":
    sys.exit(main())
