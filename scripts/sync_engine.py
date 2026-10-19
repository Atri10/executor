#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Mirror `engine/executor/` into the skill that ships it.

The skills call a bare `executor` command. Nothing puts one on `PATH`, so
the engine travels inside the router skill at
`skills/executor/scripts/lib/executor/` and the launcher beside it resolves
that copy relative to itself. Users run the bundle; this repository tests
`engine/executor/`. Two copies of one package drift the moment an edit
lands in one, so this script is the only writer of the bundle and
`--check` is the gate that keeps them identical.

    python scripts/sync_engine.py            rewrite the bundled copy
    python scripts/sync_engine.py --check    exit 1 if it differs

Exit 0 clean, 1 drifted (check mode), 2 when the source is missing.
"""
from __future__ import annotations

import argparse
import filecmp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "engine" / "executor"
BUNDLE = ROOT / "skills" / "executor" / "scripts" / "lib" / "executor"


def modules(directory: Path) -> dict[str, Path]:
    """The shipped modules, by name. `__pycache__` is residue from running
    the engine here, not something a user installs."""
    return {p.name: p for p in sorted(directory.glob("*.py")) if p.is_file()}


def drift() -> list[str]:
    """Every way the bundle disagrees with the source, as readable lines."""
    src, dst = modules(SOURCE), modules(BUNDLE)
    problems = [f"missing from the bundle: {name}"
                for name in sorted(set(src) - set(dst))]
    problems += [f"not in the engine source: {name}"
                 for name in sorted(set(dst) - set(src))]
    problems += [f"stale in the bundle: {name}"
                 for name in sorted(set(src) & set(dst))
                 if not filecmp.cmp(src[name], dst[name], shallow=False)]
    return problems


def sync() -> list[str]:
    """Rewrite the bundle to match the source. Returns what changed, with a
    leading `-` for a removed module, so a caller can print it."""
    BUNDLE.mkdir(parents=True, exist_ok=True)
    src, dst = modules(SOURCE), modules(BUNDLE)
    changed = []
    for name in sorted(src):
        target = BUNDLE / name
        if name in dst and filecmp.cmp(src[name], target, shallow=False):
            continue
        target.write_bytes(src[name].read_bytes())
        changed.append(name)
    for name in sorted(set(dst) - set(src)):
        (BUNDLE / name).unlink()
        changed.append(f"-{name}")
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report drift instead of writing it")
    args = ap.parse_args(argv)

    if not SOURCE.is_dir():
        print(f"engine source missing: {SOURCE}", file=sys.stderr)
        return 2
    if args.check:
        problems = drift()
        if problems:
            print("\n".join(problems), file=sys.stderr)
            print("the bundled engine is stale: run "
                  "python scripts/sync_engine.py", file=sys.stderr)
            return 1
        print("bundled engine: in sync")
        return 0
    changed = sync()
    print("\n".join(changed) if changed else "bundled engine: already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
