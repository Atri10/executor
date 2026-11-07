"""Pure projection from the folded journal to the model the pages render.

Nothing here reads the filesystem, the clock, or the environment. The same
fold, journal, and inputs always produce the same model, which keeps the
rendered pages byte-stable and the tests exact. Callers pass the home
directory and the criteria in, so this module never imports the engine.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from .graph_layout import lane_layout, layered_dag
from .store import PHASES

MODEL_SCHEMA = 1
TASK_ATTENTION = frozenset({"blocked", "needs_context", "fix_needed", "failed", "spawn_error"})
TASK_BAD = frozenset({"blocked", "failed", "spawn_error"})
EVIDENCE_SEVERITY = {"failed": "bad", "unavailable": "warn", "unanswered": "warn"}
TERMINAL_CHANGE_STATES = frozenset({"applied", "withdrawn"})
GRAPH_EDGE_KINDS = ("contains", "cites")
RADIUS_KEYS = ("artifacts", "plans", "tasks", "criteria", "docs")
SEVERITY_RANK = {"bad": 0, "warn": 1, "info": 2}


def mask_home(text: str, home: str) -> str:
    """Replace the home directory with `~`, for both separator styles."""
    if len(home.strip("/\\")) < 2:
        return text
    out = text.replace(home, "~")
    slashed = home.replace("\\", "/")
    return out.replace(slashed, "~") if slashed != home else out


def mask_tree(value: Any, home: str) -> Any:
    """Mask every string in a nested model. Applied once, at the boundary."""
    if isinstance(value, str):
        return mask_home(value, home)
    if isinstance(value, dict):
        return {k: mask_tree(v, home) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_tree(v, home) for v in value]
    return value


def _seconds(ts) -> float | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _outcome(did: str, d: dict, answered: dict) -> str:
    if did in answered:
        return "answered"
    if d.get("abandoned"):
        return "abandoned"
    if d.get("spawn_error"):
        return "spawn_error"
    return "open"


def _resolve(tasks: dict, plan: str, ref: str) -> str | None:
    """A `depends_on` entry is either a full task id or a local id under its plan."""
    if ref in tasks:
        return ref
    full = f"{plan}-{ref}" if plan else ""
    return full if full in tasks else None


def _task_rows(folded: dict) -> list[dict]:
    tasks = folded.get("tasks") or {}
    fanout = Counter((d or {}).get("entity") for d in (folded.get("dispatches") or {}).values())
    rows = []
    for tid in sorted(tasks):
        t = tasks[tid] or {}
        plan = t.get("plan") or ""
        resolved: set[str] = set()
        unresolved: list[str] = []
        for ref in t.get("depends_on") or []:
            hit = _resolve(tasks, plan, str(ref))
            if hit and hit != tid:
                resolved.add(hit)
            else:
                unresolved.append(str(ref))
        short = tid[len(plan) + 1:] if plan and tid.startswith(plan + "-") else tid
        rows.append({
            "id": tid,
            "short": short,
            "title": t.get("title") or tid,
            "state": str(t.get("state") or "pending"),
            "plan": plan,
            "depends_on": sorted(resolved),
            "unresolved": sorted(unresolved),
            "dependents": [],
            "dispatches": fanout.get(tid, 0),
            "fix_rounds": int(t.get("fix_rounds") or 0),
            "goal": t.get("goal") or "",
            "files": [str(f) for f in t.get("files") or []],
            "provides": [str(p) for p in t.get("provides") or []],
            "consumes": [str(c) for c in t.get("consumes") or []],
        })
    reverse: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        for dep in row["depends_on"]:
            reverse[dep].append(row["id"])
    for row in rows:
        row["dependents"] = sorted(reverse.get(row["id"], []))
    return rows


def _dag(task_rows: list[dict]) -> dict:
    ids = [t["id"] for t in task_rows]
    edges = [(dep, t["id"]) for t in task_rows for dep in t["depends_on"]]
    laid = layered_dag(ids, edges)
    neighbours: dict[str, set[str]] = {n: set() for n in ids}
    for a, b in edges:
        neighbours[a].add(b)
        neighbours[b].add(a)
    nodes = [{"id": n, "x": laid["nodes"][n]["x"], "y": laid["nodes"][n]["y"],
              "group": laid["nodes"][n]["group"], "neighbours": sorted(neighbours[n])}
             for n in ids]
    return {"width": laid["width"], "height": laid["height"], "box": laid["box"],
            "nodes": nodes, "edges": laid["edges"]}


def _dispatch_rows(folded: dict) -> list[dict]:
    answered = folded.get("answered") or {}
    rows = []
    for did, d in (folded.get("dispatches") or {}).items():
        d = d or {}
        rows.append({"id": did, "role": str(d.get("role") or ""),
                     "entity": str(d.get("entity") or ""), "at": str(d.get("at") or ""),
                     "outcome": _outcome(did, d, answered)})
    return sorted(rows, key=lambda r: (r["at"], r["id"]))


def _evidence_rows(folded: dict, criteria: list[dict]) -> list[dict]:
    runs_by_id = folded.get("evidence") or {}
    defs = {c["id"]: c for c in criteria if c.get("id")}
    rows = []
    for cid in sorted(set(defs) | set(runs_by_id)):
        runs = runs_by_id.get(cid) or []
        last = runs[-1] if runs else {}
        d = defs.get(cid, {})
        rows.append({
            "id": cid,
            "criterion": d.get("criterion") or "",
            "verdict": str(last.get("verdict") or "unanswered") if runs else "unanswered",
            "runs": len(runs),
            "commit": str(last.get("state_commit") or "")[:12],
            "cites": sorted(set(str(c) for c in d.get("cites") or [])),
        })
    return rows


def _change_rows(folded: dict) -> list[dict]:
    rows = []
    for cid in sorted(folded.get("changes") or {}):
        c = folded["changes"][cid] or {}
        radius = c.get("radius") or {}
        rows.append({
            "id": cid,
            "title": c.get("title") or cid,
            "state": str(c.get("state") or ""),
            "reason": str(c.get("reason") or ""),
            "why": str(c.get("why") or ""),
            "radius": {k: len(radius.get(k) or []) for k in RADIUS_KEYS},
        })
    return rows


def _ruling_rows(folded: dict) -> list[dict]:
    return [{"id": f"R{i:02d}", "decision": str((r or {}).get("decision") or ""),
             "why": str((r or {}).get("why") or ""),
             "cost_if_wrong": str((r or {}).get("cost_if_wrong") or "")}
            for i, r in enumerate(folded.get("rulings") or [], start=1)]


def _entity_edges(folded: dict, entity_ids: set[str]) -> list[dict]:
    kept = [{"from": e["from"], "to": e["to"], "kind": e["kind"]}
            for e in folded.get("edges") or []
            if e.get("kind") in GRAPH_EDGE_KINDS
            and e.get("from") in entity_ids and e.get("to") in entity_ids]
    return sorted(kept, key=lambda e: (e["from"], e["to"], e["kind"]))


def _entity_rows(folded: dict, init_title: str, tasks: list[dict], artifacts: dict) -> list[dict]:
    task_titles = {t["id"]: t["title"] for t in tasks}
    rows = []
    for eid, ent in sorted((folded.get("entities") or {}).items()):
        kind = str((ent or {}).get("type") or "other")
        sub = str((artifacts.get(eid) or {}).get("kind") or "")
        if kind == "initiative":
            title = init_title or eid
        else:
            title = task_titles.get(eid) or (artifacts.get(eid) or {}).get("title") or eid
        rows.append({"id": eid, "type": kind, "title": str(title), "sub": sub})
    return rows


def _entity_graph(entities: list[dict], edges: list[dict]) -> dict:
    lanes = {e["id"]: e["type"] for e in entities}
    sort_key = {e["id"]: (e["sub"], e["id"]) for e in entities}
    laid = lane_layout(lanes, sort_key, [(e["from"], e["to"], e["kind"]) for e in edges])
    neighbours: dict[str, set[str]] = {e["id"]: set() for e in entities}
    for e in edges:
        neighbours[e["from"]].add(e["to"])
        neighbours[e["to"]].add(e["from"])
    nodes = [{"id": n, "x": laid["nodes"][n]["x"], "y": laid["nodes"][n]["y"],
              "lane": laid["nodes"][n]["group"], "neighbours": sorted(neighbours[n])}
             for n in sorted(laid["nodes"])]
    return {"width": laid["width"], "height": laid["height"], "box": laid["box"],
            "lanes": laid["lanes"], "nodes": nodes, "edges": laid["edges"]}


def _artifact_rows(folded: dict, edges: list[dict]) -> dict[str, dict]:
    cited_by: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["kind"] == "cites":
            cited_by[e["to"]].append(e["from"])
    rows = {}
    for aid, a in sorted((folded.get("artifacts") or {}).items()):
        a = a or {}
        rows[aid] = {
            "id": aid,
            "kind": str(a.get("kind") or ""),
            "title": str(a.get("title") or aid),
            "status": str(a.get("status") or ""),
            "summary": str(a.get("summary") or ""),
            "round": int(a.get("round") or 0),
            "cites": sorted(set(str(c) for c in a.get("cites") or [])),
            "cited_by": sorted(set(cited_by.get(aid, []))),
        }
    return rows


def _phase_rows(folded: dict, events: list[dict]) -> list[dict]:
    states = folded.get("phase_state") or {}
    current = folded.get("phase") or "intake"
    entered: dict[str, str] = {}
    for ev in events:
        if ev.get("kind") == "phase_entered":
            name = (ev.get("data") or {}).get("phase")
            if name and name not in entered:
                entered[name] = str(ev.get("ts") or "")
    run_end = str(folded.get("last_ts") or "")
    rows = []
    for i, name in enumerate(PHASES):
        start = entered.get(name, "")
        later = next((p for p in PHASES[i + 1:] if p in entered), None)
        end = entered[later] if later else run_end
        a, b = _seconds(start), _seconds(end)
        seconds = int(b - a) if a is not None and b is not None and b >= a else None
        rows.append({"name": name, "state": str(states.get(name) or ("reached" if start else "pending")),
                     "entered": start, "seconds": seconds, "current": name == current})
    return rows


def _attention(folded: dict, tasks: list[dict], dispatches: list[dict],
               evidence: list[dict], changes: list[dict]) -> list[dict]:
    items: list[dict] = []
    for t in tasks:
        if t["state"] in TASK_ATTENTION:
            items.append({"kind": "task", "ref": t["id"], "label": f"{t['title']}: {t['state']}",
                          "severity": "bad" if t["state"] in TASK_BAD else "warn"})
    for e in evidence:
        if e["verdict"] != "proven":
            items.append({"kind": "evidence", "ref": e["id"], "label": f"{e['id']}: {e['verdict']}",
                          "severity": EVIDENCE_SEVERITY.get(e["verdict"], "info")})
    for d in dispatches:
        if d["outcome"] in ("open", "spawn_error"):
            items.append({"kind": "dispatch", "ref": d["id"], "label": f"{d['role']} dispatch {d['outcome']}",
                          "severity": "bad" if d["outcome"] == "spawn_error" else "info"})
    for cid, c in sorted((folded.get("critiques") or {}).items()):
        opened = (c or {}).get("open") or []
        if opened:
            items.append({"kind": "critique", "ref": cid, "label": f"{len(opened)} open finding(s)",
                          "severity": "warn"})
    for r in folded.get("needs_ruling") or []:
        r = r or {}
        if not r.get("ruled"):
            items.append({"kind": "ruling", "ref": str(r.get("task") or ""),
                          "label": str(r.get("concern") or "ruling needed"), "severity": "warn"})
    for c in changes:
        if c["state"] not in TERMINAL_CHANGE_STATES:
            items.append({"kind": "change", "ref": c["id"], "label": f"{c['title']}: {c['state'] or 'open'}",
                          "severity": "info"})
    items.sort(key=lambda a: SEVERITY_RANK.get(a["severity"], 9))
    return items


def _timeline_rows(events: list[dict]) -> list[dict]:
    rows = []
    for ev in events:
        ts = str(ev.get("ts") or "")
        rows.append({"seq": int(ev.get("seq") or 0), "ts": ts, "day": ts[:10],
                     "kind": str(ev.get("kind") or ""), "actor": str(ev.get("actor") or ""),
                     "entity": str(ev.get("entity") or ""), "dispatch": str(ev.get("dispatch_id") or "")})
    return rows


def initiative_model(*, init_id: str, title: str, folded: dict, events: list[dict],
                     criteria: list[dict], store: dict, home: str = "",
                     parent_href: str = "") -> dict:
    """The full page model for one initiative. Pure from its inputs."""
    tasks = _task_rows(folded)
    dispatches = _dispatch_rows(folded)
    evidence = _evidence_rows(folded, criteria)
    changes = _change_rows(folded)
    rulings = _ruling_rows(folded)
    artifacts = _artifact_rows(folded, [])
    entities = _entity_rows(folded, title, tasks, artifacts)
    edges = _entity_edges(folded, {e["id"] for e in entities})
    artifacts = _artifact_rows(folded, edges)
    attention = _attention(folded, tasks, dispatches, evidence, changes)
    phase = folded.get("phase") or "intake"
    fold_edges = folded.get("edges") or []
    proven = sum(1 for e in evidence if e["verdict"] == "proven")
    pending_changes = sum(1 for c in changes if c["state"] not in TERMINAL_CHANGE_STATES)
    model = {
        "schema": MODEL_SCHEMA,
        "init": {
            "id": init_id,
            "title": title or "",
            "parent_href": parent_href,
            "phase": phase,
            "phase_state": str((folded.get("phase_state") or {}).get(phase) or "pending"),
            "done": bool(folded.get("done")),
            "last_ts": str(folded.get("last_ts") or ""),
            "seq": int(folded.get("seq") or 0),
            "events": len(events),
            "halt": str(folded.get("halt") or ""),
        },
        "store": store,
        "kpis": {
            "tasks": {"total": len(tasks), "complete": sum(t["state"] == "complete" for t in tasks)},
            "dispatches": {
                "total": len(dispatches),
                **{o: sum(d["outcome"] == o for d in dispatches)
                   for o in ("answered", "open", "abandoned", "spawn_error")},
            },
            "evidence": {"criteria": len(evidence), "proven": proven, "unproven": len(evidence) - proven},
            "artifacts": {"total": len(artifacts)},
            "changes": {"total": len(changes), "pending": pending_changes,
                        "applied": sum(c["state"] == "applied" for c in changes)},
            "rulings": {"total": len(rulings)},
            "events": {"total": len(events)},
            "entities": {"total": len(entities)},
            "edges": dict(sorted(Counter(str(e.get("kind")) for e in fold_edges).items())),
            "attention": {"total": len(attention)},
        },
        "attention": attention,
        "phases": _phase_rows(folded, events),
        "tasks": tasks,
        "dag": _dag(tasks),
        "entities": entities,
        "entity_edges": edges,
        "entity_graph": _entity_graph(entities, edges),
        "dispatches": dispatches,
        "evidence": evidence,
        "rulings": rulings,
        "changes": changes,
        "artifacts": list(artifacts.values()),
        "timeline": _timeline_rows(events),
        "policy": {str(k): v for k, v in sorted((folded.get("policy") or {}).items())},
    }
    return mask_tree(model, home)


def initiative_row(model: dict, href: str) -> dict:
    """One line of the parent index, read from a finished initiative model."""
    init, k = model["init"], model["kpis"]
    return {
        "id": init["id"],
        "title": init["title"],
        "phase": init["phase"],
        "phase_state": init["phase_state"],
        "done": init["done"],
        "last_ts": init["last_ts"],
        "events": init["events"],
        "tasks_done": k["tasks"]["complete"],
        "tasks_total": k["tasks"]["total"],
        "evidence_proven": k["evidence"]["proven"],
        "evidence_total": k["evidence"]["criteria"],
        "open_dispatches": k["dispatches"]["open"],
        "attention": k["attention"]["total"],
        "store_verdict": model["store"]["verdict"],
        "href": href,
    }


def root_model(rows: list[dict], store: dict, home: str = "") -> dict:
    """The parent index: most recent activity first, ties by id."""
    ordered = sorted(rows, key=lambda r: r["id"])
    ordered = sorted(ordered, key=lambda r: r["last_ts"] or "", reverse=True)
    totals = {
        "initiatives": len(rows),
        "active": sum(1 for r in rows if not r["done"]),
        "done": sum(1 for r in rows if r["done"]),
        "tasks_done": sum(r["tasks_done"] for r in rows),
        "tasks_total": sum(r["tasks_total"] for r in rows),
        "attention": sum(r["attention"] for r in rows),
    }
    return mask_tree({"schema": MODEL_SCHEMA, "store": store, "totals": totals,
                      "initiatives": ordered}, home)
