# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Live engine fixtures: a throwaway git repository holding one initiative, and
a driver that plays the pump (polls the engine) and a cooperative worker
(answers each dispatch with a schema-valid payload that matches the git state).

Test code only. It lets a test start from a real state (a dispatch, a gate, a
review) without re-scripting every phase by hand."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import _payloads as PL
from executor.engine import create_initiative, emit_next, ingest
from executor.store import read_events

_GIT_IDENTITY = ["-c", "user.email=engine@example.invalid", "-c", "user.name=engine"]


def _artifact(kind: str) -> dict:
    if kind == "plan":
        return PL.plan_payload()
    if kind == "vrfy":
        return PL.vrfy_payload()
    return PL.art(kind)


class Live:
    """One initiative in a throwaway git repository."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.git("init", "-q")
        self.git("commit", "-q", "--allow-empty", "-m", "init")
        self.init = create_initiative(self.root, "live")
        self._changes = 0

    def close(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *_GIT_IDENTITY, *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def land_change(self) -> str:
        """Commit one new file on HEAD, the way a worker's change lands."""
        self._changes += 1
        (self.root / f"change{self._changes}.txt").write_text(
            f"{self._changes}\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"change {self._changes}")
        return self.git("rev-parse", "HEAD")

    def events(self) -> list[dict]:
        return read_events(self.init.idir)

    def act(self, now: float | None = None) -> dict:
        return emit_next(self.init, now=now)

    def answer(self, act: dict) -> dict:
        """The payload a cooperative worker writes for this dispatch."""
        role, schema, ent, ctx = act["role"], act["schema"], act["entity"], act["context"]
        if role in ("author", "repair"):
            return _artifact(schema)
        if role == "audit":
            return PL.audit(target=ent, rnd=ctx["round"])
        if role in ("impl", "fix"):
            return PL.report(task=ent, commits=(self.land_change(),))
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
            if kind == "PHASE-ENTER":
                continue
            if kind == "DISPATCH":
                ingest(self.init, self.answer(act))
            elif kind == "GATE":
                ingest(self.init, PL.gate(phase=act["phase"]), actor="human")
            elif kind == "MERGE":
                ingest(self.init, PL.merge(plan=act["plan"],
                                           sha=self.git("rev-parse", "HEAD")))
            else:
                return act
        raise AssertionError("the run did not settle within the poll limit")
