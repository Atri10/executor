# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Store layout migration: v1 projections -> v2 projections.

A migration is a projection change, never a data change: the journal is read
and folded, and every file written is a pure function of it. That is what makes
the migration deterministic and byte-idempotent — running it twice rewrites
identical bytes and removes nothing the second time.

    executor migrate --dry-run          what would change, touching nothing
    executor migrate --apply            write it, then verify

`scripts/migrate_layout.py` calls the same function, so there is one
implementation and no second copy to drift.
"""
from __future__ import annotations

from pathlib import Path

from . import STORE_VERSION, __version__
from . import engine as E
from . import views as V
from .paths import (classify, docs_init_dir, docs_root, meta_file,
                    run_meta_file, run_root)
from .schemas import ARTIFACT_KINDS
from .store import (ExecError, Initiative, atomic_write, layout_major,
                    read_events, read_json, write_json)


def _latest_payloads(events: list[dict]) -> dict[str, dict]:
    """The newest payload of every artifact, straight from the journal. The fold
    keeps a distilled record — enough to decide, not enough to project — so the
    migration reads the truth."""
    out: dict[str, dict] = {}
    for ev in events:
        # `plan` is not in ARTIFACT_KINDS but it is an artifact payload; the
        # journal stores the payload without its `kind`, which the event carries
        if ev["kind"] in ARTIFACT_KINDS or ev["kind"] == "plan":
            out[ev["entity"]] = {**(ev.get("data") or {}), "kind": ev["kind"],
                                 "v": ev.get("v", "v1")}
    return out


def _files_under(init: Initiative) -> list[Path]:
    out: list[Path] = []
    for base in (init.idir, docs_init_dir(init.root, init.id)):
        if base.exists():
            out += [f for f in sorted(base.rglob("*")) if f.is_file()]
    return out


def _non_canonical(init: Initiative) -> list[Path]:
    """Every file the current grammar does not admit: the v1 flat verdict
    views, a stray slot.json, a hand-placed file."""
    out: list[Path] = []
    run, docs = run_root(init.root), docs_root(init.root)
    for f in _files_under(init):
        try:
            rel, store = f.relative_to(run), "run"
        except ValueError:
            rel, store = f.relative_to(docs), "docs"
        if classify(rel, store) is None:
            out.append(f)
    return out


def plan(init: Initiative) -> dict:
    """Every write and every removal, computed without touching the disk."""
    events = read_events(init.idir)
    s = E.fold(events)
    payloads = _latest_payloads(events)
    writes: dict[Path, str] = {}
    for aid in sorted(payloads):
        p = payloads[aid]
        if p.get("kind") == "plan":
            writes.update(E._plan_files(init, p))
    writes.update(V.render_plan(init))
    writes.update(E.index_files(init, s))
    for cid, c in sorted(s["changes"].items()):
        writes.update(E.change_files(init, cid, c))
    return {"initiative": init.id, "writes": writes,
            "removes": _non_canonical(init)}


def migrate_layout(init: Initiative, *, dry_run: bool = True) -> dict:
    """Convert one store to the current layout. Returns what it did (or would
    do) and, on apply, the verification verdict."""
    init.reload()
    meta = read_json(meta_file(init.idir)) or {}
    # A store with no layout record predates the version field: its shape is
    # unknown, and guessing would write v2 projections into a tree this engine
    # cannot read. Refuse, and say which store it is.
    if layout_major(meta.get("store_version", "v0")) < 1:
        raise ExecError(
            f"store has no layout version (engine "
            f"v{meta.get('engine_version', 'unknown')}); this engine migrates "
            f"v1 layouts only", "store_outdated")
    work = plan(init)
    was_current = (str(meta.get("store_version", "")) == STORE_VERSION
                   and str(meta.get("engine_version", "")) == __version__)
    result = {"initiative": init.id, "dry_run": dry_run,
              "store_version_before": meta.get("store_version"),
              "engine_version_before": meta.get("engine_version"),
              "already_current": was_current,
              "writes": sorted(p.relative_to(init.root).as_posix()
                               for p in work["writes"]),
              "removes": sorted(p.relative_to(init.root).as_posix()
                                for p in work["removes"])}
    if dry_run:
        return result
    for path, text in work["writes"].items():
        atomic_write(path, text.encode("utf-8"))
    for path in work["removes"]:
        path.unlink()
    stamped = {**meta, "store_version": STORE_VERSION,
               "engine_version": __version__}
    write_json(meta_file(init.idir), stamped)
    write_json(run_meta_file(init.root), {
        "engine_version": stamped["engine_version"],
        "schema_version": stamped.get("schema_version", "v1"),
        "store_version": stamped["store_version"]})
    init.reload()
    s = E.fold(init.events)
    problems = (E._layout_problems(init) + E._missing_problems(init, s)
                + E._projection_problems(init, s))
    result.update({"written": len(work["writes"]),
                   "removed": len(work["removes"]),
                   "store_version_after": STORE_VERSION,
                   "engine_version_after": __version__,
                   "verified": not problems, "problems": problems})
    if problems:
        raise ExecError("migration verification failed: "
                        + "; ".join(problems), "migration_failed")
    return result
