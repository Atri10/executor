# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The kernel: fold events into state, emit the next action, ingest payloads.

No other module decides state. `fold` is a pure function over the journal;
`emit_next` reads that state and produces exactly one typed action plus a
minted payload slot; `ingest` validates a payload and appends its event.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import __version__
from .schemas import ARTIFACT_KINDS, schema_for, validate
from .store import (ExecError, Initiative, Rejection, StoreLock,
                    append_event, docs_artifact_file, docs_artifact_md,
                    docs_plan_file, docs_plan_md, docs_root, make_event,
                    mint_slot, now_iso, open_slots, prompt_file, read_json,
                    save_slot, sha256, state_file, verify_chain, write_json)

INGEST_RETRY_CAP = 2
MAX_FIX_ROUNDS = 5
NO_PROGRESS_LIMIT = 3      # same action over unchanged state → livelock
SUSPECT_S = 1800          # no heartbeat this long → suspect warning
DEADLINE_S = 3600        # dispatch lease before _dead() sweeps

# in-process serialization for the dedup+mint+commit critical section.
# Cross-process pump runs are one-pump-per-initiative by contract.
_DISPATCH_LOCK = __import__("threading").Lock()

# Actions the pump can see, and the payload kind each expects.
ROLE_SCHEMA = {"impl": "report", "fix": "report", "audit": "audit",
               "reaudit": "audit", "repair": "repair", "author": "artifact",
               "review": "verdict", "evidence": "evidence",
               "supervisor": "ruling"}

# Which artifact kinds each authoring phase produces.
PHASE_ARTIFACTS = {
    "intake": ["charter"], "discovery": ["options", "brainstorm"],
    "architecture": ["arch", "adr", "ifce"],
    "design": ["design"], "specification": ["spec", "risk", "vrfy"],
    "planning": ["plan"], "execution": [], "review": [],
    "plan_regression": [], "verification": [], "handoff": []}


# ------------------------------------------------------------ git helpers

def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ExecError(f"git {' '.join(args)}: {r.stderr.strip()}",
                        "git_error")
    return r.stdout.strip()


def rev_exists(root: Path, rev: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", rev],
        capture_output=True).returncode == 0


def path_at_rev(root: Path, rev: str, path: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{rev}:{path}"],
        capture_output=True).returncode == 0


def changed_files(root: Path, base: str, head: str) -> list[str]:
    return git(root, "diff", "--name-only", base, head).splitlines()


def branch_head(root: Path, branch: str) -> str:
    return git(root, "rev-parse", "--short", branch)


# ------------------------------------------------------------ fold

def fold(events: list[dict]) -> dict:
    """Pure: journal → folded state. The single source of truth."""
    s: dict = {
        "phase": "intake", "phase_state": {},
        "artifacts": {}, "critiques": {},
        "plans": {}, "plan_order": [],
        "tasks": {}, "verdicts": {}, "reports": {},
        "rulings": [], "evidence": {}, "dispatches": {},
        "halt": None, "done": False, "entities": {}, "edges": [],
        "pending": {}, "seq": len(events), "last_emit": None,
        "emit_streak": 0, "reject_streak": {},
    }
    for ev in events:
        _apply(s, ev)
    return s


def _apply(s: dict, ev: dict) -> None:
    k, d, e = ev["kind"], ev.get("data", {}), ev["entity"]
    seq = ev["seq"]
    if k == "created":
        s["phase"] = "intake"
        _node(s, e, "initiative")
    elif k == "phase_entered":
        s["phase"] = d["phase"]; s["phase_state"][d["phase"]] = "in_progress"
    elif k == "phase_passed":
        s["phase_state"][d["phase"]] = "passed"
    elif k == "phase_skipped":
        s["phase_state"][d["phase"]] = "skipped"
    elif k == "halt":
        s["halt"] = d.get("reason", "halted")
    elif k == "resumed":
        s["halt"] = None
    elif k in ARTIFACT_KINDS:
        a = s["artifacts"].setdefault(e, {"kind": k, "status": "drafted",
                                        "round": 0, "data": d})
        a.update(status="drafted", round=a["round"] + 1, data=d)
        _node(s, e, "artifact")
        for c in d.get("cites", []):
            _edge(s, e, c, "cites")
        if k == "plan":
            pid = e
            s["plans"].setdefault(pid, {"status": "draft", "round": 0})
            if pid not in s["plan_order"]:
                s["plan_order"].append(pid)
            for t in d.get("tasks", []):
                tid = f"{pid}-{t['id']}"
                s["tasks"].setdefault(tid, {
                    "state": "pending", "round": 0, "fix_rounds": 0,
                    "files": t["files"], "depends_on": t.get("depends_on", []),
                    "plan": pid, "title": t["title"], "goal": t["goal"],
                    "accepts": t["accepts"], "retries": 0})
                _node(s, tid, "task"); _edge(s, pid, tid, "contains")
    elif k == "audit":
        tgt = d["target"]
        c = s["critiques"].setdefault(tgt, {"round": 0, "open": []})
        if d["verdict"] == "PASS":
            c["status"] = "clean"; c["open"] = []
            if tgt in s["artifacts"]:
                s["artifacts"][tgt]["status"] = "cleared"
        else:
            c["status"] = "fail"; c["round"] = d["round"]
            c["open"] = [f for f in d.get("findings", [])
                         if f.get("status", "open") == "open"]
            if tgt in s["artifacts"]:
                s["artifacts"][tgt]["status"] = "under_audit"
        _edge(s, e, tgt, "reviews")
    elif k == "repair":
        tgt = d.get("target")
        if tgt in s["critiques"]:
            s["critiques"][tgt]["status"] = "repaired"
    elif k == "task_dispatched":
        t = s["tasks"].get(d["task"])
        if t:
            t.update(state="dispatched", role=d["role"],
                     dispatch_id=ev["dispatch_id"], model=d.get("model"),
                     dispatched_at=ev["ts"], deadline=ev["ts"],
                     base=d.get("base"), slot=d.get("respond_to"))
        s["dispatches"][ev["dispatch_id"]] = {
            "task": d["task"], "role": d["role"], "model": d.get("model"),
            "at": ev["ts"], "respond_to": d.get("respond_to")}
        _edge(s, ev["dispatch_id"], d["task"], "dispatched")
    elif k == "report":
        t = s["tasks"].get(d["task"])
        if t:
            t["state"] = "reported"
        s["reports"][d["task"]] = d
        if d.get("concerns"):
            s.setdefault("needs_ruling", []).extend(
                {"task": d["task"], "concern": c} for c in d["concerns"])
        if d.get("model_actual") and t and t.get("model") \
                and d["model_actual"] != t["model"]:
            s.setdefault("model_deviations", []).append(
                {"task": d["task"], "expected": t["model"],
                 "got": d["model_actual"]})
    elif k == "heartbeat":
        t = s["tasks"].get(d["task"])
        if t:
            t["last_beat"] = ev["ts"]
    elif k == "verdict":
        t = s["tasks"].get(d["task"])
        if t:
            t["round"] = d["round"]
            clean = (d["spec_verdict"] == "PASS" and
                     d["quality_verdict"] in ("APPROVED",
                                              "APPROVED_WITH_ROUTED_RESIDUALS"))
            t["state"] = "complete" if clean else "fix_needed"
            if not clean:
                t["fix_rounds"] = t.get("fix_rounds", 0) + 1
        s["verdicts"][f"{d['task']}-R{d['round']:02d}"] = d
        _edge(s, e, d["task"], "reviews")
    elif k == "spawn_error":
        s["dispatches"].get(d["dispatch_id"], {}).update(
            spawn_error=d["error_class"])
        t = s["tasks"].get(s["dispatches"].get(d["dispatch_id"], {})
                           .get("task"))
        if t:
            t["state"] = "spawn_error"
    elif k == "needs_context":
        t = s["tasks"].get(d["task"])
        if t:
            t["state"] = "needs_context"; t["question"] = d["question"]
        s.setdefault("questions", []).append(d)
    elif k == "ruling":
        s["rulings"].append(d)
        if d.get("stop"):
            s["halt"] = d.get("decision", "halted")
        for nr in s.get("needs_ruling", []):
            if d.get("for_task") == nr.get("task"):
                nr["ruled"] = True
        for nr in s.get("questions", []):
            if d.get("answered") and d["answered"] in nr.get("question", ""):
                nr["ruled"] = True
        t = s["tasks"].get(d.get("for_task", ""))
        if t and t["state"] in ("blocked", "needs_context", "escalated"):
            t["state"] = "pending"
    elif k == "evidence":
        s["evidence"].setdefault(d["criterion"], []).append(d)
        _edge(s, e, d["criterion"], "proves")
    elif k == "gate_decision":
        ph = d["phase"]
        if d["decision"] == "approved":
            s["phase_state"][ph] = "passed"
        elif d["decision"] == "rejected":
            s["phase_state"][ph] = "in_progress"
    elif k == "plan_started":
        s["plans"].setdefault(d["plan"], {"status": "running"})\
            .update(status="running")
    elif k in ("plan_merged", "merge"):
        s["plans"].setdefault(d["plan"], {"status": "merged"})\
            .update(status="merged", merge=d.get("merge_sha") or d.get("merge"))
    elif k == "emit":
        # streak on identical action over unchanged state (v1 exec-step)
        key = f"{d.get('action')}:{d.get('key', '')}"
        if key == s.get("last_emit"):
            s["emit_streak"] = s.get("emit_streak", 0) + 1
        else:
            s["last_emit"], s["emit_streak"] = key, 0
    elif k == "reject":
        dk = d.get("dispatch_id")
        s["reject_streak"][dk] = s["reject_streak"].get(dk, 0) + 1
    elif k == "done":
        s["done"] = True


def _node(s: dict, nid: str, ntype: str) -> None:
    s["entities"].setdefault(nid, {"type": ntype})


def _edge(s: dict, a: str, b: str, kind: str) -> None:
    s["edges"].append({"from": a, "to": b, "kind": kind})


# ------------------------------------------------------------ emit next

def emit_next(init: Initiative) -> dict:
    """Read folded state, emit exactly one action plus a resume manifest.

    The manifest is the anti-context-loss contract: a cold pump can read it
    and resume without carrying any history — it names the phase, the last
    event, the action to take, and the exact input the action expects.
    """
    s = fold(init.events)
    act = _compute(init, s)
    act["resume"] = {
        "initiative": init.id,
        "phase": s["phase"],
        "phase_state": s["phase_state"].get(s["phase"], "—"),
        "last_event": init.events[-1]["kind"] if init.events else None,
        "last_seq": len(init.events),
        "open_concerns": sum(1 for n in s.get("needs_ruling", [])
                             if not n.get("ruled")),
        "tasks_done": sum(1 for t in s["tasks"].values()
                          if t["state"] == "complete"),
        "tasks_total": len(s["tasks"]),
    }
    _record_emit(init, s, act)
    return act


def _record_emit(init: Initiative, s: dict, act: dict) -> None:
    """Record this emit with a state digest. The no-progress detector
    streaks only when the same action fires over an unchanged state —
    actual progress mutates the digest and resets the streak."""
    if act["action"] in ("WAIT", "HALT", "DONE"):
        return
    digest = sha256({
        "a": act["action"],
        "k": act.get("entity") or act.get("phase") or "",
        "ts": sorted((t, s["tasks"][t]["state"]) for t in s["tasks"]),
        "cs": sorted((c, s["critiques"][c].get("status", ""))
                     for c in s["critiques"]),
        "ph": s["phase"], "ps": s["phase_state"].get(s["phase"]),
    })
    _commit(init, "engine", "emit", init.id,
            {"action": act["action"], "key": digest})


def _compute(init: Initiative, s: dict) -> dict:
    if s["halt"]:
        return _action("HALT", init.id, reason=s["halt"])
    if s["done"]:
        return _action("DONE", init.id)
    if s["emit_streak"] and s["emit_streak"] >= NO_PROGRESS_LIMIT:
        return _action("ESCALATE", init.id,
                       reason=f"no progress after {s['emit_streak']} emits")
    ph = s["phase"]
    pstate = s["phase_state"].get(ph)

    # halt-style pending questions/rulings that block everything
    if s.get("needs_ruling") and any(not n.get("ruled")
                                     for n in s["needs_ruling"]):
        return _action("ASK", init.id,
                       topic="open concerns need rulings")

    if pstate == "passed":
        nxt = _advance(s)
        if nxt is None:
            return _action("DONE", init.id)
        return _phase_enter(init, nxt)

    if pstate is None:
        return _phase_enter(init, ph)

    # ----- authoring phases: artifact → critique → gate
    if ph in PHASE_ARTIFACTS and PHASE_ARTIFACTS[ph]:
        for kind in PHASE_ARTIFACTS[ph]:
            if not _artifacts_present(s, ph, kind):
                eid = (f"{init.id}-P{len(s['plan_order']) + 1:02d}"
                       if kind == "plan" else f"{init.id}-{_akind(kind)}")
                return _dispatch(init, s, "author", eid,
                                 schema=kind, role_detail=kind)
        # critique stage — audit each drafted artifact until it clears
        for aid in _phase_artifacts(s, ph):
            c = s["critiques"].get(aid, {})
            if c.get("status") in (None, "repaired"):
                rnd = c.get("round", 0) + 1
                return _dispatch(init, s, "audit", aid,
                                 schema="audit", role_detail=str(rnd))
            if c.get("status") == "fail":
                return _dispatch(init, s, "repair", aid,
                                 schema="repair", role_detail=str(c["round"]))
        # all artifacts cleared → gate
        return _action("GATE", init.id, phase=ph)

    # ----- plan_regression: audit every plan, loop
    if ph == "plan_regression":
        for pid in s["plan_order"]:
            c = s["critiques"].get(pid, {})
            if c.get("status") in (None, "repaired"):
                return _dispatch(init, s, "audit", pid, schema="audit",
                                 role_detail=str(c.get("round", 0) + 1))
            if c.get("status") == "fail":
                return _dispatch(init, s, "repair", pid, schema="repair",
                                 role_detail=str(c["round"]))
        return _action("GATE", init.id, phase=ph)

    # ----- execution: task machine per plan
    if ph == "execution":
        for pid in s["plan_order"]:
            act = _plan_step(init, s, pid)
            if act:
                return act
        # all plans merged
        return _action("GATE", init.id, phase=ph)

    # ----- verification: evidence per criterion
    if ph == "verification":
        pending = [c for c in _criteria(s)
                   if c not in s["evidence"]]
        if pending:
            return _dispatch(init, s, "evidence", pending[0],
                             schema="evidence")
        return _action("GATE", init.id, phase=ph)

    if ph == "handoff":
        return _action("GATE", init.id, phase=ph)

    # phases with no artifacts (design/design etc. skipped handling)
    if not PHASE_ARTIFACTS.get(ph):
        return _action("GATE", init.id, phase=ph)

    return _action("WAIT", init.id, reason="no actionable transition")


def _merge_action(init: Initiative, s, pid: str) -> dict:
    """MERGE: the pump runs the merge, then ingests a merge payload."""
    slot = mint_slot(init.idir, "merge", pid, "merge")
    save_slot(init.idir, slot)
    _commit(init, "engine", "task_dispatched", pid,
            {"task": pid, "role": "merge",
             "respond_to": slot["respond_to"], "schema": "merge"},
            dispatch_id=slot["dispatch_id"])
    write_json(state_file(init.idir),
               fold(init.events) | {"last_seq": len(init.events)})
    return _action("MERGE", init.id, plan=pid,
                   run=f"git merge --no-ff task/{pid}",
                   respond_to=slot["respond_to"],
                   dispatch_id=slot["dispatch_id"])


def _plan_step(init, s, pid) -> dict | None:
    plan = s["plans"].get(pid)
    if not plan or plan["status"] == "merged":
        return None
    tasks = [tid for tid, t in s["tasks"].items() if t["plan"] == pid]
    tasks.sort()
    for tid in tasks:
        t = s["tasks"][tid]
        st = t["state"]
        if st == "pending":
            deps = [f"{pid}-{d}" for d in t.get("depends_on", [])]
            if all(s["tasks"].get(dd, {}).get("state") == "complete"
                   for dd in deps):
                return _dispatch(init, s, "impl", tid, schema="report",
                                 base=_plan_base(init, s, pid))
        elif st == "dispatched":
            if _dead(s, t):
                return _action("ESCALATE", init.id,
                               reason=f"{tid} past deadline, rungs spent")
            # else still running — pump waits; heartbeat keeps it alive
            continue
        elif st == "spawn_error":
            return _action("REDISPATCH", init.id, task=tid)
        elif st == "needs_context":
            return _action("ASK", init.id, topic=t.get("question", tid))
        elif st == "reported":
            rnd = t.get("round", 0) + 1
            return _dispatch(init, s, "review", tid, schema="verdict",
                             role_detail=str(rnd),
                             base=_plan_base(init, s, pid))
        elif st == "fix_needed":
            if t.get("fix_rounds", 0) >= MAX_FIX_ROUNDS:
                return _action("ESCALATE", init.id,
                               reason=f"{tid} hit fix-round cap")
            return _dispatch(init, s, "fix", tid, schema="report",
                             base=_plan_base(init, s, pid))
    if all(s["tasks"][tid]["state"] == "complete" for tid in tasks):
        return _merge_action(init, s, pid)
    return None


def _dead(s, t) -> bool:
    # heartbeat-aware: a live beat resets the clock; sweep the slot first
    import time as _t
    try:
        last = t.get("last_beat") or t.get("dispatched_at") or ""
        age = _t.time() - _iso2epoch(last) if last else 0
        return age > DEADLINE_S
    except Exception:
        return False


def _iso2epoch(ts: str) -> float:
    """UTC ts → epoch. mktime() would read it as local time — wrong on
    every non-UTC host and DST-broken on the rest. timegm is exact."""
    import calendar
    import time as _t
    try:
        return calendar.timegm(_t.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return 0


def _plan_base(init, s, pid) -> str:
    # rolling merge base: previous task's merge head, else the plan base
    done = [tid for tid, t in s["tasks"].items()
            if t["plan"] == pid and t["state"] == "complete"]
    if done:
        last = max(done)
        head = s["verdicts"].get(f"{last}-R{s['tasks'][last]['round']:02d}",
                               {}).get("commit_head")
        if head:
            return head
    return branch_head(init.root, "HEAD")


def _advance(s) -> str | None:
    from .store import PHASES
    i = PHASES.index(s["phase"])
    while i + 1 < len(PHASES):
        nxt = PHASES[i + 1]
        if s["phase_state"].get(nxt) != "skipped":
            return nxt
        i += 1
    return None


def _phase_artifacts(s: dict, ph: str) -> list[str]:
    """Artifact ids owned by a phase — kind maps to phase via
    PHASE_ARTIFACTS, so no stored phase is needed."""
    kinds = set(PHASE_ARTIFACTS.get(ph, []))
    return [aid for aid, a in s["artifacts"].items() if a["kind"] in kinds]


def _artifacts_present(s: dict, ph: str, kind: str) -> bool:
    return any(a["kind"] == kind for a in s["artifacts"].values())


_AKIND = {"charter": "CHTR-01", "options": "OPTS-01", "brainstorm": "BRN-01",
          "arch": "ARCH-01", "adr": "ADR-01", "ifce": "IFCE-01",
          "design": "DSGN-01", "spec": "SPEC-01", "risk": "RISK-01",
          "vrfy": "VRFY-01", "plan": None}


def _akind(kind: str) -> str:
    return _AKIND.get(kind, kind.upper() + "-01")


def _criteria(s) -> list[str]:
    out = []
    for aid, a in s["artifacts"].items():
        if a["kind"] == "vrfy":
            for c in a["data"].get("criteria", []):
                out.append(c["id"])
    return out


def _phase_enter(init: Initiative, phase: str) -> dict:
    _commit(init, "engine", "phase_entered", init.id, {"phase": phase})
    write_json(state_file(init.idir), fold(init.reload().events)
               | {"last_seq": len(init.events)})
    return _action("PHASE-ENTER", init.id, phase=phase)




def _dispatch(init: Initiative, s, role: str, entity: str, schema: str,
              role_detail: str = "", base: str | None = None) -> dict:
    """dedup + mint + commit are one critical section: two threads must
    never mint the same dispatch_id or double-dispatch one entity.
    Cross-process pump runs stay operator-serialized (one pump per
    initiative) — the lock is the in-process guarantee."""
    with _DISPATCH_LOCK:
        for sl in open_slots(init.idir):
            if sl["entity"] == entity and sl["schema"] == schema \
                    and not sl.get("consumed"):
                return _action(
                    "DISPATCH", init.id, entity=entity, role=role,
                    role_detail=role_detail,
                    dispatch_id=sl["dispatch_id"],
                    respond_to=sl["respond_to"],
                    prompt=str(prompt_file(init.idir,
                                           sl["dispatch_id"])))
        slot = mint_slot(init.idir, role, entity, schema)
        save_slot(init.idir, slot)
        data = {"task": entity, "role": role, "role_detail": role_detail,
                "respond_to": slot["respond_to"], "schema": schema}
        if base:
            data["base"] = base
        _commit(init, "engine", "task_dispatched", entity, data,
                dispatch_id=slot["dispatch_id"])
        _write_prompt(init, slot, s)
        write_json(state_file(init.idir), fold(init.events)
                   | {"last_seq": len(init.events)})
        return _action("DISPATCH", init.id, entity=entity, role=role,
                       role_detail=role_detail,
                       dispatch_id=slot["dispatch_id"],
                       respond_to=slot["respond_to"],
                       cwd=str(init.root),
                       prompt=str(prompt_file(init.idir,
                                              slot["dispatch_id"])))


def _write_prompt(init: Initiative, slot: dict, s: dict) -> None:
    """Every prompt carries the full working set: location invariant, task
    contract, prior findings. Context loss is the norm, not the edge
    case — a cold agent must not need to recover anything by memory."""
    body = [f"# {slot['action'].upper()} — {slot['entity']}",
            "",
            f"**Dispatch id:** `{slot['dispatch_id']}`  ",
            f"**Write your JSON to:** `{slot['respond_to']}`  ",
            f"**Schema kind:** `{slot['schema']}`  ",
            f"**Repo root:** `{init.root}`  ",
            f"**Workdir:** `{init.root}` (cd here first — relative "
            "paths resolve against the repo root, NOT a worktree)", ""]
    t = s["tasks"].get(slot["entity"])
    if t:
        body += ["## Task", f"- {t['title']}", f"- {t['goal']}", "",
                 "## Files you may touch", *[f"- `{f}`" for f in t["files"]],
                 "", "## Accept when", *[f"- {a}" for a in t["accepts"]], ""]
    # context-loss mitigation: embed prior findings for this entity
    prior = [v for v in s["verdicts"].values()
             if v.get("task") == slot["entity"]]
    if prior and slot["schema"] in ("verdict", "report"):
        last = prior[-1]
        body += ["## Prior round findings — confirm or refute each",
                 *[f"- {f['id']} ({f['severity']}): {f['claim']}"
                   for f in last.get("findings", [])], ""]
    crit = s["critiques"].get(slot["entity"])
    if crit and crit.get("open") and slot["schema"] == "repair":
        body += ["## Open findings you must close",
                 *[f"- {f.get('id','?')} ({f.get('severity','?')}): "
                   f"{f.get('claim') or f.get('title','')}"
                   for f in crit["open"]], ""]
    if slot["schema"] == "verdict":
        body += ["## Review",
                 "You receive a review package with the diff and the prior "
                 "round's findings. Confirm or refute each prior finding "
                 "before hunting new ones.",
                 "- Emit `round` exactly as minted.",
                 "- `reviewed_package_sha` = the sha of this package.", ""]
    body += ["## Output",
             "Emit only JSON matching the schema for `kind: "
             f"{slot['schema']}`. Prose goes in string fields; structure is "
             "yours to fill, not to invent."]
    prompt_file(init.idir, slot["dispatch_id"]).write_text(
        "\n".join(body), encoding="utf-8")


def _action(word: str, init_id: str, **kw) -> dict:
    a = {"action": word, "initiative": init_id}
    a.update(kw)
    return a


# ------------------------------------------------------------ commit

def _commit(init: Initiative, actor: str, kind: str, entity: str,
            data: dict, dispatch_id: str | None = None,
            payload_sha: str | None = None) -> dict:
    """Serialize the journal write: lock → dedup → make → append → reload.
    Nobody may call make_event/append_event without the lock — the v1
    store raced exactly here (concurrent appends wrote duplicate seq +
    identical prev_sha and silently broke the chain). Dedup lives inside
    the lock too, or two ingests of one payload both pass the check."""
    with StoreLock(init.idir):
        init.reload()
        if payload_sha and _duplicate(init, payload_sha):
            return {"deduplicated": True}
        ev = make_event(init.idir, actor, kind, entity, data,
                        dispatch_id=dispatch_id, payload_sha=payload_sha)
        append_event(init.idir, ev)
        init.reload()
        return ev


# ------------------------------------------------------------ ingest

def ingest(init: Initiative, payload: dict, actor: str = "worker") -> dict:
    """Validate a payload, append its event, re-render. Returns the event
    or raises Rejection. Nothing is written on rejection."""
    if not isinstance(payload, dict):
        raise Rejection("type", "$", "object", type(payload).__name__)
    kind = payload.get("kind")
    if not kind:
        raise Rejection("required", "$.kind", "present", "missing")
    schema = schema_for(kind)
    validate(payload, schema)
    s = fold(init.events)
    _semantic(init, s, payload)
    ev = _commit(init, actor, kind,
                 _entity_for(init, payload), _data_for(payload),
                 dispatch_id=payload.get("dispatch_id"),
                 payload_sha=sha256(payload))
    if ev.get("deduplicated"):
        return ev
    _after(init, s, ev, payload)
    write_json(state_file(init.idir), fold(init.events)
               | {"last_seq": len(init.events)})
    return ev


def _duplicate(init: Initiative, payload_sha: str) -> bool:
    return any(e.get("payload_sha") == payload_sha
               for e in init.events)


def _entity_for(init: Initiative, p: dict) -> str:
    if p["kind"] in ARTIFACT_KINDS:
        return p.get("id") or p.get("plan_id") or init.id
    for k in ("task", "target", "criterion", "phase", "plan"):
        if p.get(k):
            base = p[k]
            if p["kind"] in ("report", "verdict") and \
                    not base.startswith("INIT-"):
                return f"{init.id}-{base}"
            return base
    return init.id


def _data_for(p: dict) -> dict:
    return {k: v for k, v in p.items()
            if k not in ("kind", "v", "engine_version", "dispatch_id")}


def _semantic(init: Initiative, s: dict, p: dict) -> None:
    """Checks beyond the schema — over live state and git."""
    k = p["kind"]
    if k == "verdict":
        task = _resolve_task(init, s, p["task"])
        t = s["tasks"].get(task)
        if not t:
            raise Rejection("unknown_entity", "$.task", "a known task",
                            p["task"])
        want = t.get("round", 0) + 1
        if p["round"] != want:
            raise Rejection("round_mismatch", "$.round", str(want),
                            str(p["round"]),
                            "the engine mints rounds; do not set your own")
        if not rev_exists(init.root, p["commit_base"]):
            raise Rejection("unknown_rev", "$.commit_base",
                            "a resolvable git rev", p["commit_base"])
        if not rev_exists(init.root, p["commit_head"]):
            raise Rejection("unknown_rev", "$.commit_head",
                            "a resolvable git rev", p["commit_head"])
        if p["commit_base"] == p["commit_head"]:
            raise Rejection("empty_range", "$.commit_head",
                            "head != base", "base == head (empty diff)")
        if t.get("slot") and p.get("reviewed_package_sha") is None:
            raise Rejection("required", "$.reviewed_package_sha",
                            "present", "missing")
        for f in p.get("findings", []):
            ev = f.get("evidence", "")
            for path in re.findall(r"[\w./-]+\.\w+", ev):
                if "/" in path and not path_at_rev(
                        init.root, p["commit_head"], path):
                    raise Rejection("missing_evidence", "$.findings",
                                    f"path exists at {p['commit_head']}",
                                    f"{path} not found")
        if t.get("model") and p.get("model_actual") \
                and p["model_actual"] != t["model"]:
            pass  # recorded by fold as model_deviation
    elif k == "report":
        task = _resolve_task(init, s, p["task"])
        t = s["tasks"].get(task)
        if not t:
            raise Rejection("unknown_entity", "$.task", "a known task",
                            p["task"])
        for c in p.get("commits", []):
            if not rev_exists(init.root, c):
                raise Rejection("unknown_rev", "$.commits",
                                "resolvable commit(s)", c)
    elif k == "evidence":
        if p["criterion"] not in _criteria(s):
            raise Rejection("unknown_entity", "$.criterion",
                            "a VRFY criterion id", p["criterion"])
        if not rev_exists(init.root, p["state_commit"]):
            raise Rejection("unknown_rev", "$.state_commit",
                            "a resolvable commit", p["state_commit"])
        for a in p.get("artifacts", []):
            if not path_at_rev(init.root, p["state_commit"], a):
                raise Rejection("missing_evidence", "$.artifacts",
                                f"path exists at {p['state_commit']}",
                                f"{a} not found")
    elif k in ARTIFACT_KINDS:
        # cite integrity: every cites: id must exist already
        known = set(s["entities"]) | set(s["artifacts"])
        for c in p.get("cites", []):
            if c not in known:
                raise Rejection("dangling_ref", "$.cites",
                                "an existing id", c,
                                "reference must resolve — no danglings")
    elif k == "gate_decision":
        if p.get("by") == "human":
            pass  # actor asserted at CLI boundary (human runs ingest)
    elif k == "spawn_error":
        if p["dispatch_id"] not in s["dispatches"]:
            raise Rejection("unknown_entity", "$.dispatch_id",
                            "an open dispatch", p["dispatch_id"])
    elif k == "merge":
        if p["plan"] not in s["plans"]:
            raise Rejection("unknown_entity", "$.plan", "a known plan",
                            p["plan"])
        if not rev_exists(init.root, p["merge_sha"]):
            raise Rejection("unknown_rev", "$.merge_sha",
                            "a resolvable merge commit", p["merge_sha"])


def _resolve_task(init: Initiative, s: dict, t: str) -> str:
    if t in s["tasks"]:
        return t
    cand = f"{init.id}-{t}" if not t.startswith("INIT-") else t
    return cand if cand in s["tasks"] else t


def _after(init: Initiative, s: dict, ev: dict, p: dict) -> None:
    """Post-ingest side effects: consume the matching slot, write the
    artifact file, re-render. Slot match is by dispatch_id when the agent
    echoed it, else by entity+schema — an agent won't reliably echo ids."""
    target = ev.get("dispatch_id")
    ent = ev["entity"]
    for x in open_slots(init.idir):
        match = (x["dispatch_id"] == target) if target else \
                (x["entity"] == ent and x["schema"] == p["kind"])
        if match:
            x["consumed"] = True
            save_slot(init.idir, x)
            break
    if p["kind"] in ARTIFACT_KINDS:
        _commit_artifact(init, p)
    _render(init)


def _commit_artifact(init: Initiative, p: dict) -> None:
    """Write the committed thinking-store .json + rendered .md, nested."""
    aid = p.get("id") or p.get("plan_id")
    if p["kind"] == "plan":
        jf = docs_plan_file(init.root, init.id, aid)
        mf = docs_plan_md(init.root, init.id, aid)
    else:
        jf = docs_artifact_file(init.root, init.id, aid)
        mf = docs_artifact_md(init.root, init.id, aid)
    jf.parent.mkdir(parents=True, exist_ok=True)
    jf.write_text(json.dumps(p, indent=2, ensure_ascii=False) + "\n",
                  encoding="utf-8")
    mf.write_text(_render_doc(p, init), encoding="utf-8")


def _render_doc(p: dict, init: Initiative) -> str:
    """Canonical .md render of an artifact — fixed skeleton, filled values."""
    aid = p.get("id") or p.get("plan_id", init.id)
    out = [f"# {aid} — {p.get('title', '')}",
           "",
           f"*{p.get('summary', '')}*",
           ""]
    for r in p.get("requirements", []):
        out.append(f"### {r['id']} — {r['requirement']}")
        out.append(f"*observable:* {r.get('observable', '')}")
        out.append("")
    for c in p.get("constraints", []):
        out.append(f"**{c['id']}** {c['constraint']}  ")
        out.append(f"*observable:* {c.get('observable', '')}  ")
        out.append("")
    for s_ in p.get("sections", []):
        out.append(f"## {s_['title']}")
        out.append(s_.get("body", ""))
        out.append("")
    for c in p.get("criteria", []):
        out.append(f"### {c['id']}")
        out.append(f"{c['criterion']}  ")
        out.append(f"*procedure:* {c['procedure']}  ")
        out.append("")
    for t in p.get("tasks", []):
        out.append(f"## {t['id']} — {t['title']}")
        out.append(t.get("goal", ""))
        out.append("")
        out.append("**files:** " + ", ".join(f"`{f}`" for f in t["files"]))
        out.append("")
        out.append("**accepts:**")
        out.extend(f"- {a}" for a in t["accepts"])
        out.append("")
    out.append(f"<!-- generated {now_iso()} engine {__version__} -->")
    return "\n".join(out) + "\n"


def _render(init: Initiative) -> None:
    """Re-render projections: state views + index. Cheap, always fresh."""
    from .views import render_all
    render_all(init)


# ------------------------------------------------------------ check

def check(init: Initiative) -> dict:
    """Re-fold the journal, verify the hash chain, audit integrity."""
    init.reload()
    chain_problems = verify_chain(init.events)
    problems = list(chain_problems)
    s = fold(init.events)
    # dangling edges: every edge endpoint must be a known entity
    known = set(s["entities"]) | set(s["artifacts"]) | set(s["tasks"]) | {
        x["id"] for a in s["artifacts"].values()
        for x in (a["data"].get("requirements", [])
                  + a["data"].get("constraints", [])
                  + a["data"].get("criteria", []))}
    for ed in s["edges"]:
        for end in (ed["from"], ed["to"]):
            if end not in known and not end.startswith("d-"):
                problems.append(f"dangling edge {ed['kind']}: {end}")
    saved = read_json(state_file(init.idir)) or {}
    if saved.get("last_seq") != len(init.events):
        problems.append(
            f"state.json stale: last_seq {saved.get('last_seq')} "
            f"!= journal {len(init.events)} — run `executor check` "
            f"to refold")
        write_json(state_file(init.idir), s | {"last_seq": len(init.events)})
    # liveness ladder: an open slot whose task hasn't beaten in SUSPECT_S
    # is suspect (early warning); past DEADLINE_S it's dead.
    import time as _t
    for x in open_slots(init.idir):
        t = s["tasks"].get(x["entity"]) or s["dispatches"].get(
            x["dispatch_id"])
        if t:
            last = t.get("last_beat") or t.get("dispatched_at") or ""
            age = _t.time() - _iso2epoch(last) if last else 0
            if SUSPECT_S < age <= DEADLINE_S:
                problems.append(f"suspect dispatch: {x['dispatch_id']} "
                                f"silent {int(age)}s")
    # layout drift: every file under idir must live under a canonical dir.
    # INIT-0002 shipped a stray `prompts/` dir this way.
    canonical = {"meta", "journal", "dispatches", "artifacts", "plans",
                 "tasks", "fixes", "reviews", "views", ".lock"}
    for f in init.idir.rglob("*"):
        if not f.is_file() or f.name in (".gitignore", ".DS_Store"):
            continue
        if f.relative_to(init.idir).parts[0] not in canonical:
            problems.append(f"non-canonical file: "
                            f"{f.relative_to(init.idir)}")
    open_s = open_slots(init.idir)
    return {"initiative": init.id, "events": len(init.events),
            "chain": "broken" if chain_problems else "ok",
            "problems": problems, "open_slots": len(open_s),
            "dangling": [p for p in problems if "dangling" in p]}
