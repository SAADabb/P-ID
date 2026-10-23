"""Repair pass: re-route every pipe that runs through something it is not connected to.

The layered layout routes pipes with simple H-V-H patterns between columns; in dense areas such a route can cross a
header bar, a valve of another pipe, an equipment symbol or the text under it. Those pipes are re-routed here with
the same orthogonal A* router as the pipes between plant areas, on a fine grid where

* symbols (with their text), header bars and other pipes' valves are blocked,
* other pipes' tracks cannot be shared (crossings are allowed, at a cost),
* the pipe leaves and enters its nozzles in the nozzle's direction.

Valves of the re-routed pipe are placed again on its longest straight run.
"""

from __future__ import annotations

from .geomqa import Rect, seg_hits_rect, segments, valve_rect
from .layout import MEdge, MNode, SheetLayout, _place_symbols
from .onesheet import _DIRS, _astar, _clean

CELL = 6.0


def label_rect(n: MNode) -> Rect | None:
    """Extent of the text drawn under an equipment symbol (render_pdf.draw_equipment)."""
    if n.kind != "equipment":
        return None
    from .render_pdf import FONT, _fonts, wrap

    _fonts()
    if n.symbol in ("tank", "vessel"):
        return None  # label inside the symbol
    width = n.w if n.symbol == "box" else max(n.w + 34, 96)
    lines = 1 if n.symbol == "box" else len(wrap(n.sublabel or "", width, 6.9, FONT, 2)) + (1 if n.label else 0)
    if n.symbol == "box" and not n.label:
        return None
    h = 4 + lines * 8.6
    return (n.x - width / 2, n.y + n.h / 2 + 1, n.x + width / 2, n.y + n.h / 2 + 1 + h)


def _body(n: MNode, pad: float = 0.0) -> Rect:
    if n.kind == "manifold":
        return (n.x - 1 - pad, n.span[0] - 1 - pad, n.x + 1 + pad, n.span[1] + 1 + pad)
    return (n.x - n.w / 2 - pad, n.y - n.h / 2 - pad - n.top_h, n.x + n.w / 2 + pad, n.y + n.h / 2 + pad)


def _blockers(sl: SheetLayout, e: MEdge, own_ends: bool = False) -> list[Rect]:
    """Rects the pipe must avoid; with ``own_ends`` also the bodies of the two items it connects."""
    ends = set() if own_ends else {e.src[0], e.dst[0]}
    own = {c.id for c, *_ in e.symbols}
    out: list[Rect] = []
    for n in sl.nodes.values():
        if n.kind in ("dummy", "terminal"):
            continue
        lr = label_rect(n)
        if lr is not None:
            out.append(lr)  # text under a symbol, also under the pipe's own equipment
        if own_ends and n.id in (e.src[0], e.dst[0]):
            out.append(_body(n))
        elif n.id not in ends:
            out.append(_body(n, 2))
    for o in sl.edges:
        for c, x, y, ori in o.symbols:
            if c.id not in own:
                out.append(valve_rect(x, y, ori, 2))
    return out


def bad_edges(sl: SheetLayout) -> list[MEdge]:
    out = []
    for e in sl.edges:
        if e.stub or len(e.path) < 2:
            continue
        segs = segments(e)
        inner = segs[1:-1] if len(segs) > 2 else segs
        rects = _blockers(sl, e)
        own = [_body(sl.nodes[x], -1) for x in (e.src[0], e.dst[0]) if x in sl.nodes and sl.nodes[x].kind not in ("dummy", "terminal")]
        # first/last segments may touch the text band of their own equipment where they leave it
        own_labels = [label_rect(sl.nodes[x]) for x in (e.src[0], e.dst[0]) if x in sl.nodes]
        if any(seg_hits_rect(s, r) for s in inner for r in rects) or any(
                seg_hits_rect(s, r) for s in (segs[:1] + segs[-1:]) for r in rects if r not in own_labels) or any(
                seg_hits_rect(s, r) for s in inner for r in own):
            out.append(e)
    return out


def _side(n: MNode, port: str, e: MEdge, outgoing: bool) -> str:
    if n.kind == "manifold":
        return n.ports.get(port, ("R" if outgoing else "L", 0.0))[0]
    if n.kind == "terminal":
        return n.ports.get("port", ("R", 0.0))[0]
    return n.ports.get(port, ("R" if outgoing else "L", 0.0))[0]


_DIR_OF = {"R": 0, "B": 1, "L": 2, "T": 3}


def reroute(sl: SheetLayout, e: MEdge) -> bool:
    a, b = sl.nodes.get(e.src[0]), sl.nodes.get(e.dst[0])
    if a is None or b is None or not e.path:
        return False
    sa, sb = _side(a, e.src[1], e, True), _side(b, e.dst[1], e, False)
    d0 = _DIR_OF[sa]                      # leave the source in the nozzle direction
    d1 = (_DIR_OF[sb] + 2) % 4            # arrive moving into the target nozzle
    if a.kind == "terminal" and len(e.path) > 1:  # a zone terminal: keep the direction the pipe enters the zone
        d0 = _dir(e.path[0], e.path[1], d0)
    if b.kind == "terminal" and len(e.path) > 1:
        d1 = _dir(e.path[-2], e.path[-1], d1)
    # a branch may leave (or join) a header bar on either side
    d0s = [d0, (d0 + 2) % 4] if a.kind == "manifold" and e.src[1] != "common" else [d0]
    d1s = [d1, (d1 + 2) % 4] if b.kind == "manifold" and e.dst[1] != "common" else [d1]
    grid = _grid(sl, e)
    best = None
    for d0_ in d0s:
        for d1_ in d1s:
            r = _route(grid, e.path[0], e.path[-1], d0_, d1_)
            if r is not None and (best is None or r[0] < best[0]):
                best = r
    if best is None:
        return False
    old_path, old_symbols = e.path, e.symbols
    e.path = best[1]
    if any(abs(a_[0] - b_[0]) > 1e-6 and abs(a_[1] - b_[1]) > 1e-6 for a_, b_ in zip(e.path, e.path[1:])):
        e.path, e.symbols = old_path, old_symbols  # snapping produced a diagonal: keep the old route
        return False
    _place_symbols(e)
    return True


def _grid(sl: SheetLayout, e: MEdge) -> dict:
    xs = [n.x - n.w / 2 for n in sl.nodes.values()] + [n.x + n.w / 2 for n in sl.nodes.values()]
    ys = [n.y - n.h / 2 - n.top_h for n in sl.nodes.values()] + [n.y + n.h / 2 + n.label_h for n in sl.nodes.values()]
    for o in sl.edges:
        for x, y in o.path:
            xs.append(x)
            ys.append(y)
    x0, y0 = min(xs) - 60, min(ys) - 60
    nx, ny = int((max(xs) + 60 - x0) / CELL) + 1, int((max(ys) + 60 - y0) / CELL) + 1

    def cell(x: float, y: float) -> tuple[int, int]:
        return int(round((x - x0) / CELL)), int(round((y - y0) / CELL))

    blocked: set[tuple[int, int]] = set()
    near: set[tuple[int, int]] = set()
    for r in _blockers(sl, e, own_ends=True):
        c0, c1 = cell(r[0], r[1]), cell(r[2], r[3])
        for i in range(c0[0], c1[0] + 1):
            for j in range(c0[1], c1[1] + 1):
                blocked.add((i, j))
        for i in range(c0[0] - 1, c1[0] + 2):
            for j in range(c0[1] - 1, c1[1] + 2):
                near.add((i, j))
    used_h: set[tuple[int, int]] = set()
    used_v: set[tuple[int, int]] = set()
    for o in sl.edges:
        if o is e:
            continue
        for s in segments(o):
            c0, c1 = cell(min(s[0], s[2]), min(s[1], s[3])), cell(max(s[0], s[2]), max(s[1], s[3]))
            horiz = abs(s[1] - s[3]) < 1e-6
            for i in range(c0[0], c1[0] + 1):
                for j in range(c0[1], c1[1] + 1):
                    (used_h if horiz else used_v).add((i, j))
                    near.add((i, j))
    return {"x0": x0, "y0": y0, "nx": nx, "ny": ny, "cell": cell, "blocked": blocked, "near": near, "h": used_h, "v": used_v}


def _route(gr: dict, p0: tuple[float, float], p1: tuple[float, float], d0: int, d1: int):
    """(cost, path) of an A* route from p0 leaving in d0 to p1 arriving in d1, or None."""
    blocked = set(gr["blocked"])
    sc, gc = gr["cell"](*p0), gr["cell"](*p1)
    dx0, dy0 = _DIRS[d0]
    dx1, dy1 = _DIRS[d1]
    # the approach cells next to the nozzles belong to this pipe; stop the approach before anything in the way
    k0 = _approach(sc, dx0, dy0, blocked)
    k1 = _approach(gc, -dx1, -dy1, blocked)
    for k in range(k0 + 1):
        blocked.discard((sc[0] + dx0 * k, sc[1] + dy0 * k))
    for k in range(k1 + 1):
        blocked.discard((gc[0] - dx1 * k, gc[1] - dy1 * k))
    s = (sc[0] + dx0 * k0, sc[1] + dy0 * k0)
    g = (gc[0] - dx1 * k1, gc[1] - dy1 * k1)
    cells = _astar(s, g, gr["nx"], gr["ny"], blocked, gr["near"], gr["h"], gr["v"], d0=d0, d1=d1)
    if cells is None:
        return None
    pts = [(gr["x0"] + c[0] * CELL, gr["y0"] + c[1] * CELL) for c in cells]
    # keep the nozzle heights / positions exactly: shift the first and last runs onto them
    pts = _snap_end(pts, p0, d0, first=True)
    pts = _snap_end(pts, p1, d1, first=False)
    path = _clean([p0] + pts + [p1])
    length = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:]))
    return length + 40 * (len(path) - 2), path


def _dir(a: tuple[float, float], b: tuple[float, float], default: int) -> int:
    if abs(b[0] - a[0]) > abs(b[1] - a[1]):
        return 0 if b[0] > a[0] else 2
    if abs(b[1] - a[1]) > 1e-6:
        return 1 if b[1] > a[1] else 3
    return default


def _approach(c: tuple[int, int], dx: int, dy: int, blocked: set) -> int:
    """Cells the pipe runs straight out of its nozzle: 3, fewer when a symbol or text is closer."""
    for k in range(1, 4):
        if (c[0] + dx * (k + 1), c[1] + dy * (k + 1)) in blocked:
            return max(1, k - 1) if k > 1 else 1
    return 3


def _snap_end(pts: list[tuple[float, float]], p: tuple[float, float], d: int, first: bool) -> list[tuple[float, float]]:
    """Move the first (or last) straight run onto the nozzle's own height / position.

    Only the coordinate across the run changes, so the perpendicular segment that follows stays axis-parallel.
    """
    pts = list(pts)
    horiz = d in (0, 2)
    order = list(range(len(pts))) if first else list(range(len(pts) - 1, -1, -1))
    ref = pts[order[0]]
    for i in order:
        q = pts[i]
        if horiz and abs(q[1] - ref[1]) < 1e-6:
            pts[i] = (q[0], p[1])
        elif not horiz and abs(q[0] - ref[0]) < 1e-6:
            pts[i] = (p[0], q[1])
        else:
            break
    return pts


def repair_sheet(sl: SheetLayout, passes: int = 3) -> int:
    """Re-route offending pipes; returns how many were re-routed."""
    done = 0
    tried: set[str] = set()
    for _ in range(passes):
        bad = [e for e in bad_edges(sl) if e.id not in tried]
        if not bad:
            break
        for e in bad:
            tried.add(e.id)
            if reroute(sl, e):
                done += 1
    return done
