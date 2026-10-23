"""One-sheet P&ID layout.

The sheet groups of ``layout_hints.yaml`` become *zones* (plant areas) of a single drawing:

1. every zone is laid out with the layered engine of :mod:`layout`; a connection that leaves the zone
   ends at a *terminal* pinned to the zone's left (inflow) or right (outflow) column;
2. the zones are arranged in rows so that connected zones sit next to each other (wire length) and the
   whole drawing fits the sheet's aspect ratio (readability);
3. every connection between zones is routed as one continuous pipe by an orthogonal A* router on a grid
   that avoids the zone frames, separates parallel runs onto their own tracks and penalises bends and
   crossings.

No off-page connectors are needed.  As everywhere, nothing here is written back to the topology.
"""

from __future__ import annotations

import heapq
import math
import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .layout import (
    MEdge,
    MNode,
    SheetLayout,
    SheetSpec,
    _shift,
    build_macro,
    default_specs,
    layout_qa,
    layout_sheet,
    place_instruments,
)
from .schema import Topology

ZONE_PAD = 26.0      # zone frame around its content
ZONE_TITLE = 30.0    # title band at the top of a zone frame
GAP = 110.0          # channel between zones (room for the inter-zone tracks)
CELL = 10.0          # router grid
DRAW_AREA = (2900.0, 2250.0)  # A0 landscape drawing field (pt) left of the notes column
TARGET_SCALE = 0.9


@dataclass
class Zone:
    spec: SheetSpec
    layout: SheetLayout
    frame: tuple[float, float, float, float] = (0, 0, 0, 0)  # x0, y0, x1, y1

    @property
    def w(self) -> float:
        return self.frame[2] - self.frame[0]

    @property
    def h(self) -> float:
        return self.frame[3] - self.frame[1]


@dataclass
class Link:
    edge: MEdge          # original macro edge (its valves are drawn inside the source zone)
    a: str               # source zone
    b: str               # target zone
    t_out: str           # terminal node ids
    t_in: str
    s_out: str = "R"     # zone side the pipe leaves from / arrives at
    s_in: str = "L"


@dataclass
class OneSheet:
    zones: list[Zone]
    layout: SheetLayout                      # every node, edge, instrument of the drawing
    links: list[Link] = field(default_factory=list)
    routes: dict[str, list[tuple[float, float]]] = field(default_factory=dict)  # link edge id -> polyline
    warnings: list[str] = field(default_factory=list)


def _terminal(nid: str, direction: str, side: str) -> MNode:
    sym = {("in", "L"): "t_in", ("in", "R"): "t_in_r", ("out", "R"): "t_out", ("out", "L"): "t_out_l"}[(direction, side)]
    n = MNode(id=nid, kind="terminal", w=2, h=4, label_h=0, symbol=sym)
    n.ports["port"] = ("R", 0.0) if direction == "in" else ("L", 0.0)
    return n


def build_onesheet(topo: Topology, hints: dict[str, Any] | None = None) -> OneSheet:
    hints = hints or {}
    cfg = hints.get("onesheet", {})
    # pass 1: every connection leaves right / enters left; arrange the zones
    zones, links = _zones(topo, hints, {})
    _arrange(zones, links, cfg)
    # pass 2: each connection uses the zone sides that face each other, then arrange again
    sides = _choose_sides(zones, links)
    zones, links = _zones(topo, hints, sides)
    rows = _arrange(zones, links, cfg)
    # pass 3: keep that arrangement, make the sides consistent with it
    sides2 = _choose_sides(zones, links)
    if sides2 != sides:
        zones, links = _zones(topo, hints, sides2)
        _arrange(zones, links, {"rows": rows})
    zmap = {z.spec.id: z for z in zones}
    for z in zones:
        _shift(z.layout, z.frame[0], z.frame[1])
        _shift_instruments(z.layout, z.frame[0], z.frame[1])
    out = SheetLayout(sheet_id="ONE", title=hints.get("title", "P&ID"))
    for z in zones:
        out.nodes.update(z.layout.nodes)
        out.edges += z.layout.edges
        out.instruments += z.layout.instruments
        out.signals += z.layout.signals
        out.warnings += z.layout.warnings
    os_ = OneSheet(zones=zones, layout=out, links=links)
    _route_links(os_, zmap)
    for lk in links:
        path = os_.routes.get(lk.edge.id)
        if path:
            out.edges.append(MEdge(id=lk.edge.id + "~x", src=(lk.t_out, "port"), dst=(lk.t_in, "port"), line_ids=[], service=lk.edge.service,
                                   header=lk.edge.header, proposed=lk.edge.proposed, path=path, logical=set()))
    xs = [z.frame[0] for z in zones] + [z.frame[2] for z in zones]
    ys = [z.frame[1] for z in zones] + [z.frame[3] for z in zones]
    for p in os_.routes.values():
        xs += [q[0] for q in p]
        ys += [q[1] for q in p]
    out.bbox = (min(xs), min(ys), max(xs), max(ys))
    return os_


def _zones(topo: Topology, hints: dict[str, Any], sides: dict[str, tuple[str, str]]) -> tuple[list[Zone], list[Link]]:
    specs = default_specs(topo, hints)
    macro = build_macro(topo, specs)
    per_nodes: dict[str, dict[str, MNode]] = {s.id: {} for s in specs}
    per_edges: dict[str, list[MEdge]] = {s.id: [] for s in specs}
    for n in macro.nodes.values():
        per_nodes[n.sheet][n.id] = n
    links: list[Link] = []
    for e in macro.edges:
        a = macro.nodes[e.src[0]]
        if e.stub or macro.nodes[e.dst[0]].sheet == a.sheet:
            per_edges[a.sheet].append(e)
            continue
        b = macro.nodes[e.dst[0]]
        so, si = sides.get(e.id, ("R", "L"))
        to, ti = _terminal(f"t:out:{e.id}", "out", so), _terminal(f"t:in:{e.id}", "in", si)
        to.sheet, ti.sheet = a.sheet, b.sheet
        per_nodes[a.sheet][to.id] = to
        per_nodes[b.sheet][ti.id] = ti
        per_edges[a.sheet].append(MEdge(id=e.id, src=e.src, dst=(to.id, "port"), chain=e.chain, line_ids=e.line_ids, service=e.service,
                                        header=e.header, proposed=e.proposed, logical=e.logical))
        per_edges[b.sheet].append(MEdge(id=e.id + "~in", src=(ti.id, "port"), dst=e.dst, line_ids=[], service=e.service,
                                        header=e.header, proposed=e.proposed, logical=set()))
        links.append(Link(e, a.sheet, b.sheet, to.id, ti.id, so, si))
    inst_lines: dict[str, int] = defaultdict(int)
    for i_ in topo.instruments:
        if (i_.target or {}).get("kind") == "line":
            inst_lines[i_.target["ref"]] += 1
    zones: list[Zone] = []
    for s in specs:
        if not per_nodes[s.id]:
            continue
        zh = {"max_width": 2400.0, **s.hints, "inst_lines": dict(inst_lines), "stack": True}
        sl = layout_sheet(s.id, s.title, per_nodes[s.id], per_edges[s.id], zh)
        place_instruments(sl, topo)
        x0, y0, x1, y1 = sl.bbox
        dx, dy = -x0 + ZONE_PAD, -y0 + ZONE_PAD + ZONE_TITLE
        _shift(sl, dx, dy)
        _shift_instruments(sl, dx, dy)
        zones.append(Zone(s, sl, (0.0, 0.0, x1 - x0 + 2 * ZONE_PAD, y1 - y0 + 2 * ZONE_PAD + ZONE_TITLE)))
    return zones, links


def _choose_sides(zones: list[Zone], links: list[Link]) -> dict[str, tuple[str, str]]:
    """Per connection, the pair of zone sides giving the shortest run for the current arrangement."""
    zmap = {z.spec.id: z for z in zones}
    ty = _term_y(zones)
    out: dict[str, tuple[str, str]] = {}
    for lk in links:
        best = None
        for so, si in (("R", "L"), ("L", "R"), ("R", "R"), ("L", "L")):
            d = _link_len(zmap[lk.a], zmap[lk.b], (zmap[lk.a].frame[0], zmap[lk.a].frame[1]), (zmap[lk.b].frame[0], zmap[lk.b].frame[1]),
                          ty[lk.t_out], ty[lk.t_in], so, si)
            d += 0 if (so, si) == ("R", "L") else 60.0  # small preference for the natural flow direction
            if best is None or d < best[0]:
                best = (d, so, si)
        out[lk.edge.id] = (best[1], best[2])
    return out


def _term_y(zones: list[Zone]) -> dict[str, float]:
    return {n.id: n.y for z in zones for n in z.layout.nodes.values() if n.kind == "terminal"}


def _link_len(za: Zone, zb: Zone, pa: tuple[float, float], pb: tuple[float, float], ya_rel: float, yb_rel: float, so: str, si: str) -> float:
    ax, ay = pa
    bx, by = pb
    x_out = ax + (za.w if so == "R" else 0.0)
    x_in = bx + (0.0 if si == "L" else zb.w)
    y_out, y_in = ay + ya_rel, by + yb_rel
    dy = abs(y_in - y_out)
    top = min(ay, by)
    bot = max(ay + za.h, by + zb.h)
    around = min((y_out - top) + (y_in - top), (bot - y_out) + (bot - y_in)) + 2 * GAP + 300.0
    if so == "R" and si == "L":
        return (x_in - x_out) + dy if x_in >= x_out + GAP / 2 else (x_out - x_in) + around
    if so == "L" and si == "R":
        return (x_out - x_in) + dy if x_in <= x_out - GAP / 2 else (x_in - x_out) + around
    if so == "R" and si == "R":  # out to the right, back in from the right
        xm = max(x_out, x_in) + GAP / 2
        return (xm - x_out) + (xm - x_in) + dy + (0.0 if x_in >= x_out or y_out > by + zb.h or y_out < by else 300.0)
    xm = min(x_out, x_in) - GAP / 2
    return (x_out - xm) + (x_in - xm) + dy + (0.0 if x_in <= x_out or y_out > by + zb.h or y_out < by else 300.0)


def _shift_instruments(sl: SheetLayout, dx: float, dy: float) -> None:
    """``layout._shift`` moves nodes and edges; instruments and signals are placed afterwards."""
    for p in sl.instruments:
        p.x += dx
        p.y += dy
        p.leader = [(x + dx, y + dy) for x, y in p.leader]
    sl.signals = [(k, [(x + dx, y + dy) for x, y in pts]) for k, pts in sl.signals]


# ------------------------------------------------------------------------------ arrangement
def _rows_geometry(order: list[Zone], breaks: tuple[int, ...]) -> tuple[dict[str, tuple[float, float]], float, float]:
    pos: dict[str, tuple[float, float]] = {}
    y = 0.0
    width = 0.0
    start = 0
    for end in (*breaks, len(order)):
        row = order[start:end]
        x = 0.0
        rh = max(z.h for z in row)
        for z in row:
            pos[z.spec.id] = (x, y)
            x += z.w + GAP
        width = max(width, x - GAP)
        y += rh + GAP
        start = end
    return pos, width, y - GAP


def _cost(order: list[Zone], breaks: tuple[int, ...], links: list[Link], zmap: dict[str, Zone], term_y: dict[str, float]) -> float:
    pos, W, H = _rows_geometry(order, breaks)
    scale = min(DRAW_AREA[0] / max(W, 1.0), DRAW_AREA[1] / max(H, 1.0))
    wire = sum(_link_len(zmap[lk.a], zmap[lk.b], pos[lk.a], pos[lk.b], term_y[lk.t_out], term_y[lk.t_in], lk.s_out, lk.s_in) for lk in links)
    # a drawing smaller than the target scale costs as much as 3000 units of pipe per percent
    return wire + 3000.0 * max(0.0, TARGET_SCALE - scale) * 100


def _arrange(zones: list[Zone], links: list[Link], cfg: dict[str, Any]) -> list[list[str]]:
    zmap = {z.spec.id: z for z in zones}
    term_y = _term_y(zones)
    if cfg.get("rows"):  # explicit arrangement from the layout hints
        order = [zmap[i] for row in cfg["rows"] for i in row if i in zmap]
        order += [z for z in zones if z not in order]
        breaks = tuple(itertools.accumulate(len([i for i in row if i in zmap]) for row in cfg["rows"][:-1]))
    else:
        order, breaks = _search(zones, links, zmap, term_y)
    pos, W, _ = _rows_geometry(order, breaks)
    # centre each row horizontally
    start = 0
    for end in (*breaks, len(order)):
        row = order[start:end]
        rw = sum(z.w for z in row) + GAP * (len(row) - 1)
        off = (W - rw) / 2
        for z in row:
            x, y = pos[z.spec.id]
            z.frame = (x + off, y, x + off + z.w, y + z.h)
        start = end
    rows: list[list[str]] = []
    start = 0
    for end in (*breaks, len(order)):
        rows.append([z.spec.id for z in order[start:end]])
        start = end
    return rows


def _search(zones: list[Zone], links: list[Link], zmap: dict[str, Zone], term_y: dict[str, float]) -> tuple[list[Zone], tuple[int, ...]]:
    """Deterministic search over row splits and zone orders: seeded restarts + pairwise-swap descent."""
    import random

    n = len(zones)
    splits: list[tuple[int, ...]] = [()]
    for k in range(1, min(n, 3)):
        splits += list(itertools.combinations(range(1, n), k))
    rng = random.Random(1)
    best: tuple[float, list[Zone], tuple[int, ...]] | None = None
    for br in splits:
        starts = [list(zones)] + [rng.sample(zones, n) for _ in range(10)]
        for order in starts:
            cur = _cost(order, br, links, zmap, term_y)
            improved = True
            while improved:
                improved = False
                for i in range(n):
                    for j in range(i + 1, n):
                        order[i], order[j] = order[j], order[i]
                        c = _cost(order, br, links, zmap, term_y)
                        if c < cur - 1e-6:
                            cur = c
                            improved = True
                        else:
                            order[i], order[j] = order[j], order[i]
            if best is None or cur < best[0] - 1e-6:
                best = (cur, list(order), br)
    assert best is not None
    return best[1], best[2]


# ---------------------------------------------------------------------------------- router
_DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))


def _route_links(os_: OneSheet, zmap: dict[str, Zone]) -> None:
    zones = os_.zones
    x0 = min(z.frame[0] for z in zones) - 3 * GAP
    y0 = min(z.frame[1] for z in zones) - 3 * GAP
    x1 = max(z.frame[2] for z in zones) + 3 * GAP
    y1 = max(z.frame[3] for z in zones) + 3 * GAP
    nx, ny = int((x1 - x0) / CELL) + 1, int((y1 - y0) / CELL) + 1

    def cell(x: float, y: float) -> tuple[int, int]:
        return int(round((x - x0) / CELL)), int(round((y - y0) / CELL))

    def pt(c: tuple[int, int]) -> tuple[float, float]:
        return x0 + c[0] * CELL, y0 + c[1] * CELL

    blocked: set[tuple[int, int]] = set()
    near: set[tuple[int, int]] = set()
    for z in zones:
        a = cell(z.frame[0], z.frame[1])
        b = cell(z.frame[2], z.frame[3])
        for i in range(a[0] - 1, b[0] + 2):
            for j in range(a[1] - 1, b[1] + 2):
                blocked.add((i, j))
        for i in range(a[0] - 2, b[0] + 3):
            for j in range(a[1] - 2, b[1] + 3):
                near.add((i, j))
    nodes = os_.layout.nodes

    def endpoints(lk: Link) -> tuple[tuple[float, float], tuple[int, int], tuple[float, float], tuple[int, int]]:
        to, ti = nodes[lk.t_out], nodes[lk.t_in]
        za, zb = zmap[lk.a], zmap[lk.b]
        s = cell(za.frame[2] if lk.s_out == "R" else za.frame[0], to.y)
        s = (s[0] + (2 if lk.s_out == "R" else -2), s[1])
        g = cell(zb.frame[0] if lk.s_in == "L" else zb.frame[2], ti.y)
        g = (g[0] - (2 if lk.s_in == "L" else -2), g[1])
        return (to.x, to.y), s, (ti.x, ti.y), g

    ends = {lk.edge.id: endpoints(lk) for lk in os_.links}
    # the stub cells where a pipe leaves / enters a zone belong to that pipe only
    reserved: dict[tuple[int, int], str] = {}
    for lid, (_, s, _, g) in ends.items():
        for c in (s, g):
            reserved.setdefault(c, lid)

    def route_all(order: list[Link]) -> tuple[dict[str, list[tuple[float, float]]], list[str], list[str]]:
        used_h: set[tuple[int, int]] = set()  # cells carrying a horizontal run
        used_v: set[tuple[int, int]] = set()
        routes: dict[str, list[tuple[float, float]]] = {}
        warn: list[str] = []
        shared: list[str] = []
        for lk in order:
            p_out, s, p_in, g = ends[lk.edge.id]
            d0 = 0 if lk.s_out == "R" else 2
            d1 = 0 if lk.s_in == "L" else 2
            forbid = blocked | {c for c, owner in reserved.items() if owner != lk.edge.id}
            cells = _astar(s, g, nx, ny, forbid, near, used_h, used_v, d0=d0, d1=d1)
            if cells is None:  # congested: allow sharing a track at a high price rather than dropping the pipe
                cells = _astar(s, g, nx, ny, forbid, near, used_h, used_v, share=60.0, d0=d0, d1=d1)
                if cells is not None:
                    shared.append(lk.edge.id)
                    warn.append(f"route of {lk.edge.id} shares a track")
            if cells is None:
                warn.append(f"no route for {lk.edge.id} ({lk.a} -> {lk.b})")
                shared.append(lk.edge.id)
                continue
            for k, c in enumerate(cells):
                prev = cells[k - 1] if k else None
                nxt = cells[k + 1] if k + 1 < len(cells) else None
                if any(q is not None and q[1] == c[1] for q in (prev, nxt)):
                    used_h.add(c)
                if any(q is not None and q[0] == c[0] for q in (prev, nxt)):
                    used_v.add(c)
            pts = [pt(c) for c in cells]
            # leave the terminal horizontally and arrive horizontally, at the terminals' own heights
            routes[lk.edge.id] = _clean([p_out, (pts[0][0], p_out[1])] + pts + [(pts[-1][0], p_in[1]), p_in])
        return routes, warn, shared

    order = sorted(os_.links, key=lambda lk: (_est(ends[lk.edge.id]), lk.edge.id))
    best = None
    for _ in range(6):  # rip up and re-route: congested pipes go first next time
        routes, warn, shared = route_all(order)
        if best is None or len(shared) < len(best[2]):
            best = (routes, warn, shared)
        if not shared:
            break
        first = [lk for lk in order if lk.edge.id in shared]
        order = first + [lk for lk in order if lk.edge.id not in shared]
    os_.routes, w = best[0], best[1]
    os_.warnings += w


def _est(ep: tuple[tuple[float, float], tuple[int, int], tuple[float, float], tuple[int, int]]) -> float:
    _, s, _, g = ep
    return abs(s[0] - g[0]) + abs(s[1] - g[1])


def _astar(s: tuple[int, int], g: tuple[int, int], nx: int, ny: int, blocked: set, near: set, used_h: set, used_v: set, share: float = 0.0, d0: int = 0, d1: int = 0) -> list[tuple[int, int]] | None:
    BEND, CROSS, NEAR = 8.0, 6.0, 0.6
    start = (s[0], s[1], d0)  # leaving the zone horizontally
    dist = {start: 0.0}
    prev: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    pq = [(abs(s[0] - g[0]) + abs(s[1] - g[1]), 0.0, start)]
    goal = None
    while pq:
        f, d, st = heapq.heappop(pq)
        if d > dist.get(st, 1e18):
            continue
        x, y, di = st
        if (x, y) == g and di == d1:
            goal = st
            break
        for nd, (dx, dy) in enumerate(_DIRS):
            if nd == (di + 2) % 4:
                continue
            c = (x + dx, y + dy)
            if not (0 <= c[0] < nx and 0 <= c[1] < ny) or (c in blocked and c != g):
                continue
            horiz = dy == 0
            step = 1.0 + (BEND if nd != di else 0.0)
            if (horiz and c in used_h) or (not horiz and c in used_v):
                if not share:
                    continue  # never share a track
                step += share
            if (horiz and c in used_v) or (not horiz and c in used_h):
                step += CROSS
            if c in near:
                step += NEAR
            ns = (c[0], c[1], nd)
            nd_ = d + step
            if nd_ < dist.get(ns, 1e18):
                dist[ns] = nd_
                prev[ns] = st
                heapq.heappush(pq, (nd_ + abs(c[0] - g[0]) + abs(c[1] - g[1]), nd_, ns))
    if goal is None:
        return None
    out = [goal]
    while out[-1] in prev:
        out.append(prev[out[-1]])
    return [(c[0], c[1]) for c in reversed(out)]


def _clean(path: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in path:
        if out and abs(out[-1][0] - p[0]) < 1e-6 and abs(out[-1][1] - p[1]) < 1e-6:
            continue
        out.append(p)
    k = 1
    while k < len(out) - 1:
        a, b, c = out[k - 1], out[k], out[k + 1]
        if (abs(a[0] - b[0]) < 1e-6 and abs(b[0] - c[0]) < 1e-6) or (abs(a[1] - b[1]) < 1e-6 and abs(b[1] - c[1]) < 1e-6):
            out.pop(k)
        else:
            k += 1
    return out


def onesheet_qa(os_: OneSheet) -> list[str]:
    out = list(os_.warnings)
    out += layout_qa(os_.layout)
    for i, a in enumerate(os_.zones):
        for b in os_.zones[i + 1:]:
            fa, fb = a.frame, b.frame
            if fa[0] < fb[2] and fb[0] < fa[2] and fa[1] < fb[3] and fb[1] < fa[3]:
                out.append(f"zones {a.spec.id} and {b.spec.id} overlap")
    return sorted(set(out))
