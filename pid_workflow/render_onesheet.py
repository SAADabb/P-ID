"""The one-sheet P&ID: an A0 drawing with border grid, plant-area zones, legend, notes, hold list,
revision block and title block.

Everything is drawn on a :class:`graphics.Recorder`; the recorded primitives are replayed into the PDF
and handed to :mod:`proteus_graphics` for the DEXPI file, so both carry exactly the same drawing.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .graphics import Owner, Prim, Recorder, replay

from .layout import MEdge, MNode, tbc_stubs
from .onesheet import OneSheet
from .render_pdf import (
    AMBER_FILL,
    FONT,
    FONT_B,
    FONT_I,
    GREY,
    INK,
    RED,
    SheetPainter,
    Style,
    _dist_seg,
    _fonts,
    arrow,
    draw_boundary,
    draw_bubble,
    draw_equipment,
    draw_open_end,
    draw_valve,
    poly,
    txt,
    wrap,
)
from .schema import Topology, is_pending

MM = 72.0 / 25.4
A0 = (1189 * MM, 841 * MM)
M_L, M_O = 20 * MM, 10 * MM          # filing margin (left), other margins
GRID_W = 6 * MM                      # reference-grid strip inside the frame
PANEL_W = 150 * MM                   # notes / legend / title-block column
TB_H = 92 * MM                       # title block height
SHEET_FONT_SCALE = 1.0


@dataclass
class Hold:
    num: int
    ur_id: str
    title: str
    text: str
    affects: list[str] = field(default_factory=list)


@dataclass
class SheetContent:
    holds: list[Hold]
    notes: list[str]
    tbd: list[str]                    # data to be completed on datasheets (not drawn as holds)
    line_labels: dict[str, str]       # topology line id -> label shown on the drawing
    revision: list[tuple[str, str, str]]  # rev, date, description
    kind: str = "pid"                 # pid | pfd
    stream_table: list[list[str]] | None = None   # PFD: rows (first cell = row title), one column per stream
    equipment_summary: list[tuple[str, str, str]] | None = None  # PFD: tag, description, key data
    _labelled: set[str] = field(default_factory=set)


@dataclass
class OneSheetDrawing:
    prims: list[Prim]
    transform: tuple[float, float, float]   # scale, ox, oy: page = (ox + s*x, oy - s*y)
    page: tuple[float, float]
    scale: float


def _field_box() -> tuple[float, float, float, float]:
    W, H = A0
    x0 = M_L + GRID_W + 10
    x1 = W - M_O - GRID_W - PANEL_W - 10
    y0 = M_O + GRID_W + 10
    y1 = H - M_O - GRID_W - 10
    return x0, y0, x1, y1


def draw_onesheet(topo: Topology, os_: OneSheet, st: Style, content: SheetContent) -> OneSheetDrawing:
    _fonts()
    st.prime([e.service for e in os_.layout.edges if e.service])
    rec = Recorder()
    W, H = A0
    _border(rec, topo)
    x0, y0, x1, y1 = _field_box()
    if content.stream_table:
        y0 = _stream_table(rec, content.stream_table, x0, y0, x1) + 14
    bx0, by0, bx1, by1 = os_.layout.bbox
    s = min((x1 - x0) / (bx1 - bx0), (y1 - y0) / (by1 - by0))
    ox = x0 + ((x1 - x0) - (bx1 - bx0) * s) / 2 - bx0 * s
    oy = y1 - ((y1 - y0) - (by1 - by0) * s) / 2 + by0 * s
    rec.saveState()
    rec.transform(s, 0, 0, -s, ox, oy)
    painter = SheetPainter(rec, topo, st)
    _zones(rec, os_)
    _content(rec, painter, os_, st, content)
    rec.restoreState()
    _panel(rec, topo, st, content, os_)
    return OneSheetDrawing(prims=rec.prims, transform=(s, ox, oy), page=A0, scale=s)


def save_onesheet_pdf(d: OneSheetDrawing, topo: Topology, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=d.page, invariant=1)
    c.setTitle(f"{topo.metadata.drawing_id} – {topo.metadata.title}")
    c.setAuthor("pid_workflow")
    c.setFillColor(colors.white)
    c.rect(0, 0, d.page[0], d.page[1], stroke=0, fill=1)
    replay(d.prims, c)
    c.showPage()
    c.save()


# ----------------------------------------------------------------------------------- border
def _border(rec: Recorder, topo: Topology) -> None:
    rec.owner = Owner("sheet", "border", "border")
    W, H = A0
    fx0, fy0, fx1, fy1 = M_L, M_O, W - M_O, H - M_O
    rec.setStrokeColor(INK)
    rec.setLineWidth(1.6)
    rec.rect(fx0, fy0, fx1 - fx0, fy1 - fy0)
    rec.setLineWidth(0.6)
    rec.rect(fx0 + GRID_W, fy0 + GRID_W, fx1 - fx0 - 2 * GRID_W, fy1 - fy0 - 2 * GRID_W)
    ncol, nrow = 16, 12
    cw = (fx1 - fx0 - 2 * GRID_W) / ncol
    rh = (fy1 - fy0 - 2 * GRID_W) / nrow
    rec.setFillColor(INK)
    rec.setFont(FONT, 9)
    for i in range(ncol + 1):
        x = fx0 + GRID_W + i * cw
        for ya, yb in ((fy0, fy0 + GRID_W), (fy1 - GRID_W, fy1)):
            rec.line(x, ya, x, yb)
        if i < ncol:
            for yy in (fy0 + 5, fy1 - GRID_W + 5):
                rec.drawCentredString(x + cw / 2, yy, str(i + 1))
    for j in range(nrow + 1):
        y = fy1 - GRID_W - j * rh
        for xa, xb in ((fx0, fx0 + GRID_W), (fx1 - GRID_W, fx1)):
            rec.line(xa, y, xb, y)
        if j < nrow:
            for xx in (fx0 + GRID_W / 2, fx1 - GRID_W / 2):
                rec.drawCentredString(xx, y - rh / 2 - 3, "ABCDEFGHJKLM"[j])
    # separator of the right-hand column
    px = W - M_O - GRID_W - PANEL_W
    rec.setLineWidth(0.9)
    rec.line(px, fy0 + GRID_W, px, fy1 - GRID_W)


# ----------------------------------------------------------------------------------- drawing
def _zones(rec: Recorder, os_: OneSheet) -> None:
    for i, z in enumerate(os_.zones, 1):
        rec.owner = Owner("zone", z.spec.id, "label")
        x0, y0, x1, y1 = z.frame
        rec.saveState()
        rec.setStrokeColor(colors.HexColor("#9a9a9a"))
        rec.setLineWidth(0.9)
        rec.setDash(10, 4)
        rec.rect(x0, y0, x1 - x0, y1 - y0)
        rec.restoreState()
        title = wrap(f"AREA {i} – {z.spec.title.upper()}", x1 - x0 - 20, 10, FONT_B, 2)
        for j, tl in enumerate(title):
            txt(rec, x0 + 10, y0 + 16 + j * 11.5, tl, 10 if len(title) > 1 else 11, FONT_B, "l", colors.HexColor("#4a4a4a"))


def _content(rec: Recorder, painter: SheetPainter, os_: OneSheet, st: Style, content: SheetContent) -> None:
    sl = os_.layout
    lines = {l.id: l for l in painter.topo.process_lines}
    # pipes
    for e in sl.edges:
        if len(e.path) < 2:
            continue
        rec.owner = Owner("line", e.id, "line")
        _edge(rec, painter, e, st, content, lines, sl)
    # equipment, boundaries, manifolds
    for n in sl.nodes.values():
        if n.kind == "equipment":
            rec.owner = Owner("equipment", n.id, "symbol", (n.x, n.y))
            draw_equipment(rec, n, st)
        elif n.kind == "boundary":
            rec.owner = Owner("boundary", n.id, "symbol", (n.x, n.y))
            draw_boundary(rec, n, st, None)
        elif n.kind == "manifold":
            rec.owner = Owner("manifold", n.id, "label")
            painter.draw_manifold(n, sl)
    # process nozzles the specification leaves unconnected: dashed stub marked TBC
    for n, px, py, dx, dy in tbc_stubs(sl):
        rec.owner = Owner("equipment", n.id, "label")
        rec.saveState()
        rec.setStrokeColor(GREY)
        rec.setLineWidth(1.0)
        rec.setDash(3, 2)
        rec.line(px, py, px + dx * 26, py + dy * 26)
        rec.restoreState()
        txt(rec, px + dx * 30, py + dy * 30 + 2.5, "TBC", 5.8, FONT_B, "l" if dx >= 0 else "r", GREY)
    # valves; tags take the first free spot (above, below, beside) so they never sit on another tag or valve

    taken: list[tuple[float, float, float, float]] = []
    for e in sl.edges:
        for comp, x, y, ori in e.symbols:
            taken.append((x - 9, y - 7, x + 9, y + 7) if ori == "H" else (x - 7, y - 9, x + 7, y + 9))

    for pl in sl.instruments:
        taken.append((pl.x - 12, pl.y - 12, pl.x + 12, pl.y + 12))
    for n in sl.nodes.values():
        if n.kind == "manifold":
            taken.append((n.x - 3, n.span[0] - 3, n.x + 3, n.span[1] + 3))
        elif n.kind in ("equipment", "boundary"):
            taken.append((n.x - n.w / 2, n.y - n.h / 2, n.x + n.w / 2, n.y + n.h / 2))
    segs = [(a, b) for e in sl.edges for a, b in zip(e.path, e.path[1:])]

    def free(r: tuple[float, float, float, float], strict: bool = True) -> bool:
        """Clear of tags, valves and bubbles; ``strict`` also clear of every pipe."""
        return not any(r[0] < q[2] and q[0] < r[2] and r[1] < q[3] and q[1] < r[3] for q in taken) and not (strict and _on_segs(r, segs))

    def place_tag(tag: str, x: float, y: float, ori: str, control: bool) -> tuple[float, float, str]:
        w = stringWidth(tag, FONT_B, 6.6)
        if ori == "H":
            cands = [(x, y - (25 if control else 12), "c"), (x, y + 18.5, "c"), (x, y - 24, "c"), (x, y + 30, "c"),
                     (x + 12, y - 12, "l"), (x - 12, y - 12, "r")]
            cands += [(x, y - 36, "c"), (x, y + 42, "c"), (x + 22, y - 12, "l"), (x - 22, y - 12, "r")]
        else:
            cands = [(x + 11, y + 2.4, "l"), (x - 11, y + 2.4, "r"), (x + 11, y - 10, "l"), (x - 11, y + 14, "r"),
                     (x + 11, y + 15, "l"), (x - 11, y - 10, "r"), (x + 22, y + 2.4, "l"), (x - 22, y + 2.4, "r")]
        # crowded spot: then the nearest free place on a wider ring
        ring = [(x + dx, y + dy, "c") for d in (30, 44, 58) for dx, dy in ((0, -d), (0, d + 6), (d, -6), (-d, -6), (d, d), (-d, d), (d, -d), (-d, -d))]
        for strict in (True, False):
            for cx, cy, al in cands + ring:
                x0 = cx - w / 2 if al == "c" else (cx if al == "l" else cx - w)
                r = (x0 - 1, cy - 6.5, x0 + w + 1, cy + 1.5)
                if free(r, strict):
                    taken.append(r)
                    return cx, cy, al
        cx, cy, al = cands[0]
        return cx, cy, al

    for e in sl.edges:
        for k, (comp, x, y, ori) in enumerate(e.symbols):
            rec.owner = Owner("valve", comp.id, "symbol", (x, y))
            i = min(range(len(e.path) - 1), key=lambda j: _dist_seg((x, y), e.path[j], e.path[j + 1]))
            dx = e.path[i + 1][0] - e.path[i][0]
            draw_valve(rec, comp, x, y, ori, st, flow_dx=dx if ori == "H" else 1)
            tag = comp.tag or ""
            col = st.proposed if is_pending(comp.provenance) else INK
            if tag:
                rec.owner = Owner("valve", comp.id, "label")
                tx, ty, al = place_tag(tag, x, y, ori, comp.function == "control")
                txt(rec, tx, ty, tag, 6.6, FONT_B, al, col)
        if e.stub and e.path and e.chain:
            (xa, ya), (xb, yb) = e.path[-2], e.path[-1]
            comp = e.chain[-1]
            rec.owner = Owner("valve", comp.id, "label")
            draw_open_end(rec, comp.open_end or "drain", xb, yb, xb - xa, yb - ya, st.proposed if is_pending(comp.provenance) else INK)
    # signals and instruments
    for kind, pts in sl.signals:
        rec.owner = Owner("signal", kind, "label")
        rec.saveState()
        rec.setStrokeColor(colors.HexColor("#2a5db0"))
        rec.setLineWidth(0.8)
        rec.setDash(3, 2)
        poly(rec, pts)
        rec.restoreState()
    for pl in sl.instruments:
        i = pl.inst
        if pl.leader:
            rec.owner = Owner("instrument", i.id, "label")
            rec.saveState()
            rec.setStrokeColor(INK)
            rec.setLineWidth(0.6)
            poly(rec, pl.leader)
            rec.restoreState()
        rec.owner = Owner("instrument", i.id, "symbol", (pl.x, pl.y))
        rec.saveState()
        rec.setStrokeColor(st.proposed if is_pending(i.provenance) else INK)
        rec.setFillColor(AMBER_FILL if is_pending(i.provenance) else colors.white)
        rec.setLineWidth(1.0)
        rec.circle(pl.x, pl.y, 11.0, stroke=1, fill=1)
        rec.line(pl.x - 11, pl.y, pl.x + 11, pl.y)
        rec.restoreState()
        rec.owner = Owner("instrument", i.id, "label")
        num = (i.tag or "").split("-")[-1] if i.tag else ""
        txt(rec, pl.x, pl.y - 2.2, i.isa_code, 6.4, FONT_B)
        txt(rec, pl.x, pl.y + 7.4, num, 6.0, FONT)
    # hold markers
    placed: dict[str, int] = {}
    for h in content.holds:
        for a in h.affects:
            n = sl.nodes.get(a)
            if n is None or n.kind not in ("equipment", "boundary"):
                continue
            k = placed.get(a, 0)
            placed[a] = k + 1
            rec.owner = Owner("hold", f"{h.ur_id}@{a}", "label")
            _hold_marker(rec, n.x + n.w / 2 + 4 + k * 26, n.y - n.h / 2 - 8, h.num)


def _diamond(rec: Recorder, x: float, y: float, lab: str, col: Any) -> None:
    """PFD stream number: a diamond on the line (layout coordinates, y down)."""
    r = 8.5 if len(lab) < 3 else 10.5
    rec.saveState()
    rec.setStrokeColor(col)
    rec.setFillColor(colors.white)
    rec.setLineWidth(1.0)
    poly(rec, [(x - r, y), (x, y - r), (x + r, y), (x, y + r)], close=True, fill=True)
    rec.restoreState()
    txt(rec, x, y + 2.6, lab, 7.0, FONT_B, "c", INK)


def _stream_table(rec: Recorder, rows: list[list[str]], x0: float, y0: float, x1: float) -> float:
    """Stream table across the bottom of the drawing field (sheet coordinates, y up); returns its top."""
    rec.owner = Owner("sheet", "stream_table", "border")
    head_w, rh, fs = 64.0, 14.0, 5.4
    n = len(rows[0]) - 1
    per_band = max(1, int((x1 - x0 - head_w) // 58))
    bands = [(i, min(n, i + per_band)) for i in range(0, n, per_band)]
    cw = (x1 - x0 - head_w) / per_band
    y = y0
    for a, b in reversed(bands):
        h = rh * len(rows)
        rec.setStrokeColor(INK)
        rec.setLineWidth(0.5)
        rec.rect(x0, y, head_w + cw * (b - a), h)
        for r, row in enumerate(rows):
            yy = y + h - rh * (r + 1)
            rec.line(x0, yy, x0 + head_w + cw * (b - a), yy)
            rec.setFillColor(INK)
            rec.setFont(FONT_B, fs)
            rec.drawString(x0 + 3, yy + 3.2, row[0])
            for k in range(a, b):
                cx = x0 + head_w + cw * (k - a)
                if r == 0:
                    rec.line(cx, y, cx, y + h)
                val = row[k + 1]
                rec.setFont(FONT_B if r == 0 else FONT, fs)
                cell = wrap(val, cw - 4, fs, FONT, 2)
                for j, ln in enumerate(cell):
                    rec.drawCentredString(cx + cw / 2, yy + 3.2 + (len(cell) - 1 - j) * (fs + 0.8) - (len(cell) - 1) * 2.6, ln)
        y += h + 6
    rec.setFont(FONT_B, 8)
    rec.drawString(x0, y + 2, "STREAM TABLE – values as stated in the specification (* carried over from equipment data); blank = not given")
    return y + 12


def _hold_marker(rec: Recorder, x: float, y: float, num: int) -> None:
    """Hexagon with 'H n' (layout coordinates, y down)."""
    rec.saveState()
    rec.setStrokeColor(RED)
    rec.setFillColor(colors.white)
    rec.setLineWidth(1.1)
    w, h = 12.0, 7.5
    poly(rec, [(x - w, y), (x - w / 2, y - h), (x + w / 2, y - h), (x + w, y), (x + w / 2, y + h), (x - w / 2, y + h)], close=True, fill=True)
    rec.restoreState()
    txt(rec, x, y + 2.6, f"H{num}", 7.0, FONT_B, "c", RED)


def _on_segs(r: tuple[float, float, float, float], segs: list) -> bool:
    return any(min(a[0], b[0]) < r[2] and r[0] < max(a[0], b[0]) + 0.01 and min(a[1], b[1]) < r[3] and r[1] < max(a[1], b[1]) + 0.01
               for a, b in segs)


def _label_spot(e: MEdge, sl: Any, a: tuple[float, float], b: tuple[float, float], half_w: float, above: float, below: float,
                path: list[tuple[float, float]] | None = None) -> tuple[float, float]:
    """Point on segment a-b where a label of the given extent touches no other pipe and no valve.

    When a-b has no such point, the other segments of ``path`` (longest first) are tried; else the middle of a-b.
    """
    others = [(p, q) for o in sl.edges if o is not e for p, q in zip(o.path, o.path[1:])]
    syms = [(x - 10, y - 10, x + 10, y + 10) for o in sl.edges for _, x, y, _ in o.symbols]
    syms += [(p.x - 12, p.y - 12, p.x + 12, p.y + 12) for p in sl.instruments]
    segs = [(a, b)] + sorted(zip(path or [], (path or [])[1:]), key=lambda pq: -(abs(pq[1][0] - pq[0][0]) + abs(pq[1][1] - pq[0][1])))
    for p0, p1 in segs:
        if abs(p1[0] - p0[0]) + abs(p1[1] - p0[1]) < 2 * half_w + 4:
            continue
        for f in (0.5, 0.35, 0.65, 0.2, 0.8, 0.1, 0.9):
            x, y = p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
            r = (x - half_w, y - above, x + half_w, y + below)
            if not _on_segs(r, others) and not any(r[0] < q[2] and q[0] < r[2] and r[1] < q[3] and q[1] < r[3] for q in syms):
                return x, y
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def _edge(rec: Recorder, painter: SheetPainter, e: MEdge, st: Style, content: SheetContent, lines: dict[str, Any], sl: Any) -> None:
    col = st.proposed if e.proposed else st.color(e.service)
    rec.saveState()
    rec.setStrokeColor(col)
    rec.setFillColor(col)
    rec.setLineWidth(2.4 if e.header else 1.5)
    if e.proposed:
        rec.setDash(5, 2.5)
    poly(rec, e.path)
    rec.setDash()
    best, bi = 0.0, 0
    for i in range(len(e.path) - 1):
        l_ = math.dist(e.path[i], e.path[i + 1])
        if l_ > best:
            best, bi = l_, i
    owner = rec.owner
    rec.owner = Owner("line", e.id, "label")
    if best > 46 and not e.stub:
        (xa, ya), (xb, yb) = e.path[bi], e.path[bi + 1]
        f = 0.72 if e.chain else 0.5
        arrow(rec, xa + (xb - xa) * f, ya + (yb - ya) * f, xb - xa, yb - ya, 4.4)
    rec.restoreState()
    if content.kind == "pfd" and len(e.line_ids or []) > 1:  # one stream per line piece between control valves
        from .proteus_graphics import _split

        pieces = _split(list(e.path), [(x, y) for _, x, y, _ in e.symbols])
        for lid, piece in zip(e.line_ids, pieces):
            lab_ = content.line_labels.get(lid, "")
            if lab_ and lab_ not in content._labelled and len(piece) >= 2:
                segs = sorted(((abs(b[0] - a[0]) + abs(b[1] - a[1]), a, b) for a, b in zip(piece, piece[1:])), key=lambda z: -z[0])
                _, a, b = segs[0]
                content._labelled.add(lab_)
                rec.owner = Owner("line", e.id, "label")
                r_ = 8.5 if len(lab_) < 3 else 10.5
                _diamond(rec, *_label_spot(e, sl, a, b, r_, r_, r_, piece), lab_, col)
        rec.owner = owner
        return
    # line number on the longest horizontal run that is free of valves
    lab = ""
    ids = e.line_ids or []
    if ids:
        lab = content.line_labels.get(ids[-1] if not e.chain else ids[0], "")
    if not lab and e.id.endswith("~x"):
        base = e.id[:-2]
        ln = next((l_ for l_ in lines if l_ == base or l_.startswith(base)), None)
        lab = content.line_labels.get(ln, "") if ln else ""
    if lab and not e.stub:
        runs = []
        min_run = 90 if content.kind != "pfd" else 28   # every PFD stream gets its number, even on short runs
        for i in range(len(e.path) - 1):
            (xa, ya), (xb, yb) = e.path[i], e.path[i + 1]
            if abs(ya - yb) < 0.01 and abs(xb - xa) > min_run:
                lo, hi = sorted((xa, xb))
                if not any(lo - 12 < sx < hi + 12 and abs(sy - ya) < 1 for _, sx, sy, _ in e.symbols):
                    runs.append((hi - lo, (lo, ya), (hi, ya)))
        if not runs and content.kind == "pfd":  # vertical run, then any segment, as fallbacks
            for i in range(len(e.path) - 1):
                (xa, ya), (xb, yb) = e.path[i], e.path[i + 1]
                if abs(xa - xb) < 0.01 and abs(yb - ya) > min_run:
                    lo, hi = sorted((ya, yb))
                    if not any(lo - 12 < sy < hi + 12 and abs(sx - xa) < 1 for _, sx, sy, _ in e.symbols):
                        runs.append((hi - lo, (xa, lo), (xa, hi)))
            if not runs:
                seg = max(zip(e.path, e.path[1:]), key=lambda ab: abs(ab[1][0] - ab[0][0]) + abs(ab[1][1] - ab[0][1]))
                runs.append((0.0, seg[0], seg[1]))
        if runs and content.kind == "pfd":
            if lab not in content._labelled:  # one diamond per stream
                content._labelled.add(lab)
                _, a, b = max(runs)
                rec.owner = Owner("line", e.id, "label")
                r_ = 8.5 if len(lab) < 3 else 10.5
                _diamond(rec, *_label_spot(e, sl, a, b, r_, r_, r_, e.path), lab, col)
        elif runs:
            _, a, b = max(runs)
            w_ = stringWidth(lab, FONT, 6.4) / 2 + 1
            xm, ym = _label_spot(e, sl, a, b, w_, 11, -1)
            txt(rec, xm, ym - 4.5, lab, 6.4, FONT, "c", col)
    rec.owner = owner


# ------------------------------------------------------------------------------- right panel
def _panel(rec: Recorder, topo: Topology, st: Style, content: SheetContent, os_: OneSheet) -> None:
    W, H = A0
    px0 = W - M_O - GRID_W - PANEL_W
    px1 = W - M_O - GRID_W
    top = H - M_O - GRID_W
    bottom = M_O + GRID_W
    rec.owner = Owner("sheet", "panel", "border")
    y = top - 8
    _legend.pfd = content.kind == "pfd"  # type: ignore[attr-defined]
    y = _legend(rec, st, px0, px1, y, os_)
    y = _notes(rec, "GENERAL NOTES", content.notes, px0, px1, y, numbered=True)
    if content.equipment_summary:
        y = _equipment_summary(rec, content.equipment_summary, px0, px1, y)
    y = _holds(rec, content.holds, px0, px1, y)
    y = _notes(rec, "DATA TO BE COMPLETED ON DATASHEETS (NOT HOLDS)", content.tbd, px0, px1, y, numbered=False)
    _title_block(rec, topo, content, px0, px1, bottom)


def _equipment_summary(rec: Recorder, rows: list[tuple[str, str, str]], x0: float, x1: float, y: float) -> float:
    y = _heading(rec, "EQUIPMENT SUMMARY", x0, x1, y)
    for tag, name, data in rows:
        rec.setFillColor(INK)
        rec.setFont(FONT_B, 6.8)
        rec.drawString(x0 + 8, y, tag[:22])
        rec.setFont(FONT, 6.6)
        lines = wrap(name + (f" – {data}" if data else ""), x1 - x0 - 100, 6.6, FONT, 2)
        for j, ln in enumerate(lines):
            rec.drawString(x0 + 92, y - j * 8.0, ln)
        y -= len(lines) * 8.0 + 2
    return y - 6


def _heading(rec: Recorder, s: str, x0: float, x1: float, y: float) -> float:
    rec.setFillColor(INK)
    rec.setFont(FONT_B, 10)
    rec.drawString(x0 + 8, y - 12, s)
    rec.setStrokeColor(INK)
    rec.setLineWidth(0.6)
    rec.line(x0, y - 17, x1, y - 17)
    return y - 28


def _legend(rec: Recorder, st: Style, x0: float, x1: float, y: float, os_: OneSheet) -> float:
    y = _heading(rec, "LEGEND", x0, x1, y)
    services: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for e in os_.layout.edges:
        lb = st.label(e.service)
        if e.service and lb not in seen:
            seen.add(lb)
            services.append((lb, st.color(e.service)))
    services.sort()
    colw = (x1 - x0 - 16) / 2
    for i, (lb, col) in enumerate(services):
        cx = x0 + 8 + (i % 2) * colw
        cy = y - (i // 2) * 13
        rec.setStrokeColor(col)
        rec.setLineWidth(2.0)
        rec.line(cx, cy + 3, cx + 26, cy + 3)
        rec.setFillColor(INK)
        rec.setFont(FONT, 7.6)
        rec.drawString(cx + 32, cy, lb)
    y -= ((len(services) + 1) // 2) * 13 + 8
    # symbol samples (drawn in a local y-down space like the drawing itself)
    has_cv = any(sym.function == "control" for e in os_.layout.edges for sym, *_ in e.symbols)
    samples = ([("control", "Control valve")] if has_cv else []) + [
        ("pump", "Pump (parallel units drawn once)"),
        ("diamond", "Stream number – see stream table"),
        ("future", "Future equipment (LifeCyclePhase = Future)"),
        ("hold", "HOLD – decision needed, see hold list"),
    ] if getattr(_legend, "pfd", False) else [
        ("valve", "Isolation valve, technology to be selected (generic)"),
        ("check", "Check valve"),
        ("globe", "Globe valve (by-pass)"),
        ("control", "Control valve with actuator"),
        ("bubble", "Instrument – ISA 5.1 function / loop number"),
        ("pump", "Centrifugal pump"),
        ("proposed", "Proposed addition (rule-based, pending review)"),
        ("future", "Future equipment (LifeCyclePhase = Future)"),
        ("hold", "HOLD – decision needed, see hold list"),
        ("signal", "Instrument signal"),
    ]
    from .schema import Component, Provenance

    def comp(kind: str, model: str, fn: str, pending: bool = False) -> Component:
        prov = Provenance(origin="generated", rule="legend", status="pending_review") if pending else Provenance(origin="source", document="legend", page=1, section="legend", basis="explicit")
        return Component(id="legend", kind=kind, model_class=model, function=fn, provenance=prov)

    for i, (k, lb) in enumerate(samples):
        cx = x0 + 8 + (i % 2) * colw
        cy = y - (i // 2) * 24
        rec.saveState()
        rec.transform(1, 0, 0, -1, cx + 14, cy + 3)
        if k == "valve":
            draw_valve(rec, comp("valve", "CustomOperatedValve", "isolation"), 0, 0, "H", st)
        elif k == "check":
            draw_valve(rec, comp("check_valve", "CheckValve", "check"), 0, 0, "H", st)
        elif k == "globe":
            draw_valve(rec, comp("valve", "GlobeValve", "bypass"), 0, 0, "H", st)
        elif k == "control":
            draw_valve(rec, comp("valve", "CustomOperatedValve", "control"), 0, 6, "H", st)
        elif k == "proposed":
            draw_valve(rec, comp("valve", "CustomOperatedValve", "isolation", True), 0, 0, "H", st)
        elif k == "bubble":
            draw_bubble(rec, 0, 0, "PT", "101", False, st)
        elif k == "pump":
            rec.setStrokeColor(INK)
            rec.setFillColor(colors.white)
            rec.circle(0, 0, 9, stroke=1, fill=1)
            poly(rec, [(-5, -5.6), (7.4, 0), (-5, 5.6)], close=True)
        elif k == "future":
            rec.setStrokeColor(GREY)
            rec.setDash(4, 3)
            rec.rect(-12, -7, 24, 14)
        elif k == "hold":
            _hold_marker(rec, 0, 0, 1)
        elif k == "diamond":
            _diamond(rec, 0, 0, "7", INK)
        elif k == "signal":
            rec.setStrokeColor(colors.HexColor("#2a5db0"))
            rec.setDash(3, 2)
            rec.line(-13, 0, 13, 0)
        rec.restoreState()
        rec.setFillColor(INK)
        rec.setFont(FONT, 7.4)
        for j, ln in enumerate(wrap(lb, colw - 44, 7.4, FONT, 2)):
            rec.drawString(cx + 36, cy - j * 8.6, ln)
    y -= ((len(samples) + 1) // 2) * 24 + 4
    return y


def _notes(rec: Recorder, title: str, notes: list[str], x0: float, x1: float, y: float, numbered: bool) -> float:
    if not notes:
        return y
    y = _heading(rec, title, x0, x1, y)
    rec.setFillColor(INK)
    for i, n in enumerate(notes, 1):
        prefix = f"{i}." if numbered else "–"
        lines = wrap(n, x1 - x0 - 36, 7.4, FONT, 6)
        rec.setFont(FONT_B if numbered else FONT, 7.4)
        rec.drawString(x0 + 8, y, prefix)
        rec.setFont(FONT, 7.4)
        for j, ln in enumerate(lines):
            rec.drawString(x0 + 24, y - j * 9.0, ln)
        y -= len(lines) * 9.0 + 3.5
    return y - 6


def _holds(rec: Recorder, holds: list[Hold], x0: float, x1: float, y: float) -> float:
    if not holds:
        return y
    y = _heading(rec, "HOLDS – DECISIONS REQUIRED BEFORE ISSUE", x0, x1, y)
    for h in holds:
        rec.saveState()
        rec.transform(1, 0, 0, -1, x0 + 20, y + 3)
        _hold_marker(rec, 0, 0, h.num)
        rec.restoreState()
        rec.setFillColor(INK)
        rec.setFont(FONT_B, 7.4)
        rec.drawString(x0 + 40, y, h.title)
        rec.setFont(FONT, 7.2)
        lines = wrap(h.text, x1 - x0 - 50, 7.2, FONT, 5)
        for j, ln in enumerate(lines):
            rec.drawString(x0 + 40, y - 9 - j * 8.6, ln)
        y -= 9 + len(lines) * 8.6 + 5
    return y - 6


def _title_block(rec: Recorder, topo: Topology, content: SheetContent, x0: float, x1: float, bottom: float) -> None:
    md = topo.metadata
    rec.owner = Owner("sheet", "title_block", "border")
    rec.setStrokeColor(INK)
    rec.setLineWidth(1.2)
    h = TB_H
    rec.rect(x0, bottom, x1 - x0, h)
    rec.setLineWidth(0.6)
    # revision block above the title block
    rev_rows = content.revision
    rh = 12.0
    ry = bottom + h
    rec.rect(x0, ry, x1 - x0, rh * (len(rev_rows) + 1))
    cols = [(x0, "REV"), (x0 + 34, "DATE"), (x0 + 100, "DESCRIPTION")]
    for k, (cx, lb) in enumerate(cols):
        if k:
            rec.line(cx, ry, cx, ry + rh * (len(rev_rows) + 1))
        rec.setFont(FONT_B, 6.8)
        rec.setFillColor(INK)
        rec.drawString(cx + 4, ry + 3.5, lb)
    for i, (rv, d, desc) in enumerate(rev_rows, 1):
        yy = ry + rh * i
        rec.line(x0, yy, x1, yy)
        rec.setFont(FONT, 6.8)
        rec.drawString(x0 + 4, yy + 3.5, rv)
        rec.drawString(x0 + 38, yy + 3.5, d)
        rec.drawString(x0 + 104, yy + 3.5, wrap(desc, x1 - x0 - 110, 6.8, FONT, 1)[0])
    # title block rows
    rows = [
        ("PROJECT", md.project, 11.0),
        ("TITLE", md.title, 12.0),
        ("CONTENT", "Process flow diagram – complete scope on one sheet" if content.kind == "pfd"
         else "Piping & instrumentation diagram – complete scope on one sheet", 8.5),
    ]
    yy = bottom + h
    for lb, val, sz in rows:
        rh_ = 15 + sz * 2.1
        yy -= rh_
        rec.line(x0, yy, x1, yy)
        rec.setFont(FONT, 6.4)
        rec.setFillColor(GREY)
        rec.drawString(x0 + 5, yy + rh_ - 9, lb)
        rec.setFillColor(INK)
        rec.setFont(FONT_B, sz)
        for j, ln in enumerate(wrap(val, x1 - x0 - 12, sz, FONT_B, 2)):
            rec.drawString(x0 + 5, yy + rh_ - 11 - sz - j * (sz + 2), ln)
    cells = [
        ("DRAWING No.", md.drawing_id), ("REV.", md.revision.split(" ")[0]), ("SHEET", "1 of 1"),
        ("STATUS", "DRAFT – FOR REVIEW"), ("SCALE", "NTS"), ("DATE", content.revision[-1][1] if content.revision else ""),
        ("STANDARDS", "ISO 10628-2 symbols · ISA 5.1 tags · DEXPI 1.3 / Proteus XML"),
        ("SOURCE", f"{md.source_documents[0]['file']}" if md.source_documents else ""),
    ]
    cw = (x1 - x0) / 3
    ch = 26.0
    for i, (lb, val) in enumerate(cells[:6]):
        cx = x0 + (i % 3) * cw
        cy = yy - ch * (i // 3 + 1)
        rec.rect(cx, cy, cw, ch)
        rec.setFont(FONT, 6.2)
        rec.setFillColor(GREY)
        rec.drawString(cx + 4, cy + ch - 8, lb)
        rec.setFillColor(INK)
        rec.setFont(FONT_B, 8.6 if lb != "STATUS" else 7.6)
        rec.drawString(cx + 4, cy + 5, val)
    cy = yy - 2 * ch
    for lb, val in cells[6:]:
        cy -= 13
        rec.setFont(FONT, 6.2)
        rec.setFillColor(GREY)
        rec.drawString(x0 + 4, cy + 3, lb)
        rec.setFillColor(INK)
        rec.setFont(FONT, 6.8)
        rec.drawString(x0 + 56, cy + 3, wrap(val, x1 - x0 - 62, 6.8, FONT, 1)[0])
    rec.setFont(FONT_I, 6.2)
    rec.setFillColor(GREY)
    rec.drawString(x0 + 4, bottom + 4, "Generated by pid_workflow from the specification – not for construction")
