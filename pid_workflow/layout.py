"""Deterministic layout and routing for review drawings.

Nothing here is written back to the topology: coordinates exist only in the computed
:class:`SheetLayout` objects that the renderer consumes.

Pipeline (per sheet)
--------------------
1. *Macro graph*: equipment, boundaries and manifolds are nodes; every chain of inline
   valves between two nodes collapses into one edge that remembers its valves.
2. *Layering*: flow direction left -> right (longest path after breaking cycles; the
   broken edges become "return" edges routed around the sheet).
3. *Ordering*: barycentre sweeps with crossing counting; manifold branches keep b1..bn order.
4. *Coordinates*: y by isotonic relaxation toward neighbours (straight lines where possible),
   x by layer with gaps sized to the valves that must fit.
5. *Routing*: orthogonal H-V-H routes with per-gap vertical tracks; valves are placed on the
   first horizontal run; instruments get a free spot beside their line or equipment.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .schema import Boundary, Component, Equipment, Instrument, ProcessLine, Topology, is_pending, logical

SYM_W = 30.0      # width reserved per inline valve
TRACK_W = 9.0     # spacing of vertical tracks
MIN_GAP = 46.0
MIN_GAP_M = 28.0
V_GAP = 14.0      # vertical gap between nodes
LABEL_H = 30.0    # label band under an equipment symbol
LANE_GAP = 16.0
MAX_ROW_W = 1290.0  # sheets wider than this are folded into rows

# ---------------------------------------------------------------------------- symbols
_DIMS: dict[str, tuple[float, float]] = {
    "CentrifugalPump": (38, 38),
    "PlateHeatExchanger": (50, 78),
    "CustomHeatExchanger": (54, 74),
    "Tank": (72, 100),
    "Vessel": (58, 104),
    "CustomCompressor": (56, 64),
    "Boiler": (84, 74),
    "CustomEquipment": (112, 56),
}


@dataclass
class MNode:
    id: str
    kind: str  # equipment | manifold | boundary | offpage | dummy
    obj: Any = None
    sheet: str = ""
    w: float = 0.0
    h: float = 0.0
    label_h: float = 0.0   # reserved band below the symbol (label / drain stub)
    top_h: float = 0.0     # reserved band above the symbol (vent stub)
    ports: dict[str, tuple[str, float]] = field(default_factory=dict)  # port -> (side, rel_y)
    label: str = ""
    sublabel: str = ""
    layer: int = 0
    order: float = 0.0
    x: float = 0.0
    y: float = 0.0
    # manifold only
    span: tuple[float, float] = (0.0, 0.0)
    port_y: dict[str, float] = field(default_factory=dict)
    symbol: str = ""
    note: str = ""

    @property
    def band(self) -> float:
        return self.top_h + self.h + self.label_h

    def port_xy(self, port: str) -> tuple[float, float]:
        side, rel = self.ports.get(port, ("R", 0.0))
        if self.kind == "manifold":
            return self.x, self.port_y.get(port, self.y)
        if side == "L":
            return self.x - self.w / 2, self.y + rel
        if side == "R":
            return self.x + self.w / 2, self.y + rel
        if side == "T":
            return self.x + rel, self.y - self.h / 2
        return self.x + rel, self.y + self.h / 2


@dataclass
class MEdge:
    id: str
    src: tuple[str, str]
    dst: tuple[str, str]
    chain: list[Component] = field(default_factory=list)
    line_ids: list[str] = field(default_factory=list)
    service: str = ""
    header: bool = False
    proposed: bool = False
    back: bool = False
    stub: bool = False  # open-ended branch (drain / vent / purge)
    path: list[tuple[float, float]] = field(default_factory=list)
    symbols: list[tuple[Component, float, float, str]] = field(default_factory=list)  # comp, x, y, orientation H|V
    logical: set[str] = field(default_factory=set)
    label_pos: tuple[float, float] | None = None


@dataclass
class Placed:
    """A positioned instrument bubble and its leader."""

    inst: Instrument
    x: float
    y: float
    leader: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class SheetLayout:
    sheet_id: str
    title: str
    nodes: dict[str, MNode] = field(default_factory=dict)
    edges: list[MEdge] = field(default_factory=list)
    instruments: list[Placed] = field(default_factory=list)
    signals: list[tuple[str, list[tuple[float, float]]]] = field(default_factory=list)  # kind, polyline
    bbox: tuple[float, float, float, float] = (0, 0, 1, 1)
    lanes: int = 0
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------ macro graph
def _label_of(obj: Any) -> tuple[str, str]:
    tag = getattr(obj, "tag", None)
    name = getattr(obj, "name", None) or obj.id
    if isinstance(obj, Equipment) and obj.attributes.get("label") and not tag:
        tag = None
    return (tag or "", name)


def _slots(n: int, h: float, span_max: float = 30.0) -> list[float]:
    if n <= 1:
        return [0.0]
    span = min(h * 0.62, span_max * (n - 1))
    return [(-span / 2) + i * span / (n - 1) for i in range(n)]


def make_equipment_node(e: Equipment, sheet: str) -> MNode:
    w, h = _DIMS.get(e.model_class, (112, 56))
    if e.model_class == "CustomEquipment":
        n = e.name or ""
        if "heat pump" in n.lower():
            w, h, sym = 148, 92, "heatpump"
        else:
            sym = "box"
            w = 124 if "ermenter" in n else 112
    else:
        sym = {"CentrifugalPump": "pump", "PlateHeatExchanger": "phx", "CustomHeatExchanger": "hx", "Tank": "tank", "Vessel": "vessel",
               "CustomCompressor": "compressor", "Boiler": "boiler"}[e.model_class]
    tag, name = _label_of(e)
    node = MNode(id=e.id, kind="equipment", obj=e, sheet=sheet, w=w, h=h,
                 label_h=0.0 if sym in ("tank", "vessel") else (LABEL_H if sym not in ("box", "heatpump") else (LABEL_H - 8 if sym == "box" else 14)),
                 label=tag, sublabel=name, symbol=sym)
    by_side: dict[str, list[str]] = defaultdict(list)
    for nz in e.nozzles:
        if nz.role in ("inlet", "suction"):
            by_side["L"].append(nz.name)
        elif nz.role in ("outlet", "discharge"):
            by_side["R"].append(nz.name)
        elif nz.role == "vent":
            by_side["T"].append(nz.name)
        elif nz.role == "drain":
            by_side["B"].append(nz.name)
        else:  # level_tap etc.: instrument connection on the left-top
            by_side["L2"].append(nz.name)
    for side in ("L", "R"):
        names = by_side.get(side, [])
        if sym == "heatpump":
            offs = {"evap_in": -26, "evap_out": -26, "cond_in": 26, "cond_out": 26}
            for nm in names:
                node.ports[nm] = (side, offs.get(nm, 0.0))
        elif sym in ("phx", "hx") and len(names) > 1:
            offs = _slots(len(names), h, 34)
            for nm, off in zip(names, offs):
                node.ports[nm] = (side, off)
        else:
            offs = _slots(len(names), h, 22)
            for nm, off in zip(names, offs):
                node.ports[nm] = (side, off)
    for nm in by_side.get("T", []):
        node.ports[nm] = ("T", 0.0)
    for nm in by_side.get("B", []):
        node.ports[nm] = ("B", 0.0)
    for nm in by_side.get("L2", []):
        node.ports[nm] = ("L", -h * 0.32)
    return node


def make_boundary_node(b: Boundary, sheet: str) -> MNode:
    n = MNode(id=b.id, kind="boundary", obj=b, sheet=sheet, w=150, h=30, label_h=0, symbol="flag_in" if b.direction == "in" else "flag_out",
              label="", sublabel=b.name or b.id)
    n.ports["port"] = ("R", 0.0) if b.direction == "in" else ("L", 0.0)
    return n


def make_manifold_node(c: Component, sheet: str) -> MNode:
    n = MNode(id=c.id, kind="manifold", obj=c, sheet=sheet, w=8, h=max(44.0, 36.0 * (c.branches or 2)), label_h=0, symbol="manifold", sublabel=c.name or c.id)
    cside, bside = ("L", "R") if c.role == "split" else ("R", "L")
    n.ports["common"] = (cside, 0.0)
    for i in range(1, (c.branches or 2) + 1):
        n.ports[f"b{i}"] = (bside, 0.0)
    return n


def make_offpage_node(nid: str, direction: str, label: str, sub: str) -> MNode:
    n = MNode(id=nid, kind="offpage", sheet="", w=176, h=34, label_h=0, symbol="offpage_in" if direction == "in" else "offpage_out", label=label, sublabel=sub)
    n.ports["port"] = ("R", 0.0) if direction == "in" else ("L", 0.0)
    return n


@dataclass
class Macro:
    nodes: dict[str, MNode]
    edges: list[MEdge]
    comp_sheet: dict[str, str]


def build_macro(topo: Topology, specs: list[SheetSpec]) -> Macro:
    import fnmatch

    conn = topo.connectable()
    by_from = {(l.from_.ref, l.from_.port): l for l in topo.process_lines}
    nodes: dict[str, MNode] = {}
    sheet_of_area = {a: sp.id for sp in specs for a in sp.areas}

    def explicit(obj_id: str) -> str | None:
        for sp in specs:
            if any(fnmatch.fnmatchcase(obj_id, pat) for pat in sp.assign):
                return sp.id
        return None

    macro_ids = [o.id for o in (*topo.equipment, *topo.boundaries, *[c for c in topo.components if c.kind == "manifold"])]
    inherited: dict[str, str] = {}
    if any(sp.assign for sp in specs):
        gen_manifolds = {c.id for c in topo.components if c.kind == "manifold" and c.provenance.origin == "generated"}
        missing = [i for i in macro_ids if explicit(i) is None and i not in gen_manifolds]
        if missing:
            raise ValueError(f"layout hints leave objects without a sheet: {missing[:12]}")
        # generated manifolds (bypass / purge tees) are drawn on the sheet of the nearest assigned neighbour
        nbrs: dict[str, list[str]] = defaultdict(list)
        for l in topo.process_lines:
            nbrs[l.from_.ref].append(l.to.ref)
            nbrs[l.to.ref].append(l.from_.ref)
        for g in sorted(gen_manifolds):
            seen = {g}
            frontier = [g]
            while frontier and g not in inherited:
                nxt: list[str] = []
                for u in frontier:
                    for v in sorted(nbrs[u]):
                        if v in seen:
                            continue
                        seen.add(v)
                        if explicit(v):
                            inherited[g] = explicit(v)  # type: ignore[assignment]
                            break
                        nxt.append(v)
                    if g in inherited:
                        break
                frontier = nxt

    def sheet_of_obj(obj_id: str, area: str | None) -> str:  # noqa: F811
        return explicit(obj_id) or inherited.get(obj_id) or sheet_of_area.get(area or "", specs[0].id)

    for e in topo.equipment:
        nodes[e.id] = make_equipment_node(e, sheet_of_obj(e.id, e.area))
    for b in topo.boundaries:
        nodes[b.id] = make_boundary_node(b, sheet_of_obj(b.id, b.area))
    for c in topo.components:
        if c.kind == "manifold":
            nodes[c.id] = make_manifold_node(c, sheet_of_obj(c.id, c.area))
    edges: list[MEdge] = []
    for l0 in topo.process_lines:
        o = conn[l0.from_.ref]
        if l0.from_.ref not in nodes:
            continue  # starts at an inline component: reached by walking
        cur = l0
        chain: list[Component] = []
        lines = [l0]
        dst: tuple[str, str] | None = None
        while True:
            t = conn[cur.to.ref]
            if cur.to.ref in nodes:
                dst = (cur.to.ref, cur.to.port)
                break
            chain.append(t)
            nxt = by_from.get((t.id, "out"))
            if nxt is None:
                break
            cur = nxt
            lines.append(nxt)
        e = MEdge(id=l0.id, src=(l0.from_.ref, l0.from_.port), dst=dst or ("", ""), chain=chain, line_ids=[l.id for l in lines],
                  service=l0.service, header=any(l.header for l in lines),
                  proposed=all(is_pending(l.provenance) and l.split_from is None for l in lines),
                  stub=dst is None, logical={logical(l) for l in lines})
        edges.append(e)
    return Macro(nodes, edges, {c.id: sheet_of_obj(c.id, c.area) for c in topo.components})


# ------------------------------------------------------------------------------- layering
def _break_cycles(node_ids: list[str], fwd: dict[str, list[str]], start_pref: list[str]) -> set[tuple[str, str]]:
    """DFS cycle breaking; returns the set of (u, v) back edges."""
    state: dict[str, int] = {}
    back: set[tuple[str, str]] = set()
    order = list(start_pref) + [n for n in node_ids if n not in start_pref]

    def dfs(u: str) -> None:
        state[u] = 1
        for v in fwd.get(u, []):
            if state.get(v, 0) == 0:
                dfs(v)
            elif state.get(v) == 1:
                back.add((u, v))
        state[u] = 2

    for n in order:
        if state.get(n, 0) == 0:
            dfs(n)
    return back


def _count_crossings(a: list[str], b: list[str], adj: dict[str, list[str]], pos_b: dict[str, int]) -> int:
    pairs = []
    for i, u in enumerate(a):
        for v in adj.get(u, []):
            if v in pos_b:
                pairs.append((i, pos_b[v]))
    c = 0
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            if (pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1]) < 0:
                c += 1
    return c


def _isotonic(z: list[float]) -> list[float]:
    """Pool-adjacent-violators: closest non-decreasing sequence."""
    blocks: list[list[float]] = []  # [sum, count]
    for v in z:
        blocks.append([v, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += c
    out: list[float] = []
    for s, c in blocks:
        out += [s / c] * int(c)
    return out


def _layout_component(sheet_id: str, title: str, nodes: dict[str, MNode], edges: list[MEdge], hints: dict[str, Any] | None = None) -> SheetLayout:
    hints = hints or {}
    sl = SheetLayout(sheet_id=sheet_id, title=title)
    sl.nodes = nodes
    sl.edges = [e for e in edges if not e.stub]
    stubs = [e for e in edges if e.stub]
    ids = sorted(nodes)
    for st in stubs:  # reserve room for drain / vent / purge branches
        a = nodes.get(st.src[0])
        if a is None:
            continue
        side = "B" if a.kind == "manifold" else a.ports.get(st.src[1], ("B", 0.0))[0]
        room = 22.0 + 24.0 * len(st.chain) + 14.0
        if side == "T":
            a.top_h = max(a.top_h, room)
        elif side == "B":
            a.label_h = max(a.label_h, room)
    fwd: dict[str, list[str]] = defaultdict(list)
    for e in sl.edges:
        fwd[e.src[0]].append(e.dst[0])
    indeg = defaultdict(int)
    for e in sl.edges:
        indeg[e.dst[0]] += 1
    pref = list(hints.get("start_nodes", []))
    pref += sorted([n for n in ids if nodes[n].kind in ("offpage",) and nodes[n].symbol == "offpage_in"])
    pref += sorted([n for n in ids if nodes[n].kind == "boundary" and nodes[n].symbol == "flag_in"])
    pref += sorted([n for n in ids if indeg[n] == 0])
    back = _break_cycles(ids, fwd, pref)
    for e in sl.edges:
        if (e.src[0], e.dst[0]) in back:
            e.back = True
    fedges = [e for e in sl.edges if not e.back]

    # ---- longest-path layering
    preds: dict[str, list[str]] = defaultdict(list)
    succs: dict[str, list[str]] = defaultdict(list)
    for e in fedges:
        preds[e.dst[0]].append(e.src[0])
        succs[e.src[0]].append(e.dst[0])
    layer: dict[str, int] = {}

    def depth(n: str) -> int:
        if n in layer:
            return layer[n]
        layer[n] = 0  # guard against residual cycles
        layer[n] = max((depth(p) + 1 for p in preds[n]), default=0)
        return layer[n]

    for n in ids:
        depth(n)
    # pull pure sources toward their successors
    for n in sorted(ids, key=lambda k: -layer[k]):
        if not preds[n] and succs[n]:
            layer[n] = min(layer[s] for s in succs[n]) - 1
    # pull pure sinks toward their predecessors is unnecessary (already adjacent)
    lo = min(layer.values()) if layer else 0
    for n in layer:
        layer[n] -= lo
    for n in ids:
        nodes[n].layer = layer[n]

    # ---- dummies for long edges
    dummies: dict[str, MNode] = {}
    paths: dict[str, list[str]] = {}
    for e in fedges:
        a, b = e.src[0], e.dst[0]
        path = [a]
        for k in range(layer[a] + 1, layer[b]):
            d = MNode(id=f"d:{e.id}:{k}", kind="dummy", w=0, h=10, layer=k)
            dummies[d.id] = d
            path.append(d.id)
        path.append(b)
        paths[e.id] = path
    allnodes = {**nodes, **dummies}
    nlayers = (max(n.layer for n in allnodes.values()) + 1) if allnodes else 1
    layers: list[list[str]] = [[] for _ in range(nlayers)]
    # initial order: DFS order for determinism
    seen: set[str] = set()
    ordered: list[str] = []

    def visit(n: str) -> None:
        if n in seen:
            return
        seen.add(n)
        ordered.append(n)
        for e in fedges:
            if e.src[0] == n:
                for d in paths[e.id][1:]:
                    visit(d)

    for n in pref + ids:
        if n in nodes:
            visit(n)
    for n in dummies:
        visit(n)
    for n in ordered:
        layers[allnodes[n].layer].append(n)

    # adjacency between consecutive layers (dummy chains included)
    down: dict[str, list[tuple[str, int]]] = defaultdict(list)  # u -> [(v, port index)]
    up: dict[str, list[tuple[str, int]]] = defaultdict(list)

    def port_rank(node_id: str, port: str) -> int:
        n = allnodes.get(node_id)
        if n is not None and n.kind == "manifold":
            return 0 if port == "common" else int(port[1:])
        if n is not None and port in n.ports:
            return list(n.ports).index(port)
        return 0

    for e in fedges:
        p = paths[e.id]
        for i in range(len(p) - 1):
            u, v = p[i], p[i + 1]
            ru = port_rank(u, e.src[1]) if i == 0 else 0
            rv = port_rank(v, e.dst[1]) if i == len(p) - 2 else 0
            down[u].append((v, ru))
            up[v].append((u, rv))

    def bary(order: list[str], nb: dict[str, list[tuple[str, int]]], pos: dict[str, int]) -> list[str]:
        key = {}
        for n in order:
            ns = [(pos[m] + 0.001 * r) for m, r in nb.get(n, []) if m in pos]
            key[n] = (sum(ns) / len(ns)) if ns else None
        # keep nodes without neighbours in place
        res: list[tuple[float, int, str]] = []
        for i, n in enumerate(order):
            res.append((key[n] if key[n] is not None else i, i, n))
        res.sort()
        return [n for _, _, n in res]

    def total_crossings() -> int:
        c = 0
        for i in range(nlayers - 1):
            pos_b = {n: k for k, n in enumerate(layers[i + 1])}
            adj = {u: [v for v, _ in down[u]] for u in layers[i]}
            c += _count_crossings(layers[i], layers[i + 1], adj, pos_b)
        return c

    best = [list(l) for l in layers]
    best_c = total_crossings()
    for sweep in range(30):
        rng = range(1, nlayers) if sweep % 2 == 0 else range(nlayers - 2, -1, -1)
        for i in rng:
            if sweep % 2 == 0:
                pos = {n: k for k, n in enumerate(layers[i - 1])}
                layers[i] = bary(layers[i], up, pos)
            else:
                pos = {n: k for k, n in enumerate(layers[i + 1])}
                layers[i] = bary(layers[i], down, pos)
        c = total_crossings()
        if c < best_c:
            best_c, best = c, [list(l) for l in layers]
    layers = best
    for i, l in enumerate(layers):
        for k, n in enumerate(l):
            allnodes[n].order = k

    # ---- manifold bars are as tall as the neighbours they serve
    for e in fedges:
        p_ = paths[e.id]
        a_, b_ = nodes[e.src[0]], nodes[e.dst[0]]
        if a_.kind == "manifold" and e.src[1] != "common":
            a_.span_need = getattr(a_, "span_need", 0.0) + min(allnodes[p_[1]].band, 150.0) + V_GAP  # type: ignore[attr-defined]
        if b_.kind == "manifold" and e.dst[1] != "common":
            b_.span_need = getattr(b_, "span_need", 0.0) + min(allnodes[p_[-2]].band, 150.0) + V_GAP  # type: ignore[attr-defined]
    for n_ in nodes.values():
        if n_.kind == "manifold":
            n_.h = max(n_.h, getattr(n_, "span_need", 0.0) - V_GAP)

    # ---- y coordinates
    def sep(a: MNode, b: MNode) -> float:
        return (a.band + b.band) / 2 + V_GAP

    for l in layers:
        y = 0.0
        for n in l:
            node = allnodes[n]
            node.y = y + node.band / 2
            y += node.band + V_GAP

    def rel_of(node_id: str, port: str) -> float:
        n = allnodes[node_id]
        if n.kind == "manifold":
            return 0.0
        return n.ports.get(port, ("R", 0.0))[1] if n.kind != "dummy" else 0.0

    def place(layer_nodes: list[str], desired: dict[str, float]) -> None:
        if not layer_nodes:
            return
        cum = [0.0]
        for a, b in zip(layer_nodes, layer_nodes[1:]):
            cum.append(cum[-1] + sep(allnodes[a], allnodes[b]))
        z = [desired[n] - c for n, c in zip(layer_nodes, cum)]
        fitted = _isotonic(z)
        for n, f, c in zip(layer_nodes, fitted, cum):
            allnodes[n].y = f + c

    # port rel for the first / last hop
    in_hops: dict[str, list[tuple[str, float, float]]] = defaultdict(list)   # v -> [(u, rel_u_out, rel_v_in)]
    out_hops: dict[str, list[tuple[str, float, float]]] = defaultdict(list)  # u -> [(v, rel_u_out, rel_v_in)]
    for e in fedges:
        p = paths[e.id]
        for i in range(len(p) - 1):
            ru = rel_of(p[i], e.src[1]) if i == 0 else 0.0
            rv = rel_of(p[i + 1], e.dst[1]) if i == len(p) - 2 else 0.0
            in_hops[p[i + 1]].append((p[i], ru, rv))
            out_hops[p[i]].append((p[i + 1], ru, rv))

    def node_band_y(n: str) -> float:
        return allnodes[n].y

    def lab_shift(n: str) -> float:
        return (allnodes[n].top_h - allnodes[n].label_h) / 2  # node centre relative to its band centre

    for it in range(14):
        for i in range(1, nlayers):
            des = {}
            for n in layers[i]:
                hops = in_hops.get(n, [])
                if hops:
                    des[n] = sum(allnodes[u].y + lab_shift(u) + ru - rv for u, ru, rv in hops) / len(hops) - lab_shift(n)
                else:
                    des[n] = allnodes[n].y
            place(layers[i], des)
        for i in range(nlayers - 2, -1, -1):
            des = {}
            for n in layers[i]:
                hops = out_hops.get(n, [])
                if hops:
                    des[n] = sum(allnodes[v].y + lab_shift(v) + rv - ru for v, ru, rv in hops) / len(hops) - lab_shift(n)
                else:
                    des[n] = allnodes[n].y
            place(layers[i], des)
    # y currently holds band centres; convert to node centres
    for n in allnodes.values():
        n.y += lab_shift(n.id) if n.id in allnodes else 0.0

    # ---- x coordinates (layers -> columns; wide sheets are folded into rows)
    col_w = [max((allnodes[n].w for n in l), default=0.0) for l in layers]

    def _port_y(n: MNode, port: str | None, out: bool) -> float:
        if port is None or n.kind in ("dummy", "manifold"):
            return n.y
        return n.y + n.ports.get(port, ("R", 0.0))[1]

    def min_gap(i: int) -> float:
        def thin(l: list[str]) -> bool:
            return all(allnodes[n].kind in ("manifold", "dummy") for n in l) and bool(l)
        return MIN_GAP_M if (thin(layers[i]) or thin(layers[i + 1])) else MIN_GAP

    inst_lines: dict[str, int] = hints.get("inst_lines", {})

    def chain_zone(i: int) -> float:
        z = 0.0
        for e in fedges:
            if allnodes[paths[e.id][0]].layer == i:
                need = (len(e.chain) * SYM_W + 14) if e.chain else 0.0
                n_inst = sum(inst_lines.get(lg, 0) for lg in e.logical)
                if n_inst:
                    need += 14 + 30 * ((n_inst + 1) // 2)  # room for bubbles beside the pipe
                z = max(z, need)
        return z

    def hops_in_gap(i: int) -> list[tuple[MEdge, int]]:
        out = []
        for e in fedges:
            p = paths[e.id]
            for k in range(len(p) - 1):
                if allnodes[p[k]].layer == i:
                    out.append((e, k))
        return out

    # preliminary widths -> decide where to fold
    est_gaps = []
    for i in range(nlayers - 1):
        est_tracks = sum(1 for e, k in hops_in_gap(i)
                         if abs(_port_y(allnodes[paths[e.id][k]], e.src[1] if k == 0 else None, True)
                                - _port_y(allnodes[paths[e.id][k + 1]], e.dst[1] if k == len(paths[e.id]) - 2 else None, False)) > 0.5)
        est_gaps.append(max(min_gap(i), chain_zone(i) + 22 + est_tracks * TRACK_W))
    max_w = float(hints.get("max_width", MAX_ROW_W))
    crossing = [len(hops_in_gap(i)) for i in range(nlayers - 1)]
    row_of_layer = [0] * nlayers
    cut_after: list[int] = []
    start = 0
    while True:
        width = 0.0
        last_fit = start
        for l in range(start, nlayers):
            width += col_w[l] + (est_gaps[l - 1] if l > start else 0.0)
            if width <= max_w:
                last_fit = l
            else:
                break
        if last_fit >= nlayers - 1 and width <= max_w:
            break
        lo = start + max(1, int((last_fit - start) * 0.55))
        cand = [i for i in range(lo, last_fit + 1) if i < nlayers - 1]
        if not cand:
            break
        cut = min(cand, key=lambda i: (crossing[i], -i))
        cut_after.append(cut)
        start = cut + 1
        if start >= nlayers - 1:
            break
    for r, cut in enumerate(cut_after):
        for l in range(cut + 1, nlayers):
            row_of_layer[l] = r + 1
    nrows = len(cut_after) + 1
    is_wrapped = lambda u, v: row_of_layer[allnodes[u].layer] != row_of_layer[allnodes[v].layer]  # noqa: E731

    # vertical offsets per row (rows are stacked; wrapped edges use the space between them)
    row_layers = [[l for l in range(nlayers) if row_of_layer[l] == r] for r in range(nrows)]
    row_off = [0.0] * nrows
    row_top = [0.0] * nrows
    row_bot = [0.0] * nrows
    for r in range(nrows):
        nn = [allnodes[n] for l in row_layers[r] for n in layers[l]]
        row_top[r] = min((n.y - n.h / 2 - n.top_h for n in nn), default=0.0)
        row_bot[r] = max((n.y + n.h / 2 + n.label_h for n in nn), default=0.0)
    for r in range(1, nrows):
        n_wrap = crossing[cut_after[r - 1]]
        row_off[r] = (row_bot[r - 1] + row_off[r - 1]) + 64 + 10 * n_wrap - row_top[r]
    for r in range(nrows):
        for l in row_layers[r]:
            for n in layers[l]:
                allnodes[n].y += row_off[r]
        row_top[r] += row_off[r]
        row_bot[r] += row_off[r]

    # ---- manifold port ys and bar spans (branch anchors follow the neighbour on the same row)
    def set_manifold_ports() -> None:
        for n in nodes.values():
            if n.kind == "manifold":
                n.port_y = {}
        for e in fedges:
            p = paths[e.id]
            a, b = nodes[e.src[0]], nodes[e.dst[0]]
            if a.kind == "manifold" and not is_wrapped(p[0], p[1]):
                a.port_y[e.src[1]] = allnodes[p[1]].y if len(p) > 2 else _port_y(b, e.dst[1], False)
            if b.kind == "manifold" and not is_wrapped(p[-2], p[-1]):
                b.port_y[e.dst[1]] = allnodes[p[-2]].y if len(p) > 2 else _port_y(a, e.src[1], True)
        for n in nodes.values():
            if n.kind != "manifold":
                continue
            ys = list(n.port_y.values()) or [n.y]
            n.y = n.port_y["common"] if "common" in n.port_y else sum(ys) / len(ys)
            for pnm in n.ports:
                n.port_y.setdefault(pnm, n.y)
            allys = ys + [n.y]
            n.span = (min(allys) - 10, max(allys) + 10)

    set_manifold_ports()

    # push non-manifold nodes of a layer off the bars of its manifolds (bars follow their neighbours)
    for _ in range(2):
        moved = False
        for l in layers:
            row = [allnodes[n] for n in l if allnodes[n].kind != "dummy"]
            bars = sorted((n for n in row if n.kind == "manifold"), key=lambda n: n.span[0])
            if not bars:
                continue
            others = [n for n in row if n.kind != "manifold"]

            def top_of(n: MNode) -> float:
                return n.y - n.h / 2 - n.top_h

            def bot_of(n: MNode) -> float:
                return n.y + n.h / 2 + n.label_h

            # forbidden zones = the bars' spans (merged); every other node lives in one free segment
            zones: list[list[float]] = []
            for m in bars:
                lo, hi = m.span[0] - 8, m.span[1] + 8
                if zones and lo <= zones[-1][1]:
                    zones[-1][1] = max(zones[-1][1], hi)
                else:
                    zones.append([lo, hi])
            bounds = [(-1e9, zones[0][0])] + [(zones[k][1], zones[k + 1][0]) for k in range(len(zones) - 1)] + [(zones[-1][1], 1e9)]
            segs: list[list[MNode]] = [[] for _ in bounds]
            for n in others:
                k = 0
                for kk, (lo_, hi_) in enumerate(bounds):
                    mid = n.y
                    if mid >= lo_ and mid <= hi_ or (kk == len(bounds) - 1):
                        k = kk
                        if mid <= hi_:
                            break
                segs[k].append(n)
            for (lo_, hi_), grp in zip(bounds, segs):
                grp.sort(key=lambda q: q.y)
                before = [n.y for n in grp]
                prev = lo_
                for n in grp:                       # sweep down: clear of the previous node / zone
                    n.y = max(n.y, prev + n.top_h + n.h / 2)
                    prev = n.y + n.h / 2 + n.label_h + V_GAP
                nxt = hi_
                for n in reversed(grp):             # sweep up: stay above the next node / zone
                    n.y = min(n.y, nxt - n.label_h - n.h / 2)
                    nxt = n.y - n.h / 2 - n.top_h - V_GAP
                if any(abs(a_ - n.y) > 0.01 for a_, n in zip(before, grp)):
                    moved = True
        if not moved:
            break
        set_manifold_ports()

    def _port_y_final(n: MNode, port: str | None, e: MEdge) -> float:
        if n.kind == "dummy":
            return n.y
        if n.kind == "manifold":
            return n.port_y.get(port or "common", n.y)
        if port is None:
            return n.y
        return n.y + n.ports.get(port, ("R", 0.0))[1]

    # ---- vertical tracks per gap (wrapped hops do not use them)
    track_assign: dict[tuple[str, int], int] = {}
    gap_info: list[tuple[float, int]] = []
    for i in range(nlayers - 1):
        cz = chain_zone(i)
        items = []
        for e, k in hops_in_gap(i):
            p = paths[e.id]
            if is_wrapped(p[k], p[k + 1]):
                continue
            ya = _port_y_final(allnodes[p[k]], e.src[1] if k == 0 else None, e)
            yb = _port_y_final(allnodes[p[k + 1]], e.dst[1] if k == len(p) - 2 else None, e)
            if abs(ya - yb) > 0.5:
                items.append((min(ya, yb), max(ya, yb), e.id, k))
        items.sort()
        tracks: list[float] = []
        for lo, hi, eid, k in items:
            for t, last in enumerate(tracks):
                if lo > last + 4:
                    tracks[t] = hi
                    track_assign[(eid, k)] = t
                    break
            else:
                tracks.append(hi)
                track_assign[(eid, k)] = len(tracks) - 1
        gap_info.append((cz, len(tracks)))
    gaps = [0.0 if (i in cut_after) else max(min_gap(i), cz + 22 + tr * TRACK_W) for i, (cz, tr) in enumerate(gap_info)]
    col_x: list[float] = []
    x = 0.0
    for i in range(nlayers):
        if i > 0 and row_of_layer[i] != row_of_layer[i - 1]:
            x = 0.0
        col_x.append(x + col_w[i] / 2)
        x += col_w[i] + (gaps[i] if i < len(gaps) else 0.0)
    for i, l in enumerate(layers):
        for n in l:
            allnodes[n].x = col_x[i]
    row_left = [min(col_x[l] - col_w[l] / 2 for l in row_layers[r]) for r in range(nrows)]
    row_right = [max(col_x[l] + col_w[l] / 2 for l in row_layers[r]) for r in range(nrows)]

    def port_x(n: MNode, port: str | None, out: bool) -> float:
        if n.kind in ("dummy", "manifold") or port is None:
            return n.x
        return n.port_xy(port)[0]

    # wrapped hops: order them per cut so that the folded lines do not cross each other
    wrap_rank: dict[tuple[str, int], tuple[int, int]] = {}
    for r, cut in enumerate(cut_after):
        hs = []
        for e, k in hops_in_gap(cut):
            p = paths[e.id]
            ya = _port_y_final(allnodes[p[k]], e.src[1] if k == 0 else None, e)
            hs.append((ya, e.id, k))
        hs.sort()
        for rank, (_, eid, k) in enumerate(hs):
            wrap_rank[(eid, k)] = (rank, len(hs))

    for e in sorted(sl.edges, key=lambda z: z.id):
        if e.back:
            continue
        p = paths[e.id]
        pts: list[tuple[float, float]] = []
        for k in range(len(p) - 1):
            u, v = allnodes[p[k]], allnodes[p[k + 1]]
            ya = _port_y_final(u, e.src[1] if k == 0 else None, e)
            yb = _port_y_final(v, e.dst[1] if k == len(p) - 2 else None, e)
            xa = port_x(u, e.src[1] if k == 0 else None, True)
            xb = port_x(v, e.dst[1] if k == len(p) - 2 else None, False)
            if not pts:
                pts.append((xa, ya))
            if is_wrapped(p[k], p[k + 1]):
                r = row_of_layer[u.layer]
                rank, n_w = wrap_rank[(e.id, k)]
                x_exit = row_right[r] + 26 + (n_w - 1 - rank) * TRACK_W
                x_entry = row_left[r + 1] - 26 - rank * TRACK_W
                lane = (row_bot[r] + row_top[r + 1]) / 2 + ((n_w - 1 - rank) - (n_w - 1) / 2) * 9
                pts += [(x_exit, ya), (x_exit, lane), (x_entry, lane), (x_entry, yb)]
            elif abs(ya - yb) > 0.5:
                gi = u.layer
                t = track_assign.get((e.id, k), 0)
                gap_start = col_x[gi] + col_w[gi] / 2
                tx = gap_start + gap_info[gi][0] + 18 + t * TRACK_W
                tx = min(tx, col_x[gi + 1] - col_w[gi + 1] / 2 - 8)
                pts += [(tx, ya), (tx, yb)]
            pts.append((xb, yb))
        e.path = _simplify(pts)

    # ---- back edges
    top = min([n.y - n.h / 2 - n.top_h for n in nodes.values()] + [n.span[0] for n in nodes.values() if n.kind == "manifold"] or [0])
    bot = max([n.y + n.band / 2 for n in nodes.values()] or [0])
    k_top = k_bot = 0
    for e in sorted([z for z in sl.edges if z.back], key=lambda z: z.id):
        a, b = nodes[e.src[0]], nodes[e.dst[0]]
        ya = a.port_y.get(e.src[1], a.y) if a.kind == "manifold" else a.y + a.ports.get(e.src[1], ("R", 0))[1]
        yb = b.port_y.get(e.dst[1], b.y) if b.kind == "manifold" else b.y + b.ports.get(e.dst[1], ("L", 0))[1]
        xa = a.x if a.kind == "manifold" else a.port_xy(e.src[1])[0]
        xb = b.x if b.kind == "manifold" else b.port_xy(e.dst[1])[0]
        use_bottom = (k_bot <= k_top)
        if use_bottom:
            lane = bot + 26 + k_bot * LANE_GAP
            k_bot += 1
        else:
            lane = top - 26 - k_top * LANE_GAP
            k_top += 1
        x1 = xa + 22 + (k_bot + k_top) * 3
        x2 = xb - 22 - (k_bot + k_top) * 3
        e.path = _simplify([(xa, ya), (x1, ya), (x1, lane), (x2, lane), (x2, yb), (xb, yb)])
    sl.lanes = k_top + k_bot

    # ---- inline symbol placement
    for e in sl.edges:
        _place_symbols(e)
    # ---- stubs (drain / vent / purge) hang from their source node
    for st in stubs:
        a = nodes.get(st.src[0])
        if a is None:
            continue
        side, rel = a.ports.get(st.src[1], ("B", 0.0))
        if a.kind == "manifold":
            px, py = a.x, a.port_y.get(st.src[1], a.y)
            side = "B"
        else:
            px, py = a.port_xy(st.src[1])
        if side == "T":
            end = (px, py - 18 - 24 * len(st.chain))
        elif side == "B":
            end = (px, py + 18 + 24 * len(st.chain))
        elif side == "R":
            end = (px + 22 + 26 * len(st.chain), py)
        else:
            end = (px - 22 - 26 * len(st.chain), py)
        st.path = [(px, py), end]
        sl.edges.append(st)
        _place_symbols(st)
    # bounding box
    xs, ys = [], []
    for n in nodes.values():
        if n.kind == "manifold":
            xs += [n.x - 4, n.x + 4]
            ys += [n.span[0], n.span[1]]
        else:
            xs += [n.x - n.w / 2, n.x + n.w / 2]
            ys += [n.y - n.h / 2 - n.top_h, n.y + n.h / 2 + n.label_h]
    for e in sl.edges:
        for (px, py) in e.path:
            xs.append(px)
            ys.append(py)
    sl.bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1, 1)
    return sl


def _shift(sl: SheetLayout, dx: float, dy: float) -> None:
    for n in sl.nodes.values():
        n.x += dx
        n.y += dy
        n.span = (n.span[0] + dy, n.span[1] + dy)
        n.port_y = {k: v + dy for k, v in n.port_y.items()}
    for e in sl.edges:
        e.path = [(x + dx, y + dy) for x, y in e.path]
        e.symbols = [(c, x + dx, y + dy, o) for c, x, y, o in e.symbols]
    x0, y0, x1, y1 = sl.bbox
    sl.bbox = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)


def layout_sheet(sheet_id: str, title: str, nodes: dict[str, MNode], edges: list[MEdge], hints: dict[str, Any] | None = None) -> SheetLayout:
    """Lay out every connected component on its own, then pack the components on the sheet."""
    hints = hints or {}
    parent = {n: n for n in nodes}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in edges:
        if not e.stub and e.src[0] in parent and e.dst[0] in parent:
            parent[find(e.src[0])] = find(e.dst[0])
    groups: dict[str, list[str]] = defaultdict(list)
    for n in sorted(nodes):
        groups[find(n)].append(n)
    comps = sorted(groups.values(), key=lambda g: (-len(g), g[0]))
    subs: list[SheetLayout] = []
    for g in comps:
        gs = set(g)
        sub_edges = [e for e in edges if e.src[0] in gs and (e.stub or e.dst[0] in gs)]
        subs.append(_layout_component(sheet_id, title, {n: nodes[n] for n in g}, sub_edges, hints))
    out = SheetLayout(sheet_id=sheet_id, title=title)
    max_w = float(hints.get("max_width", MAX_ROW_W))
    gap_x, gap_y = 60.0, 44.0
    cur_x = cur_y = shelf_h = 0.0
    placed: list[tuple[SheetLayout, float, float]] = []
    for sub in subs:
        x0, y0, x1, y1 = sub.bbox
        w, h = x1 - x0, y1 - y0
        if cur_x > 0 and cur_x + w > max_w:
            cur_y += shelf_h + gap_y
            cur_x, shelf_h = 0.0, 0.0
        _shift(sub, cur_x - x0, cur_y - y0)
        cur_x += w + gap_x
        shelf_h = max(shelf_h, h)
        out.nodes.update(sub.nodes)
        out.edges += sub.edges
        out.lanes += sub.lanes
        out.warnings += sub.warnings
    xs = [s_.bbox[0] for s_ in subs] + [s_.bbox[2] for s_ in subs]
    ys = [s_.bbox[1] for s_ in subs] + [s_.bbox[3] for s_ in subs]
    out.bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1, 1)
    return out


def _simplify(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 0.01 and abs(out[-1][1] - p[1]) < 0.01:
            continue
        out.append(p)
    changed = True
    while changed and len(out) > 2:
        changed = False
        for i in range(1, len(out) - 1):
            a, b, c = out[i - 1], out[i], out[i + 1]
            if (abs(a[0] - b[0]) < 0.01 and abs(b[0] - c[0]) < 0.01) or (abs(a[1] - b[1]) < 0.01 and abs(b[1] - c[1]) < 0.01):
                del out[i]
                changed = True
                break
    return out


def _place_symbols(e: MEdge) -> None:
    """Spread the inline valves along the longest straight run of the edge path."""
    e.symbols = []
    if not e.chain:
        return
    segs = []
    for i in range(len(e.path) - 1):
        (x1, y1), (x2, y2) = e.path[i], e.path[i + 1]
        length = abs(x2 - x1) + abs(y2 - y1)
        segs.append((length, i))
    if not segs:
        return
    n = len(e.chain)
    # prefer the first horizontal run when it is long enough, otherwise the longest run
    order = sorted(segs, key=lambda s: -s[0])
    first_h = next(((l, i) for l, i in segs if abs(e.path[i + 1][1] - e.path[i][1]) < 0.01 and l > 0), None)
    choice = first_h if (first_h and first_h[0] >= n * SYM_W * 0.9) else order[0]
    length, i = choice
    (x1, y1), (x2, y2) = e.path[i], e.path[i + 1]
    horiz = abs(y2 - y1) < 0.01
    # keep clear of the ends
    margin = min(14.0, length * 0.15)
    avail = max(length - 2 * margin, 1.0)
    step = min(SYM_W, avail / n)
    for k, c in enumerate(e.chain):
        t = margin + (k + 0.5) * step + (avail - n * step) / 2
        f = t / length if length else 0.5
        px, py = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
        e.symbols.append((c, px, py, "H" if horiz else "V"))


# ------------------------------------------------------------------------ instruments
def place_instruments(sl: SheetLayout, topo: Topology) -> None:
    """Bubbles beside their line or equipment, avoiding symbols, bars and each other."""
    insts = {i.id: i for i in topo.instruments}
    taken: list[tuple[float, float, float, float]] = []
    for n in sl.nodes.values():
        if n.kind == "dummy":
            continue
        r = _rect(n)
        taken.append((r[0] - 4, r[1] - 4, r[2] + 4, r[3] + 4) if n.kind == "manifold" else r)
        if n.kind == "equipment":
            taken.append((n.x - n.w / 2, n.y + n.h / 2, n.x + n.w / 2, n.y + n.h / 2 + n.label_h))
    sym_rect: dict[str, tuple[float, float, float, float]] = {}
    for e in sl.edges:
        for comp, x, y, ori in e.symbols:
            r = (x - 11, y - 8, x + 11, y + 8) if ori == "H" else (x - 8, y - 11, x + 8, y + 11)
            taken.append(r)
            sym_rect[comp.id] = r
            if comp.function == "control":
                taken.append((x - 8, y - 30, x + 8, y - 8))

    def free(cx: float, cy: float) -> bool:
        r = (cx - 12, cy - 12, cx + 12, cy + 12)
        return not any(_hit(r, q) for q in taken)

    line_edges: dict[str, list[MEdge]] = defaultdict(list)
    for e in sl.edges:
        for lg in e.logical:
            line_edges[lg].append(e)
    byid: dict[str, Placed] = {}

    def commit(pl: Placed) -> None:
        sl.instruments.append(pl)
        byid[pl.inst.id] = pl
        taken.append((pl.x - 12, pl.y - 12, pl.x + 12, pl.y + 12))

    for i in topo.instruments:
        t = i.target or {}
        if t.get("kind") == "line":
            runs: list[tuple[float, float, float]] = []  # length, xmid, y
            for e in line_edges.get(t["ref"], []):
                for k in range(len(e.path) - 1):
                    (x1, y1), (x2, y2) = e.path[k], e.path[k + 1]
                    if abs(y1 - y2) > 0.01 or abs(x1 - x2) < 24:
                        continue
                    lo, hi = sorted((x1, x2))
                    cuts = sorted((sx - 15, sx + 15) for _, sx, sy, ori in e.symbols if abs(sy - y1) < 1 and lo <= sx <= hi)
                    cur = lo + 8
                    for ca, cb in cuts + [(hi - 8, hi)]:
                        if ca - cur >= 20:
                            runs.append((ca - cur, (cur + ca) / 2, y1))
                        cur = max(cur, cb)
            runs.sort(key=lambda r: -r[0])
            chosen = None
            for length, xm, y in runs:
                for dx in (0, 30, -30, 60, -60, 90, -90):
                    for dy in (-34, 34, -52, 52):
                        if abs(xm + dx - xm) <= length / 2 and free(xm + dx, y + dy):
                            chosen = (xm + dx, y, y + dy)
                            break
                    if chosen:
                        break
                if chosen:
                    break
            if chosen is None:
                edges = [e for e in line_edges.get(t["ref"], []) if e.path]
                if not edges:
                    continue
                x, y = edges[0].path[0]
                chosen = (x + 24, y, y - 34)
            x, y, by = chosen
            commit(Placed(i, x, by, [(x, by + (11 if by < y else -11)), (x, y)]))
        elif t.get("kind") == "equipment":
            n = sl.nodes.get(t["ref"])
            if n is None:
                continue
            placed = False
            for side in (1, -1):
                for dy in (12, 36, -4):
                    bx = n.x + side * (n.w / 2 + 30)
                    by = n.y - n.h / 2 + dy
                    if free(bx, by):
                        commit(Placed(i, bx, by, [(bx - side * 11, by), (n.x + side * n.w / 2, by)]))
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                bx, by = n.x + n.w / 2 + 30, n.y - n.h / 2 + 12
                commit(Placed(i, bx, by, [(bx - 11, by), (n.x + n.w / 2, by)]))
    # controllers sit beside their transmitter; control signals run to the final element
    for s in topo.signals:
        if s.kind != "measurement" or s.from_ not in byid or s.to not in insts or s.to in byid:
            continue
        src = byid[s.from_]
        c = insts[s.to]
        up = src.y < src.leader[-1][1]
        placed = False
        for dy in ((-58, 58) if up else (58, -58)):
            for dx in (0, 36, -36, 72):
                if free(src.x + dx, src.y + dy):
                    commit(Placed(c, src.x + dx, src.y + dy, []))
                    placed = True
                    break
            if placed:
                break
        if not placed:
            commit(Placed(c, src.x, src.y + (-58 if up else 58), []))
    for s in topo.signals:
        a_ = byid.get(s.from_)
        if a_ is None:
            continue
        if s.kind == "measurement" and s.to in byid:
            b_ = byid[s.to]
            if abs(a_.x - b_.x) < 1:
                d = 12 if b_.y > a_.y else -12
                sl.signals.append(("measurement", [(a_.x, a_.y + d), (b_.x, b_.y - d)]))
            else:
                sl.signals.append(("measurement", [(a_.x + (12 if b_.x > a_.x else -12), a_.y), (b_.x, a_.y), (b_.x, b_.y + (12 if b_.y < a_.y else -12))]))
        elif s.kind == "control" and s.to in sym_rect:
            r = sym_rect[s.to]
            tx, ty = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
            sl.signals.append(("control", [(a_.x + (12 if tx > a_.x else -12), a_.y), (tx, a_.y), (tx, ty - 27 if a_.y < ty else ty + 12)]))
    x0_, y0_, x1_, y1_ = sl.bbox
    for pl_ in sl.instruments:
        x0_, y0_, x1_, y1_ = min(x0_, pl_.x - 14), min(y0_, pl_.y - 14), max(x1_, pl_.x + 14), max(y1_, pl_.y + 14)
    sl.bbox = (x0_, y0_, x1_, y1_)


# ------------------------------------------------------------------------- sheet assembly
@dataclass
class SheetSpec:
    id: str
    title: str
    areas: list[str]
    assign: list[str] = field(default_factory=list)  # glob patterns of object ids drawn on this sheet
    hints: dict[str, Any] = field(default_factory=dict)


@dataclass
class DrawingLayout:
    sheets: list[SheetLayout]
    specs: list[SheetSpec]
    cross: list[tuple[str, str, str, str]]  # (edge id, from sheet, to sheet, service)
    overview: Overview | None = None


def default_specs(topo: Topology, hints: dict[str, Any] | None = None) -> list[SheetSpec]:
    hints = hints or {}
    if hints.get("sheets"):
        return [SheetSpec(s["id"], s["title"], s.get("areas", []), s.get("assign", []), s.get("hints", {})) for s in hints["sheets"]]
    return [SheetSpec(f"S{i}", a.name, [a.id]) for i, a in enumerate(topo.areas, 1)]


def _node_label(n: MNode) -> str:
    return n.label or n.sublabel


def build_layouts(topo: Topology, hints: dict[str, Any] | None = None) -> DrawingLayout:
    specs = default_specs(topo, hints)
    macro = build_macro(topo, specs)
    sheet_index = {s.id: i for i, s in enumerate(specs, 1)}
    per_nodes: dict[str, dict[str, MNode]] = {s.id: {} for s in specs}
    per_edges: dict[str, list[MEdge]] = {s.id: [] for s in specs}
    for n in macro.nodes.values():
        per_nodes[n.sheet][n.id] = n
    cross: list[tuple[str, str, str, str]] = []
    for e in macro.edges:
        a = macro.nodes[e.src[0]]
        if e.stub:
            per_edges[a.sheet].append(e)
            continue
        b = macro.nodes[e.dst[0]]
        if a.sheet == b.sheet:
            per_edges[a.sheet].append(e)
            continue
        cross.append((e.id, a.sheet, b.sheet, e.service))
        xo = make_offpage_node(f"x:out:{e.id}", "out", f"to Sh.{sheet_index[b.sheet]}", f"{_node_label(b)} · {e.line_ids[-1]}")
        xo.sheet = a.sheet
        per_nodes[a.sheet][xo.id] = xo
        per_edges[a.sheet].append(MEdge(id=e.id, src=e.src, dst=(xo.id, "port"), chain=e.chain, line_ids=e.line_ids, service=e.service,
                                        header=e.header, proposed=e.proposed, logical=e.logical))
        xi = make_offpage_node(f"x:in:{e.id}", "in", f"from Sh.{sheet_index[a.sheet]}", f"{_node_label(a)} · {e.line_ids[0]}")
        xi.sheet = b.sheet
        per_nodes[b.sheet][xi.id] = xi
        per_edges[b.sheet].append(MEdge(id=e.id + "~in", src=(xi.id, "port"), dst=e.dst, chain=[], line_ids=[], service=e.service,
                                        header=e.header, proposed=e.proposed, logical=set()))
    sheets: list[SheetLayout] = []
    inst_lines: dict[str, int] = defaultdict(int)
    for i_ in topo.instruments:
        if (i_.target or {}).get("kind") == "line":
            inst_lines[i_.target["ref"]] += 1
    for s in specs:
        sl = layout_sheet(s.id, s.title, per_nodes[s.id], per_edges[s.id], {**s.hints, "inst_lines": dict(inst_lines)})
        place_instruments(sl, topo)
        sheets.append(sl)
    dl = DrawingLayout(sheets=sheets, specs=specs, cross=cross)
    dl.overview = build_overview(topo, specs, macro, cross)
    return dl


@dataclass
class Overview:
    boxes: dict[str, tuple[float, float, float, float]]  # sheet id -> (cx, cy, w, h)
    links: list[tuple[str, str, list[tuple[str, int, int]]]]  # a, b, [(service, n a->b, n b->a)]
    titles: dict[str, str] = field(default_factory=dict)


def build_overview(topo: Topology, specs: list[SheetSpec], macro: Macro, cross: list[tuple[str, str, str, str]]) -> Overview:
    """Block diagram of the sheets: spring layout of the sheet graph, bundled services per pair."""
    import networkx as nx

    pair: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for _, a, b, svc in cross:
        key = (a, b) if a <= b else (b, a)
        pair[key][svc][0 if a <= b else 1] += 1
    g = nx.Graph()
    g.add_nodes_from(sp.id for sp in specs)
    for (a, b), svcs in pair.items():
        g.add_edge(a, b, weight=len(svcs))
    pos = nx.spring_layout(g, seed=11, k=1.6, iterations=300) if len(specs) > 1 else {specs[0].id: (0.0, 0.0)}
    pts = {k: (float(v[0]), float(v[1])) for k, v in pos.items()}
    ids_ = sorted(pts)
    dmin = min((math.dist(pts[a_], pts[b_]) for i, a_ in enumerate(ids_) for b_ in ids_[i + 1:]), default=1.0) or 1.0
    k = 300.0 / dmin  # keeps every pair of 200 x 62 boxes clear of each other
    boxes = {sid: (p_[0] * k, p_[1] * k, 200.0, 62.0) for sid, p_ in pts.items()}
    links = []
    for (a, b), svcs in sorted(pair.items()):
        links.append((a, b, [(svc, v[0], v[1]) for svc, v in sorted(svcs.items())]))
    return Overview(boxes=boxes, links=links, titles={sp.id: sp.title for sp in specs})


# ------------------------------------------------------------------------------ layout QA
def _rect(n: MNode) -> tuple[float, float, float, float]:
    if n.kind == "manifold":
        return (n.x - 3, n.span[0], n.x + 3, n.span[1])
    return (n.x - n.w / 2, n.y - n.h / 2, n.x + n.w / 2, n.y + n.h / 2)


def _hit(a: tuple[float, float, float, float], b: tuple[float, float, float, float], tol: float = 0.5) -> bool:
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


def layout_qa(sl: SheetLayout) -> list[str]:
    """Geometric checks on a laid-out sheet; returns human-readable problems (empty = clean)."""
    out: list[str] = []
    nodes = [n for n in sl.nodes.values() if n.kind != "dummy"]
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if a.kind == "manifold" and b.kind == "manifold":
                continue
            if _hit(_rect(a), _rect(b)):
                out.append(f"{sl.sheet_id}: {a.id} overlaps {b.id}")
    sym_rects = []
    for e in sl.edges:
        for comp, x, y, ori in e.symbols:
            r = (x - 10, y - 7, x + 10, y + 7) if ori == "H" else (x - 7, y - 10, x + 7, y + 10)
            sym_rects.append((comp.id, r))
    for cid, r in sym_rects:
        for n in nodes:
            if _hit(r, _rect(n)):
                out.append(f"{sl.sheet_id}: valve {cid} sits on {n.id}")
    for i, (ca, ra) in enumerate(sym_rects):
        for cb, rb in sym_rects[i + 1:]:
            if _hit(ra, rb):
                out.append(f"{sl.sheet_id}: valves {ca} and {cb} overlap")
    for pl in sl.instruments:
        r = (pl.x - 11, pl.y - 11, pl.x + 11, pl.y + 11)
        for n in nodes:
            if _hit(r, _rect(n)):
                out.append(f"{sl.sheet_id}: instrument {pl.inst.id} sits on {n.id}")
        for cid, rs in sym_rects:
            if _hit(r, rs):
                out.append(f"{sl.sheet_id}: instrument {pl.inst.id} overlaps valve {cid}")
    # pipes passing through equipment symbols (own end points excluded)
    for e in sl.edges:
        for k in range(len(e.path) - 1):
            (x1, y1), (x2, y2) = e.path[k], e.path[k + 1]
            seg = (min(x1, x2), min(y1, y2), max(x1, x2) + 0.01, max(y1, y2) + 0.01)
            for n in nodes:
                if n.kind not in ("equipment",):
                    continue
                if n.id in (e.src[0], e.dst[0]):
                    continue
                if _hit(seg, _rect(n), tol=1.0):
                    out.append(f"{sl.sheet_id}: line {e.id} crosses {n.id}")
                    break
    return sorted(set(out))
