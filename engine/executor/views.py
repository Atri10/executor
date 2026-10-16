# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Projections — every human-readable file regenerated from state.

These are views, never sources of truth. `render_all` runs after every
accepted ingest and on `executor check` / `status`, so a stale view is a
render lag, not a stored lie.
"""
from __future__ import annotations

from .store import Initiative, now_iso, views_dir, write_json
from . import __version__

SEV = {"critical": 0, "important": 1, "minor": 2, "info": 3}


def render_all(init: Initiative) -> None:
    """Regenerate every projection into views/ + the committed index."""
    from .engine import fold
    s = fold(init.events)
    vdir = views_dir(init.idir)
    vdir.mkdir(parents=True, exist_ok=True)
    _progress(init, s, vdir)
    _dispatches(init, s, vdir)
    _verdicts(init, s, vdir)
    _summary(init, s, vdir)
    _graph_json(init, s, vdir)


def _progress(init, s, vdir) -> None:
    lines = [f"# {init.id} — progress", "",
             f"*phase:* `{s['phase']}` · *generated:* {now_iso()} · "
             f"*engine:* {__version__}", "",
             "| Task | State | Round | Fix-rounds | Files |", "|---|---|---|---|---|"]
    for tid in sorted(s["tasks"]):
        t = s["tasks"][tid]
        lines.append(
            f"| {tid} | {t['state']} | R{t.get('round',0):02d} | "
            f"{t.get('fix_rounds',0)} | {len(t.get('files',[]))} |")
    (vdir / "progress.md").write_text("\n".join(lines) + "\n",
                                     encoding="utf-8")


def _dispatches(init, s, vdir) -> None:
    lines = [f"# {init.id} — dispatches", "",
             "| Dispatch | Entity | Role | Schema | At | Outcome |",
             "|---|---|---|---|---|---|"]
    for did, d in sorted(s["dispatches"].items()):
        if d.get("spawn_error"):
            out = f"spawn_error: {d['spawn_error']}"
        elif did in s["answered"]:
            out = "answered"
        else:
            out = "open"
        lines.append(f"| {did} | {d['entity']} | {d['role']} | {d['schema']} | "
                     f"{d['at']} | {out} |")
    (vdir / "dispatches.md").write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")


def _verdicts(init, s, vdir) -> None:
    for vid, v in s["verdicts"].items():
        lines = [f"# {vid}", "",
                 f"spec: **{v['spec_verdict']}** · "
                 f"quality: **{v['quality_verdict']}**", ""]
        if v.get("findings"):
            lines += ["| ID | Sev | Finding |", "|---|---|---|"]
            for f in sorted(v["findings"],
                            key=lambda x: SEV.get(x["severity"], 9)):
                lines.append(f"| {f['id']} | {f['severity']} | "
                             f"{f['claim']} |")
        (vdir / f"{vid}-verdict.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")


def _summary(init, s, vdir) -> None:
    lines = [f"# {init.id} — gate summary", "",
             "| Phase | State |", "|---|---|"]
    for ph, st in s["phase_state"].items():
        lines.append(f"| {ph} | {st} |")
    open_c = sum(len(c.get("open", [])) for c in s["critiques"].values())
    done = sum(1 for t in s["tasks"].values() if t["state"] == "complete")
    lines += ["", f"open critique findings: **{open_c}**",
              f"tasks complete: **{done} / {len(s['tasks'])}**",
              f"rulings: {len(s['rulings'])}"]
    (vdir / "summary.md").write_text("\n".join(lines) + "\n",
                                    encoding="utf-8")


def _graph_json(init, s, vdir) -> None:
    write_json(vdir / "graph.json",
               {"nodes": s["entities"], "edges": s["edges"],
                "generated": now_iso(), "engine": __version__})


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
    from executor.engine import _criteria_defs
    total = {c["id"] for c in _criteria_defs(s)}
    # Computed, not seeded: a criterion with no evidence event is exactly
    # the difference between the declared criteria and the answered ones.
    counts["unanswered"] = len(total - answered)
    return counts


def status_card(init: Initiative, s: dict) -> str:
    """The gate card `executor status` prints. Never artifact bytes, and plain
    ASCII: Windows consoles on legacy code pages cannot draw the glyphs that
    make a card pretty, and a crash on the status command is worse."""
    lines = [f"INITIATIVE {init.id} - {init.meta.get('title', '')}",
             f"phase: {s['phase']} ({s['phase_state'].get(s['phase'], '-')})",
             f"events: {s['seq']} | artifacts: {len(s['artifacts'])} | "
             f"tasks: {len(s['tasks'])}"]
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
    if s["halt"]:
        lines.append(f"HALTED: {s['halt']}")
    if s["phase_state"].get(s["phase"]) == "gate_pending":
        lines.append(f"-> GATE {s['phase']}: awaiting a human decision "
                     f"(ingest a gate_decision payload)")
    return "\n".join(lines)


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


def render_handoff_index(init_id: str, s: dict) -> dict:
    """The machine-readable index of a finished run: every artifact, plan, task,
    verdict and final evidence state. A pure function of the folded state."""
    return {
        "initiative": init_id,
        "phase": s["phase"],
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
    }


def render_handoff_md(init_id: str, s: dict) -> str:
    """The human-readable handoff: the same facts as the index, as tables."""
    idx = render_handoff_index(init_id, s)
    lines = [f"# {init_id} — handoff", "",
             f"Phase at handoff: `{idx['phase']}`", "",
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
    return "\n".join(lines) + "\n"
