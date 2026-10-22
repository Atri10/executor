#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Measure a store's cost curve: the fold, the cache, and what a projection
costs. Reproduces the numbers recorded in `docs/proposals/layout.md §7` and
`audit.md §4`.

Usage:
    python3 scripts/measure_store.py <.executor/INIT-NNNN directory>

Prints, for prefixes of the journal: the fold time, the serialised size of the
folded state, and the cumulative bytes a whole-state rewrite would have
written. Then the journal's bytes by event kind.
"""
from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from executor.engine import fold  # noqa: E402
from executor.store import read_events  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    idir = Path(argv[0]).resolve()
    events = read_events(idir)
    if not events:
        print("no events in", idir)
        return 1
    marks = {10, 50, 100, 200, 320, len(events)}
    cumulative = 0
    print(f"{'n':>6} {'fold ms':>9} {'state bytes':>12}")
    for n in range(1, len(events) + 1):
        started = time.perf_counter()
        s = fold(events[:n])
        elapsed = (time.perf_counter() - started) * 1000
        size = len(json.dumps(s))
        cumulative += size
        if n in marks:
            print(f"{n:>6} {elapsed:>9.2f} {size:>12}")
    print(f"\ncumulative state bytes written over {len(events)} projections: "
          f"{cumulative / 1e6:.1f} MB")
    by_kind = collections.Counter()
    for line in (idir / "journal" / "events.v1.jsonl").read_bytes().splitlines():
        if line.strip():
            by_kind[json.loads(line)["kind"]] += len(line) + 1
    print(f"journal bytes: {sum(by_kind.values()) / 1e6:.2f} MB")
    for kind, size in by_kind.most_common(8):
        print(f"  {kind:<16} {size / 1e6:>7.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
