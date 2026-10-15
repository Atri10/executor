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
             "| Dispatch | Task | Role | Model | At | Outcome |",
             "|---|---|---|---|---|---|"]
    for did, d in sorted(s["dispatches"].items()):
        out = d.get("spawn_error") or (
            "complete" if s["tasks"].get(d["task"], {})
                         .get("state") in ("complete", "reported")
            else "in-flight")
        lines.append(f"| {did} | {d['task']} | {d['role']} | "
                     f"{d.get('model') or '—'} | {d['at']} | {out} |")
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


def status_card(init: Initiative, s: dict) -> str:
    """The gate card `executor status` prints — never artifact bytes."""
    lines = [f"INITIATIVE {init.id} — {init.meta.get('title','')}",
             f"phase: {s['phase']} ({s['phase_state'].get(s['phase'],'—')})",
             f"events: {s['seq']} · artifacts: {len(s['artifacts'])} · "
             f"tasks: {len(s['tasks'])}"]
    open_c = sum(len(c.get("open", [])) for c in s["critiques"].values())
    if open_c:
        lines.append(f"open critique findings: {open_c}")
    if s.get("needs_ruling"):
        unruled = [n for n in s["needs_ruling"] if not n.get("ruled")]
        if unruled:
            lines.append(f"⚠ {len(unruled)} concern(s) awaiting rulings")
    if s["halt"]:
        lines.append(f"⛔ HALTED: {s['halt']}")
    if s["phase_state"].get(s["phase"]) == "gate_pending":
        lines.append(f"→ GATE {s['phase']} — awaiting human decision "
                     f"(ingest a gate_decision payload)")
    return "\n".join(lines)
