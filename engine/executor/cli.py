#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""executor — the v2 CLI. The pump loop is next → ingest.

    executor new "<title>"                     scaffold INIT-NNNN
    executor next [INIT]                       one typed action + its prompt
    executor ingest <path|-> [INIT]            a worker payload: validate → fold → render
    executor decide <path|-> [INIT]            a human decision: gate_decision, ruling, resume
    executor status [INIT]                     gate card
    executor check [INIT]                      chain, edges, liveness, layout, policy
    executor doctor [INIT]                     check + open dispatches + policy in force
    executor graph [INIT] [--format json|mermaid]
    executor migrate [INIT] [--dry-run]        reports the store version verdict; never edits
    executor autonomy [INIT] [<phase> <allow|gate|deny>]   per-phase autonomy; deny by default

Exit codes: 0 ok · 1 check found problems or a refusal · 2 usage or engine error.
Every write goes through engine.ingest, engine.emit_next or engine.create_initiative.
Human decisions are only accepted through `decide`; a worker payload cannot name
itself human, so it cannot approve its own gate or rule on its own concern.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from executor import __version__                                   # noqa: E402
from executor.engine import (check, create_initiative, emit_next,  # noqa: E402
                             fold, ingest, open_dispatches)
from executor.paths import autonomy_file, docs_root                # noqa: E402
from executor.policy import (AUTONOMY_MODES, effective_policy,      # noqa: E402
                             normalize_autonomy)
from executor.store import (PHASES, ExecError, Initiative,          # noqa: E402
                            Rejection, find_initiative, meta_file, read_json,
                            repo_root, store_version_verdict, write_json)
from executor.views import status_card                             # noqa: E402

HUMAN_COMMANDS = frozenset({"gate_decision", "ruling", "resume"})


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _err(e: ExecError | Rejection) -> int:
    if isinstance(e, Rejection):
        print(json.dumps({"rejected": e.to_dict()}, indent=2), file=sys.stderr)
    else:
        print(json.dumps({"error": e.msg, "code": e.code}, indent=2), file=sys.stderr)
    return 2


def _read_payload(path: str) -> dict:
    """UTF-8 on every platform: a Windows console or a legacy locale must not
    decide how a payload decodes."""
    if path == "-":
        raw = sys.stdin.buffer.read().decode("utf-8")
    else:
        raw = Path(path).read_bytes().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise Rejection("not_json", "$", "valid JSON",
                        f"parse error at {e.lineno}:{e.colno}") from e


def _target(args: list[str], gate: bool = True) -> tuple[Initiative, list[str]]:
    """The initiative a command acts on: an explicit INIT-id as the first argument,
    or the one in flight. Returns the remaining arguments. `gate=False` opens a
    store whatever its engine version; only `migrate` asks for that."""
    if args and args[0].upper().startswith("INIT-"):
        return find_initiative(repo_root(), args[0].upper(), gate=gate), args[1:]
    return find_initiative(repo_root(), gate=gate), args


def cmd_new(args: list[str]) -> int:
    title = " ".join(args).strip('"').strip()
    if not title:
        raise ExecError('usage: executor new "<title>"', "usage")
    init = create_initiative(repo_root(), title)
    _emit({"created": init.id, "title": title,
           "store": str(init.idir), "docs": str(docs_root(init.root) / init.id)})
    return 0


def cmd_next(args: list[str]) -> int:
    init, _ = _target(args)
    _emit(emit_next(init))
    return 0


def cmd_ingest(args: list[str]) -> int:
    if not args:
        raise ExecError("usage: executor ingest <path.json|-> [INIT-ID]", "usage")
    payload = _read_payload(args[0])
    if payload.get("kind") in HUMAN_COMMANDS:
        raise Rejection("unauthorized", "$.kind", "a worker payload",
                        payload["kind"], "use `executor decide` for human decisions")
    init, _ = _target(args[1:])
    ev = ingest(init, payload, actor="worker")
    _emit(ev if ev.get("deduplicated") else
          {"accepted": ev["kind"], "seq": ev["seq"], "entity": ev["entity"]})
    return 0


def cmd_decide(args: list[str]) -> int:
    if not args:
        raise ExecError("usage: executor decide <path.json|-> [INIT-ID]", "usage")
    payload = _read_payload(args[0])
    kind = payload.get("kind")
    if kind not in HUMAN_COMMANDS:
        raise Rejection("unauthorized", "$.kind",
                        "gate_decision, ruling or resume", str(kind),
                        "worker payloads go through `executor ingest`")
    init, _ = _target(args[1:])
    ev = ingest(init, payload, actor="human")
    _emit({"accepted": ev["kind"], "seq": ev["seq"], "entity": ev["entity"]})
    return 0


def cmd_status(args: list[str]) -> int:
    init, _ = _target(args)
    print(status_card(init, fold(init.events)))
    return 0


def cmd_check(args: list[str]) -> int:
    init, _ = _target(args)
    res = check(init)
    _emit(res)
    return 0 if res["chain"] == "ok" and not res["problems"] else 1


def cmd_doctor(args: list[str]) -> int:
    init, _ = _target(args)
    res = check(init)
    values, sources, _sha = effective_policy(init.root, init.id, init.idir)
    res.update({
        "open_dispatch_ids": [d["dispatch_id"] for d in open_dispatches(init)],
        "policy": {"values": values, "sources": sources},
        "last_seq": len(init.events),
    })
    _emit(res)
    return 0 if res["chain"] == "ok" and not res["problems"] else 1


def cmd_autonomy(args: list[str]) -> int:
    """executor autonomy [INIT] [<phase> <allow|gate|deny>]. With no phase, prints
    the policy in force. With a phase and mode, sets it. An unknown phase or mode is
    refused, so a typo can never widen a phase: the engine fails closed on anything
    it does not recognise, and so does this command."""
    init, rest = _target(args)
    path = autonomy_file(init.idir)
    current = normalize_autonomy(read_json(path), PHASES)
    if not rest:
        _emit({"initiative": init.id, "autonomy": current})
        return 0
    if len(rest) != 2:
        raise ExecError("usage: executor autonomy [INIT] <phase> <allow|gate|deny>",
                        "usage")
    phase, mode = rest
    if phase not in PHASES:
        raise ExecError(f"unknown phase {phase!r}; phases are {', '.join(PHASES)}",
                        "unknown_phase")
    if mode not in AUTONOMY_MODES:
        raise ExecError(f"mode must be one of {', '.join(AUTONOMY_MODES)}; got {mode!r}",
                        "unknown_mode")
    write_json(path, {**current, phase: mode})
    _emit({"initiative": init.id, "set": {phase: mode},
           "autonomy": normalize_autonomy(read_json(path), PHASES)})
    return 0


def cmd_graph(args: list[str]) -> int:
    fmt = "json"
    if "--format" in args:
        i = args.index("--format")
        if i + 1 >= len(args):
            raise ExecError("usage: --format json|mermaid", "usage")
        fmt = args[i + 1]
        args = args[:i] + args[i + 2:]
    if fmt not in ("json", "mermaid"):
        raise ExecError(f"unknown graph format {fmt!r}", "usage")
    init, _ = _target(args)
    s = fold(init.events)
    if fmt == "mermaid":
        lines = ["flowchart LR"]
        for e in s["edges"]:
            a = e["from"].replace("-", "_")
            b = e["to"].replace("-", "_")
            lines.append(f"    {a} -->|{e['kind']}| {b}")
        for nid, n in s["entities"].items():
            lines.append(f"    {nid.replace('-', '_')}[\"{nid}\\n{n['type']}\"]")
        print("\n".join(lines))
    else:
        _emit({"nodes": s["entities"], "edges": s["edges"], "initiative": init.id})
    return 0


def cmd_migrate(args: list[str]) -> int:
    """Reports the store's version verdict, the same one the engine enforces when
    it opens a store. It opens the store ungated, because a skewed store is exactly
    what it must explain. No upgrade path exists yet, so it never edits anything."""
    init, rest = _target(args, gate=False)
    meta = read_json(meta_file(init.idir)) or {}
    verdict = store_version_verdict(meta.get("engine_version", "0"))
    _emit({"initiative": init.id,
           "store_engine_version": meta.get("engine_version"),
           "engine": __version__, "dry_run": "--dry-run" in rest,
           "verdict": verdict,
           "action": "none" if verdict == "current"
           else "refused: no migration is defined for this engine version"})
    return 0 if verdict == "current" else 1


COMMANDS = {"new": cmd_new, "next": cmd_next, "ingest": cmd_ingest,
            "decide": cmd_decide, "status": cmd_status, "check": cmd_check,
            "doctor": cmd_doctor, "graph": cmd_graph, "migrate": cmd_migrate,
            "autonomy": cmd_autonomy}


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
    except (Rejection, ExecError) as e:
        return _err(e)
    except FileNotFoundError as e:
        return _err(ExecError(str(e), "missing_file"))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv))
