# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""The kernel: fold the journal, decide the next action, ingest payloads.

fold       pure: journal -> state. The only interpretation of events.
emit_next  decides exactly one action and writes only when the run moves: a
           phase is entered, a gate opens, a worker is dispatched, a dispatch
           is abandoned, a preflight verdict is recorded, or the run escalates.
           A repeated poll returns the same instruction and writes nothing.
ingest     validates one payload against the schema, the state, the open
           dispatch it answers and git, then commits exactly one event. A
           rejection writes nothing.
check      read-only audit of the chain, edges, liveness, dispatches and layout.

Every write holds the store lock from the first read of the journal to the
last write, so the state a payload is validated against is the state it is
committed against.
"""
from __future__ import annotations

import calendar
import contextlib
import re
import subprocess
import threading
import time
from pathlib import Path

from .paths import (artifact_file, audit_file, classify, dispatch_id,
                    dispatches_dir, docs_artifact_file, docs_artifact_md,
                    docs_export_journal, docs_index_file, docs_index_md,
                    docs_init_dir, docs_plan_file, docs_plan_md, docs_report_file,
                    docs_root, docs_verdict_file, fix_package_file,
                    fix_report_file, is_dispatch_id, journal_file, payload_file,
                    plan_audit_file, plan_file, plan_repair_file, preflight_file,
                    prompt_file, repair_file, review_package_file, run_root,
                    state_file, task_impl_report, verdict_file)
from .policy import default_state, load_policy, policy_sha
from .schemas import ARTIFACT_KINDS, schema_for, validate
from .store import (PHASES, ExecError, Initiative, Rejection, StoreLock,
                    append_event, atomic_write, init_store, make_event,
                    next_seq, read_events, read_json, scan_journal, sha256,
                    verify_chain, write_json)
from .views import (render_all, render_handoff_index, render_handoff_md,
                    render_report_md, render_verdict_md)


# A human sends these: a worker cannot approve its own gate or rule on its own concern.
HUMAN_KINDS = frozenset({"gate_decision", "ruling", "resume"})
# While the run is halted only these may land: a human ending the halt, or the
# ruling the halt may be waiting on.
HALT_OPEN_KINDS = frozenset({"ruling", "resume"})
# Kinds that answer no dispatch: human decisions, halts and the merge record.
SLOT_FREE_KINDS = HUMAN_KINDS | {"halt", "merge"}
# Kinds the engine writes itself; a worker can never produce these.
ENGINE_KINDS = frozenset({"created", "phase_entered", "gate_opened",
                          "task_dispatched", "abandon", "preflight", "policy"})
WORKER_KINDS = (frozenset({"report", "heartbeat", "verdict", "spawn_error",
                           "needs_context", "evidence", "audit"})
                | frozenset(ARTIFACT_KINDS))
KNOWN_KINDS = ENGINE_KINDS | SLOT_FREE_KINDS | WORKER_KINDS
# Events that carry a dispatch id but do not close that dispatch.
NON_ANSWERING = frozenset({"heartbeat", "task_dispatched"})
# Schemas whose payload must echo the engine-minted round.
ROUND_SCHEMAS = frozenset({"verdict", "audit"})

PHASE_ARTIFACTS = {
    "intake": ["charter"], "discovery": ["options", "brainstorm"],
    "architecture": ["arch", "adr", "ifce"],
    "design": ["design"], "specification": ["spec", "risk", "vrfy"],
    "planning": ["plan"], "execution": [], "review": [],
    "plan_regression": [], "verification": [], "handoff": []}

_AKIND = {"charter": "CHTR-01", "options": "OPTS-01", "brainstorm": "BRN-01",
          "arch": "ARCH-01", "adr": "ADR-01", "ifce": "IFCE-01",
          "design": "DSGN-01", "spec": "SPEC-01", "risk": "RISK-01",
          "vrfy": "VRFY-01"}

_held = threading.local()


# ------------------------------------------------------------ locking

@contextlib.contextmanager
def _exclusive(idir: Path):
    """The store lock, re-entrant within a thread so helpers that write may run
    inside an outer locked section. Other threads and processes wait for the
    whole outer section."""
    key = str(idir)
    if getattr(_held, "key", None) == key:
        yield
        return
    with StoreLock(idir):
        _held.key = key
        try:
            yield
        finally:
            _held.key = None


# ------------------------------------------------------------ git

def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise ExecError(f"git {' '.join(args)} failed: {r.stderr.strip()}",
                        "git_error")
    return r.stdout


def _safe_rev(rev) -> bool:
    """Agent-supplied revisions reach git as arguments: a leading '-' would be
    read as an option, and anything outside a plain rev charset is refused."""
    return (isinstance(rev, str) and not rev.startswith("-")
            and re.fullmatch(r"[A-Za-z0-9._/~^@{}-]+", rev) is not None)


def rev_exists(root: Path, rev: str) -> bool:
    return _safe_rev(rev) and subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{rev}^{{commit}}"],
        capture_output=True).returncode == 0


def path_at_rev(root: Path, rev: str, path: str) -> bool:
    return (_safe_rev(rev) and not path.startswith("-")
            and subprocess.run(["git", "-C", str(root), "cat-file", "-e",
                                f"{rev}:{path}"],
                               capture_output=True).returncode == 0)


def _head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").strip()


def _resolve(root: Path, rev: str) -> str:
    return _git(root, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def _is_ancestor(root: Path, a: str, b: str) -> bool:
    return subprocess.run(["git", "-C", str(root), "merge-base",
                           "--is-ancestor", a, b],
                          capture_output=True).returncode == 0


# ------------------------------------------------------------ fold

def fold(events: list[dict]) -> dict:
    """Pure: journal -> folded state. The single source of truth.

    `answered` maps each dispatch id to the digest of the payload that closed
    it (None when the engine closed it without an answer). Openness, base and
    context of a dispatch live in the journal too, so a lost file costs nothing."""
    s: dict = {
        "phase": "intake", "phase_state": {},
        "artifacts": {}, "critiques": {},
        "plans": {}, "plan_order": [],
        "tasks": {}, "verdicts": {}, "reports": {},
        "rulings": [], "evidence": {},
        "dispatches": {}, "answered": {}, "lost": {},
        "needs_ruling": [], "questions": [],
        "halt": None, "done": False, "entities": {}, "edges": [],
        "policy": default_state(),
        "seq": len(events),
    }
    for ev in events:
        _apply(s, ev)
    return s


def _crit_key(s: dict, target: str) -> str:
    """Critiques belong to the phase they happened in: plan_regression re-audits
    what planning already cleared, and must not inherit that verdict."""
    return f"{s['phase']}:{target}"


def _apply(s: dict, ev: dict) -> None:
    k, d, e = ev["kind"], ev.get("data") or {}, ev["entity"]
    did = ev.get("dispatch_id")
    if did and k not in NON_ANSWERING:
        s["answered"][did] = ev.get("payload_sha")
    if k == "created":
        _node(s, e, "initiative")
    elif k == "phase_entered":
        s["phase"] = d["phase"]
        s["phase_state"][d["phase"]] = "in_progress"
    elif k == "gate_opened":
        s["phase_state"][d["phase"]] = "gate_pending"
    elif k == "gate_decision":
        _apply_gate(s, d)
    elif k == "halt":
        s["halt"] = d.get("reason", "halted")
    elif k == "resume":
        s["halt"] = None
    elif k in ARTIFACT_KINDS:
        _apply_artifact(s, k, e, d)
    elif k == "audit":
        _apply_audit(s, d)
    elif k == "task_dispatched":
        _apply_dispatch(s, ev, d)
    elif k == "abandon":
        _apply_lost(s, did, "abandoned", d.get("reason", "abandoned"))
    elif k == "spawn_error":
        _apply_lost(s, did, "spawn_error", d["error_class"])
    elif k == "report":
        _apply_report(s, e, d)
    elif k == "heartbeat":
        if did in s["dispatches"]:
            s["dispatches"][did]["last_beat"] = ev["ts"]
    elif k == "verdict":
        _apply_verdict(s, e, d)
    elif k == "needs_context":
        t = s["tasks"].get(e)
        if t is not None:
            t.update(state="needs_context", question=d["question"])
        s["questions"].append({"task": e, "question": d["question"],
                               "ruled": False})
    elif k == "ruling":
        _apply_ruling(s, d)
    elif k == "preflight":
        _apply_preflight(s, d)
    elif k == "evidence":
        s["evidence"].setdefault(d["criterion"], []).append(d)
    elif k == "policy":
        s["policy"] = {**d, "recorded": True}
    elif k == "merge":
        s["plans"].setdefault(d["plan"], {"status": "draft"}).update(
            status="merged", merge_sha=d["merge_sha"])


def _apply_gate(s: dict, d: dict) -> None:
    ph = d["phase"]
    if d["decision"] == "rejected":
        s["halt"] = f"gate {ph} rejected: {d.get('note') or 'no note'}"
        return
    s["phase_state"][ph] = "passed"          # approved or waived
    if ph == "handoff":
        s["done"] = True


def _apply_artifact(s: dict, kind: str, aid: str, d: dict) -> None:
    a = s["artifacts"].setdefault(aid, {"kind": kind, "status": "drafted",
                                        "round": 0, "data": d})
    a.update(status="drafted", round=a["round"] + 1, data=d)
    _node(s, aid, "artifact")
    for c in d.get("cites", []):
        _edge(s, aid, c, "cites")
    crit = s["critiques"].get(_crit_key(s, aid))
    if crit is not None and crit["status"] == "fail":
        crit["status"] = "repaired"          # a re-drafted artifact is a repair
    if kind == "plan":
        s["plans"].setdefault(aid, {"status": "draft"})
        if aid not in s["plan_order"]:
            s["plan_order"].append(aid)
        _apply_plan_tasks(s, aid, d.get("tasks", []))


def _apply_plan_tasks(s: dict, pid: str, rows: list[dict]) -> None:
    """A redrafted plan updates the tasks that have not started and drops the
    ones it no longer lists. A task already under way keeps its contract."""
    wanted = {f"{pid}-{t['id']}": t for t in rows}
    for tid, t in list(s["tasks"].items()):
        if t["plan"] == pid and tid not in wanted and t["state"] == "pending":
            del s["tasks"][tid]
    for tid, row in wanted.items():
        fields = {"title": row["title"], "goal": row["goal"],
                  "files": row["files"], "accepts": row["accepts"],
                  "depends_on": row.get("depends_on", [])}
        cur = s["tasks"].get(tid)
        if cur is None:
            s["tasks"][tid] = {"state": "pending", "round": 0, "fix_rounds": 0,
                               "plan": pid, "base": None, **fields}
            _node(s, tid, "task")
            _edge(s, pid, tid, "contains")
        elif cur["state"] == "pending":
            cur.update(fields)


def _apply_audit(s: dict, d: dict) -> None:
    tgt = d["target"]
    c = s["critiques"].setdefault(_crit_key(s, tgt),
                                  {"round": 0, "status": None, "open": []})
    c["round"] = d["round"]
    art = s["artifacts"].get(tgt)
    if d["verdict"] == "PASS":
        c.update(status="clean", open=[])
        if art is not None:
            art["status"] = "cleared"
    else:
        c.update(status="fail",
                 open=[f for f in d.get("findings", [])
                       if f.get("status", "open") == "open"])
        if art is not None:
            art["status"] = "under_audit"


def _apply_dispatch(s: dict, ev: dict, d: dict) -> None:
    did, e = ev["dispatch_id"], ev["entity"]
    s["dispatches"][did] = {"entity": e, "role": d["role"],
                            "schema": d["schema"],
                            "respond_to": d["respond_to"],
                            "base": d.get("base"),
                            "context": d.get("context") or {}, "at": ev["ts"]}
    if d["schema"] in ARTIFACT_KINDS:
        _node(s, e, "artifact")          # the artifact this dispatch authors
    t = s["tasks"].get(e)
    if t is not None:
        t.update(prior_state=t["state"], state="dispatched", role=d["role"],
                 schema=d["schema"], dispatch_id=did, base=d.get("base"))
    _edge(s, did, e, "dispatched")


def _apply_lost(s: dict, did: str | None, key: str, value: str) -> None:
    """A dispatch closed without an answer: the worker never started (spawn
    error) or went silent past its deadline (abandon). The task returns to the
    state it was dispatched from, and the loss counts against the retry cap."""
    dsp = s["dispatches"].get(did)
    if dsp is None:
        return
    dsp[key] = value
    lk = f"{dsp['entity']}:{dsp['schema']}"
    s["lost"][lk] = s["lost"].get(lk, 0) + 1
    t = s["tasks"].get(dsp["entity"])
    if t is not None:
        t["state"] = t.get("prior_state", "pending")


def _apply_report(s: dict, tid: str, d: dict) -> None:
    t = s["tasks"].get(tid)
    s["reports"][tid] = d
    if t is not None:
        t["state"] = "blocked" if d["result"] == "BLOCKED" else "reported"
        if d["result"] == "BLOCKED":
            t["question"] = f"BLOCKED: {d['summary']}"
    for concern in d.get("concerns", []):
        s["needs_ruling"].append({"task": tid, "concern": concern,
                                  "ruled": False})
    if d["result"] == "BLOCKED":
        s["needs_ruling"].append({"task": tid, "ruled": False,
                                  "concern": f"BLOCKED: {d['summary']}"})


def _apply_verdict(s: dict, tid: str, d: dict) -> None:
    s["verdicts"][f"{tid}-R{d['round']:02d}"] = d
    t = s["tasks"].get(tid)
    if t is None:
        return
    t["round"] = d["round"]
    clean = (d["spec_verdict"] == "PASS"
             and d["quality_verdict"] in s["policy"]["values"]["clean_quality"])
    t["state"] = "complete" if clean else "fix_needed"
    if not clean:
        t["fix_rounds"] += 1


def _apply_ruling(s: dict, d: dict) -> None:
    """A ruling clears the concerns it names and frees the task it is about.
    A freed task resumes the state it was in before the question, so a question
    raised during review resumes review, not implementation."""
    s["rulings"].append(d)
    if d.get("stop"):
        s["halt"] = d["decision"]
    tgt, quoted = d.get("for_task"), d.get("answered")
    for n in s["needs_ruling"]:
        if tgt and n["task"] == tgt:
            n["ruled"] = True
    freed = {tgt} if tgt else set()
    for q in s["questions"]:
        if (tgt and q["task"] == tgt) or (quoted and quoted in q["question"]):
            q["ruled"] = True
            freed.add(q["task"])
    for tid in freed:
        t = s["tasks"].get(tid)
        if t is not None and t["state"] in ("blocked", "needs_context"):
            t["state"] = t.get("prior_state", "pending")


def _apply_preflight(s: dict, d: dict) -> None:
    pid = d["plan"]
    s["plans"].setdefault(pid, {"status": "draft"})["preflight"] = d["verdict"]
    for c in d.get("conflicts", []):
        s["needs_ruling"].append({"task": pid, "ruled": False,
                                  "concern": f"file overlap: {c['tasks']} "
                                             f"share {c['files']}"})


def _node(s: dict, nid: str, ntype: str) -> None:
    s["entities"].setdefault(nid, {"type": ntype})


def _edge(s: dict, a: str, b: str, kind: str) -> None:
    edge = {"from": a, "to": b, "kind": kind}
    if edge not in s["edges"]:
        s["edges"].append(edge)


# ------------------------------------------------------------ small helpers

def _clock(now: float | None) -> float:
    return time.time() if now is None else now


def _iso2epoch(ts: str) -> float:
    """UTC ISO timestamp to epoch seconds. timegm reads it as UTC; mktime would
    read it as local time and drift on every non-UTC host."""
    try:
        return float(calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def _silent_for(dsp: dict, now: float) -> float:
    return now - _iso2epoch(dsp.get("last_beat") or dsp["at"])


def _next_phase(ph: str) -> str | None:
    i = PHASES.index(ph) + 1
    return PHASES[i] if i < len(PHASES) else None


def _criteria_defs(s: dict) -> list[dict]:
    out: list[dict] = []
    for a in s["artifacts"].values():
        if a["kind"] == "vrfy":
            out.extend(a["data"].get("criteria", []))
    return out


def _last_findings(s: dict, tid: str) -> list[dict]:
    mine = [v for v in s["verdicts"].values() if v["task"] == tid]
    return mine[-1].get("findings", []) if mine else []


def _action(word: str, init_id: str, **kw) -> dict:
    return {"action": word, "initiative": init_id, **kw}


def _known_ids(s: dict) -> set[str]:
    """Ids a citation may name: an authored artifact, a task, a plan, a
    criterion, or a requirement or constraint inside an authored artifact. A
    dispatch that has not produced its artifact yet is not a citable id."""
    known = set(s["artifacts"]) | set(s["tasks"]) | set(s["plans"])
    for a in s["artifacts"].values():
        for key in ("requirements", "constraints", "criteria"):
            known |= {x["id"] for x in a["data"].get(key, [])}
    return known


def _kind_of(s: dict, aid: str) -> str:
    return "plan" if aid in s["plan_order"] else s["artifacts"][aid]["kind"]


def _phase_artifacts(s: dict, ph: str) -> list[str]:
    kinds = set(PHASE_ARTIFACTS.get(ph, []))
    return [aid for aid, a in s["artifacts"].items() if a["kind"] in kinds]


def _more_plans_wanted(s: dict) -> bool:
    """The planner says whether another plan is needed. No plan yet means one is."""
    if not s["plan_order"]:
        return True
    last = s["artifacts"][s["plan_order"][-1]]["data"]
    return bool(last.get("more_plans"))


def _write_text(path: Path, text: str) -> None:
    atomic_write(path, text.encode("utf-8"))


# ------------------------------------------------------------ journal writes

def _event(init: Initiative, actor: str, kind: str, entity: str, data: dict,
           dispatch_id_: str | None = None,
           payload_sha: str | None = None) -> dict:
    """The next chained event, not yet appended. Callers hold the lock."""
    return make_event(init.idir, actor, kind, entity, data,
                      dispatch_id=dispatch_id_, payload_sha=payload_sha)


def _append(init: Initiative, ev: dict) -> dict:
    append_event(init.idir, ev)
    init.events.append(ev)
    return ev


def _record(init: Initiative, actor: str, kind: str, entity: str, data: dict,
            dispatch_id_: str | None = None) -> dict:
    """An engine write: the caller holds the lock."""
    return _append(init, _event(init, actor, kind, entity, data, dispatch_id_))


def _sync_policy(init: Initiative) -> dict:
    """Journal the effective policy when it differs from the one in force. The
    caller holds the lock. Ingest calls this only after every check has passed,
    so a rejected payload journals no policy change."""
    values, sources = load_policy(init.root, init.id)
    sha = policy_sha(values)
    state = fold(init.events)["policy"]
    if not state["recorded"] or state["sha"] != sha:
        _record(init, "engine", "policy", init.id,
                {"values": values, "sources": sources, "sha": sha})
    return values


def _project(init: Initiative) -> None:
    """Refresh the fold cache and every projection after a journal change. Once
    the handoff gate is approved, the committed handoff files follow."""
    s = fold(init.events)
    write_json(state_file(init.idir), s | {"last_seq": len(init.events)})
    render_all(init)
    if s["done"]:
        _export_handoff(init, s)


def _export_handoff(init: Initiative, s: dict) -> None:
    """The committed handoff: an index of the run and a byte copy of its journal.
    Both are pure functions of the journal, so a re-export rewrites identical
    bytes."""
    write_json(docs_index_file(init.root, init.id),
               render_handoff_index(init.id, s))
    _write_text(docs_index_md(init.root, init.id),
                render_handoff_md(init.id, s))
    atomic_write(docs_export_journal(init.root, init.id),
                 journal_file(init.idir).read_bytes())


# ------------------------------------------------------------ dispatches

def _open_slots(s: dict) -> list[dict]:
    """Dispatches the journal records and nothing has answered, in id order.
    Openness, base and context come from the journal alone."""
    return [{"dispatch_id": did, "entity": d["entity"], "schema": d["schema"],
             "role": d["role"], "respond_to": d["respond_to"],
             "base": d["base"], "context": d["context"]}
            for did, d in sorted(s["dispatches"].items())
            if did not in s["answered"]]


def _open_for(s: dict, entity: str, schema: str | None = None) -> dict | None:
    for sl in _open_slots(s):
        if sl["entity"] == entity and (schema is None or sl["schema"] == schema):
            return sl
    return None


def open_dispatches(init: Initiative) -> list[dict]:
    """What a worker may still answer, in id order. Reads the journal and
    writes nothing, so it is safe at any time."""
    return _open_slots(fold(read_events(init.idir)))


def _dispatch_action(init: Initiative, sl: dict) -> dict:
    return _action("DISPATCH", init.id, entity=sl["entity"], role=sl["role"],
                   schema=sl["schema"], dispatch_id=sl["dispatch_id"],
                   respond_to=sl["respond_to"], cwd=str(init.root),
                   prompt=str(prompt_file(init.idir, sl["dispatch_id"])),
                   base=sl["base"], context=sl["context"])


# ------------------------------------------------------------ emit next

def emit_next(init: Initiative, now: float | None = None) -> dict:
    """Decide exactly one action, plus a resume manifest. Idempotent: while a
    dispatch is open, polling returns the same instruction and writes nothing."""
    with _exclusive(init.idir):
        init.reload()
        before = len(init.events)
        _sync_policy(init)
        act = _decide(init, fold(init.events), _clock(now))
        if len(init.events) != before:
            _project(init)
        act["resume"] = _manifest(init, fold(init.events))
        return act


def _manifest(init: Initiative, s: dict) -> dict:
    """What a cold pump needs to resume with no history."""
    return {
        "initiative": init.id,
        "phase": s["phase"],
        "phase_state": s["phase_state"].get(s["phase"], "-"),
        "last_event": init.events[-1]["kind"] if init.events else None,
        "last_seq": len(init.events),
        "open_concerns": sum(1 for n in s["needs_ruling"] if not n["ruled"]),
        "open_slots": len(_open_slots(s)),
        "tasks_done": sum(1 for t in s["tasks"].values()
                          if t["state"] == "complete"),
        "tasks_total": len(s["tasks"]),
    }


def _decide(init: Initiative, s: dict, now: float) -> dict:
    if s["halt"]:
        return _action("HALT", init.id, reason=s["halt"])
    if s["done"]:
        return _action("DONE", init.id)
    unruled = [n for n in s["needs_ruling"] if not n["ruled"]]
    if unruled:
        return _action("ASK", init.id, topic=unruled[0]["concern"],
                       task=unruled[0]["task"])
    ph = s["phase"]
    pstate = s["phase_state"].get(ph)
    if pstate == "passed":
        nxt = _next_phase(ph)
        return _enter(init, nxt) if nxt else _action("DONE", init.id)
    if pstate is None:
        return _enter(init, ph)
    if pstate == "gate_pending":
        return _action("GATE", init.id, phase=ph)
    work = _phase_work(init, s, ph, now)
    return work if work is not None else _open_gate(init, ph)


def _enter(init: Initiative, phase: str) -> dict:
    _record(init, "engine", "phase_entered", init.id, {"phase": phase})
    return _action("PHASE-ENTER", init.id, phase=phase)


def _open_gate(init: Initiative, ph: str) -> dict:
    _record(init, "engine", "gate_opened", init.id, {"phase": ph})
    return _action("GATE", init.id, phase=ph)


def _escalate(init: Initiative, reason: str) -> dict:
    """Escalation latches: the halt is a journal event, so every later poll
    returns HALT until a human sends a resume. The engine never retries past a
    cap by itself."""
    _record(init, "engine", "halt", init.id, {"reason": reason,
                                              "source": "engine"})
    return _action("ESCALATE", init.id, reason=reason)


def _phase_work(init: Initiative, s: dict, ph: str, now: float):
    """The next dispatch, ask or escalation for this phase; None when the phase
    has nothing left to do and its gate may open."""
    if ph == "execution":
        return _execution(init, s, now)
    if ph == "verification":
        return _verification(init, s, now)
    if ph == "planning" and _more_plans_wanted(s):
        cap = s["policy"]["values"]["max_plans"]
        if len(s["plan_order"]) >= cap:
            return _escalate(init, f"the planner asked for more than "
                                   f"{cap} plans")
        return _author(init, s, "plan", now)
    for kind in PHASE_ARTIFACTS.get(ph, []):
        if not any(a["kind"] == kind for a in s["artifacts"].values()):
            return _author(init, s, kind, now)
    targets = (list(s["plan_order"]) if ph == "plan_regression"
               else _phase_artifacts(s, ph))
    for tgt in targets:
        c = s["critiques"].get(_crit_key(s, tgt))
        if c is None or c["status"] == "repaired":
            rnd = _audit_rounds(s, tgt)
            cap = s["policy"]["values"]["max_audit_rounds"]
            if rnd >= cap:
                return _escalate(init, f"{tgt} not cleared after "
                                       f"{cap} audit rounds")
            return _dispatch(init, s, "audit", tgt, "audit", now=now,
                             context={"round": rnd + 1})
        if c["status"] == "fail":
            return _dispatch(init, s, "repair", tgt, _kind_of(s, tgt), now=now,
                             context={"round": c["round"], "findings": c["open"]})
    return None


def _audit_rounds(s: dict, tgt: str) -> int:
    """Audit rounds are numbered per target across phases, so a plan audited in
    planning and again in plan_regression gets rounds 1 and 2, and each round
    keeps its own canonical file."""
    return max((c["round"] for key, c in s["critiques"].items()
                if key.split(":", 1)[1] == tgt), default=0)


def _author(init: Initiative, s: dict, kind: str, now: float) -> dict:
    eid = (f"{init.id}-P{len(s['plan_order']) + 1:02d}" if kind == "plan"
           else f"{init.id}-{_AKIND[kind]}")
    return _dispatch(init, s, "author", eid, kind, now=now)


def _verification(init: Initiative, s: dict, now: float):
    for crit in _criteria_defs(s):
        runs = s["evidence"].get(crit["id"], [])
        if runs and runs[-1]["verdict"] == "proven":
            continue
        cap = s["policy"]["values"]["max_evidence_tries"]
        if len(runs) >= cap:
            return _escalate(init, f"{crit['id']} not proven after "
                                   f"{cap} attempts")
        return _dispatch(init, s, "evidence", crit["id"], "evidence", now=now,
                         context={"criterion": crit["criterion"],
                                  "procedure": crit["procedure"]})
    return None


def _execution(init: Initiative, s: dict, now: float):
    pending = [pid for pid in s["plan_order"]
               if s["plans"][pid]["status"] != "merged"]
    if not pending:
        return None
    for pid in pending:
        act = _plan_step(init, s, pid, now)
        if act is not None:
            return act
    return _escalate(init, "no dispatchable work: every pending task is blocked "
                           "or its dependencies can never complete")


def _plan_step(init: Initiative, s: dict, pid: str, now: float):
    tids = sorted(tid for tid, t in s["tasks"].items() if t["plan"] == pid)
    for tid in tids:
        t = s["tasks"][tid]
        st = t["state"]
        if st == "dispatched":
            sl = _open_for(s, tid)
            if sl is None:
                return _escalate(init, f"{tid} is dispatched with no open "
                                       f"dispatch on record")
            return _dispatch(init, s, sl["role"], tid, sl["schema"], now=now,
                             base=sl["base"], context=sl["context"])
        if st == "pending":
            if not all(s["tasks"].get(f"{pid}-{dep}", {}).get("state")
                       == "complete" for dep in t["depends_on"]):
                continue
            pre = _preflight(init, s, pid)
            if pre is not None:
                return pre
            return _dispatch(init, s, "impl", tid, "report", now=now,
                             base=_head(init.root))
        if st in ("needs_context", "blocked"):
            return _action("ASK", init.id, topic=t.get("question", tid),
                           task=tid)
        if st == "reported":
            return _review(init, s, tid, now)
        if st == "fix_needed":
            cap = s["policy"]["values"]["max_fix_rounds"]
            if t["fix_rounds"] >= cap:
                return _escalate(init, f"{tid} hit the fix-round cap "
                                       f"({cap})")
            return _dispatch(init, s, "fix", tid, "report", now=now,
                             base=t["base"],
                             context={"round": t["fix_rounds"],
                                      "findings": _last_findings(s, tid)})
    if tids and all(s["tasks"][tid]["state"] == "complete" for tid in tids):
        return _merge(init, s, pid)
    return None


def _review(init: Initiative, s: dict, tid: str, now: float) -> dict:
    t = s["tasks"][tid]
    return _dispatch(init, s, "review", tid, "verdict", now=now,
                     base=t["base"],
                     context={"round": t["round"] + 1,
                              "findings": _last_findings(s, tid)})


def _merge(init: Initiative, s: dict, pid: str) -> dict:
    """The pump performs the merge and ingests the merge record. Nothing is
    journaled here: a repeated poll returns the same MERGE instruction."""
    heads = {}
    for tid in sorted(tid for tid, t in s["tasks"].items() if t["plan"] == pid):
        commits = s["reports"].get(tid, {}).get("commits") or []
        heads[tid] = commits[-1] if commits else None
    return _action("MERGE", init.id, plan=pid, heads=heads)


def _preflight(init: Initiative, s: dict, pid: str):
    """File-ownership scan, once per plan before its first dispatch. Two tasks
    that share a file and have no dependency path between them are a plan
    defect: the verdict is recorded and each overlap becomes a ruling to make."""
    path = preflight_file(init.idir, pid)
    if path.exists():
        return None
    tasks = {tid: t for tid, t in s["tasks"].items() if t["plan"] == pid}
    conflicts = []
    ids = sorted(tasks)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if _ordered(tasks, a, b):
                continue
            shared = sorted(set(tasks[a]["files"]) & set(tasks[b]["files"]))
            if shared:
                conflicts.append({"tasks": [a, b], "files": shared})
    verdict = "conflict" if conflicts else "clear"
    write_json(path, {"plan": pid, "verdict": verdict,
                      "conflicts": conflicts})
    _record(init, "engine", "preflight", pid,
            {"plan": pid, "verdict": verdict, "conflicts": conflicts})
    if conflicts:
        return _action("ASK", init.id, task=pid,
                       topic=f"{pid}: file ownership overlaps between "
                             f"unordered tasks: {conflicts}")
    return None


def _ordered(tasks: dict, a: str, b: str) -> bool:
    """True when a depends on b or b on a, directly or through the plan."""
    return _reaches(tasks, a, b) or _reaches(tasks, b, a)


def _reaches(tasks: dict, src: str, dst: str) -> bool:
    seen, todo = set(), [src]
    while todo:
        cur = todo.pop()
        for dep in tasks.get(cur, {}).get("depends_on", []):
            nxt = f"{tasks[cur]['plan']}-{dep}"
            if nxt == dst:
                return True
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return False


def _review_package(init: Initiative, s: dict, tid: str, rnd: int,
                    base: str) -> dict:
    """What the reviewer must see: the range from the task's base to what the
    worker reported, the changed files, the diff itself and the prior findings.
    The package sha is what the verdict must echo back."""
    head = _resolve(init.root, s["reports"][tid]["commits"][-1])
    diff = _git(init.root, "diff", "--no-color", base, head)
    names = _git(init.root, "diff", "--name-only", base, head).splitlines()
    core = {"task": tid, "round": rnd, "base": base, "head": head,
            "changed_files": names, "diff_sha256": sha256(diff),
            "prior_findings": _last_findings(s, tid)}
    return {**core, "diff": diff, "package_sha": sha256(core)}


def _dispatch(init: Initiative, s: dict, role: str, entity: str, schema: str,
              *, now: float, base: str | None = None,
              context: dict | None = None) -> dict:
    """Journal a dispatch and write what the worker needs. An open dispatch for
    the same entity and schema is re-emitted, never duplicated; one silent past
    the deadline is abandoned first. The dispatch id is the seq of the event
    that records it, so the id and the journal cannot disagree."""
    pol = s["policy"]["values"]
    open_sl = _open_for(s, entity, schema)
    if open_sl is not None:
        if _silent_for(s["dispatches"][open_sl["dispatch_id"]], now) <= pol["deadline_s"]:
            return _dispatch_action(init, open_sl)
        _record(init, "engine", "abandon", entity,
                {"reason": f"silent past {pol['deadline_s']}s"},
                dispatch_id_=open_sl["dispatch_id"])
        s = fold(init.events)
    lost = s["lost"].get(f"{entity}:{schema}", 0)
    if lost > pol["spawn_retry_cap"]:
        return _escalate(init, f"{entity}: {schema} dispatch lost {lost} times")
    ctx = dict(context or {})
    package = None
    if role == "review":
        assert base is not None, "a review is measured from its task's dispatch base"
        package = _review_package(init, s, entity, ctx["round"], base)
        ctx.update(package_sha=package["package_sha"], base=package["base"],
                   head=package["head"])
    did = dispatch_id(next_seq(init.events))
    sl = {"dispatch_id": did, "entity": entity, "role": role,
          "schema": schema,
          "respond_to": payload_file(init.idir, did).relative_to(
              init.root).as_posix(),
          "base": base, "context": ctx}
    if package is not None:
        write_json(review_package_file(init.idir, entity, ctx["round"]), package)
    if role == "fix":
        write_json(fix_package_file(init.idir, entity, ctx["round"]),
                   {"task": entity, "findings": ctx.get("findings", []),
                    "base": base})
    _write_text(prompt_file(init.idir, did), _render_prompt(init, s, sl))
    _record(init, "engine", "task_dispatched", entity,
            {"role": role, "schema": schema, "respond_to": sl["respond_to"],
             "base": base, "context": ctx}, dispatch_id_=did)
    return _dispatch_action(init, sl)


def _render_prompt(init: Initiative, s: dict, sl: dict) -> str:
    """Everything a cold worker needs: where to write, what kind to emit, the
    task contract, the findings to answer and, for review, the package."""
    ctx = sl["context"]
    e = sl["entity"]
    lines = [f"# {sl['role'].upper()} - {e}", "",
             f"Dispatch id: `{sl['dispatch_id']}`",
             f"Write your JSON payload to: `{sl['respond_to']}`",
             f"Payload kind: `{sl['schema']}` (emit exactly this kind)",
             f"Working directory: `{init.root}` (cd here; paths are "
             f"repo-relative)", ""]
    if "round" in ctx:
        echo = (" (echo it in the `round` field)"
                if sl["schema"] in ROUND_SCHEMAS else "")
        lines += [f"Round: `{ctx['round']}`{echo}", ""]
    t = s["tasks"].get(e)
    if t is not None:
        lines += ["## Task", f"- id: `{e}`", f"- {t['title']}", f"- {t['goal']}",
                  "", "## Files you may touch",
                  *[f"- `{f}`" for f in t["files"]], "",
                  "## Accept when", *[f"- {a}" for a in t["accepts"]], ""]
    if "criterion" in ctx:
        lines += ["## Criterion", f"- {ctx['criterion']}",
                  f"- procedure: {ctx['procedure']}", ""]
    if sl["role"] == "review":
        pkg = review_package_file(init.idir, e, ctx["round"])
        lines += ["## Review package",
                  f"Read `{pkg}` first. It holds the diff from `{ctx['base']}` "
                  f"to `{ctx['head']}`, the changed files and the prior "
                  f"findings. Confirm or refute each prior finding before "
                  f"hunting new ones.",
                  f"Set `reviewed_package_sha` to `{ctx['package_sha']}`, "
                  f"`commit_base` to `{ctx['base']}` and `commit_head` to "
                  f"`{ctx['head']}`.", ""]
    if ctx.get("findings"):
        lines += ["## Findings to address",
                  *[f"- {f.get('id', '?')} ({f.get('severity', '?')}): "
                    f"{f.get('claim', '')}" for f in ctx["findings"]], ""]
    req = schema_for(sl["schema"]).get("required", [])
    lines += ["## Output",
              f"Emit only JSON for `kind: {sl['schema']}`. Required keys: "
              + ", ".join(f"`{k}`" for k in req)
              + ". Prose goes in string fields; structure is yours to fill, "
                "not to invent."]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------ ingest

def ingest(init: Initiative, payload: dict, actor: str = "worker") -> dict:
    """Validate one payload against the schema, the state, the open dispatch
    it answers and git, then commit exactly one event. Returns the event, or
    {"deduplicated": True} when the payload is a redelivery of an answer already
    accepted. Raises Rejection and writes nothing otherwise. Human-only kinds
    need actor "human"."""
    kind = _validated_kind(payload)
    with _exclusive(init.idir):
        init.reload()
        _authorize(kind, actor)
        s = fold(init.events)
        if s["halt"] and kind not in HALT_OPEN_KINDS:
            raise Rejection("halted", "$.kind", "ruling or resume while halted",
                            kind, f"run is halted: {s['halt']}")
        digest = sha256(payload)
        if kind in SLOT_FREE_KINDS:
            entity = _check_free(init, s, payload)
            _sync_policy(init)
            ev = _event(init, actor, kind, entity, _data_for(payload),
                        payload_sha=digest)
        else:
            try:
                sl = _bind(s, payload)
            except Rejection:
                if _duplicate(init, digest):
                    return {"deduplicated": True}
                raise
            entity = _check(init, s, payload, sl)
            _sync_policy(init)
            ev = _event(init, actor, kind, entity, _data_for(payload),
                        dispatch_id_=sl["dispatch_id"], payload_sha=digest)
            _effects(init, s, payload, sl)
        _append(init, ev)
        _project(init)
        return ev


def _validated_kind(payload) -> str:
    if not isinstance(payload, dict):
        raise Rejection("type", "$", "object", type(payload).__name__)
    if "kind" not in payload:
        raise Rejection("required", "$.kind", "present", "missing")
    if not isinstance(payload["kind"], str):
        raise Rejection("type", "$.kind", "string",
                        type(payload["kind"]).__name__)
    validate(payload, schema_for(payload["kind"]))
    return payload["kind"]


def _authorize(kind: str, actor: str) -> None:
    if kind in HUMAN_KINDS and actor != "human":
        raise Rejection("unauthorized", "$.kind", "actor human",
                        f"actor {actor}",
                        f"{kind} is human-only; pass --actor human")


def _duplicate(init: Initiative, digest: str) -> bool:
    return any(e.get("payload_sha") == digest for e in init.events)


def _data_for(p: dict) -> dict:
    return {k: v for k, v in p.items()
            if k not in ("kind", "v", "engine_version", "dispatch_id")}


def _entity_for(p: dict) -> str:
    """The entity a slot-bearing payload speaks for, read from the payload."""
    k = p["kind"]
    if k in ARTIFACT_KINDS:
        return p["id"]
    if k in ("report", "verdict", "heartbeat", "needs_context"):
        return p["task"]
    if k == "evidence":
        return p["criterion"]
    if k == "audit":
        return p["target"]
    return p.get("dispatch_id", "-")


def _bind(s: dict, p: dict) -> dict:
    """The open dispatch a slot-bearing payload answers. A payload that answers
    none is unsolicited and is refused: the engine decides what is asked."""
    kind = p["kind"]
    open_ = _open_slots(s)
    if kind == "spawn_error":
        cands = [x for x in open_ if x["dispatch_id"] == p.get("dispatch_id")]
    elif kind in ("heartbeat", "needs_context"):
        cands = [x for x in open_ if x["entity"] == p["task"]]
    else:
        entity = _entity_for(p)
        cands = [x for x in open_ if x["entity"] == entity
                 and x["schema"] == kind]
    did = p.get("dispatch_id")
    if did is not None and kind != "spawn_error":
        cands = [x for x in cands if x["dispatch_id"] == did]
    if not cands:
        expected = "; ".join(sorted({f"{x['schema']} for {x['entity']}"
                                     for x in open_})) or "none"
        raise Rejection("no_open_slot", "$",
                        f"an open dispatch answered by {kind}",
                        f"{kind} for {did or _entity_for(p)}",
                        f"open: {expected}")
    return cands[0]


def _check(init: Initiative, s: dict, p: dict, sl: dict) -> str:
    """Semantic checks for slot-bearing kinds over live state and git. Returns
    the entity the event is recorded against."""
    k = p["kind"]
    if k in ARTIFACT_KINDS:
        _check_artifact(s, p)
        return p["id"]
    if k == "report":
        for c in p.get("commits", []):
            if not rev_exists(init.root, c):
                raise Rejection("unknown_rev", "$.commits",
                                "resolvable commit(s)", c)
        if p["result"] != "BLOCKED":
            _check_advances(init, s, p, sl)
        return p["task"]
    if k == "verdict":
        _check_verdict(init, p, sl)
        return p["task"]
    if k == "evidence":
        _check_evidence(init, p)
        return p["criterion"]
    if k == "audit":
        _check_audit(p, sl)
        return p["target"]
    if k == "spawn_error":
        return sl["entity"]
    return p["task"]          # heartbeat, needs_context


def _check_free(init: Initiative, s: dict, p: dict) -> str:
    """Checks for kinds that answer no dispatch."""
    k = p["kind"]
    if k == "gate_decision":
        if p["phase"] != s["phase"] or \
                s["phase_state"].get(p["phase"]) != "gate_pending":
            raise Rejection("no_open_gate", "$.phase",
                            f"{s['phase']} with its gate pending", p["phase"])
        return p["phase"]
    if k == "resume":
        if not s["halt"]:
            raise Rejection("not_halted", "$.kind", "a halted run", "running")
        return init.id
    if k == "ruling":
        tgt = p.get("for_task")
        if tgt and tgt not in s["tasks"] and tgt not in s["plans"]:
            raise Rejection("unknown_entity", "$.for_task",
                            "a known task or plan", tgt)
        return tgt or init.id
    if k == "merge":
        _check_merge(init, s, p)
        return p["plan"]
    return init.id            # halt


def _check_artifact(s: dict, p: dict) -> None:
    known = _known_ids(s)
    for c in p.get("cites", []):
        if c not in known:
            raise Rejection("dangling_ref", "$.cites", "an authored id", c,
                            "cite only artifacts, tasks or criteria that exist")
    if p["kind"] == "plan":
        if p.get("plan_id") != p["id"]:
            raise Rejection("mismatch", "$.plan_id", p["id"],
                            str(p.get("plan_id")))
        ids = [t["id"] for t in p["tasks"]]
        if len(set(ids)) != len(ids):
            raise Rejection("duplicate", "$.tasks", "unique task ids",
                            "duplicate id")
        for t in p["tasks"]:
            for dep in t.get("depends_on", []):
                if dep not in ids:
                    raise Rejection("dangling_ref",
                                    f"$.tasks.{t['id']}.depends_on",
                                    "a task id in this plan", dep)
    if p["kind"] == "vrfy":
        ids = [c["id"] for c in p["criteria"]]
        if len(set(ids)) != len(ids):
            raise Rejection("duplicate", "$.criteria", "unique criterion ids",
                            "duplicate id")


def _check_advances(init: Initiative, s: dict, p: dict, sl: dict) -> None:
    """A worker that reports work must have added something. An implementation
    is measured from the base it was dispatched on; a fix is also measured from
    the head of the report it answers. A head equal to, or an ancestor of, either
    adds nothing."""
    refs = [sl["base"]]
    if sl["role"] == "fix":
        prior = (s["reports"].get(p["task"]) or {}).get("commits") or []
        if prior:
            refs.append(prior[-1])
    commits = p.get("commits") or []
    if not commits:
        raise Rejection("empty_range", "$.commits", "at least one commit",
                        "none", "commit the change before reporting it")
    head = _resolve(init.root, commits[-1])
    for ref in refs:
        base = _resolve(init.root, ref)
        if head == base or _is_ancestor(init.root, head, base):
            raise Rejection("empty_range", "$.commits",
                            f"a commit after {base[:12]}", head[:12],
                            "the change is not in the repository yet")


def _check_verdict(init: Initiative, p: dict, sl: dict) -> None:
    ctx = sl["context"]
    if p["round"] != ctx.get("round"):
        raise Rejection("round_mismatch", "$.round", str(ctx.get("round")),
                        str(p["round"]), "the engine mints rounds")
    if p["reviewed_package_sha"] != ctx.get("package_sha"):
        raise Rejection("package_mismatch", "$.reviewed_package_sha",
                        str(ctx.get("package_sha")), p["reviewed_package_sha"],
                        "review the package the engine wrote for this round")
    if (p["commit_base"], p["commit_head"]) != (ctx.get("base"), ctx.get("head")):
        raise Rejection("range_mismatch", "$.commit_base",
                        f"{ctx.get('base')}..{ctx.get('head')}",
                        f"{p['commit_base']}..{p['commit_head']}",
                        "the range is the package's, not yours to choose")
    for f in p.get("findings", []):
        for path in re.findall(r"[\w./-]+\.\w+", f.get("evidence", "")):
            if "/" in path and not path_at_rev(init.root, p["commit_head"], path):
                raise Rejection("missing_evidence", "$.findings",
                                f"path exists at {p['commit_head']}",
                                f"{path} not found")


def _check_evidence(init: Initiative, p: dict) -> None:
    if not rev_exists(init.root, p["state_commit"]):
        raise Rejection("unknown_rev", "$.state_commit",
                        "a resolvable commit", p["state_commit"])
    for a in p.get("artifacts", []):
        if not path_at_rev(init.root, p["state_commit"], a):
            raise Rejection("missing_evidence", "$.artifacts",
                            f"path exists at {p['state_commit']}", a)


def _check_audit(p: dict, sl: dict) -> None:
    if p["round"] != sl["context"].get("round"):
        raise Rejection("round_mismatch", "$.round",
                        str(sl["context"].get("round")), str(p["round"]),
                        "the engine mints audit rounds")


def _check_merge(init: Initiative, s: dict, p: dict) -> None:
    pl = s["plans"].get(p["plan"])
    if pl is None:
        raise Rejection("unknown_entity", "$.plan", "a known plan", p["plan"])
    if pl["status"] == "merged":
        raise Rejection("already_merged", "$.plan", "an unmerged plan", p["plan"])
    open_tasks = sorted(tid for tid, t in s["tasks"].items()
                        if t["plan"] == p["plan"] and t["state"] != "complete")
    if open_tasks:
        raise Rejection("incomplete", "$.plan", "every task complete",
                        ", ".join(open_tasks))
    if not rev_exists(init.root, p["merge_sha"]):
        raise Rejection("unknown_rev", "$.merge_sha",
                        "a resolvable merge commit", p["merge_sha"])


def _effects(init: Initiative, s: dict, p: dict, sl: dict) -> None:
    """Canonical files for a payload that is about to be committed. Runs before
    the event is appended, so a payload that is rejected leaves no files, and a
    file written before a crash is overwritten identically on retry."""
    k = p["kind"]
    if k in ARTIFACT_KINDS:
        _write_artifact(init, p)
        if sl["role"] == "repair":
            _write_repair_record(init, p, sl)
    elif k == "audit":
        write_json(plan_audit_file(init.idir, p["target"], p["round"])
                   if p["target"] in s["plans"]
                   else audit_file(init.idir, p["target"], p["round"]), p)
    elif k == "report":
        if sl["role"] == "fix":
            write_json(fix_report_file(init.idir, p["task"],
                                       sl["context"]["round"]), p)
        else:
            write_json(task_impl_report(init.idir, p["task"],
                                        sl["dispatch_id"]), p)
        _write_text(docs_report_file(init.root, init.id, p["task"],
                                     sl["dispatch_id"]),
                    render_report_md(p, sl["dispatch_id"]))
    elif k == "verdict":
        write_json(verdict_file(init.idir, p["task"], p["round"]), p)
        _write_text(docs_verdict_file(init.root, init.id, p["task"], p["round"]),
                    render_verdict_md(p))


def _write_repair_record(init: Initiative, p: dict, sl: dict) -> None:
    """The engine writes the repair: which open findings the re-drafted artifact
    answers, and the digest of the artifact it produced. A worker never sends a
    repair payload; a critique is cleared only by a re-drafted artifact."""
    rnd = sl["context"]["round"]
    record = {"target": p["id"], "round": rnd,
              "addressed": sl["context"]["findings"],
              "artifact_sha256": sha256(p)}
    write_json(plan_repair_file(init.idir, p["id"], rnd)
               if p["kind"] == "plan"
               else repair_file(init.idir, p["id"], rnd), record)


def _write_artifact(init: Initiative, p: dict) -> None:
    """Run-store copy of the latest payload, plus the committed thinking store:
    canonical JSON and rendered markdown, both deterministic."""
    aid = p["id"]
    if p["kind"] == "plan":
        write_json(plan_file(init.idir, aid), p)
        jf = docs_plan_file(init.root, init.id, aid)
        mf = docs_plan_md(init.root, init.id, aid)
    else:
        write_json(artifact_file(init.idir, aid), p)
        jf = docs_artifact_file(init.root, init.id, aid)
        mf = docs_artifact_md(init.root, init.id, aid)
    write_json(jf, p)
    _write_text(mf, _render_doc(p))


def _render_doc(p: dict) -> str:
    out = [f"# {p['id']} — {p.get('title', '')}", "", f"*{p.get('summary', '')}*", ""]
    for r in p.get("requirements", []):
        out += [f"### {r['id']} — {r['requirement']}",
                f"*observable:* {r.get('observable', '')}", ""]
    for c in p.get("constraints", []):
        out += [f"**{c['id']}** {c['constraint']}  ",
                f"*observable:* {c.get('observable', '')}  ", ""]
    for sec in p.get("sections", []):
        out += [f"## {sec['title']}", sec.get("body", ""), ""]
    for c in p.get("criteria", []):
        out += [f"### {c['id']}", f"{c['criterion']}  ",
                f"*procedure:* {c['procedure']}  ", ""]
    for t in p.get("tasks", []):
        out += [f"## {t['id']} — {t['title']}", t.get("goal", ""), "",
                "**files:** " + ", ".join(f"`{f}`" for f in t["files"]), "",
                "**accepts:**", *[f"- {a}" for a in t["accepts"]], ""]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ initiatives

def _next_init_id(root: Path) -> str:
    nums = [int(d.name.split("-")[1]) for d in run_root(root).glob("INIT-*")
            if d.is_dir() and d.name.split("-")[1].isdigit()]
    return f"INIT-{max(nums, default=0) + 1:04d}"


def create_initiative(root: Path, title: str) -> Initiative:
    """Scaffold a new initiative and journal its creation under the lock."""
    iid = _next_init_id(root)
    idir = init_store(root, iid, title)
    init = Initiative(iid, root, idir)
    with _exclusive(idir):
        init.reload()
        _record(init, "engine", "created", iid, {"title": title})
        _sync_policy(init)
        _project(init)
    return init


# ------------------------------------------------------------ check

def check(init: Initiative, now: float | None = None) -> dict:
    """Read-only audit. Writes nothing, so it is safe at any time. A stale fold
    cache is reported; the next write refreshes it."""
    with _exclusive(init.idir):
        events, torn = scan_journal(init.idir)
        chain = verify_chain(events)
        problems = list(chain)
        if torn:
            problems.append(f"{torn} unparseable journal line(s) skipped")
        unknown = sorted({str(e.get("kind")) for e in events} - KNOWN_KINDS)
        if unknown:
            problems.append(f"unknown event kind(s): {', '.join(unknown)}")
        try:
            s = fold(events)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            problems.append(f"fold failed: {exc}")
            return _report(init, events, chain, problems, [])
        known = _known_ids(s) | set(s["entities"]) | {init.id}
        for ed in s["edges"]:
            for end in (ed["from"], ed["to"]):
                if end not in known and not is_dispatch_id(end):
                    problems.append(f"dangling edge {ed['kind']}: {end}")
        cache = read_json(state_file(init.idir)) or {}
        if cache.get("last_seq") != len(events):
            problems.append(f"state cache stale: last_seq "
                            f"{cache.get('last_seq')} != journal {len(events)} "
                            f"(the next write refreshes it)")
        pol = s["policy"]["values"]
        try:
            files, _ = load_policy(init.root, init.id)
            if policy_sha(files) != s["policy"]["sha"]:
                problems.append("policy drift: the policy files differ from the "
                                "journal's last policy event (the next poll or "
                                "ingest records them)")
        except ExecError as exc:
            problems.append(f"policy invalid: {exc}")
        clock = _clock(now)
        open_ = _open_slots(s)
        for sl in open_:
            silent = _silent_for(s["dispatches"][sl["dispatch_id"]], clock)
            if silent > pol["deadline_s"]:
                problems.append(f"dead dispatch {sl['dispatch_id']}: silent "
                                f"{int(silent)}s (the next poll abandons it)")
            elif silent > pol["suspect_s"]:
                problems.append(f"suspect dispatch {sl['dispatch_id']}: silent "
                                f"{int(silent)}s")
        ddir = dispatches_dir(init.idir)
        if ddir.exists():
            for d in sorted(ddir.iterdir()):
                if d.name not in s["dispatches"]:
                    problems.append(f"orphan dispatch directory {d.name}: "
                                    f"never journaled")
        problems += _layout_problems(init)
        return _report(init, events, chain, problems,
                       [sl["dispatch_id"] for sl in open_])


def _layout_problems(init: Initiative) -> list[str]:
    out = []
    run = run_root(init.root)
    for f in sorted(init.idir.rglob("*")):
        if f.is_file() and classify(f.relative_to(run), "run") is None:
            out.append(f"non-canonical file: {f.relative_to(run).as_posix()}")
    docs = docs_init_dir(init.root, init.id)
    if docs.exists():
        for f in sorted(docs.rglob("*")):
            if f.is_file() and classify(f.relative_to(docs_root(init.root)),
                                        "docs") is None:
                out.append(f"non-canonical committed file: "
                           f"{f.relative_to(docs_root(init.root)).as_posix()}")
    return out


def _report(init: Initiative, events: list[dict], chain: list[str],
            problems: list[str], open_ids: list[str]) -> dict:
    return {"initiative": init.id, "events": len(events),
            "chain": "broken" if chain else "ok", "problems": problems,
            "open_slots": len(open_ids), "open_dispatch_ids": open_ids,
            "dangling": [p for p in problems if p.startswith("dangling")]}
