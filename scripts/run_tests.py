#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Run the whole suite under branch coverage and hold the 100% floor.

    python scripts/run_tests.py             tests + coverage; fails below 100%
    python scripts/run_tests.py --no-cover  tests only (fast edit loop)
    python scripts/run_tests.py -k paths    only matching tests; the floor is
                                            reported but not enforced

Pure Python, no shell: the identical command runs on macOS, Linux and
Windows. Exit 0 when green, 1 on a failing test or a coverage shortfall,
2 when `coverage` is not installed (pip install -r requirements-dev.txt).
"""
from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "engine" / "tests"
FLOOR = 100.0


def run_suite(pattern: str | None) -> bool:
    loader = unittest.TestLoader()
    if pattern:
        loader.testNamePatterns = [f"*{pattern}*"]
    suite = loader.discover(str(TESTS), top_level_dir=str(TESTS))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-cover", action="store_true",
                    help="run the tests without measuring coverage")
    ap.add_argument("-k", dest="pattern", default=None,
                    help="only run tests whose name contains this text")
    args = ap.parse_args(argv)

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "engine"))

    if args.no_cover:
        return 0 if run_suite(args.pattern) else 1

    try:
        import coverage
    except ImportError:
        print("coverage is not installed: "
              "pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    cov = coverage.Coverage(config_file=str(ROOT / "pyproject.toml"))
    cov.start()
    try:
        ok = run_suite(args.pattern)
    finally:
        cov.stop()
        cov.save()
    pct = cov.report(show_missing=True)
    if not ok:
        return 1
    if args.pattern:
        return 0
    if pct < FLOOR:
        print(f"coverage {pct:.2f}% is below the {FLOOR:.0f}% floor",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
