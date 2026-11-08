#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Run the whole suite under branch coverage and hold the 100% floor.

    python scripts/run_tests.py             tests + coverage; fails below 100%
    python scripts/run_tests.py --no-cover  tests only (fast edit loop)
    python scripts/run_tests.py -k paths    only matching tests; the floor is
                                            reported but not enforced
    python scripts/run_tests.py --shard 2/4 run one deterministic shard of the
                                            suite, so a slow platform can split
                                            the work across parallel jobs

Pure Python, no shell: the identical command runs on macOS, Linux and
Windows. Exit 0 when green, 1 on a failing test or a coverage shortfall,
2 when `coverage` is not installed (pip install -r requirements-dev.txt).
"""
from __future__ import annotations

import argparse
import os
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "engine" / "tests"
FLOOR = 100.0


def flatten(suite) -> list[unittest.TestCase]:
    tests = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(flatten(item))
        else:
            tests.append(item)
    return tests


def select_shard(tests: list[unittest.TestCase], spec: str) -> list[unittest.TestCase]:
    """`I/N` keeps the tests whose id hashes into bucket I-1. The split is
    deterministic across platforms and processes, so a shard never overlaps
    another and no test is dropped."""
    try:
        index, count = (int(part) for part in spec.split("/", 1))
    except ValueError:
        raise SystemExit("--shard expects I/N, for example 2/4")
    if count < 1 or not 1 <= index <= count:
        raise SystemExit(f"--shard {spec}: index must be within 1..{count}")
    return [t for t in tests if zlib.crc32(t.id().encode()) % count == index - 1]


def run_suite(pattern: str | None, shard: str | None = None) -> bool:
    loader = unittest.TestLoader()
    if pattern:
        loader.testNamePatterns = [f"*{pattern}*"]
    suite = loader.discover(str(TESTS), top_level_dir=str(TESTS))
    if shard:
        suite = unittest.TestSuite(select_shard(flatten(suite), shard))
    return unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-cover", action="store_true",
                    help="run the tests without measuring coverage")
    ap.add_argument("-k", dest="pattern", default=None,
                    help="only run tests whose name contains this text")
    ap.add_argument("--shard", default=None, metavar="I/N",
                    help="run shard I of N (deterministic split by test id)")
    args = ap.parse_args(argv)

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "engine"))

    if args.no_cover:
        return 0 if run_suite(args.pattern, args.shard) else 1

    try:
        import coverage
    except ImportError:
        print("coverage is not installed: "
              "pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    cov = coverage.Coverage(config_file=str(ROOT / "pyproject.toml"))
    cov.start()
    try:
        ok = run_suite(args.pattern, args.shard)
    finally:
        cov.stop()
        cov.save()
    pct = cov.report(show_missing=True)
    if not ok:
        return 1
    if args.pattern or args.shard:
        # A filtered or sharded run never covers the whole program; the floor
        # belongs to the full run.
        return 0
    if pct < FLOOR:
        print(f"coverage {pct:.2f}% is below the {FLOOR:.0f}% floor",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
