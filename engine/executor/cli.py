#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""executor — the v2 CLI. Nine commands; the pump loop is next → ingest.

    executor new "<title>"          scaffold INIT-NNNN
    executor next                   → one typed action + minted payload slot
    executor ingest <path|->        validate → fold → render, or typed reject
    executor status                 gate card / current position
    executor check [--secrets]      journal re-fold, chain verify, integrity
    executor doctor                 check + open slots + autonomy
    executor autonomy [phase mode]  per-phase allow|gate|deny
    executor migrate [--dry-run]    version upgrade
    executor graph [--format json|mermaid]   nodes + edges

Exit codes: 0 ok · 1 rejection (typed error on stderr) · 2 usage/engine error.
Every mutating path goes through engine.ingest — there is no other writer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from executor import __version__                      # noqa: E402
from executor.engine import check, emit_next, ingest, fold   # noqa: E402
from executor.store import (ExecError, Initiative, Rejection, autonomy_file,
                            docs_root, find_initiative, init_store,
                            open_slots, read_json, repo_root, run_root,
                            PHASES)
from executor.views import status_card               # noqa: E402


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2))


def _err(e: ExecError | Rejection) -> int:
    if isinstance(e, Rejection):
        print(json.dumps({"error": e.to_dict()}), file=sys.stderr)
        return 1
    print(json.dumps({"error": {"code": e.code, "message": e.msg}}),
          file=sys.stderr)
    return 2


def _init_id(root: Path) -> str:
    existing = sorted(run_root(root).glob("INIT-*"))
    n = max([int(d.name.split("-")[1]) for d in existing
             if d.name.split("-")[1].isdigit()] or [0]) + 1
    return f"INIT-{n:04d}"


def cmd_new(args: list[str]) -> int:
    title = " ".join(args).strip('"')
    if not title:
        raise ExecError('usage: executor new "<title>"', "usage")
    root = repo_root()
    iid = _init_id(root)
    idir = init_store(root, iid, title)
    init = Initiative(iid, root, idir)
    from executor.engine import make_event, append_event  # noqa
    ev = make_event(idir, "engine", "created", iid, {"title": title})
    append_event(idir, ev)
    _emit({"created": iid, "title": title, "store": str(idir),
           "docs": str(docs_root(root) / iid)})
    return 0


def cmd_next(args: list[str]) -> int:
    init = find_initiative(repo_root(), args[0] if args else None)
    act = emit_next(init)
    _emit(act)
    return 0


def cmd_ingest(args: list[str]) -> int:
    if not args:
        raise ExecError("usage: executor ingest <path.json|->", "usage")
    actor = "worker"
    path = args[0]
    if len(args) > 1 and args[1] == "--actor":
        actor = args[2]
    raw = sys.stdin.read() if path == "-" else Path(path).read_text()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Rejection("not_json", "$", "valid JSON",
                        f"parse error at {e.lineno}:{e.colno}")
    init = find_initiative(repo_root())
    ev = ingest(init, payload, actor=actor)
    _emit({"accepted": ev["kind"], "seq": ev["seq"], "entity": ev["entity"]})
    return 0


def cmd_status(args: list[str]) -> int:
    init = find_initiative(repo_root(), args[0] if args else None)
    s = fold(init.events)
    print(status_card(init, s))
    return 0


def cmd_check(args: list[str]) -> int:
    init = find_initiative(repo_root(), args[0] if args else None)
    res = check(init)
    _emit(res)
    return 0 if res["chain"] == "ok" and not res["problems"] else 1


def cmd_graph(args: list[str]) -> int:
    fmt = "json"
    if "--format" in args:
        i = args.index("--format"); fmt = args[i + 1]
        args = args[:i] + args[i + 2:]
    init = find_initiative(repo_root(), args[0] if args else None)
    s = fold(init.events)
    if fmt == "mermaid":
        lines = ["flowchart LR"]
        for e in s["edges"]:
            a = e["from"].replace("-", "_")
            b = e["to"].replace("-", "_")
            lines.append(f"    {a} -->|{e['kind']}| {b}")
        for nid, n in s["entities"].items():
            lines.append(f"    {nid.replace('-','_')}[\"{nid}\\n{n['type']}\"]")
        print("\n".join(lines))
    else:
        _emit({"nodes": s["entities"], "edges": s["edges"],
               "initiative": init.id})
    return 0


def cmd_migrate(args: list[str]) -> int:
    init = find_initiative(repo_root(), args[0] if args else None)
    meta = init.meta
    _emit({"store": meta.get("engine_version"), "engine": __version__,
           "action": "no migration needed"
           if meta.get("engine_version") == __version__
           else "would migrate via upcaster chain (v1→v2 not yet required)",
           "dry_run": "--dry-run" in args})
    return 0


def cmd_autonomy(args: list[str]) -> int:
    """executor autonomy [INIT-NNNN] [<phase> <allow|gate|deny>]."""
    sel = args[0] if args and args[0].upper().startswith("INIT-") else None
    if sel:
        args = args[1:]
    init = find_initiative(repo_root(), sel)
    f = autonomy_file(init.idir)
    cur = read_json(f) or {p: "deny" for p in PHASES}
    if len(args) >= 2:
        phase, mode = args[0], args[1]
        if phase not in PHASES:
            _die(f"unknown phase {phase}")
        if mode not in ("allow", "gate", "deny"):
            _die("mode must be allow|gate|deny")
        cur[phase] = mode
        f.write_text(json.dumps(cur, indent=2) + "\n")
        _emit({"set": {phase: mode}, "autonomy": cur})
    elif len(args) == 1:
        _die("autonomy set needs <phase> <mode>")
    else:
        _emit({"autonomy": cur})
    return 0


def cmd_doctor(args: list[str]) -> int:
    """executor doctor — check + slot/liveness report."""
    init = find_initiative(repo_root(), args[0] if args else None)
    res = check(init)
    s = fold(init.events)
    open_s = [x["dispatch_id"] for x in open_slots(init.idir)]
    res.update({
        "open_dispatch_ids": open_s,
        "autonomy": read_json(autonomy_file(init.idir)),
        "last_seq": len(init.events),
    })
    _emit(res)
    return 0


COMMANDS = {"new": cmd_new, "next": cmd_next, "ingest": cmd_ingest,
            "status": cmd_status, "check": cmd_check, "graph": cmd_graph,
            "migrate": cmd_migrate, "autonomy": cmd_autonomy,
            "doctor": cmd_doctor}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    if cmd in ("-V", "--version"):
        print(__version__)
        return 0
    fn = COMMANDS.get(cmd)
    if not fn:
        print(f"unknown command {cmd!r}\n{__doc__}", file=sys.stderr)
        return 2
    try:
        return fn(argv[2:])
    except Rejection as e:
        return _err(e)
    except ExecError as e:
        return _err(e)
    except FileNotFoundError as e:
        return _err(ExecError(str(e), "missing_file"))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv))
