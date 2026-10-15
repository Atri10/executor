# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Valid payloads, one definition each, shared by the schema, fold, next and
ingest suites. A suite that needs an invalid payload starts from one of these
and breaks exactly one thing, so a failure always names that one thing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from executor import paths as P  # noqa: E402

INIT = "INIT-0001"
PLAN = f"{INIT}-P01"
TASK = f"{PLAN}-T01"
SEC = [{"id": "s1", "title": "Why", "body": "Because."}]


def art(kind: str, **extra) -> dict:
    """A valid artifact payload of `kind`, carrying that kind's id segment."""
    seg = P.ARTIFACT_SEGMENTS[kind]
    return {"kind": kind, "v": "v1", "id": f"{INIT}-{seg}-01", "title": "t",
            "summary": "s", "sections": SEC, **extra}


def task_row(local: str = "T01", **extra) -> dict:
    return {"id": local, "title": f"task {local}", "goal": "g",
            "files": ["a.py"], "accepts": ["it works"], **extra}


def plan_payload(pid: str = PLAN, tasks: list[dict] | None = None,
                 **extra) -> dict:
    rows = [task_row("T01")] if tasks is None else tasks
    return {"kind": "plan", "v": "v1", "id": pid, "plan_id": pid,
            "title": "t", "summary": "s", "sections": SEC, "objective": "o",
            "tasks": rows, **extra}


def vrfy_payload(*criteria: tuple[str, str], **extra) -> dict:
    rows = [{"id": cid, "criterion": text, "procedure": "run it"}
            for cid, text in (criteria or (("V1", "works"),))]
    return art("vrfy", criteria=rows, **extra)


def finding(fid: str = "F1", severity: str = "important",
            claim: str = "a claim", **extra) -> dict:
    return {"id": fid, "severity": severity, "claim": claim, **extra}


def report(task: str = TASK, commits: tuple[str, ...] = ("abc1234",),
           result: str = "DONE", **extra) -> dict:
    return {"kind": "report", "v": "v1", "task": task, "result": result,
            "summary": "done", "commits": list(commits), **extra}


def verdict(task: str = TASK, rnd: int = 1, base: str = "abc1234",
            head: str = "def5678", spec: str = "PASS",
            quality: str = "APPROVED", **extra) -> dict:
    return {"kind": "verdict", "v": "v1", "task": task, "round": rnd,
            "spec_verdict": spec, "quality_verdict": quality,
            "commit_base": base, "commit_head": head,
            "reviewed_package_sha": "0123456789", **extra}


def heartbeat(task: str = TASK, **extra) -> dict:
    return {"kind": "heartbeat", "v": "v1", "task": task, **extra}


def evidence(criterion: str = "V1", commit: str = "abc1234",
             verdict: str = "proven", **extra) -> dict:
    return {"kind": "evidence", "v": "v1", "criterion": criterion,
            "command": "make test", "observed": "ok", "verdict": verdict,
            "state_commit": commit, **extra}


def gate(phase: str = "intake", decision: str = "approved", **extra) -> dict:
    return {"kind": "gate_decision", "v": "v1", "phase": phase,
            "decision": decision, "by": "human", **extra}


def ruling(decision: str = "use X", why: str = "cheaper", **extra) -> dict:
    return {"kind": "ruling", "v": "v1", "decision": decision, "why": why,
            **extra}


def audit(target: str = f"{INIT}-CHTR-01", rnd: int = 1,
          verdict: str = "PASS", findings: tuple[dict, ...] = (),
          **extra) -> dict:
    return {"kind": "audit", "v": "v1", "target": target, "round": rnd,
            "verdict": verdict, "findings": list(findings), **extra}


def repair(target: str = f"{INIT}-CHTR-01", rnd: int = 1, **extra) -> dict:
    return {"kind": "repair", "v": "v1", "target": target, "round": rnd,
            **extra}


def halt(reason: str = "stop", **extra) -> dict:
    return {"kind": "halt", "v": "v1", "reason": reason, **extra}


def spawn_error(dispatch_id: str = "D00001", error_class: str = "network",
                **extra) -> dict:
    return {"kind": "spawn_error", "v": "v1", "dispatch_id": dispatch_id,
            "error_class": error_class, **extra}


def needs_context(task: str = TASK, question: str = "which db?",
                  **extra) -> dict:
    return {"kind": "needs_context", "v": "v1", "task": task,
            "question": question, **extra}


def merge(plan: str = PLAN, sha: str = "abc1234", **extra) -> dict:
    return {"kind": "merge", "v": "v1", "plan": plan, "merge_sha": sha,
            **extra}


GOOD: dict[str, dict] = {
    **{k: art(k) for k in ("charter", "options", "brainstorm", "arch", "adr",
                           "ifce", "design", "spec", "risk")},
    "vrfy": vrfy_payload(),
    "plan": plan_payload(),
    "report": report(),
    "verdict": verdict(),
    "heartbeat": heartbeat(),
    "evidence": evidence(),
    "gate_decision": gate(),
    "ruling": ruling(),
    "audit": audit(),
    "repair": repair(),
    "halt": halt(),
    "spawn_error": spawn_error(),
    "needs_context": needs_context(),
    "merge": merge(),
    "resume": {"kind": "resume", "v": "v1", "reason": "client confirmed"},
}
