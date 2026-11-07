# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Atri10
"""Coordinates for the explorer graphs. Pure and deterministic.

Layout runs here, not in the browser, so the geometry a reader sees is a
function of the fold and can be tested. Dependency graphs flow top to bottom,
one layer per row. Entity graphs stack one band per lane, each band wrapped to
a fixed row width. The browser draws these coordinates and handles input; it
never decides where a node goes.
"""
from __future__ import annotations

NODE_W = 232
NODE_H = 72
COL_GAP = 40
ROW_GAP = 40
BAND_GAP = 40
HEADER = 28
MARGIN = 40
SWEEPS = 4
LANE_ORDER = ("initiative", "task", "artifact")
LANE_WRAP = 5
LABEL_LIFT = 12


def longest_path_layers(ids: list[str], edges) -> dict[str, int]:
    """Layer = length of the longest path from a root. Relaxation runs at most
    len(ids) rounds, so cycles terminate; their layers are arbitrary but stable."""
    known = set(ids)
    preds: dict[str, set[str]] = {n: set() for n in ids}
    for e in edges:
        a, b = e[0], e[1]
        if a in known and b in known and a != b:
            preds[b].add(a)
    layer = {n: 0 for n in ids}
    for _ in range(len(ids)):
        changed = False
        for n in sorted(ids):
            want = max((layer[p] + 1 for p in preds[n]), default=0)
            if want > layer[n]:
                layer[n] = want
                changed = True
        if not changed:
            break
    return layer


def _barycentre(n: str, neighbours: list[str], pos: dict[str, int]) -> float:
    if not neighbours:
        return float(pos[n])
    return sum(pos[m] for m in neighbours) / len(neighbours)


def _layers(ids: list[str], edges, layer: dict[str, int]) -> list[list[str]]:
    """One row per layer, ordered by the barycentre of each node's neighbours in
    the adjacent layer. Sweeps go down, then up; ties fall back to the id, so the
    order is reproducible."""
    known = set(ids)
    up: dict[str, list[str]] = {n: [] for n in ids}
    down: dict[str, list[str]] = {n: [] for n in ids}
    for e in edges:
        a, b = e[0], e[1]
        if a in known and b in known and layer[a] < layer[b]:
            up[b].append(a)
            down[a].append(b)
    rows: dict[int, list[str]] = {}
    for n in sorted(ids):
        rows.setdefault(layer[n], []).append(n)
    pos = {n: i for row in rows.values() for i, n in enumerate(row)}
    for sweep in range(SWEEPS):
        forward = sweep % 2 == 0
        adjacent = up if forward else down
        for k in sorted(rows, reverse=not forward):
            rows[k].sort(key=lambda n: (_barycentre(n, adjacent[n], pos), n))
            for i, n in enumerate(rows[k]):
                pos[n] = i
    return [rows[k] for k in sorted(rows)]


def _place(rows: list[list[str]], extra: list[int]) -> tuple[dict[str, tuple[int, int]], int, int]:
    """Top-left corner of every box. Rows stack top to bottom, each centred under
    the widest row; `extra[i]` is space added above row i."""
    if not rows:
        return {}, 2 * MARGIN, 2 * MARGIN
    widths = [len(row) * NODE_W + (len(row) - 1) * COL_GAP for row in rows]
    span = max(widths)
    boxes: dict[str, tuple[int, int]] = {}
    y = MARGIN
    for i, row in enumerate(rows):
        y += extra[i]
        x0 = MARGIN + (span - widths[i]) // 2
        for j, node in enumerate(row):
            boxes[node] = (x0 + j * (NODE_W + COL_GAP), y)
        y += NODE_H + ROW_GAP
    height = y - ROW_GAP + MARGIN
    return boxes, 2 * MARGIN + span, height


def edge_path(src: tuple[int, int], dst: tuple[int, int]) -> str:
    """A curve from the source's bottom centre down to the target's top centre.
    An edge that does not go down (same row, or a citation from a lower band)
    leaves from the right face and bows outward, so it never folds back through
    its own boxes."""
    (xs, ys), (xd, yd) = src, dst
    if yd >= ys + NODE_H:
        x1, y1 = xs + NODE_W // 2, ys + NODE_H
        x2, y2 = xd + NODE_W // 2, yd
        reach = max(24, (y2 - y1) // 2)
        return f"M{x1} {y1} C{x1} {y1 + reach} {x2} {y2 - reach} {x2} {y2}"
    x1, y1 = xs + NODE_W, ys + NODE_H // 2
    x2, y2 = xd + NODE_W, yd + NODE_H // 2
    bow = 56
    return f"M{x1} {y1} C{x1 + bow} {y1} {x2 + bow} {y2} {x2} {y2}"


def _laid_out(boxes: dict[str, tuple[int, int]], width: int, height: int, group: dict, edges) -> dict:
    nodes = {n: {"x": x, "y": y, "group": group[n]} for n, (x, y) in boxes.items()}
    out, seen = [], set()
    for e in edges:
        a, b = e[0], e[1]
        kind = e[2] if len(e) > 2 else ""
        if a == b or a not in boxes or b not in boxes or (a, b, kind) in seen:
            continue
        seen.add((a, b, kind))
        out.append({"from": a, "to": b, "kind": kind, "d": edge_path(boxes[a], boxes[b])})
    out.sort(key=lambda e: (e["from"], e["to"], e["kind"]))
    return {"width": width, "height": height, "box": {"w": NODE_W, "h": NODE_H},
            "nodes": nodes, "edges": out}


def layered_dag(ids: list[str], edges) -> dict:
    """Top-to-bottom layers by dependency depth. `edges` are (from, to) pairs where
    `from` must come before `to`."""
    layer = longest_path_layers(ids, edges)
    rows = _layers(ids, edges, layer)
    boxes, width, height = _place(rows, [0] * len(rows))
    group = {n: k for k, row in enumerate(rows) for n in row}
    return _laid_out(boxes, width, height, group, edges)


def lane_layout(lanes: dict[str, str], sort_key: dict[str, tuple], edges) -> dict:
    """One band per lane, bands stacked in LANE_ORDER (other lanes by name after
    them). Each band wraps its members into rows of LANE_WRAP, sorted by
    `sort_key` and then by id. Every band gets a label above its first row."""
    present = set(lanes.values())
    names = [lane for lane in LANE_ORDER if lane in present] + sorted(present - set(LANE_ORDER))
    rows: list[list[str]] = []
    extra: list[int] = []
    starts: list[int] = []
    for band, name in enumerate(names):
        members = sorted((n for n, lane in lanes.items() if lane == name),
                         key=lambda n: (sort_key.get(n, ()), n))
        starts.append(len(rows))
        for chunk_at, start in enumerate(range(0, len(members), LANE_WRAP)):
            rows.append(members[start:start + LANE_WRAP])
            lift = HEADER if chunk_at == 0 else 0
            if chunk_at == 0 and band:
                lift += BAND_GAP
            extra.append(lift)
    boxes, width, height = _place(rows, extra)
    labels = [{"name": name, "x": MARGIN, "y": boxes[rows[first][0]][1] - LABEL_LIFT}
              for name, first in zip(names, starts)]
    group = {n: lanes[n] for row in rows for n in row}
    laid = _laid_out(boxes, width, height, group, edges)
    laid["lanes"] = labels
    return laid
