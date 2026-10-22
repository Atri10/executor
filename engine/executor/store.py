# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Durable store mechanics for the executor engine.

The only mutation surface. Everything a run ever records lives here:

- ``events.vN.jsonl`` — append-only, hash-chained journal. The truth.
- ``state.json``        — a rebuildable fold cache, never authoritative.
- ``meta.json``          — engine/schema/store version stamps.
- ``dispatches/``       — prompts and the worker respond_to targets.
- ``views/``             — projections, never sources of truth.

No other module writes to ``.executor/``; all writes funnel through these
helpers so atomicity and the hash chain hold in one place.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import SCHEMA_VERSION, STORE_VERSION, __version__

RUN_STORE = ".executor"
DOCS_STORE = "docs/executor"
JOURNAL_FMT = "events.v{}.jsonl"
GENESIS_SHA = "0" * 64


# ---------------------------------------------------------------- paths

def repo_root(start: Path | None = None) -> Path:
    """Locate the git worktree root, like exec_root()."""
    start = (start or Path.cwd()).resolve()
    for d in [start, *start.parents]:
        if (d / ".git").exists():
            return d
    raise ExecError("not inside a git repository", "exec_root")


# Path helpers live in paths.py — the single naming authority. Re-export
# the ones this module uses so call sites read naturally.
from .paths import (autonomy_file, dispatch_dir, dispatches_dir,
                    docs_root, init_dir, journal_dir, journal_file,
                    lock_file, meta_dir, meta_file, payload_file, prompt_file,
                    run_meta_file, run_root, state_file,
                    task_dir, views_dir, artifact_dir, artifact_file,
                    plan_dir, plan_file, audit_file, repair_file,
                    task_impl_report, review_package_file, verdict_file,
                    fix_package_file, fix_report_file, preflight_file,
                    plan_audit_file, plan_repair_file, docs_init_dir,
                    docs_index_file, docs_index_md, docs_artifact_dir,
                    docs_artifact_file, docs_artifact_md, docs_plan_dir,
                    docs_plan_file, docs_plan_md, docs_task_dir,
                    docs_report_file, docs_verdict_file,
                    docs_export_journal, view_file)


# ---------------------------------------------------------------- errors

class ExecError(Exception):
    """A typed, user-facing engine error. The CLI prints it and exits 2."""

    def __init__(self, msg: str, code: str = "engine_error"):
        super().__init__(msg)
        self.code = code
        self.msg = msg


class Rejection(Exception):
    """A payload validation failure. Carries the structured error the pump
    relays back to the worker — never a stack trace."""
    def __init__(self, code: str, field: str, expected: str, got: str,
                 hint: str = ""):
        super().__init__(f"{code} at {field}: expected {expected}, got {got}")
        self.code, self.field = code, field
        self.expected, self.got, self.hint = expected, got, hint

    def to_dict(self) -> dict:
        return {"code": self.code, "field": self.field,
                "expected": self.expected, "got": self.got,
                "hint": self.hint}


# ---------------------------------------------------------------- json/io

def canonical(obj) -> bytes:
    """Deterministic bytes for hashing/signing a payload."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def atomic_write(path: Path, data: bytes) -> None:
    """Write via tmp+rename so a crash never leaves a torn file. A write that
    fails part-way removes its temp file and leaves the target untouched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def json_text(obj) -> str:
    """The one serialisation of a JSON projection: two-space indent, insertion
    order, trailing newline. Migrations and renderers compare bytes, so this
    must be the only writer."""
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def write_json(path: Path, obj) -> None:
    atomic_write(path, json_text(obj).encode("utf-8"))


def write_json_if_changed(path: Path, obj) -> bool:
    """Write only when the bytes differ. A projection that has not changed costs
    nothing, which is what makes a repeated poll free and a byte comparison
    against a re-render meaningful."""
    data = json_text(obj).encode("utf-8")
    try:
        if path.read_bytes() == data:
            return False
    except OSError:
        pass
    atomic_write(path, data)
    return True


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------- locking

_WINDOWS = os.name == "nt"

# How long a writer waits for the store lock before reporting `store_locked`.
LOCK_WAIT_S = 10.0


def _lock_retry(fd: int, unlock: bool = False) -> None:
    """Take (or release) the Windows byte-range lock. `LK_NBLCK` fails at once
    instead of blocking inside the C runtime for its own timeout, so a writer
    that cannot get the lock reports `store_locked` after LOCK_WAIT_S rather
    than hanging the process. A poll interval of 5ms keeps a contended acquire
    under a millisecond of added latency while leaving no descriptor held for
    the OS's own retry window."""
    import msvcrt
    import time
    os.lseek(fd, 0, os.SEEK_SET)
    if unlock:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.005)


class StoreLock:
    """Single-writer advisory lock on the initiative dir. Context manager.
    flock on POSIX; msvcrt byte-range locking on Windows, which locks from the
    descriptor's current offset, so it is rewound first. Every entry opens its
    own descriptor, which is why the lock excludes threads as well as
    processes. The platform is a module constant so tests can drive both
    branches on any OS."""

    def __init__(self, idir: Path):
        self.path = lock_file(idir)
        self.fd: int = -1

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR)
        try:
            if _WINDOWS:
                _lock_retry(self.fd)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX)
        except OSError as e:
            os.close(self.fd)
            self.fd = -1
            raise ExecError(f"could not lock {self.path}: {e}",
                            "store_locked") from e
        return self

    def __exit__(self, *exc):
        if self.fd < 0:
            return
        try:
            if _WINDOWS:
                _lock_retry(self.fd, unlock=True)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = -1


# ---------------------------------------------------------------- journal

def sha_line(line: bytes) -> str:
    return hashlib.sha256(line.rstrip(b"\n")).hexdigest()


def parse_journal(raw: bytes) -> tuple[list[dict], int]:
    """Parse journal bytes line by line. Returns (events, torn): a non-empty
    line that is not a JSON event object is counted and skipped. It neither
    stops the scan nor is trusted, so a crash mid-append (even one that cut a
    multibyte character in half) can never hide the events written after it.
    `verify_chain` is what notices a gap. Pure, so corruption can be tested
    exhaustively without touching the filesystem."""
    events: list[dict] = []
    torn = 0
    for chunk in raw.split(b"\n"):
        line = chunk.rstrip(b"\r")
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:  # JSONDecodeError and UnicodeDecodeError
            torn += 1
            continue
        if isinstance(ev, dict) and isinstance(ev.get("seq"), int):
            events.append(ev)
        else:
            torn += 1
    return events, torn


def scan_journal(idir: Path) -> tuple[list[dict], int]:
    """The journal file's (events, torn); a missing file is empty."""
    path = journal_file(idir)
    if not path.exists():
        return [], 0
    return parse_journal(path.read_bytes())


def read_events(idir: Path) -> list[dict]:
    return scan_journal(idir)[0]


def verify_chain(events: list[dict]) -> list[str]:
    """Return the integrity violations (empty = clean chain). Every line_sha is
    recomputed from its event body, so an edit to any committed event is
    caught, including the last one, which nothing links to."""
    problems: list[str] = []
    prev = GENESIS_SHA
    for i, ev in enumerate(events):
        if ev.get("seq") != i + 1:
            problems.append(f"event {i+1}: seq {ev.get('seq')} != {i+1}")
        if ev.get("prev_sha") != prev:
            problems.append(f"event seq {ev.get('seq')}: prev_sha mismatch")
        body = {k: v for k, v in ev.items() if k != "line_sha"}
        if sha256(body) != ev.get("line_sha"):
            problems.append(f"event seq {ev.get('seq')}: line_sha mismatch "
                            f"(event edited after commit)")
        prev = ev.get("line_sha") or prev
    return problems


def next_seq(events: list[dict]) -> int:
    return (events[-1]["seq"] + 1) if events else 1


def chain_tip(events: list[dict]) -> str:
    return events[-1]["line_sha"] if events else GENESIS_SHA


def make_event(idir: Path, actor: str, kind: str, entity: str,
               data: dict, dispatch_id: str | None = None,
               payload_sha: str | None = None) -> dict:
    """Build the next chained event (not yet appended)."""
    events = read_events(idir)
    ev = {
        "seq": next_seq(events),
        "ts": now_iso(),
        "v": SCHEMA_VERSION,
        "engine_version": __version__,
        "actor": actor,
        "kind": kind,
        "entity": entity,
        "dispatch_id": dispatch_id,
        "payload_sha": payload_sha,
        "prev_sha": chain_tip(events),
        "data": data,
    }
    ev["line_sha"] = sha256({k: ev[k] for k in ev if k != "line_sha"})
    return ev


def _tail_is_clean(path: Path) -> bool:
    """True when the journal is empty or ends on a newline."""
    if not path.exists() or path.stat().st_size == 0:
        return True
    with open(path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        return f.read(1) == b"\n"


def append_event(idir: Path, ev: dict) -> dict:
    """Append one event to the journal (fsync'd). Caller holds the lock. A
    torn fragment left by a crash is closed off with a newline first, so the
    new event is never glued onto it."""
    path = journal_file(idir)
    path.parent.mkdir(parents=True, exist_ok=True)
    lead = b"" if _tail_is_clean(path) else b"\n"
    line = json.dumps(ev, sort_keys=False, ensure_ascii=False) + "\n"
    with open(path, "ab") as f:
        f.write(lead + line.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    return ev


# ---------------------------------------------------------------- meta

def init_store(root: Path, init_id: str, title: str) -> Path:
    """Scaffold a new initiative store + committed docs dir. Refuses an
    existing initiative: re-scaffolding would reset its meta and autonomy."""
    idir = init_dir(root, init_id)
    if idir.exists():
        raise ExecError(f"{init_id} already exists at {idir}", "exists")
    for d in (idir, journal_dir(idir), meta_dir(idir), dispatches_dir(idir),
              views_dir(idir), docs_init_dir(root, init_id)):
        d.mkdir(parents=True, exist_ok=True)
    write_json(meta_file(idir), {
        "initiative": init_id, "title": title,
        "engine_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "store_version": STORE_VERSION,
        "created_at": now_iso(),
    })
    write_json(run_root(root) / "meta.json", {
        "engine_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "store_version": STORE_VERSION,
    })
    write_json(autonomy_file(idir), {p: "deny" for p in PHASES})
    return idir


def store_version_verdict(engine_version) -> str:
    """Compare a store's engine version with this engine's major version. Pure, so
    the CLI reports the same verdict the engine enforces. The result is one of
    'current', 'store_outdated' (the store is older) or 'engine_too_old' (the store
    is newer than this engine)."""
    ev = str(engine_version)
    if _major(ev) > _major(__version__):
        return "engine_too_old"
    if _major(ev) < _major(__version__):
        return "store_outdated"
    return "current"


def layout_major(version: str) -> int:
    """The numeric part of a store-layout version: v2 -> 2."""
    try:
        return int(str(version).lstrip("v").split(".")[0])
    except (ValueError, IndexError):
        return 0


def check_store_version(idir: Path) -> None:
    """Refuse clearly on version skew rather than misreading a store.

    Two gates, because they mean different things: the *engine* major says
    whether this binary understands the store at all, and the *layout* version
    says whether the projections on disk are the ones this engine writes. A v1
    layout under a v2 engine is readable but not writable — the engine would
    mix two layouts in one tree, which is exactly the half-migrated state the
    layout proposal forbids."""
    meta = read_json(meta_file(idir))
    if meta is None:
        raise ExecError(f"no meta.json in {idir}: not an executor store "
                        f"(or one from before v2). Use `executor new`.",
                        "no_meta")
    ev = str(meta.get("engine_version", "0"))
    verdict = store_version_verdict(ev)
    if verdict == "engine_too_old":
        raise ExecError(
            f"store written by engine v{ev}; you have v{__version__}. "
            f"Install executor ≥ {_major(ev)}.x or run `executor migrate`.",
            "engine_too_old")
    if verdict == "store_outdated":
        raise ExecError(
            f"store written by engine v{ev}; you have v{__version__}. "
            f"Run `executor migrate --dry-run` then `executor migrate --apply`.",
            "store_outdated")
    sv = str(meta.get("store_version", STORE_VERSION))
    if layout_major(sv) < layout_major(STORE_VERSION):
        raise ExecError(
            f"store layout {sv}; this engine writes {STORE_VERSION}. "
            f"Run `executor migrate --dry-run` then `executor migrate --apply`.",
            "store_outdated")


def _major(v: str) -> int:
    try:
        return int(str(v).split(".")[0])
    except (ValueError, IndexError):
        return 0


# Phase order — single source for both the machine and meta init.
PHASES = ["intake", "discovery", "architecture", "design", "specification",
          "planning", "plan_regression", "execution", "review",
          "verification", "handoff"]


@dataclass
class Initiative:
    id: str
    root: Path
    idir: Path
    events: list[dict] = field(default_factory=list)

    @property
    def meta(self) -> dict:
        return read_json(meta_file(self.idir)) or {}

    @property
    def state(self) -> dict:
        return read_json(state_file(self.idir)) or {}

    def reload(self) -> "Initiative":
        self.events = read_events(self.idir)
        return self


def _finished(idir: Path) -> bool:
    """A run is finished once its handoff gate was approved. The cached phase
    alone does not say so: an initiative parked at handoff with the gate still
    open is in flight. A missing or unreadable cache means not finished."""
    state = read_json(state_file(idir))
    phases = state.get("phase_state") if isinstance(state, dict) else None
    return isinstance(phases, dict) and phases.get("handoff") == "passed"


def find_initiative(root: Path, init_id: str | None = None,
                    gate: bool = True) -> Initiative:
    """Resolve an initiative by id, or the one in flight. Two in flight is an
    error, never a silent pick: acting on the wrong initiative is worse than
    asking. When every initiative is finished the newest is returned, so
    status and check still work on a completed run.

    `gate=False` skips the version check. Only `migrate` uses it: it must open a
    skewed store to tell the user what is wrong. Every other command is gated."""
    store = run_root(root)
    if init_id:
        idir = init_dir(root, init_id)
        if not idir.exists():
            raise ExecError(f"no initiative {init_id} at {idir}",
                            "no_initiative")
        if gate:
            check_store_version(idir)
        return Initiative(init_id, root, idir).reload()
    cands = [d for d in sorted(store.glob("INIT-*")) if d.is_dir()]
    if not cands:
        raise ExecError("no initiatives in .executor/ — run `executor new`",
                        "no_initiative")
    actives = [d for d in cands if not _finished(d)]
    if len(actives) > 1:
        names = ", ".join(d.name for d in actives)
        raise ExecError(f"{len(actives)} active initiatives ({names}); "
                        f"pass INIT-ID", "ambiguous")
    pick = actives[0] if actives else cands[-1]
    if gate:
        check_store_version(pick)
    return Initiative(pick.name, root, pick).reload()
