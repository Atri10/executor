# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Projections — every human-readable file regenerated from the fold.

These are views, never sources of truth. `render_all` runs after every
accepted ingest and on `executor check` / `status`, so a stale view is a
render lag, not a stored lie.

Two rules make a view checkable:

* **A projection is a function of the journal.** The stamp a view carries
  is the journal tip's timestamp, never the wall clock, so rendering one
  journal twice produces identical bytes. That is what lets `check`
  compare a committed or run-store projection against a fresh render.
* **A leaf has one owner.** `views/tasks/<TASK-ID>/task.md` carries every
  round of that task and nothing else; `views/plans/<PLAN-ID>/plan.md`
  carries that plan and nothing else. The flat per-round file is gone, so
  the tree is `O(entities)` rather than `O(rounds)`.
"""
from __future__ import annotations

from .paths import view_plan_file, view_task_file
from .store import Initiative, json_text, views_dir, write_json

SEV = {"critical": 0, "important": 1, "minor": 2, "info": 3}

# The sentence that makes seq-derived dispatch ids legible. It appears in
# the registry view and in `executor graph`, because an unexplained gap
# reads as a bug.
DISPATCH_SEMANTICS = ("dispatch ids are journal sequence numbers: a gap is "
                     "an event that was not a dispatch")


def _stamp(init: Initiative) -> str:
    """The run's own clock: the journal tip. A projection that stamped the
    wall clock could not be compared to a re-render."""
    return init.events[-1]["ts"] if init.events else "no-events"


def render_plan(init: Initiative) -> dict:
    """Every view file, as text, without writing. The migration needs the same
    bytes the engine writes, so the renderer is one function and `render_all`
    is its only writer."""
    from .engine import fold
    s = fold(init.events)
    stamp = _stamp(init)
    vdir = views_dir(init.idir)
    out = {vdir / "progress.md": progress_md(init, s, stamp),
           vdir / "dispatches.md": dispatches_md(init, s, stamp),
           vdir / "summary.md": summary_md(init, s, stamp),
           vdir / "index.md": index_md(init, s, stamp),
           vdir / "graph.json": json_text(graph_obj(init, s, stamp))}
    for pid in s["plan_order"]:
        out[view_plan_file(init.idir, pid)] = plan_view_md(init, s, pid, stamp)
    for tid in sorted(s["tasks"]):
        out[view_task_file(init.idir, tid)] = task_view_md(init, s, tid, stamp)
    return out


def render_all(init: Initiative) -> None:
    """Regenerate every projection into the views tree."""
    for path, text in render_plan(init).items():
        _text(path, text)


def _text(path, text: str) -> None:
    """Write only when the bytes change: a repeated poll costs nothing, and a
    byte comparison against a re-render stays meaningful."""
    data = text.encode("utf-8")
    try:
        if path.read_bytes() == data:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _header(init: Initiative, title: str, stamp: str) -> list[str]:
    return [f"# {init.id} — {title}", "",
            f"*phase:* `{fold_phase(init)}` · *stamp:* {stamp} · "
            f"*engine:* {_version()}", ""]


def _version() -> str:
    from . import __version__
    return __version__


def fold_phase(init: Initiative) -> str:
    from .engine import fold
    return fold(init.events)["phase"]


# ---------------------------------------------------------------- aggregates

def progress_md(init: Initiative, s: dict, stamp: str) -> str:
    lines = _header(init, "progress", stamp)
    lines += ["| Task | State | Round | Fix-rounds | Files |",
              "|---|---|---|---|---|"]
    for tid in sorted(s["tasks"]):
        t = s["tasks"][tid]
        lines.append(
            f"| {tid} | {t['state']} | R{t.get('round', 0):02d} | "
            f"{t.get('fix_rounds', 0)} | {len(t.get('files', []))} |")
    if s["rulings"]:
        lines += ["", "## Rulings", "",
                  "| Seq | Target | Decision | Stops the run |",
                  "|---|---|---|---|"]
        for i, r in enumerate(s["rulings"]):
            decision = " ".join(str(r.get("decision", "")).split())
            if len(decision) > 120:
                decision = decision[:117] + "…"
            lines.append(f"| {r.get('_seq', i + 1)} | {r.get('for_task') or '-'} "
                         f"| {decision} | {'yes' if r.get('stop') else 'no'} |")
    return "\n".join(lines) + "\n"


def dispatches_md(init: Initiative, s: dict, stamp: str) -> str:
    from .paths import dispatch_key
    lines = _header(init, "dispatches", stamp)
    lines += [f"*{DISPATCH_SEMANTICS}*", "",
              "| Dispatch | Entity | Role | Schema | At | Outcome |",
              "|---|---|---|---|---|---|"]
    for did, d in sorted(s["dispatches"].items(), key=lambda kv: dispatch_key(kv[0])):
        lines.append(f"| {did} | {d['entity']} | {d['role']} | {d['schema']} | "
                     f"{d['at']} | {_outcome(s, did, d)} |")
    return "\n".join(lines) + "\n"


def _outcome(s: dict, did: str, d: dict) -> str:
    """The dispatch's own terminal field, in the order the engine writes them.
    An abandoned dispatch is not an answer; reading the fold's `answered` map
    alone reported both as answered (audit D17)."""
    if d.get("spawn_error"):
        return f"spawn_error: {d['spawn_error']}"
    if d.get("abandoned"):
        return f"abandoned: {d['abandoned']}"
    return "answered" if did in s["answered"] else "open"


def summary_md(init: Initiative, s: dict, stamp: str) -> str:
    lines = _header(init, "gate summary", stamp)
    lines += ["| Phase | State |", "|---|---|"]
    for ph, st in s["phase_state"].items():
        lines.append(f"| {ph} | {st} |")
    open_c = sum(len(c.get("open", [])) for c in s["critiques"].values())
    done = sum(1 for t in s["tasks"].values() if t["state"] == "complete")
    lines += ["", f"open critique findings: **{open_c}**",
              f"tasks complete: **{done} / {len(s['tasks'])}**",
              f"rulings: {len(s['rulings'])}"]
    if s["changes"]:
        lines += ["", "| Change | State | Tasks | Criteria |",
                  "|---|---|---|---|"]
        for cid, c in sorted(s["changes"].items()):
            r = c.get("radius") or {}
            lines.append(f"| {cid} | {c['state']} | "
                         f"{len(r.get('tasks', []))} | "
                         f"{len(r.get('criteria', []))} |")
    return "\n".join(lines) + "\n"


def graph_obj(init: Initiative, s: dict, stamp: str) -> dict:
    return {"nodes": s["entities"], "edges": s["edges"],
            "dispatch_id_semantics": DISPATCH_SEMANTICS,
            "stamp": stamp, "engine": _version()}


def index_md(init: Initiative, s: dict, stamp: str) -> str:
    """The stable root index: everything the tree holds, named by id."""
    lines = _header(init, "index", stamp)
    lines += ["## Aggregates", "",
              "- [progress](progress.md) — every task and its state",
              "- [dispatches](dispatches.md) — every dispatch and its outcome",
              "- [summary](summary.md) — phase states, criteria, changes",
              "- [graph](graph.json) — entities and edges, machine-readable",
              "", f"*{DISPATCH_SEMANTICS}*", ""]
    if s["plan_order"]:
        lines += ["## Plans", ""]
        for pid in s["plan_order"]:
            n = sum(1 for tid, t in s["tasks"].items() if t["plan"] == pid)
            lines.append(f"- [{pid}](plans/{pid}/plan.md) — {n} task(s), "
                         f"{s['plans'].get(pid, {}).get('status', 'draft')}")
        lines.append("")
    if s["tasks"]:
        lines += ["## Tasks", ""]
        for tid in sorted(s["tasks"]):
            lines.append(f"- [{tid}](tasks/{tid}/task.md) — "
                         f"{s['tasks'][tid]['state']}")
        lines.append("")
    if s["changes"]:
        lines += ["## Changes", ""]
        for cid, c in sorted(s["changes"].items()):
            lines.append(f"- {cid} — {c['state']}: {c['title']}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- per entity

def plan_view_md(init: Initiative, s: dict, pid: str, stamp: str) -> str:
    lines = _header(init, f"plan {pid}", stamp)
    plan = s["plans"].get(pid, {})
    lines += [f"- status: **{plan.get('status', 'draft')}**",
              f"- merged: `{plan.get('merge_sha') or '-'}`", ""]
    lines += ["| Task | State | Depends on | Round |", "|---|---|---|---|"]
    for tid in sorted(t for t, v in s["tasks"].items() if v["plan"] == pid):
        t = s["tasks"][tid]
        deps = ", ".join(t.get("depends_on", [])) or "-"
        lines.append(f"| {tid} | {t['state']} | {deps} | "
                     f"R{t.get('round', 0):02d} |")
    return "\n".join(lines) + "\n"


def task_view_md(init: Initiative, s: dict, tid: str, stamp: str) -> str:
    """One leaf per task: its contract, every review round, every finding.
    This replaces one flat file per round (audit D03)."""
    t = s["tasks"][tid]
    lines = _header(init, f"task {tid}", stamp)
    lines += [f"- state: **{t['state']}** · round **R{t.get('round', 0):02d}** · "
              f"fix-rounds **{t.get('fix_rounds', 0)}**",
              f"- title: {t.get('title', '')}", ""]
    if t.get("files"):
        lines += ["**files**", "", *[f"- `{f}`" for f in t["files"]], ""]
    rounds = sorted((v for v in s["verdicts"].values()
                     if v["task"] == tid), key=lambda v: v["round"])
    if rounds:
        lines += ["## Rounds", "",
                  "| Round | Spec | Quality | Findings |", "|---|---|---|---|"]
        for v in rounds:
            lines.append(f"| R{v['round']:02d} | {v['spec_verdict']} | "
                         f"{v['quality_verdict']} | {len(v.get('findings', []))} |")
        lines.append("")
        for v in rounds:
            if not v.get("findings"):
                continue
            lines += [f"### R{v['round']:02d} findings", ""]
            for f in sorted(v["findings"], key=lambda x: SEV.get(x["severity"], 9)):
                lines.append(f"- **{f['id']}** ({f['severity']}): {f['claim']}")
            lines.append("")
    reports = [r for k, r in s["reports"].items() if k == tid]
    if reports:
        lines += ["## Reports", ""]
        for r in reports:
            commits = ", ".join(f"`{c[:12]}`" for c in r.get("commits", [])) or "none"
            lines.append(f"- {r.get('result')} — {commits}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- committed

def render_report_md(p: dict, did: str) -> str:
    """The committed record of one worker report. No timestamp, so re-rendering
    the same payload writes the same bytes."""
    lines = [f"# {p['task']} — report {did}", "",
             f"**result:** {p['result']}", "", p["summary"], "", "**commits:**"]
    lines += [f"- `{c}`" for c in p.get("commits", [])] or ["- none"]
    if p.get("concerns"):
        lines += ["", "**concerns:**", *[f"- {c}" for c in p["concerns"]]]
    return "\n".join(lines) + "\n"


def render_verdict_md(p: dict) -> str:
    """The committed record of one review round. Findings are sorted by
    severity so the same verdict always renders the same bytes."""
    lines = [f"# {p['task']} — verdict R{p['round']:02d}", "",
             f"- spec: **{p['spec_verdict']}**",
             f"- quality: **{p['quality_verdict']}**",
             f"- range: `{p['commit_base']}..{p['commit_head']}`",
             f"- package: `{p['reviewed_package_sha']}`", "", "## Findings"]
    found = sorted(p.get("findings", []), key=lambda f: SEV.get(f["severity"], 9))
    lines += [f"- **{f['id']}** ({f['severity']}): {f['claim']}" for f in found] or ["- none"]
    return "\n".join(lines) + "\n"


def evidence_counts(s: dict) -> dict[str, int]:
    """Verification counts, unanswered included. A criterion with no
    evidence event is unproven however obviously it 'must' work, so it is
    counted rather than absorbed into a sentence about the others."""
    counts = {"proven": 0, "failed": 0, "unavailable": 0}
    answered = set()
    for cid, runs in s["evidence"].items():
        verdict = runs[-1]["verdict"]
        if verdict in counts:
            counts[verdict] += 1
            answered.add(cid)
    total = {c["id"] for c in _criteria_defs(s)}
    # Computed, not seeded: a criterion with no evidence event is exactly
    # the difference between the declared criteria and the answered ones.
    counts["unanswered"] = len(total - answered)
    return counts


def _criteria_defs(s: dict) -> list[dict]:
    from .engine import _criteria_defs as defs
    return defs(s)


def status_card(init: Initiative, s: dict) -> str:
    """The gate card `executor status` prints. Never artifact bytes, and plain
    ASCII: Windows consoles on legacy code pages cannot draw the glyphs that
    make a card pretty, and a crash on the status command is worse."""
    lines = [f"INITIATIVE {init.id} - {init.meta.get('title', '')}",
             f"phase: {s['phase']} ({s['phase_state'].get(s['phase'], '-')})",
             f"events: {s['seq']} | artifacts: {len(s['artifacts'])} | "
             f"tasks: {len(s['tasks'])}"]
    pol = s["policy"]               # every fold carries the policy in force
    v, src = pol["values"], pol.get("sources") or {}
    lines.append(
        f"policy: audit<={v.get('max_audit_rounds')} "
        f"fix<={v.get('max_fix_rounds')} "
        f"evidence<={v.get('max_evidence_tries')} "
        f"autonomy[{s['phase']}]="
        f"{v.get('autonomy', {}).get(s['phase'], 'deny')} "
        f"(from {src.get('max_fix_rounds', 'default')})")
    if any(a["kind"] == "vrfy" for a in s["artifacts"].values()):
        c = evidence_counts(s)
        lines.append(f"evidence: {c['proven']} proven | {c['failed']} failed "
                     f"| {c['unavailable']} unavailable "
                     f"| {c['unanswered']} unanswered")
    open_c = sum(len(c["open"]) for c in s["critiques"].values())
    if open_c:
        lines.append(f"open critique findings: {open_c}")
    unruled = [n for n in s["needs_ruling"] if not n["ruled"]]
    if unruled:
        lines.append(f"! {len(unruled)} concern(s) awaiting rulings")
    if s.get("changes"):
        for cid, c in sorted(s["changes"].items()):
            if c["state"] in ("requested", "scoped"):
                radius = c.get("radius") or {}
                lines.append(
                    f"change: {cid} {c['state']} "
                    f"({len(radius.get('tasks', []))} task(s), "
                    f"{len(radius.get('criteria', []))} criteria"
                    f"{', coarse' if radius.get('coarse') else ''})")
    if s["halt"]:
        lines.append(f"HALTED: {s['halt']}")
    if s["phase_state"].get(s["phase"]) == "gate_pending":
        lines.append(f"-> GATE {s['phase']}: awaiting a human decision "
                     f"(ingest a gate_decision payload)")
    return "\n".join(lines)


def render_handoff_index(init_id: str, s: dict) -> dict:
    """The machine-readable index of a run: every artifact, plan, task,
    verdict and final evidence state, plus its changes. A pure function of
    the folded state, so it is written mid-run and verified against the fold."""
    return {
        "initiative": init_id,
        "phase": s["phase"],
        "phase_state": dict(s["phase_state"]),
        "stamp": s.get("last_ts", ""),
        "artifacts": [{"id": aid, "kind": a["kind"], "status": a["status"],
                       "rounds": a["round"]}
                      for aid, a in sorted(s["artifacts"].items())],
        "plans": [{"id": pid, "status": s["plans"][pid]["status"],
                   "tasks": sorted(t for t in s["tasks"]
                                   if t.startswith(pid + "-"))}
                  for pid in s["plan_order"]],
        "tasks": {tid: t["state"] for tid, t in sorted(s["tasks"].items())},
        "verdicts": sorted(s["verdicts"]),
        "evidence": {cid: runs[-1]["verdict"]
                     for cid, runs in sorted(s["evidence"].items())},
        "changes": [{"id": cid, "state": c["state"], "title": c["title"]}
                    for cid, c in sorted(s.get("changes", {}).items())],
    }


def render_handoff_md(init_id: str, s: dict) -> str:
    """The human-readable index: the same facts as the JSON, as tables."""
    idx = render_handoff_index(init_id, s)
    lines = [f"# {init_id} — index", "",
             f"Phase: `{idx['phase']}`", "",
             "## Artifacts", "", "| Id | Kind | Status | Rounds |", "|---|---|---|---|"]
    lines += [f"| {a['id']} | {a['kind']} | {a['status']} | {a['rounds']} |"
              for a in idx["artifacts"]]
    lines += ["", "## Plans", ""]
    lines += [f"- `{p['id']}` ({p['status']}): {len(p['tasks'])} task(s)"
              for p in idx["plans"]] or ["- none"]
    lines += ["", "## Tasks", "", "| Task | State |", "|---|---|"]
    lines += [f"| {tid} | {state} |" for tid, state in idx["tasks"].items()]
    lines += ["", "## Evidence", ""]
    lines += [f"- {cid}: {v}" for cid, v in idx["evidence"].items()] or ["- none"]
    if idx["changes"]:
        lines += ["", "## Changes", ""]
        lines += [f"- `{c['id']}` ({c['state']}): {c['title']}"
                  for c in idx["changes"]]
    return "\n".join(lines) + "\n"
