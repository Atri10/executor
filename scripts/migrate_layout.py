#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Convert an executor store to the current layout.

Usage:
    python3 scripts/migrate_layout.py <repo-root> [INIT] --dry-run
    python3 scripts/migrate_layout.py <repo-root> [INIT] --apply

`--dry-run` prints every write and removal and touches nothing. `--apply`
writes the projections, removes the files the grammar no longer admits,
stamps the store version, and then verifies: every file classifies, every
required file exists, the committed index equals a fresh render, and the
journal chain verifies. It is byte-idempotent: a second `--apply` rewrites
identical bytes and removes nothing.

This is the same implementation the skill ships (`executor migrate
--dry-run|--apply`); the engine is imported from `engine/` so there is one
copy of the logic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from executor.migrate import migrate_layout          # noqa: E402
from executor.store import ExecError, find_initiative  # noqa: E402


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print((__doc__ or "").strip())
        return 0
    paths = [a for a in argv if not a.startswith("--")]
    apply_ = "--apply" in argv
    if not paths:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    repo, ident = Path(paths[0]).resolve(), (paths[1] if len(paths) > 1 else None)
    try:
        init = find_initiative(repo, ident, gate=False)
        result = migrate_layout(init, dry_run=not apply_)
    except ExecError as err:
        print(json.dumps({"code": err.code, "message": str(err)}, indent=2))
        return 1
    result["mode"] = "apply" if apply_ else "dry-run"
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
