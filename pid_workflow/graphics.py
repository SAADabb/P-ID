"""Drawing primitives shared by the PDF and the DEXPI (Proteus) graphics.

The one-sheet drawing is *recorded* once: the symbol painters draw on :class:`Recorder`, a small
stand-in for a ReportLab canvas that keeps every stroke as a primitive in sheet coordinates
(points, y up), tagged with the model object it belongs to.  The same primitive list is then

* replayed on a real ReportLab canvas  -> the PDF, and
* written as Proteus graphics           -> ShapeCatalogue, positions, labels, centre lines,

so the PDF and the DEXPI file cannot drift apart.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from reportlab.lib import colors

Pt = tuple[float, float]


@dataclass
class Owner:
    kind: str            # equipment | valve | instrument | boundary | manifold | line | signal | sheet
    ref: str = ""        # topology id (or a sheet element name)
    role: str = "symbol"  # symbol | label | line
    anchor: Pt | None = None  # symbol origin in sheet coordinates


@dataclass
class Prim:
    kind: str                     # poly | circle | text
    owner: Owner
    pts: list[Pt] = field(default_factory=list)
    closed: bool = False
    r: float = 0.0
    stroke: str | None = "#000000"
    fill: str | None = None
    width: float = 1.0
    dash: tuple[float, ...] = ()
    text: str = ""
    size: float = 0.0
    font: str = ""
    align: str = "l"              # l | c | r
    angle: float = 0.0            # degrees, counter-clockwise


def _hex(c: Any) -> str | None:
    if c is None:
        return None
    if isinstance(c, str):
        return c
    return c.hexval().replace("0x", "#")


class _Path:
    def __init__(self) -> None:
        self.subpaths: list[tuple[list[Pt], bool]] = []
        self.cur: list[Pt] = []

    def moveTo(self, x: float, y: float) -> None:  # noqa: N802 - ReportLab API
        if self.cur:
            self.subpaths.append((self.cur, False))
        self.cur = [(x, y)]

    def lineTo(self, x: float, y: float) -> None:  # noqa: N802
        self.cur.append((x, y))

    def curveTo(self, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:  # noqa: N802
        x0, y0 = self.cur[-1]
        for k in range(1, 9):
            t = k / 8
            a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
            self.cur.append((a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3))

    def close(self) -> None:
        if self.cur:
            self.subpaths.append((self.cur, True))
        self.cur = []

    def rect(self, x: float, y: float, w: float, h: float) -> None:
        self.moveTo(x, y)
        self.lineTo(x + w, y)
        self.lineTo(x + w, y + h)
        self.lineTo(x, y + h)
        self.close()

    def done(self) -> list[tuple[list[Pt], bool]]:
        if self.cur:
            self.subpaths.append((self.cur, False))
            self.cur = []
        return self.subpaths


class Recorder:
    """The subset of the ReportLab canvas API used by the painters, recording primitives."""

    def __init__(self) -> None:
        self.prims: list[Prim] = []
        self.owner = Owner("sheet", "sheet")
        self._m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)  # a b c d e f, like PDF
        self._st: dict[str, Any] = {"stroke": "#000000", "fill": "#000000", "width": 1.0, "dash": (), "font": "", "size": 10.0}
        self._stack: list[tuple[tuple[float, ...], dict[str, Any]]] = []

    # ---- state
    def saveState(self) -> None:  # noqa: N802
        self._stack.append((self._m, dict(self._st)))

    def restoreState(self) -> None:  # noqa: N802
        self._m, self._st = self._stack.pop()

    def setStrokeColor(self, c: Any) -> None:  # noqa: N802
        self._st["stroke"] = _hex(c)

    def setFillColor(self, c: Any) -> None:  # noqa: N802
        self._st["fill"] = _hex(c)

    def setLineWidth(self, w: float) -> None:  # noqa: N802
        self._st["width"] = w

    def setDash(self, *a: Any) -> None:  # noqa: N802
        if not a or (len(a) == 1 and not a[0]):
            self._st["dash"] = ()
        elif len(a) == 1 and isinstance(a[0], (list, tuple)):
            self._st["dash"] = tuple(a[0])
        else:
            self._st["dash"] = tuple(x for x in a if isinstance(x, (int, float)))[:2]

    def setLineJoin(self, *_: Any) -> None:  # noqa: N802
        pass

    def setLineCap(self, *_: Any) -> None:  # noqa: N802
        pass

    def setFont(self, font: str, size: float) -> None:  # noqa: N802
        self._st["font"], self._st["size"] = font, size

    def clipPath(self, *_: Any, **__: Any) -> None:  # noqa: N802
        pass

    # ---- transforms
    def transform(self, a: float, b: float, c: float, d: float, e: float, f: float) -> None:
        A, B, C, D, E, F = self._m
        self._m = (A * a + C * b, B * a + D * b, A * c + C * d, B * c + D * d, A * e + C * f + E, B * e + D * f + F)

    def translate(self, dx: float, dy: float) -> None:
        self.transform(1, 0, 0, 1, dx, dy)

    def scale(self, sx: float, sy: float) -> None:
        self.transform(sx, 0, 0, sy, 0, 0)

    def rotate(self, deg: float) -> None:
        r = math.radians(deg)
        self.transform(math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)

    def _p(self, x: float, y: float) -> Pt:
        a, b, c, d, e, f = self._m
        return (a * x + c * y + e, b * x + d * y + f)

    def _len(self) -> float:
        a, b, c, d, _, _ = self._m
        return math.sqrt(abs(a * d - b * c))

    def map(self, x: float, y: float) -> Pt:
        """Sheet coordinates of a point given in the current user space."""
        return self._p(x, y)

    # ---- drawing
    def _poly(self, pts: list[Pt], closed: bool, fill: bool, stroke: bool) -> None:
        if len(pts) < 2:
            return
        self.prims.append(Prim("poly", self.owner, [self._p(*q) for q in pts], closed, stroke=self._st["stroke"] if stroke else None,
                               fill=self._st["fill"] if fill else None, width=self._st["width"] * self._len(),
                               dash=tuple(x * self._len() for x in self._st["dash"])))

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._poly([(x1, y1), (x2, y2)], False, False, True)

    def rect(self, x: float, y: float, w: float, h: float, stroke: int = 1, fill: int = 0) -> None:
        self._poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True, bool(fill), bool(stroke))

    def roundRect(self, x: float, y: float, w: float, h: float, r: float, stroke: int = 1, fill: int = 0) -> None:  # noqa: N802
        r = min(r, w / 2, h / 2)
        pts: list[Pt] = []
        for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
            for k in range(7):
                a = math.radians(a0 + 15 * k)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self._poly(pts, True, bool(fill), bool(stroke))

    def circle(self, x: float, y: float, r: float, stroke: int = 1, fill: int = 0) -> None:
        self.prims.append(Prim("circle", self.owner, [self._p(x, y)], r=r * self._len(), stroke=self._st["stroke"] if stroke else None,
                               fill=self._st["fill"] if fill else None, width=self._st["width"] * self._len(),
                               dash=tuple(x_ * self._len() for x_ in self._st["dash"])))

    def beginPath(self) -> _Path:  # noqa: N802
        return _Path()

    def drawPath(self, p: _Path, fill: int = 0, stroke: int = 1) -> None:  # noqa: N802
        for pts, closed in p.done():
            self._poly(pts, closed, bool(fill), bool(stroke))

    def _text(self, x: float, y: float, s: str, align: str) -> None:
        if not s:
            return
        a, b, c, d, _, _ = self._m
        ang = math.degrees(math.atan2(b, a))
        self.prims.append(Prim("text", self.owner, [self._p(x, y)], stroke=None, fill=self._st["fill"], text=s,
                               size=self._st["size"] * math.hypot(c, d), font=self._st["font"], align=align, angle=ang))

    def drawString(self, x: float, y: float, s: str) -> None:  # noqa: N802
        self._text(x, y, s, "l")

    def drawCentredString(self, x: float, y: float, s: str) -> None:  # noqa: N802
        self._text(x, y, s, "c")

    def drawRightString(self, x: float, y: float, s: str) -> None:  # noqa: N802
        self._text(x, y, s, "r")


def replay(prims: list[Prim], c: Any) -> None:
    """Draw recorded primitives on a ReportLab canvas whose user space is the sheet space."""
    for p in prims:
        c.saveState()
        if p.kind == "text":
            c.setFillColor(colors.HexColor(p.fill or "#000000"))
            c.setFont(p.font, p.size)
            c.translate(*p.pts[0])
            if p.angle:
                c.rotate(p.angle)
            {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[p.align](0, 0, p.text)
        else:
            if p.stroke:
                c.setStrokeColor(colors.HexColor(p.stroke))
            if p.fill:
                c.setFillColor(colors.HexColor(p.fill))
            c.setLineWidth(p.width)
            c.setLineJoin(1)
            if p.dash:
                c.setDash(*p.dash)
            if p.kind == "circle":
                c.circle(p.pts[0][0], p.pts[0][1], p.r, stroke=1 if p.stroke else 0, fill=1 if p.fill else 0)
            else:
                path = c.beginPath()
                path.moveTo(*p.pts[0])
                for q in p.pts[1:]:
                    path.lineTo(*q)
                if p.closed:
                    path.close()
                c.drawPath(path, stroke=1 if p.stroke else 0, fill=1 if p.fill else 0)
        c.restoreState()
