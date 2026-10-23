"""Strict geometric checks of a laid-out drawing.

What a reader of a P&ID must never see:

* a pipe drawn through a symbol it is not connected to (equipment, battery-limit flag, header bar, valve, instrument
  bubble) - it reads as a connection or hides the symbol;
* two different pipes drawn on top of each other (a shared track) - the reader cannot tell them apart;
* a symbol on top of another symbol.

``check`` returns typed issues so that the repair router can act on them; ``describe`` turns them into the
human-readable lines of the layout report.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .layout import MEdge, MNode, SheetLayout

Rect = tuple[float, float, float, float]
Seg = tuple[float, float, float, float]   # x1, y1, x2, y2 (axis-parallel)


@dataclass(frozen=True)
class Issue:
    kind: str          # crosses | overlap | symbol_overlap
    edge: str          # the edge to repair ("" for symbol overlaps)
    other: str         # what it hits
    where: tuple[float, float]


def node_rect(n: MNode, pad: float = 0.0) -> Rect:
    if n.kind == "manifold":
        return (n.x - 2.5 - pad, n.span[0] - pad, n.x + 2.5 + pad, n.span[1] + pad)
    return (n.x - n.w / 2 - pad, n.y - n.h / 2 - pad, n.x + n.w / 2 + pad, n.y + n.h / 2 + pad)


def valve_rect(x: float, y: float, ori: str, pad: float = 0.0) -> Rect:
    return (x - 9 - pad, y - 6.5 - pad, x + 9 + pad, y + 6.5 + pad) if ori == "H" else (x - 6.5 - pad, y - 9 - pad, x + 6.5 + pad, y + 9 + pad)


def segments(e: MEdge) -> list[Seg]:
    return [(a[0], a[1], b[0], b[1]) for a, b in zip(e.path, e.path[1:]) if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1e-6]


def seg_hits_rect(s: Seg, r: Rect, tol: float = 0.8) -> bool:
    x1, y1, x2, y2 = s
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    return lo_x < r[2] - tol and r[0] + tol < hi_x + 0.01 and lo_y < r[3] - tol and r[1] + tol < hi_y + 0.01


def base_id(edge_id: str) -> str:
    """The pieces of one pipe drawn across zones share a base id (x, x~x, x~in)."""
    return edge_id.split("~")[0]


def obstacles(sl: SheetLayout) -> list[tuple[str, str, Rect]]:
    """(owner kind, owner id, rect) of everything a foreign pipe must not cross."""
    out: list[tuple[str, str, Rect]] = []
    for n in sl.nodes.values():
        if n.kind in ("dummy", "terminal"):
            continue
        out.append((n.kind, n.id, node_rect(n, -0.5)))
    for e in sl.edges:
        for comp, x, y, ori in e.symbols:
            out.append(("valve", comp.id, valve_rect(x, y, ori)))
    for p in sl.instruments:
        out.append(("instrument", p.inst.id, (p.x - 11, p.y - 11, p.x + 11, p.y + 11)))
    return out


def check(sl: SheetLayout) -> list[Issue]:
    issues: list[Issue] = []
    obs = obstacles(sl)
    own_valves = {e.id: {c.id for c, *_ in e.symbols} for e in sl.edges}
    # ---- pipes through symbols
    for e in sl.edges:
        ends = {e.src[0], e.dst[0]}
        for s in segments(e):
            for kind, oid, r in obs:
                if oid in ends or oid in own_valves[e.id] or kind == "terminal":
                    continue
                if seg_hits_rect(s, r):
                    issues.append(Issue("crosses", e.id, oid, ((s[0] + s[2]) / 2, (s[1] + s[3]) / 2)))
                    break
    # ---- pipes on top of each other (same track, overlapping run)
    buckets: dict[tuple[str, int], list[tuple[str, float, float, float]]] = defaultdict(list)
    for e in sl.edges:
        for s in segments(e):
            if abs(s[1] - s[3]) < 1e-6:   # horizontal
                buckets[("h", round(s[1]))].append((e.id, s[1], min(s[0], s[2]), max(s[0], s[2])))
            else:
                buckets[("v", round(s[0]))].append((e.id, s[0], min(s[1], s[3]), max(s[1], s[3])))
    seen: set[tuple[str, str]] = set()
    for (ori, c), segs in buckets.items():
        near = segs + buckets.get((ori, c + 1), [])
        for i, (ea, ca, a0, a1) in enumerate(segs):
            for eb, cb, b0, b1 in near[i + 1:]:
                if base_id(ea) == base_id(eb) or abs(ca - cb) > 1.5:
                    continue
                if min(a1, b1) - max(a0, b0) > 3.0 and (ea, eb) not in seen:
                    seen.add((ea, eb))
                    mid = (max(a0, b0) + min(a1, b1)) / 2
                    issues.append(Issue("overlap", eb, ea, (mid, ca) if ori == "h" else (ca, mid)))
    # ---- symbols on symbols (instrument bubbles and valves are placed after the pipes)
    sym = [(k, i, r) for k, i, r in obs if k in ("valve", "instrument")]
    big = [(k, i, r) for k, i, r in obs if k not in ("valve", "instrument")]
    for k, i, r in sym:
        for k2, i2, r2 in big + sym:
            if i2 == i:
                continue
            if r[0] < r2[2] - 0.5 and r2[0] < r[2] - 0.5 and r[1] < r2[3] - 0.5 and r2[1] < r[3] - 0.5:
                issues.append(Issue("symbol_overlap", "", f"{i} / {i2}", ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)))
    uniq: dict[tuple, Issue] = {}
    for it in issues:
        key = (it.kind, it.edge, it.other) if it.kind != "symbol_overlap" else (it.kind, tuple(sorted(it.other.split(" / "))))
        uniq.setdefault(key, it)
    return list(uniq.values())


def describe(issues: list[Issue], sheet: str) -> list[str]:
    out = []
    for it in issues:
        if it.kind == "crosses":
            out.append(f"{sheet}: line {it.edge} passes through {it.other}")
        elif it.kind == "overlap":
            out.append(f"{sheet}: lines {it.edge} and {it.other} overlap")
        else:
            out.append(f"{sheet}: symbols overlap: {it.other}")
    return sorted(out)
