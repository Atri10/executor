# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Live engine fixtures: a throwaway git repository holding one initiative, and
a driver that plays the pump (polls the engine) and a cooperative worker
(answers each dispatch with a schema-valid payload that matches the git state).

Test code only. It lets a test start from a real state (a dispatch, a gate, a
review) without re-scripting every phase by hand.

Hermetic git: every test repository ignores the developer's global and system
git configuration. A global `commit.gpgsign` with an interactive signer (a
hardware key, a password manager) blocks a non-interactive test forever, so
signing is off and the identity is fixed here, on every platform. Every test
module that runs git goes through `hermetic_git`."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import _payloads as PL
from executor.engine import create_initiative, emit_next, ingest
from executor.store import read_events

_GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0"}
_GIT_IDENTITY = ["-c", "user.email=engine@example.invalid", "-c", "user.name=engine",
                 "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
                 # Never launch a detached gc or maintenance task: a background
                 # collector can write into the repo while tearDown removes the
                 # temp directory (OSError 66, directory not empty).
                 "-c", "gc.auto=0", "-c", "maintenance.auto=false"]


def hermetic_git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """One git call in a test repository. The caller decides what a failure means,
    so a test can assert on a non-zero return code."""
    return subprocess.run(["git", "-C", str(root), *_GIT_IDENTITY, *args],
                          capture_output=True, text=True, env=_GIT_ENV)


def _artifact(kind: str, ent: str) -> dict:
    """A cooperative draft of `kind`, carrying the id the dispatch asked for."""
    if kind == "plan":
        return PL.plan_payload(pid=ent)
    if kind == "vrfy":
        return PL.vrfy_payload()
    return PL.art(kind)


class Live:
    """One initiative in a throwaway git repository."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.git("init", "-q", "-b", "integration")
        # The stores are engine state, not source: excluded from git so a
        # checkout between branches is not blocked by a journal write, and so
        # `land_change` commits only the code a worker would commit.
        (self.root / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (self.root / ".git" / "info" / "exclude").write_text(
            ".executor/\ndocs/\n", encoding="utf-8")
        self.git("commit", "-q", "--allow-empty", "-m", "feat: init")
        self.init = create_initiative(self.root, "live")
        self._changes = 0

    def close(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        done = hermetic_git(self.root, *args)
        done.check_returncode()
        return done.stdout.strip()

    def branch_at(self, name: str, base: str | None = None) -> None:
        """Check out `name`, forked from `base` (default: HEAD)."""
        if base is None:
            self.git("checkout", "-q", "-B", name)
        else:
            self.git("checkout", "-q", "-B", name, base)

    def land_change(self, branch: str | None = None) -> str:
        """Commit one new file on HEAD (or on `branch`), the way a worker's
        change lands: a conventional subject, on the task's own branch."""
        if branch is not None:
            self.branch_at(branch)
        self._changes += 1
        (self.root / f"change{self._changes}.txt").write_text(
            f"{self._changes}\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"feat: change {self._changes}")
        return self.git("rev-parse", "HEAD")

    def events(self) -> list[dict]:
        return read_events(self.init.idir)

    def dispatch_with_stamp(self, act: dict, stamp: str) -> dict:
        """Append a second record of the open dispatch `act` whose timestamp is
        `stamp`, through the store, so the journal chain stays valid. The fold reads
        the dispatch from the latest such record, so this is the fault the engine
        must survive: a dispatch it can no longer date."""
        from executor.store import append_event, make_event
        ev = make_event(self.init.idir, "engine", "task_dispatched", act["entity"],
                        {"role": act["role"], "schema": act["schema"],
                         "respond_to": act["respond_to"], "base": act["base"],
                         "context": act["context"]},
                        dispatch_id=act["dispatch_id"])
        ev["ts"] = stamp
        ev.pop("line_sha", None)
        from executor.store import sha256
        ev["line_sha"] = sha256({k: v for k, v in ev.items() if k != "line_sha"})
        append_event(self.init.idir, ev)
        self.init.events.append(ev)
        return ev

    def act(self, now: float | None = None) -> dict:
        return emit_next(self.init, now=now)

    def answer(self, act: dict) -> dict:
        """The payload a cooperative worker writes for this dispatch."""
        role, schema, ent, ctx = act["role"], act["schema"], act["entity"], act["context"]
        if role in ("author", "repair"):
            return _artifact(schema, ent)
        if role == "audit":
            return PL.audit(target=ent, rnd=ctx["round"])
        if role in ("impl", "fix"):
            branch = f"task/{ent}"
            return PL.report(task=ent, commits=(self.land_change(branch),),
                             branch=branch)
        if role == "review":
            return PL.verdict(task=ent, rnd=ctx["round"], base=ctx["base"],
                              head=ctx["head"],
                              reviewed_package_sha=ctx["package_sha"])
        if role == "evidence":
            return PL.evidence(criterion=ent, commit=self.git("rev-parse", "HEAD"))
        raise AssertionError(f"no cooperative answer for role {role!r}")

    def run(self, stop, limit: int = 200) -> dict:
        """Poll and answer until `stop(action)` holds, or until the engine asks
        for something a cooperative worker cannot give (ASK, HALT, ESCALATE)."""
        for _ in range(limit):
            act = self.act()
            if stop(act):
                return act
            kind = act["action"]
            if kind in ("PHASE-ENTER", "CHANGE-SCOPE", "CHANGE-DONE"):
                continue
            if kind == "DISPATCH":
                ingest(self.init, self.answer(act))
            elif kind == "GATE":
                ingest(self.init, PL.gate(phase=act["phase"]), actor="human")
            elif kind == "MERGE":
                branch = f"plan/{act['plan']}"
                self.branch_at(branch)
                ingest(self.init, PL.merge(plan=act["plan"],
                                           sha=self.git("rev-parse", "HEAD"),
                                           branch=branch))
            else:
                return act
        raise AssertionError("the run did not settle within the poll limit")
