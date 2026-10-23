"""Review PDF: cover, overview, one drawing sheet per area, and the review tables.

Drawing symbols are simplified ISO 10628 / ISA 5.1 style shapes drawn directly with ReportLab so
the output stays vector and searchable.  Everything is positioned by ``layout.py``.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any

import yaml
from pypdf import PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .layout import DrawingLayout, MEdge, MNode, SheetLayout
from .catalog import valve_symbol
from .schema import Component, Topology, is_pending

FONT = "FreeSans"
FONT_B = "FreeSans-Bold"
FONT_I = "FreeSans-Italic"
_FONTS_READY = False

PAGE = landscape(A3)
MARGIN = 26.0
TITLE_H = 70.0


def _fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    base = Path("/usr/share/fonts/truetype/freefont")
    for name, f in ((FONT, "FreeSans.ttf"), (FONT_B, "FreeSansBold.ttf"), (FONT_I, "FreeSansOblique.ttf")):
        p = base / f
        if not p.exists():  # fall back to DejaVu
            p = Path("/usr/share/fonts/truetype/dejavu") / {"FreeSans.ttf": "DejaVuSans.ttf", "FreeSansBold.ttf": "DejaVuSans-Bold.ttf", "FreeSansOblique.ttf": "DejaVuSans-Oblique.ttf"}[f]
        pdfmetrics.registerFont(TTFont(name, str(p)))
    _FONTS_READY = True


class Style:
    """Line colours: project service prefixes first, then multilingual keywords, then a fixed palette (deterministic)."""

    def __init__(self, path: str | Path):
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        self.rules = d["service_colors"]
        self.keywords = d.get("keyword_colors", [])
        self.palette = [colors.HexColor(c) for c in d.get("palette", ["#1f5fbf", "#0a8f8f", "#c0262d", "#7d3c98", "#2e8b57", "#d4561a"])]
        self.default = colors.HexColor(d["default_color"])
        self.proposed = colors.HexColor(d["proposed_color"])
        self.future_dash = d.get("future_dash", [4, 3])
        self._auto: dict[str, Any] = {}
        self._variant: dict[str, int] = {}

    def _match(self, service: str) -> tuple[Any, str] | None:
        for r in self.rules:
            if service.startswith(r["prefix"]):
                return colors.HexColor(r["color"]), r["label"]
        low = service.lower()
        for r in self.keywords:
            if any(k in low for k in r["any"]):
                base = colors.HexColor(r["color"])
                k = self._variant.get(service, 0)
                if k:  # several services share a keyword (steam 8/4/1 bar): lighter shades, deterministic
                    f = min(0.22 * k, 0.6)
                    base = colors.Color(base.red + (1 - base.red) * f, base.green + (1 - base.green) * f, base.blue + (1 - base.blue) * f)
                return base, service
        return None

    def prime(self, services: list[str]) -> None:
        """Give services that share a keyword colour distinct shades, in sorted order (same result on every drawing)."""
        groups: dict[int, list[str]] = {}
        for sv in sorted(set(services)):
            if any(sv.startswith(r["prefix"]) for r in self.rules):
                continue
            low = sv.lower()
            for i, r in enumerate(self.keywords):
                if any(k in low for k in r["any"]):
                    if i > 0:  # the first keyword group is drains/vents: one grey
                        groups.setdefault(i, []).append(sv)
                    break
        self._variant = {sv: k for g in groups.values() for k, sv in enumerate(g)}

    def color(self, service: str) -> Any:
        m = self._match(service)
        if m is not None:
            return m[0]
        if not service:
            return self.default
        if service not in self._auto:
            used = {c.hexval() for c in self._auto.values()}
            free = [c for c in self.palette if c.hexval() not in used] or self.palette
            import zlib

            self._auto[service] = free[zlib.crc32(service.encode()) % len(free)]
        return self._auto[service]

    def label(self, service: str) -> str:
        m = self._match(service)
        return m[1] if m is not None else service


INK = colors.HexColor("#1c1c1c")
GREY = colors.HexColor("#8a8a8a")
LIGHT = colors.HexColor("#f4f1ea")
AMBER_FILL = colors.HexColor("#fff0d9")
RED = colors.HexColor("#b3261e")


# -------------------------------------------------------------------------- primitives
def txt(c: canvas.Canvas, x: float, y: float, s: str, size: float = 7, font: str = FONT, align: str = "c", color: Any = INK) -> None:
    """Draw text at layout coordinates (the canvas is y-flipped, so flip locally)."""
    c.saveState()
    c.translate(x, y)
    c.scale(1, -1)
    c.setFillColor(color)
    c.setFont(font, size)
    if align == "c":
        c.drawCentredString(0, 0, s)
    elif align == "r":
        c.drawRightString(0, 0, s)
    else:
        c.drawString(0, 0, s)
    c.restoreState()


def wrap(s: str, width: float, size: float, font: str = FONT, max_lines: int = 3) -> list[str]:
    words = s.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;") + "…"
    return lines


def poly(c: canvas.Canvas, pts: list[tuple[float, float]], close: bool = False, fill: bool = False, stroke: bool = True) -> None:
    p = c.beginPath()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    if close:
        p.close()
    c.drawPath(p, fill=1 if fill else 0, stroke=1 if stroke else 0)


def arrow(c: canvas.Canvas, x: float, y: float, dx: float, dy: float, size: float = 4.2) -> None:
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    px, py = -uy, ux
    c.saveState()
    c.setLineWidth(0.3)
    poly(c, [(x + ux * size, y + uy * size), (x - ux * size * 0.6 + px * size * 0.55, y - uy * size * 0.6 + py * size * 0.55),
             (x - ux * size * 0.6 - px * size * 0.55, y - uy * size * 0.6 - py * size * 0.55)], close=True, fill=True)
    c.restoreState()


# ---------------------------------------------------------------------------- equipment
def draw_equipment(c: canvas.Canvas, n: MNode, st: Style) -> None:
    e = n.obj
    x, y, w, h = n.x, n.y, n.w, n.h
    future = getattr(e, "lifecycle", "") == "future"
    c.saveState()
    c.setStrokeColor(INK)
    c.setFillColor(colors.white)
    c.setLineWidth(1.3)
    if future:
        c.setDash(*st.future_dash)
        c.setStrokeColor(GREY)
    sym = n.symbol
    if sym == "pump":
        r = w / 2
        c.circle(x, y, r, stroke=1, fill=1)
        poly(c, [(x - r * 0.55, y - r * 0.62), (x + r * 0.82, y), (x - r * 0.55, y + r * 0.62)], close=True, fill=False)
    elif sym in ("phx", "hx"):
        c.rect(x - w / 2, y - h / 2, w, h, stroke=1, fill=1)
        c.setLineWidth(0.9)
        if sym == "phx":
            k = 7
            for i in range(1, k):
                xx = x - w / 2 + w * i / k
                c.line(xx, y - h / 2, xx, y + h / 2)
            poly(c, [(x - w / 2, y + h / 2), (x + w / 2, y - h / 2)])
        else:
            pts = []
            for i in range(8):
                pts.append((x - w / 2 + 5 + (w - 10) * (i % 2), y - h / 2 + 8 + (h - 16) * i / 7))
            poly(c, [(x - w / 2 + 5, pts[0][1])] + pts + [(x + w / 2 - 5, pts[-1][1])])
    elif sym == "tank":
        c.roundRect(x - w / 2, y - h / 2, w, h, 9, stroke=1, fill=1)
        c.setLineWidth(0.8)
        c.setDash(3, 2)
        c.line(x - w / 2 + 3, y - h * 0.12, x + w / 2 - 3, y - h * 0.12)
        c.setDash()
    elif sym == "vessel":
        c.roundRect(x - w / 2, y - h / 2, w, h, w / 2, stroke=1, fill=1)
        c.setLineWidth(0.8)
        c.line(x - w / 2 + 2, y - h * 0.18, x + w / 2 - 2, y - h * 0.18)
    elif sym == "compressor":
        poly(c, [(x - w / 2, y - h / 2), (x + w / 2, y - h * 0.2), (x + w / 2, y + h * 0.2), (x - w / 2, y + h / 2)], close=True, fill=True)
    elif sym == "boiler":
        c.rect(x - w / 2, y - h / 2, w, h, stroke=1, fill=1)
        c.setLineWidth(0.9)
        poly(c, [(x - w / 2 + 8, y + h * 0.25), (x - w / 4, y + h * 0.1), (x, y + h * 0.25), (x + w / 4, y + h * 0.1), (x + w / 2 - 8, y + h * 0.25)])
        txt(c, x, y - h * 0.12, "B", 12, FONT_B)
    elif sym == "heatpump":
        c.rect(x - w / 2, y - h / 2, w, h, stroke=1, fill=1)
        c.setLineWidth(0.8)
        c.line(x - w / 2, y, x + w / 2, y)
        txt(c, x - w / 2 + 6, y - h / 2 + 11, "EVAPORATOR", 6, FONT, "l", GREY)
        txt(c, x - w / 2 + 6, y + h / 2 - 5, "CONDENSER", 6, FONT, "l", GREY)
        c.setLineWidth(1.1)
        c.circle(x, y, 13, stroke=1, fill=1)
        poly(c, [(x - 6, y - 7), (x + 8, y), (x - 6, y + 7)], close=True)
    elif sym == "fan":
        r = min(w, h) / 2
        c.circle(x, y, r, stroke=1, fill=1)
        c.setLineWidth(0.9)
        for a in (0, 120, 240):  # three blades
            ra = math.radians(a)
            poly(c, [(x, y), (x + r * 0.85 * math.cos(ra), y + r * 0.85 * math.sin(ra)), (x + r * 0.5 * math.cos(ra + 0.6), y + r * 0.5 * math.sin(ra + 0.6))], close=True)
    elif sym == "turbine":
        poly(c, [(x - w / 2, y - h * 0.2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h * 0.2)], close=True, fill=True)
    elif sym == "motor":
        c.circle(x, y, min(w, h) / 2, stroke=1, fill=1)
        txt(c, x, y + 3.5, "M", 10, FONT_B)
    elif sym == "air_cooler":
        c.rect(x - w / 2, y - h / 2 + 12, w, h - 12, stroke=1, fill=1)
        c.setLineWidth(0.8)
        for k in range(6):
            xx = x - w / 2 + 6 + (w - 12) * k / 5
            c.line(xx, y - h / 2 + 14, xx, y + h / 2 - 2)
        for fx in (x - w / 4, x + w / 4):
            c.circle(fx, y - h / 2 + 6, 6, stroke=1, fill=1)
    elif sym == "cooling_tower":
        poly(c, [(x - w / 2, y + h / 2), (x - w * 0.32, y - h / 2 + 14), (x + w * 0.32, y - h / 2 + 14), (x + w / 2, y + h / 2)], close=True, fill=True)
        c.setLineWidth(0.8)
        c.circle(x, y - h / 2 + 7, 7, stroke=1, fill=1)
        c.setDash(2, 2)
        for k in range(3):
            yy = y + h * 0.05 + k * 9
            c.line(x - w * 0.32, yy, x + w * 0.32, yy)
        c.setDash()
    elif sym == "column":
        c.roundRect(x - w / 2, y - h / 2, w, h, w / 2, stroke=1, fill=1)
        c.setLineWidth(0.7)
        for k in range(1, 7):
            yy = y - h / 2 + h * k / 7
            c.line(x - w / 2 + 3, yy, x + w / 2 - 3, yy)
    elif sym == "filter":
        c.rect(x - w / 2, y - h / 2, w, h, stroke=1, fill=1)
        c.setLineWidth(0.8)
        c.setDash(3, 2)
        c.line(x - w / 2, y + h / 2, x + w / 2, y - h / 2)
        c.setDash()
    elif sym == "heater":
        c.rect(x - w / 2, y - h / 2, w, h, stroke=1, fill=1)
        c.setLineWidth(0.9)
        poly(c, [(x - w / 2 + 8, y + h * 0.3), (x - w / 4, y + h * 0.1), (x, y + h * 0.3), (x + w / 4, y + h * 0.1), (x + w / 2 - 8, y + h * 0.3)])
        poly(c, [(x - 8, y + h / 2 - 4), (x, y + h / 2 - 16), (x + 8, y + h / 2 - 4)])
    elif sym == "mixer":
        c.roundRect(x - w / 2, y - h / 2, w, h, 12, stroke=1, fill=1)
        c.setLineWidth(0.9)
        c.line(x, y - h / 2 - 10, x, y + h * 0.25)
        poly(c, [(x - 12, y + h * 0.25 - 5), (x + 12, y + h * 0.25 + 5)])
        poly(c, [(x - 12, y + h * 0.25 + 5), (x + 12, y + h * 0.25 - 5)])
    elif sym == "box":
        c.roundRect(x - w / 2, y - h / 2, w, h, 3, stroke=1, fill=1)
    else:
        c.rect(x - w / 2, y - h / 2, w, h, stroke=1, fill=1)
    c.restoreState()
    # labels
    tag, name = n.label, n.sublabel
    lc = GREY if future else INK
    if sym == "box":
        lines = wrap(name, w - 8, 6.6, FONT, 3)
        yy = y - (len(lines) - 1) * 3.7 + 2
        for i, ln in enumerate(lines):
            txt(c, x, yy + i * 7.4, ln, 6.6, FONT, "c", lc)
        if tag:
            txt(c, x, y + h / 2 + 8, tag, 7.5, FONT_B, "c", lc)
        return
    lifecycle = getattr(e, "lifecycle", "")
    suffix = {"existing": " [existing]", "modified": " [modified]", "future": " [future]"}.get(lifecycle, "")
    if suffix.strip(" []") in name.lower():
        suffix = ""
    if sym in ("tank", "vessel"):  # label inside the vessel, below the level line
        yy = y - h * 0.12 + 13
        if tag:
            txt(c, x, yy, tag, 8.6, FONT_B, "c", lc)
            yy += 10
        for ln in wrap(name + suffix, w - 8, 6.6, FONT, 4):
            txt(c, x, yy, ln, 6.6, FONT, "c", lc)
            yy += 7.8
        return
    yy = y + h / 2 + 9
    if sym == "heatpump":
        yy = y + h / 2 + 10
    if tag:
        txt(c, x, yy, tag, 8.8, FONT_B, "c", lc)
        yy += 9
    for ln in wrap(name + suffix, max(w + 34, 96), 6.9, FONT, 2):
        txt(c, x, yy, ln, 6.9, FONT, "c", lc)
        yy += 7.8


def draw_boundary(c: canvas.Canvas, n: MNode, st: Style, svc_color: Any) -> None:
    x, y, w, h = n.x, n.y, n.w, n.h
    c.saveState()
    c.setStrokeColor(INK)
    c.setFillColor(colors.white if n.kind == "boundary" else colors.HexColor("#eef3ff"))
    c.setLineWidth(1.0)
    inflow = n.symbol in ("flag_in", "offpage_in")
    # arrow-shaped flag: the point faces the pipe side
    if inflow:  # flow leaves to the right
        pts = [(x - w / 2, y - h / 2), (x + w / 2 - 10, y - h / 2), (x + w / 2, y), (x + w / 2 - 10, y + h / 2), (x - w / 2, y + h / 2)]
    else:
        pts = [(x + w / 2, y - h / 2), (x - w / 2 + 10, y - h / 2), (x - w / 2, y), (x - w / 2 + 10, y + h / 2), (x + w / 2, y + h / 2)]
    poly(c, pts, close=True, fill=True)
    c.restoreState()
    inner = w - 26
    cx = x + (-4 if inflow else 4)
    if n.kind == "offpage":
        txt(c, cx, y - 7.5, n.label, 7.4, FONT_B, "c", INK)
        for i, ln in enumerate(wrap(n.sublabel.split(" · ")[0], inner, 6.2, FONT, 2)):
            txt(c, cx, y + 1.5 + i * 7.2, ln, 6.2, FONT, "c", GREY)
    else:
        sub = wrap(n.sublabel, inner, 6.8, FONT, 2)
        for i, ln in enumerate(sub):
            txt(c, cx, y - (len(sub) - 1) * 3.7 + 2.6 + i * 7.6, ln, 6.8, FONT, "c", INK)


# --------------------------------------------------------------------------- valves
def draw_valve(c: canvas.Canvas, comp: Component, x: float, y: float, ori: str, st: Style, flow_dx: float = 1.0) -> None:
    proposed = is_pending(comp.provenance)
    col = st.proposed if proposed else INK
    c.saveState()
    c.translate(x, y)
    if comp.kind == "relief":
        ori, flow_dx = "H", 1.0  # safety valves are always drawn upright: inlet from below, spring on top
    if ori == "V":
        c.rotate(90)
    if flow_dx < 0:
        c.scale(-1, 1)
    c.setStrokeColor(col)
    c.setLineWidth(1.1)
    fill = AMBER_FILL if proposed else colors.white
    c.setFillColor(fill)
    wv, hv = 9.0, 6.2
    fn = comp.function
    sym = valve_symbol(comp.model_class, fn) if comp.kind != "strainer" else "strainer"
    if comp.kind == "check_valve" or sym == "check":
        # triangle + bar, flow to the right
        poly(c, [(-wv * 0.7, -hv), (wv * 0.7, 0), (-wv * 0.7, hv)], close=True, fill=True)
        c.line(wv * 0.7, -hv, wv * 0.7, hv)
    elif sym == "strainer":
        c.line(-wv, 0, wv, 0)
        poly(c, [(-wv * 0.5, 0), (wv * 0.3, hv * 1.4), (wv * 0.9, hv * 0.6), (0, 0)], close=True, fill=True)
        c.setDash(1.5, 1.2)
        c.line(-wv * 0.1, hv * 0.5, wv * 0.55, hv * 1.0)
        c.setDash()
    elif sym == "relief" or comp.kind == "relief":
        # angle safety valve: inlet from below, outlet to the side, spring on top
        poly(c, [(-hv, wv), (0, 0), (hv, wv)], close=True, fill=True)       # inlet from below
        poly(c, [(0, 0), (wv, -hv), (wv, hv)], close=True, fill=True)       # outlet to the side
        poly(c, [(0, 0), (0, -5), (-3, -7), (3, -9.5), (-3, -12), (3, -14.5), (0, -16)])  # spring
    else:
        poly(c, [(-wv, -hv), (0, 0), (-wv, hv)], close=True, fill=True)
        poly(c, [(wv, -hv), (0, 0), (wv, hv)], close=True, fill=True)
        if sym == "globe":
            c.setFillColor(col)
            c.circle(0, 0, 2.3, stroke=0, fill=1)
        elif sym == "ball":
            c.setFillColor(fill)
            c.circle(0, 0, 3.2, stroke=1, fill=1)
        elif sym == "butterfly":
            c.line(0, -hv, 0, hv)
            c.setFillColor(col)
            c.circle(0, 0, 1.6, stroke=0, fill=1)
        elif sym == "plug":
            c.setFillColor(col)
            c.rect(-1.8, -1.8, 3.6, 3.6, stroke=0, fill=1)
        if fn == "control":
            c.line(0, 0, 0, -hv - 6)
            c.setFillColor(fill)
            p = c.beginPath()
            p.moveTo(-6, -hv - 6)
            p.curveTo(-6, -hv - 14, 6, -hv - 14, 6, -hv - 6)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
    c.restoreState()


def draw_open_end(c: canvas.Canvas, kind: str, x: float, y: float, dx: float, dy: float, col: Any) -> None:
    c.saveState()
    c.setStrokeColor(col)
    c.setFillColor(col)
    c.setLineWidth(1.0)
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    if kind == "drain":
        arrow(c, x + ux * 4, y + uy * 4, ux, uy, 4.0)
    else:  # vent: open pipe end with two ticks
        px, py = -uy, ux
        c.line(x + px * 4, y + py * 4, x - px * 4, y - py * 4)
        c.line(x + px * 2.5 + ux * 4, y + py * 2.5 + uy * 4, x - px * 2.5 + ux * 4, y - py * 2.5 + uy * 4)
    c.restoreState()


# --------------------------------------------------------------------------- instruments
def draw_bubble(c: canvas.Canvas, x: float, y: float, code: str, number: str, proposed: bool, st: Style, controller: bool = False) -> None:
    r = 11.0
    c.saveState()
    c.setStrokeColor(st.proposed if proposed else INK)
    c.setFillColor(AMBER_FILL if proposed else colors.white)
    c.setLineWidth(1.0)
    c.circle(x, y, r, stroke=1, fill=1)
    c.line(x - r, y, x + r, y)
    if controller:
        c.line(x - r - 2, y - r, x + r + 2, y - r) if False else None
    c.restoreState()
    txt(c, x, y - 2.2, code, 6.4, FONT_B)
    txt(c, x, y + 7.4, number, 6.0, FONT)


# ------------------------------------------------------------------------------ sheets
class SheetPainter:
    def __init__(self, c: canvas.Canvas, topo: Topology, st: Style):
        self.c = c
        self.topo = topo
        self.st = st
        self.comp = {x.id: x for x in topo.components}
        self.lines = {l.id: l for l in topo.process_lines}
        self.scales: dict[str, float] = {}

    def frame(self, title: str, sheet_no: str, total: str, subtitle: str = "") -> tuple[float, float, float, float]:
        c = self.c
        W, H = PAGE
        c.setStrokeColor(INK)
        c.setLineWidth(1.4)
        c.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN)
        c.setLineWidth(0.5)
        # title block
        c.rect(MARGIN, MARGIN, W - 2 * MARGIN, TITLE_H)
        md = self.topo.metadata
        cols = [(MARGIN, 330, "PROJECT", md.project), (MARGIN + 330, 410, "DRAWING", title),
                (MARGIN + 740, 120, "SHEET", f"{sheet_no} of {total}"), (MARGIN + 860, 120, "REV.", md.revision.split(" ")[0]),
                (MARGIN + 980, W - 2 * MARGIN - 980, "STATUS", "DRAFT – pending engineering review")]
        for x, w, k, v in cols:
            c.line(x, MARGIN, x, MARGIN + TITLE_H)
            c.setFillColor(GREY)
            c.setFont(FONT, 6.5)
            c.drawString(x + 6, MARGIN + TITLE_H - 11, k)
            c.setFillColor(INK)
            f = FONT_B if k in ("DRAWING", "STATUS") else FONT
            lines = wrap(v, w - 12, 11 if k == "DRAWING" else 9.5, f, 2)
            for i, ln in enumerate(lines):
                c.setFont(f, 11 if k == "DRAWING" else 9.5)
                c.drawString(x + 6, MARGIN + TITLE_H - 28 - i * 13, ln)
        c.setFillColor(GREY)
        c.setFont(FONT, 6.5)
        c.drawString(MARGIN + 6, MARGIN + 7, f"Drawing {md.drawing_id} · source: {md.source_documents[0]['file']} · generated {dt.date.today().isoformat()} by pid_workflow · NOT FOR CONSTRUCTION")
        return MARGIN + 8, MARGIN + TITLE_H + 8, W - MARGIN - 8, H - MARGIN - 8

    def legend(self, x: float, y: float, w: float, h: float, services: list[str], has_proposed: bool, has_future: bool) -> None:
        """Legend box in PDF coordinates (y up), anchored at its bottom-left corner."""
        c = self.c
        c.saveState()
        c.setFillColor(colors.white)
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        c.rect(x, y, w, h, fill=1)
        c.setFillColor(INK)
        c.setFont(FONT_B, 8)
        c.drawString(x + 7, y + h - 12, "LEGEND")
        labels: list[tuple[str, Any]] = []
        seen: set[str] = set()
        for sv in services:
            lb = self.st.label(sv)
            if lb not in seen:
                seen.add(lb)
                labels.append((lb, self.st.color(sv)))
        col_w = (w - 14) / 2
        for i, (lb, col) in enumerate(labels):
            cx = x + 7 + (i // 5) * col_w
            cy = y + h - 26 - (i % 5) * 11
            c.setStrokeColor(col)
            c.setLineWidth(2.2)
            c.line(cx, cy + 2.6, cx + 22, cy + 2.6)
            c.setFillColor(INK)
            c.setFont(FONT, 7)
            c.drawString(cx + 28, cy, lb)
        yy = y + h - 26 - 5 * 11 - 3
        c.setLineWidth(1.0)
        if has_proposed:
            c.setStrokeColor(self.st.proposed)
            c.setFillColor(AMBER_FILL)
            c.rect(x + 7, yy - 1, 22, 8, fill=1)
            c.setFillColor(INK)
            c.setFont(FONT, 7)
            c.drawString(x + 35, yy, "Proposed addition – pending review")
            yy -= 11
        if has_future:
            c.setStrokeColor(GREY)
            c.setDash(*self.st.future_dash)
            c.rect(x + 7, yy - 1, 22, 8)
            c.setDash()
            c.setFillColor(INK)
            c.setFont(FONT, 7)
            c.drawString(x + 35, yy, "Future equipment (LifeCyclePhase=Future)")
            yy -= 11
        c.setFillColor(RED)
        c.circle(x + 12, yy + 3, 4.2, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(FONT_B, 5.2)
        c.drawCentredString(x + 12, yy + 1.4, "n")
        c.setFillColor(INK)
        c.setFont(FONT, 7)
        c.drawString(x + 35, yy, "Open point – numbered list on the right")
        yy -= 11
        c.setFont(FONT, 6.6)
        c.setFillColor(GREY)
        c.drawString(x + 7, yy, "Valves: gate/generic ▷◁ · check ▷| · globe ▷●◁ · control + actuator · bubble = function / proposed tag no.")
        c.restoreState()

    def sheet(self, sl: SheetLayout, page_label: str, total: str, ur_index: dict[str, int]) -> None:
        c = self.c
        x0, y0, x1, y1 = self.frame(sl.title, page_label, total)
        strip = 124.0
        bx0, by0, bx1, by1 = sl.bbox
        avail_w, avail_h = (x1 - x0), (y1 - y0 - strip - 10)
        pad = 26.0
        s = min(avail_w / (bx1 - bx0 + 2 * pad), avail_h / (by1 - by0 + 2 * pad), 1.6)
        ox = x0 + (avail_w - (bx1 - bx0) * s) / 2 - bx0 * s
        oy_top = y1 - (avail_h - (by1 - by0) * s) / 2 + by0 * s
        c.saveState()
        p = c.beginPath()
        p.rect(x0, y0 + strip + 10, avail_w, avail_h)
        c.clipPath(p, stroke=0)
        c.transform(s, 0, 0, -s, ox, oy_top)
        self.draw_content(sl, ur_index)
        c.restoreState()
        self.scales[sl.sheet_id] = s
        # bottom strip: legend + open points
        used = sorted({e.service for e in sl.edges if e.service})
        has_prop = any(n.kind == "manifold" and is_pending(n.obj.provenance) for n in sl.nodes.values()) or any(
            is_pending(sym.provenance) for e in sl.edges for sym, *_ in e.symbols) or any(is_pending(p_.inst.provenance) for p_ in sl.instruments) or any(e.proposed for e in sl.edges)
        has_future = any(getattr(n.obj, "lifecycle", "") == "future" for n in sl.nodes.values())
        c.setStrokeColor(INK)
        c.setLineWidth(0.5)
        c.line(x0, y0 + strip + 5, x1, y0 + strip + 5)
        lw = 330.0
        self.legend(x0 + 2, y0 + 2, lw, strip, used, has_prop, has_future)
        ids = set(sl.nodes) | {sym.id for e in sl.edges for sym, *_ in e.symbols}
        pts = []
        for u in self.topo.unresolved_requirements:
            if u.status == "open" and any(a in ids for a in u.affects) and u.id in ur_index:
                pts.append((ur_index[u.id], u))
        pts.sort(key=lambda t: t[0])
        c.setFont(FONT_B, 8)
        c.setFillColor(INK)
        c.drawString(x0 + lw + 16, y0 + strip - 10, "OPEN POINTS ON THIS SHEET")
        col_w = (x1 - (x0 + lw + 16) - 6) / 3
        col, yy = 0, y0 + strip - 24
        shown = 0
        for num, u in pts:
            lines = wrap(u.description, col_w - 22, 6.6, FONT, 3)
            h = len(lines) * 7.8 + 3
            if yy - h < y0 + 3:
                col += 1
                yy = y0 + strip - 24
                if col >= 3:
                    break
            xx = x0 + lw + 16 + col * col_w
            c.setFillColor(RED)
            c.circle(xx + 5, yy - 2.5, 4.4, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont(FONT_B, 5.6)
            c.drawCentredString(xx + 5, yy - 4.2, str(num))
            c.setFillColor(INK)
            c.setFont(FONT, 6.6)
            for i, ln in enumerate(lines):
                c.drawString(xx + 14, yy - 4.2 - i * 7.8, ln)
            yy -= h + 3
            shown += 1
        if shown < len(pts):
            c.setFont(FONT_I, 6.6)
            c.setFillColor(GREY)
            c.drawRightString(x1 - 4, y0 + 3, f"+{len(pts) - shown} more in the open-points table")
        c.showPage()

    # ---- content in layout coordinates (y down, scaled)
    def draw_content(self, sl: SheetLayout, ur_index: dict[str, int]) -> None:
        c = self.c
        st = self.st
        # pipes first
        for e in sl.edges:
            self.draw_edge(sl, e)
        for n in sl.nodes.values():
            if n.kind == "equipment":
                draw_equipment(c, n, st)
            elif n.kind in ("boundary", "offpage"):
                draw_boundary(c, n, st, None)
            elif n.kind == "manifold":
                self.draw_manifold(n, sl)
        # valves on top of pipes
        for e in sl.edges:
            self.draw_symbols(sl, e)
        # instruments & signals
        for kind, pts in sl.signals:
            c.saveState()
            c.setStrokeColor(colors.HexColor("#2a5db0"))
            c.setLineWidth(0.8)
            c.setDash(3, 2)
            poly(c, pts)
            c.restoreState()
        for pl in sl.instruments:
            if pl.leader:
                c.saveState()
                c.setStrokeColor(INK)
                c.setLineWidth(0.6)
                poly(c, pl.leader)
                c.restoreState()
            i = pl.inst
            num = (i.tag or "").split("-")[-1] if i.tag else ""
            draw_bubble(c, pl.x, pl.y, i.isa_code, num, is_pending(i.provenance), st)
        # open-point markers
        placed: dict[str, int] = {}
        for u_id, num in ur_index.items():
            u = next(x for x in self.topo.unresolved_requirements if x.id == u_id)
            for a in u.affects:
                n = sl.nodes.get(a)
                if n is not None and n.kind in ("equipment", "boundary"):
                    k = placed.get(a, 0)
                    placed[a] = k + 1
                    mx = n.x + n.w / 2 - 2 - k * 11
                    my = n.y - n.h / 2 - 2
                    c.saveState()
                    c.setFillColor(RED)
                    c.circle(mx, my, 4.6, fill=1, stroke=0)
                    c.restoreState()
                    txt(c, mx, my + 1.9, str(num), 5.8, FONT_B, "c", colors.white)

    def draw_manifold(self, n: MNode, sl: SheetLayout) -> None:
        c = self.c
        c.saveState()
        svc = next((e.service for e in sl.edges if e.src[0] == n.id or e.dst[0] == n.id), "")
        c.setStrokeColor(self.st.proposed if is_pending(n.obj.provenance) else self.st.color(svc))
        c.setLineWidth(3.2)
        c.setLineCap(0)
        c.line(n.x, n.span[0], n.x, n.span[1])
        c.restoreState()

    def draw_edge(self, sl: SheetLayout, e: MEdge) -> None:
        c = self.c
        if len(e.path) < 2:
            return
        col = self.st.proposed if e.proposed else self.st.color(e.service)
        c.saveState()
        c.setStrokeColor(col)
        c.setFillColor(col)
        c.setLineWidth(2.4 if e.header else 1.5)
        c.setLineJoin(1)
        if e.proposed:
            c.setDash(5, 2.5)
        poly(c, e.path)
        c.setDash()
        # flow arrow at the middle of the longest segment (skip where valves sit)
        best, bi = 0.0, 0
        for i in range(len(e.path) - 1):
            l = math.dist(e.path[i], e.path[i + 1])
            if l > best:
                best, bi = l, i
        if best > 46 and not e.stub:
            (x1, y1), (x2, y2) = e.path[bi], e.path[bi + 1]
            f = 0.72 if e.chain else 0.5
            ax, ay = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
            arrow(c, ax, ay, x2 - x1, y2 - y1, 4.4)
        c.restoreState()
        # service label on header / long runs
        if (e.header or best > 150) and not e.stub and best > 70 and not e.chain:
            (x1, y1), (x2, y2) = e.path[bi], e.path[bi + 1]
            if abs(y1 - y2) < 0.01:
                lab = e.service
                ln = self.lines.get(e.line_ids[0]) if e.line_ids else None
                if ln is not None:
                    dn = ln.properties.get("nominal_diameter")
                    rng = ln.properties.get("nominal_diameter_range")
                    mn = ln.properties.get("nominal_diameter_min")
                    if dn is not None and dn.value:
                        lab += f" · DN{dn.value}"
                    elif rng is not None:
                        lab += f" · DN{rng.value['min']}–{rng.value['max']}"
                    elif mn is not None:
                        lab += f" · ≥DN{mn.value}"
                txt(c, (x1 + x2) / 2, y1 - 4.5, lab, 6.6, FONT, "c", col)

    def draw_symbols(self, sl: SheetLayout, e: MEdge) -> None:
        c = self.c
        for k, (comp, x, y, ori) in enumerate(e.symbols):
            # direction of the local flow
            i = min(range(len(e.path) - 1), key=lambda j: _dist_seg((x, y), e.path[j], e.path[j + 1]))
            dx = e.path[i + 1][0] - e.path[i][0]
            draw_valve(c, comp, x, y, ori, self.st, flow_dx=dx if ori == "H" else 1)
            tag = comp.tag or ""
            col = self.st.proposed if is_pending(comp.provenance) else INK
            if tag:
                if ori == "H":
                    up = -25 if comp.function == "control" else -12
                    txt(c, x, y + (up if k % 2 == 0 or comp.function == "control" else 18.5), tag, 6.6, FONT_B, "c", col)
                else:
                    txt(c, x + 11, y + 2.4, tag, 6.6, FONT_B, "l", col)
            if comp.function == "control":
                pass
        if e.stub and e.path and e.chain:
            # terminal symbol at the open end
            (x1, y1), (x2, y2) = e.path[-2], e.path[-1]
            comp = e.chain[-1]
            draw_open_end(c, comp.open_end or "drain", x2, y2, x2 - x1, y2 - y1, self.st.proposed if is_pending(comp.provenance) else INK)


def _dist_seg(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


# ------------------------------------------------------------------------ cover / overview
def draw_cover(c: canvas.Canvas, topo: Topology, layout: DrawingLayout, facts: dict[str, Any], ur_index: dict[str, int], pages: list[tuple[str, str]]) -> None:
    W, H = PAGE
    md = topo.metadata
    c.setStrokeColor(INK)
    c.setLineWidth(1.4)
    c.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN)
    x = MARGIN + 40
    y = H - MARGIN - 70
    c.setFillColor(INK)
    c.setFont(FONT_B, 26)
    c.drawString(x, y, "Draft P&ID — review set")
    c.setFont(FONT, 15)
    y -= 26
    c.drawString(x, y, md.title)
    y -= 20
    c.setFont(FONT, 10.5)
    c.setFillColor(GREY)
    c.drawString(x, y, f"{md.project}  ·  drawing {md.drawing_id}  ·  revision {md.revision}  ·  generated {dt.date.today().isoformat()}")
    # status banner
    y -= 34
    c.setFillColor(AMBER_FILL)
    c.setStrokeColor(colors.HexColor("#e07b00"))
    c.setLineWidth(1.2)
    c.roundRect(x, y - 8, 640, 34, 5, fill=1)
    c.setFillColor(INK)
    c.setFont(FONT_B, 11)
    c.drawString(x + 12, y + 8, "DRAFT — NOT FOR CONSTRUCTION")
    c.setFont(FONT, 9)
    c.drawString(x + 12, y - 4, "Every addition is pending engineering review. Nothing was invented that the specification does not state.")
    y -= 44

    def block(title: str, lines: list[str], x0: float, y0: float, w: float) -> float:
        c.setFillColor(INK)
        c.setFont(FONT_B, 11)
        c.drawString(x0, y0, title)
        yy = y0 - 15
        c.setFont(FONT, 9)
        for ln in lines:
            for part in wrap(ln, w, 9, FONT, 4):
                c.drawString(x0, yy, part)
                yy -= 12
            yy -= 2
        return yy

    col_w = 520
    # left column: what this is / how to read it
    yl = block("What this is", [
        f"A draft piping & instrumentation diagram generated from “{md.source_documents[0]['file']}” ({md.source_documents[0]['pages']} pages).",
        "The AI read the specification into a traceable topology (every object points to a page and section); deterministic code then enriched, validated, laid out, drew and exported it.",
        "Black items come from the specification. Orange items are proposals created by the project rules of section 5 of the specification and wait for approval.",
        "Red numbered dots mark open points: values or choices the specification does not give. None of them was assumed.",
    ], x, y, col_w)
    yl = block("Results of the automatic checks", [
        f"Structural validation: {'PASS' if facts.get('validation_ok') else 'FAIL'} ({facts.get('validation_errors', 0)} errors, {facts.get('validation_warnings', 0)} warnings).",
        f"DEXPI Proteus XML round trip: {'PASS' if facts.get('roundtrip_ok') else 'FAIL'} — {facts.get('roundtrip_summary', '')}",
        f"Enrichment is idempotent: re-running it adds nothing ({facts.get('idempotent', 'checked in tests')}).",
    ], x, yl - 10, col_w)
    # contents under the left column
    c.setFont(FONT_B, 11)
    c.setFillColor(INK)
    c.drawString(x, yl - 12, "Contents")
    yc = yl - 30
    for pg, title in pages:
        c.setFont(FONT, 9.5)
        c.drawString(x, yc, title)
        c.drawRightString(x + col_w, yc, pg)
        yc -= 13.5
    yl = yc
    # middle column: numbers
    xm = x + col_w + 30
    c.setFont(FONT_B, 11)
    c.setFillColor(INK)
    c.drawString(xm, y, "The model in numbers")
    rows = [("Equipment (source)", facts["equipment"]), ("Process lines (after valve insertion)", facts["lines"]),
            ("Manifolds / tees", facts["manifolds"]), ("Valves (source / proposed)", f"{facts['valves_source']} / {facts['valves_generated']}"),
            ("Instruments (proposed)", facts["instruments"]), ("Control loops", facts["loops"]),
            ("Proposals pending review", facts["pending"]), ("Open points", facts["open_points"]), ("Interpretations to confirm", facts["interpreted"])]
    yy = y - 18
    for k, v in rows:
        c.setFont(FONT, 9.5)
        c.setFillColor(INK)
        c.drawString(xm, yy, k)
        c.setFont(FONT_B, 9.5)
        c.drawRightString(xm + 240, yy, str(v))
        c.setStrokeColor(colors.HexColor("#d8d4c8"))
        c.setLineWidth(0.4)
        c.line(xm, yy - 4, xm + 240, yy - 4)
        yy -= 16
    # attention list
    ya = min(yl, yy) - 22
    c.setFont(FONT_B, 11)
    c.setFillColor(INK)
    c.drawString(x, ya, "Where an engineer should look first")
    ya -= 16
    top = [u for u in topo.unresolved_requirements if u.status == "open" and u.category in ("conflict", "ambiguity") and u.id in ur_index]
    for u in top:
        c.setFillColor(RED)
        c.circle(x + 5, ya + 3, 5, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(FONT_B, 6.5)
        c.drawCentredString(x + 5, ya + 1, str(ur_index[u.id]))
        c.setFillColor(INK)
        c.setFont(FONT, 9)
        for i, part in enumerate(wrap(u.description, 1050, 9, FONT, 3)):
            c.drawString(x + 18, ya - i * 11.5, part)
        ya -= 11.5 * min(3, len(wrap(u.description, 1050, 9, FONT, 3))) + 6
    c.setFont(FONT, 7)
    c.setFillColor(GREY)
    c.drawString(MARGIN + 10, MARGIN + 10, "Generated by pid_workflow — extraction, enrichment, validation, layout, export and review are separate, re-runnable stages.")
    c.showPage()


def _border_point(cx: float, cy: float, w: float, h: float, tx: float, ty: float) -> tuple[float, float]:
    dx, dy = tx - cx, ty - cy
    if dx == dy == 0:
        return cx, cy
    k = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
    return cx + dx * k, cy + dy * k


def draw_overview(c: canvas.Canvas, painter: SheetPainter, layout: DrawingLayout, page_label: str, total: str, specs_titles: list[str]) -> None:
    ov = layout.overview
    assert ov is not None
    x0, y0, x1, y1 = painter.frame("Overview – sheets and the services between them", page_label, total)
    xs = [b[0] for b in ov.boxes.values()]
    ys = [b[1] for b in ov.boxes.values()]
    bw = (max(xs) - min(xs)) + 260
    bh = (max(ys) - min(ys)) + 140
    s = min((x1 - x0) / bw, (y1 - y0) / bh, 1.5)
    ox = (x0 + x1) / 2 - ((max(xs) + min(xs)) / 2) * s
    oy = (y0 + y1) / 2 + ((max(ys) + min(ys)) / 2) * s
    c.saveState()
    c.transform(s, 0, 0, -s, ox, oy)
    idx = {sp.id: i for i, sp in enumerate(layout.specs, 1)}
    # links first
    for a, b, svcs in ov.links:
        (ax, ay, aw, ah), (bx_, by_, bw_, bh_) = ov.boxes[a], ov.boxes[b]
        dx, dy = bx_ - ax, by_ - ay
        n = math.hypot(dx, dy) or 1
        px, py = -dy / n, dx / n
        for k, (svc, nab, nba) in enumerate(svcs):
            off = (k - (len(svcs) - 1) / 2) * 17
            p1 = _border_point(ax, ay, aw, ah, bx_ + px * off, by_ + py * off)
            p2 = _border_point(bx_, by_, bw_, bh_, ax + px * off, ay + py * off)
            p1 = (p1[0] + px * off, p1[1] + py * off)
            p2 = (p2[0] + px * off, p2[1] + py * off)
            col = painter.st.color(svc)
            c.saveState()
            c.setStrokeColor(col)
            c.setFillColor(col)
            c.setLineWidth(2.2)
            c.line(*p1, *p2)
            if nab:
                arrow(c, p2[0] - (p2[0] - p1[0]) / n * 0.0, p2[1], p2[0] - p1[0], p2[1] - p1[1], 7)
            if nba:
                arrow(c, p1[0], p1[1], p1[0] - p2[0], p1[1] - p2[1], 7)
            c.restoreState()
            mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            lab = f"{painter.st.label(svc)} · {nab}→ {nba}←" if nab and nba else f"{painter.st.label(svc)} · {max(nab, nba)} line(s)"
            wlab = pdfmetrics.stringWidth(lab, FONT, 7) + 6
            c.saveState()
            c.setFillColor(colors.white)
            c.rect(mx - wlab / 2, my - 6, wlab, 11, stroke=0, fill=1)
            c.restoreState()
            txt(c, mx, my + 2, lab, 7, FONT, "c", col)
    for sid, (cx, cy, w, h) in ov.boxes.items():
        c.saveState()
        c.setFillColor(LIGHT)
        c.setStrokeColor(INK)
        c.setLineWidth(1.5)
        c.roundRect(cx - w / 2, cy - h / 2, w, h, 7, fill=1)
        c.restoreState()
        txt(c, cx, cy - h / 2 + 15, f"Sheet {idx[sid]}", 10, FONT_B)
        for i, ln in enumerate(wrap(ov.titles[sid], w - 14, 8, FONT, 3)):
            txt(c, cx, cy - h / 2 + 28 + i * 9.5, ln, 8)
    c.restoreState()
    c.showPage()


# ---------------------------------------------------------------------------- tables
def _para(s: str, size: float = 7.6, bold: bool = False, color: str = "#1c1c1c") -> Paragraph:
    return Paragraph(s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
                     ParagraphStyle("p", fontName=FONT_B if bold else FONT, fontSize=size, leading=size + 2.2, textColor=colors.HexColor(color)))


def _tbl(data: list[list[Any]], widths: list[float], header_color: str = "#2b2b2b") -> LongTable:
    t = LongTable(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_B),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f5ef")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8d4c8")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def table_pages(path: Path, topo: Topology, ur_index: dict[str, int], interpreted: list[tuple[str, int, str]]) -> None:
    W, H = PAGE
    doc = SimpleDocTemplate(str(path), pagesize=PAGE, leftMargin=MARGIN + 14, rightMargin=MARGIN + 14, topMargin=MARGIN + 14, bottomMargin=MARGIN + 14,
                            title="Review tables")
    h1 = ParagraphStyle("h1", fontName=FONT_B, fontSize=15, leading=19, spaceAfter=4)
    note = ParagraphStyle("n", fontName=FONT, fontSize=8.4, leading=11, textColor=colors.HexColor("#555555"), spaceAfter=8)
    story: list[Any] = []
    avail = W - 2 * (MARGIN + 14)

    # ---- proposals
    story += [Paragraph("Proposed additions pending review", h1),
              Paragraph("Everything below was created by a project rule of section 5 / section 4 of the specification. Approve or reject each line; tags are proposals "
                        "(ISA 5.1, `tag_status: proposed`). Generic valves are listed with their technology as “to be selected”.", note)]
    rows: list[list[Any]] = [["Tag (proposed)", "Item", "Rule", "Why / where"]]
    objs: list[tuple[str, str, Any]] = []
    for cmp_ in topo.components:
        if cmp_.provenance.origin == "generated" and cmp_.kind != "manifold":
            tech = "generic – technology to be selected" if cmp_.technology_status == "unspecified_generic" else (cmp_.technology or cmp_.model_class)
            objs.append((cmp_.provenance.rule or "", cmp_.tag or cmp_.id, f"{cmp_.name} [{tech}]"))
    for cmp_ in topo.components:
        if cmp_.provenance.origin == "generated" and cmp_.kind == "manifold":
            objs.append((cmp_.provenance.rule or "", "—", f"{cmp_.name} (tee)"))
    for i in topo.instruments:
        if i.provenance.origin == "generated":
            objs.append((i.provenance.rule or "", i.tag or i.id, f"{i.name} [{i.function}]"))
    for lp in topo.control_loops:
        objs.append((lp.provenance.rule or "", lp.id, f"{lp.name}"))
    prov_of: dict[str, Any] = {c.id: c for c in topo.components}
    prov_of.update({i.id: i for i in topo.instruments})
    prov_of.update({lp.id: lp for lp in topo.control_loops})
    by_rule: dict[str, list[tuple[str, str, str]]] = {}
    for cmp_ in [*topo.components, *topo.instruments, *topo.control_loops]:
        if cmp_.provenance.origin != "generated":
            continue
        expl = (cmp_.provenance.explanation or "").split("): ", 1)[-1]
        label = cmp_.name or cmp_.id
        if getattr(cmp_, "kind", "") == "manifold":
            label += " (tee)"
        tag = getattr(cmp_, "tag", None) or "—"
        by_rule.setdefault(cmp_.provenance.rule or "?", []).append((tag, label, expl))
    for rule in sorted(by_rule):
        for tag, label, expl in sorted(by_rule[rule]):
            rows.append([_para(tag, 7.6, True, "#b8620a"), _para(label), _para(rule, 7.2), _para(expl, 7.2, color="#444444")])
    story.append(_tbl(rows, [70, 300, 100, avail - 470]))

    # ---- tag modifications / line splits
    mods = [m for m in topo.modifications if m.field in ("tag", "nozzles", "loop_id")]
    if mods:
        story += [Spacer(1, 14), Paragraph("Changes to source objects (source value preserved)", h1)]
        r2: list[list[Any]] = [["Object", "Field", "Source value", "Proposed", "Rule"]]
        for m in mods:
            r2.append([_para(m.object_id), _para(m.field), _para(str(m.old)), _para(str(m.new), bold=True), _para(m.provenance.rule or "")])
        story.append(_tbl(r2, [220, 80, 180, 220, avail - 700]))
    splits = [m for m in topo.modifications if m.field == "split"]
    story += [Spacer(1, 8), Paragraph(f"{len(splits)} source lines were split to insert components; each child line keeps the service and properties of its source line (field `split_from`).", note)]

    # ---- open points
    from reportlab.platypus import PageBreak
    story += [PageBreak(), Paragraph("Open points – what the specification does not say", h1),
              Paragraph("These are preserved as unresolved requirements. Nothing here was assumed (design pressures, relief sizing, safety thresholds, failure positions, "
                        "material classes, nozzle sizes and instrument ranges are never invented).", note)]
    r3: list[list[Any]] = [["#", "Id", "Kind", "Open point", "Affects", "Question for the engineer"]]
    for u in topo.unresolved_requirements:
        if u.status != "open":
            continue
        aff = ", ".join(u.affects[:6]) + (f" … (+{len(u.affects) - 6})" if len(u.affects) > 6 else "")
        r3.append([_para(str(ur_index.get(u.id, "")), 8, True, "#b3261e"), _para(u.id, 7), _para(u.category, 7.4), _para(u.description, 7.4), _para(aff, 6.8, color="#555555"),
                   _para(u.question or "", 7.4)])
    story.append(_tbl(r3, [22, 100, 58, avail - 22 - 100 - 58 - 190 - 200, 190, 200]))

    # ---- interpretations
    story += [PageBreak(), Paragraph("Interpretations to confirm", h1),
              Paragraph("Facts that are not stated word for word in the specification but were needed to draw a connected diagram. They are in the source topology with "
                        "`basis: interpreted` and the note below.", note)]
    r4: list[list[Any]] = [["Objects", "Page / section", "Interpretation"]]
    for note_txt, n, sect in interpreted:
        r4.append([_para(str(n), 8, True), _para(sect, 7.2), _para(note_txt, 7.6)])
    story.append(_tbl(r4, [60, 240, avail - 300]))
    doc.build(story)


# ------------------------------------------------------------------------------- entry
def interpreted_notes(topo: Topology) -> list[tuple[str, int, str]]:
    seen: dict[tuple[str, str], int] = {}
    for o in topo.objects().values():
        p = o.provenance
        if p.origin == "source" and p.basis == "interpreted":
            note = p.note or (f"“{p.quote}”" if p.quote else "(no note)")
            key = (note, f"p.{p.page} · {p.section}")
            seen[key] = seen.get(key, 0) + 1
    return sorted(((k[0], n, k[1]) for k, n in seen.items()), key=lambda t: (t[2], t[0]))


def facts_for(topo: Topology, extra: dict[str, Any]) -> dict[str, Any]:
    valves = [c for c in topo.components if c.kind != "manifold"]
    pending = sum(1 for o in topo.objects().values() if o.provenance.origin == "generated" and o.provenance.status == "pending_review")
    f = {
        "equipment": len(topo.equipment), "lines": len(topo.process_lines),
        "manifolds": sum(1 for c in topo.components if c.kind == "manifold"),
        "valves_source": sum(1 for v in valves if v.provenance.origin == "source"),
        "valves_generated": sum(1 for v in valves if v.provenance.origin == "generated"),
        "instruments": sum(1 for i in topo.instruments if i.provenance.origin == "generated"),
        "loops": len(topo.control_loops), "pending": pending,
        "open_points": sum(1 for u in topo.unresolved_requirements if u.status == "open"),
        "interpreted": sum(n for _, n, _ in interpreted_notes(topo)),
    }
    f.update(extra)
    return f


def render_review_pdf(topo: Topology, layout: DrawingLayout, out_path: str | Path, style_path: str | Path, extra_facts: dict[str, Any] | None = None) -> dict[str, float]:
    _fonts()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    st = Style(style_path)
    open_urs = [u for u in topo.unresolved_requirements if u.status == "open"]
    ur_index = {u.id: i for i, u in enumerate(open_urs, 1)}
    facts = facts_for(topo, extra_facts or {})
    n_sheets = len(layout.sheets)
    total = str(2 + n_sheets)
    tmp_main = out_path.with_suffix(".main.pdf")
    tmp_tab = out_path.with_suffix(".tables.pdf")
    c = canvas.Canvas(str(tmp_main), pagesize=PAGE)
    c.setTitle(f"{topo.metadata.title} – draft P&ID review set")
    c.setAuthor("pid_workflow")
    painter = SheetPainter(c, topo, st)
    pages = [("1", "Cover"), ("2", "Overview – sheets and services")]
    for i, sl in enumerate(layout.sheets, 1):
        pages.append((str(2 + i), f"Sheet {i} – {sl.title}"))
    pages.append((str(3 + n_sheets) + "+", "Review tables"))
    draw_cover(c, topo, layout, facts, ur_index, pages)
    draw_overview(c, painter, layout, "2", total, [s.title for s in layout.sheets])
    for i, sl in enumerate(layout.sheets, 1):
        painter.sheet(sl, f"Sheet {i}", str(n_sheets), ur_index)
    c.save()
    table_pages(tmp_tab, topo, ur_index, interpreted_notes(topo))
    w = PdfWriter()
    for f in (tmp_main, tmp_tab):
        w.append(str(f))
    w.add_metadata({"/Title": f"{topo.metadata.title} – draft P&ID review set", "/Author": "pid_workflow"})
    with open(out_path, "wb") as fh:
        w.write(fh)
    tmp_main.unlink(missing_ok=True)
    tmp_tab.unlink(missing_ok=True)
    return painter.scales
