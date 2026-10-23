"""Write the one-sheet drawing into the Proteus XML as DEXPI graphics.

The model part of the file is written by :mod:`proteus_ext`; this module adds, from the same recorded
primitives that produce the PDF:

* ``<Drawing>``: sheet extent (A0, millimetres), the border / grid / panel / title block as
  ``<DrawingBorder>``, plant-area frames, hold markers and signal lines as drawing ``<Label>`` s;
* ``<ShapeCatalogue>``: one shape per distinct symbol (equipment, valve, instrument bubble, battery
  limit), in symbol coordinates;
* on every equipment / valve / instrument / battery-limit element: ``ComponentName`` + ``<Position>``
  (a DEXPI shape usage) and its tag / name texts as ``<Label>`` s;
* on every ``<CenterLine>``: ``<Presentation>`` and the routed ``<Coordinate>`` s of that pipe.

Coordinates are millimetres on the sheet, origin bottom-left, y up.
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from lxml import etree

from .graphics import Prim
from .layout import MEdge
from .onesheet import OneSheet
from .render_onesheet import MM, OneSheetDrawing

TO_MM = 1.0 / MM
LINE_TYPE = {(): "0"}  # 0 = Solid, 1 = Dot, 2 = Dash (DEXPI DashStyle index)
JUST = {"l": "LeftBottom", "c": "CenterBottom", "r": "RightBottom"}
LABEL_CLASS = {
    "equipment": "EquipmentTagNameLabel",
    "valve": "ValveLabel",
    "instrument": "ProcessInstrumentationFunctionLabel",
    "boundary": "OffPageConnectorDescriptionLabel",
    "line": "PipingNetworkSegmentLabel",
    "manifold": "Label",
}


def _f(v: float) -> str:
    return f"{v:.2f}"


def _rgb(hexcol: str | None) -> tuple[str, str, str]:
    h = (hexcol or "#000000").lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return f"{r:.3f}", f"{g:.3f}", f"{b:.3f}"


def _presentation(parent: etree._Element, color: str | None, width_pt: float = 0.5, dash: tuple[float, ...] = ()) -> etree._Element:
    p = etree.SubElement(parent, "Presentation")
    p.set("Layer", "0")
    p.set("LineType", "0" if not dash else ("1" if dash[0] <= 1.5 else "2"))
    p.set("LineWeight", _f(width_pt * TO_MM))
    r, g, b = _rgb(color)
    p.set("R", r)
    p.set("G", g)
    p.set("B", b)
    return p


def _coord(parent: etree._Element, x: float, y: float) -> None:
    c = etree.SubElement(parent, "Coordinate")
    c.set("X", _f(x))
    c.set("Y", _f(y))
    c.set("Z", "0")


def _position(parent: etree._Element, x: float, y: float, index: int | None = None) -> etree._Element:
    pos = etree.Element("Position")
    loc = etree.SubElement(pos, "Location")
    loc.set("X", _f(x))
    loc.set("Y", _f(y))
    loc.set("Z", "0")
    ax = etree.SubElement(pos, "Axis")
    ax.set("X", "0")
    ax.set("Y", "0")
    ax.set("Z", "1")
    ref = etree.SubElement(pos, "Reference")
    ref.set("X", "1")
    ref.set("Y", "0")
    ref.set("Z", "0")
    if index is None:
        parent.append(pos)
    else:
        parent.insert(index, pos)
    return pos


def _circle_pts(cx: float, cy: float, r: float, n: int = 24) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]


def _emit(parent: etree._Element, p: Prim, dx: float = 0.0, dy: float = 0.0, circles: bool = True) -> None:
    """One primitive (sheet points) as Proteus graphics in millimetres, shifted by (dx, dy) mm."""
    if p.kind == "text":
        t = etree.SubElement(parent, "Text")
        t.set("String", p.text)
        t.set("Font", p.font.replace("FreeSans", "Arial"))
        t.set("Height", _f(p.size * TO_MM))
        t.set("Justification", JUST[p.align])
        t.set("TextAngle", _f(p.angle))
        _presentation(t, p.fill)
        x, y = p.pts[0]
        _position(t, x * TO_MM - dx, y * TO_MM - dy)
        return
    if p.kind == "circle" and circles:
        c = etree.SubElement(parent, "Circle")
        c.set("Radius", _f(p.r * TO_MM))
        c.set("Filled", "Solid" if p.fill and p.fill.lower() not in ("#ffffff",) else "Transparent")
        _presentation(c, p.stroke or p.fill, p.width, p.dash)
        x, y = p.pts[0]
        _position(c, x * TO_MM - dx, y * TO_MM - dy)
        return
    pts = _circle_pts(p.pts[0][0], p.pts[0][1], p.r) if p.kind == "circle" else list(p.pts)
    if p.closed and pts[0] != pts[-1]:
        pts.append(pts[0])
    if not p.stroke and p.fill:  # filled-only shapes (arrow heads, dots) keep their outline
        pass
    pl = etree.SubElement(parent, "PolyLine")
    pl.set("NumPoints", str(len(pts)))
    _presentation(pl, p.stroke or p.fill, p.width, p.dash)
    for x, y in pts:
        _coord(pl, x * TO_MM - dx, y * TO_MM - dy)


def _index(root: etree._Element) -> dict[str, list[etree._Element]]:
    idx: dict[str, list[etree._Element]] = defaultdict(list)
    for ga in root.iter("GenericAttribute"):
        if ga.get("Name") == "TopologyId":
            el = ga.getparent().getparent()
            idx[ga.get("Value")].append(el)
    return idx


def _tee_index(el: etree._Element) -> int:
    for ga in el.iter("GenericAttribute"):
        if ga.get("Name") == "TeeIndex":
            return int(ga.get("Value"))
    return 0


def _line_coordinates(os_: OneSheet, d: OneSheetDrawing) -> dict[str, list[tuple[float, float]]]:
    """Sheet coordinates (points) of every topology line, split at its inline valves."""
    s, ox, oy = d.transform

    def page(p: tuple[float, float]) -> tuple[float, float]:
        return ox + s * p[0], oy - s * p[1]

    edges = {e.id: e for e in os_.layout.edges}
    out: dict[str, list[tuple[float, float]]] = {}
    for e in os_.layout.edges:
        if e.id.endswith("~x") or e.id.endswith("~in") or not e.line_ids or len(e.path) < 2:
            continue
        path = list(e.path)
        if e.dst[0].startswith("t:out:"):  # continues across the sheet and into the target zone
            for suffix in ("~x", "~in"):
                nxt = edges.get(e.id + suffix)
                if nxt is not None and nxt.path:
                    path += nxt.path[1:] if nxt.path[0] == path[-1] else nxt.path
        pieces = _split(path, [(x, y) for _, x, y, _ in e.symbols])
        for lid, piece in zip(e.line_ids, pieces):
            if len(piece) >= 2:
                out[lid] = [page(q) for q in piece]
    return out


def _split(path: list[tuple[float, float]], cuts: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Cut a polyline at points lying on it (valve positions), in order along the path."""
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + math.dist(a, b))

    def param(c: tuple[float, float]) -> float:
        best = (1e18, 0.0)
        for i, (a, b) in enumerate(zip(path, path[1:])):
            L = math.dist(a, b) or 1e-9
            t = max(0.0, min(1.0, ((c[0] - a[0]) * (b[0] - a[0]) + (c[1] - a[1]) * (b[1] - a[1])) / (L * L)))
            q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            dd = math.dist(q, c)
            if dd < best[0] - 1e-9:
                best = (dd, cum[i] + t * L)
        return best[1]

    def at(u: float) -> tuple[float, float]:
        for i in range(len(path) - 1):
            if cum[i + 1] >= u - 1e-9:
                L = cum[i + 1] - cum[i] or 1e-9
                t = (u - cum[i]) / L
                a, b = path[i], path[i + 1]
                return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        return path[-1]

    bounds = [0.0] + sorted(param(c) for c in cuts) + [cum[-1]]
    pieces = []
    for u0, u1 in zip(bounds, bounds[1:]):
        pts = [at(u0)] + [path[i] for i in range(len(path)) if u0 + 1e-6 < cum[i] < u1 - 1e-6] + [at(u1)]
        pieces.append(pts)
    return pieces


def add_graphics(xml_path: str | Path, d: OneSheetDrawing, os_: OneSheet, topo: Any, style_colors: Any) -> dict[str, int]:
    """Add the drawing to an exported Proteus file in place; returns counts for the report."""
    xml_path = Path(xml_path)
    tree = etree.parse(str(xml_path))
    root = tree.getroot()
    idx = _index(root)
    s, ox, oy = d.transform
    stats = defaultdict(int)

    def anchor_mm(a: tuple[float, float]) -> tuple[float, float]:
        return (ox + s * a[0]) * TO_MM, (oy - s * a[1]) * TO_MM

    by_owner: dict[tuple[str, str], dict[str, list[Prim]]] = defaultdict(lambda: defaultdict(list))
    anchors: dict[tuple[str, str], tuple[float, float]] = {}
    sheet_prims: list[Prim] = []
    free_labels: dict[tuple[str, str], list[Prim]] = defaultdict(list)
    for p in d.prims:
        o = p.owner
        if o.kind == "sheet":
            sheet_prims.append(p)
        elif o.kind in ("zone", "hold", "signal"):
            free_labels[(o.kind, o.ref)].append(p)
        else:
            key = (o.kind, o.ref)
            by_owner[key][o.role].append(p)
            if o.role == "symbol" and o.anchor is not None:
                anchors[key] = o.anchor

    # ---- drawing + catalogue
    plant_info = root.find("PlantInformation")
    pos_after = list(root).index(plant_info) + 1 if plant_info is not None else 0
    W, H = d.page
    drawing = etree.Element("Drawing")
    drawing.set("Name", topo.metadata.drawing_id)
    drawing.set("Type", "PID")
    drawing.set("Title", topo.metadata.title)
    drawing.set("Size", "A0")
    bg = etree.SubElement(drawing, "Presentation")  # background colour only
    for k in ("R", "G", "B"):
        bg.set(k, "1")
    ext = etree.SubElement(drawing, "Extent")
    mn = etree.SubElement(ext, "Min")
    mn.set("X", "0")
    mn.set("Y", "0")
    mn.set("Z", "0")
    mx = etree.SubElement(ext, "Max")
    mx.set("X", _f(W * TO_MM))
    mx.set("Y", _f(H * TO_MM))
    mx.set("Z", "0")
    border = etree.SubElement(drawing, "DrawingBorder")
    border.set("ID", "DrawingBorder-1")
    border.set("ComponentClass", "DrawingBorder")
    for p in sheet_prims:
        _emit(border, p, circles=False)
    n_lab = 0
    for (kind, ref), prims in sorted(free_labels.items()):
        n_lab += 1
        lab = etree.SubElement(drawing, "Label")
        lab.set("ID", f"{'NoteIdentifierLabel' if kind == 'hold' else 'Label'}-{kind}.{n_lab}")
        lab.set("ComponentClass", "Label")
        lab.set("ComponentName", f"{kind}:{ref}")
        for p in prims:
            _emit(lab, p, circles=False)
    root.insert(pos_after, drawing)
    catalogue = etree.Element("ShapeCatalogue")
    catalogue.set("Name", "pid_workflow ISO 10628 / ISA 5.1 symbols")
    root.insert(pos_after + 1, catalogue)
    shapes: dict[tuple, str] = {}

    def shape_for(tag: str, cls: str, prims: list[Prim], ax: float, ay: float) -> str:
        key = (tag, cls, tuple((p.kind, tuple((round(x * TO_MM - ax, 1), round(y * TO_MM - ay, 1)) for x, y in p.pts), round(p.r, 1), p.closed,
                                p.stroke, p.fill, round(p.width, 2), p.dash) for p in prims))
        if key in shapes:
            return shapes[key]
        name = f"{cls}-{sum(1 for k in shapes if k[1] == cls) + 1}"
        shapes[key] = name
        sh = etree.SubElement(catalogue, tag)
        sh.set("ID", f"Shape-{name}")
        sh.set("ComponentClass", cls)
        sh.set("ComponentName", name)
        for p in prims:
            _emit(sh, p, ax, ay)
        stats["shapes"] += 1
        return name

    label_no = defaultdict(int)

    def add_labels(el: etree._Element, kind: str, prims: list[Prim]) -> None:
        if not prims:
            return
        cls = LABEL_CLASS.get(kind, "Label")
        label_no[cls] += 1
        lab = etree.SubElement(el, "Label")
        lab.set("ID", f"{cls}-{label_no[cls]}")
        lab.set("ComponentClass", cls)
        for p in prims:
            _emit(lab, p, circles=False)
        stats["labels"] += 1
        if kind == "line":
            stats["segment_labels"] += 1

    for (kind, ref), roles in by_owner.items():
        if kind == "line":
            continue
        targets = idx.get(ref, [])
        if kind == "manifold":
            tees = sorted([t for t in targets if t.get("ComponentClass") == "PipeTee"], key=_tee_index)
            if tees:
                add_labels(tees[0], kind, roles.get("label", []) + roles.get("symbol", []))
            continue
        el = next((t for t in targets if t.tag in ("Equipment", "PipingComponent", "ProcessInstrumentationFunction", "PipeOffPageConnector")), None)
        if el is None:
            stats["unplaced"] += 1
            continue
        sym = [p for p in roles.get("symbol", []) if p.kind != "text"]
        lab = [p for p in roles.get("symbol", []) if p.kind == "text"] + roles.get("label", [])
        if sym and (kind, ref) in anchors:
            ax, ay = anchor_mm(anchors[(kind, ref)])
            name = shape_for(el.tag, el.get("ComponentClass") or el.tag, sym, ax, ay)
            el.set("ComponentName", name)
            _position(el, ax, ay, index=0)
            stats["placed"] += 1
        add_labels(el, kind, lab)

    # ---- pipes: centre-line coordinates
    coords = _line_coordinates(os_, d)
    line_style: dict[str, tuple[str | None, float, tuple]] = {}
    for p in d.prims:
        if p.owner.kind == "line" and p.owner.role == "line" and p.kind == "poly":
            line_style.setdefault(p.owner.ref, (p.stroke, p.width, p.dash))
    edge_of_line: dict[str, MEdge] = {}
    for e in os_.layout.edges:
        for lid in e.line_ids:
            edge_of_line.setdefault(lid, e)
    for lid, pts in coords.items():
        cls = [t for t in idx.get(lid, []) if t.tag == "CenterLine"]
        if not cls:
            continue
        e = edge_of_line[lid]
        color, width, dash = line_style.get(e.id, ("#000000", 1.0, ()))
        cl = cls[0]
        pres = _presentation(etree.Element("x"), color, width, dash)
        cl.insert(0, pres)
        for i, (x, y) in enumerate(pts):
            c = etree.Element("Coordinate")
            c.set("X", _f(x * TO_MM))
            c.set("Y", _f(y * TO_MM))
            c.set("Z", "0")
            cl.insert(1 + i, c)
        stats["centerlines"] += 1
    # line-number labels go on the segment of the line they name
    for (kind, ref), roles in by_owner.items():
        if kind != "line" or not roles.get("label"):
            continue
        e = next((x for x in os_.layout.edges if x.id == ref), None)
        lid = (e.line_ids[0] if e and e.line_ids else ref.split("~")[0])
        cls = [t for t in idx.get(lid, []) if t.tag == "CenterLine"]
        if cls:
            add_labels(cls[0].getparent(), "line", roles["label"])
    tree.write(str(xml_path), xml_declaration=True, encoding="utf-8", pretty_print=True)
    stats["drawing_labels"] = n_lab
    stats["border_primitives"] = len(sheet_prims)
    return dict(stats)


def verify_graphics(xml_path: str | Path, stats: dict[str, int]) -> list[tuple[str, bool, str]]:
    """Re-load the file with pyDEXPI and check that the drawing came through."""
    import warnings

    from pydexpi.dexpi_classes import graphics as g
    from pydexpi.loaders import ProteusSerializer

    xml_path = Path(xml_path)
    out: list[tuple[str, bool, str]] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ser = ProteusSerializer()
        model = ser.load(xml_path.parent, xml_path.name)
    errs = [e for e in ser.proteus_loader.get_error_registry().errors if "ERROR" in str(e.level) or "CRITICAL" in str(e.level)]
    dg = model.diagram
    out.append(("pyDEXPI loads the Drawing (Diagram with A0 extent)", dg is not None and dg.maxX > 1000, f"{dg.name if dg else None}: {dg.maxX if dg else 0:.0f} × {dg.maxY if dg else 0:.0f} mm"))
    usages = connectors = labels = 0
    missing_shape = 0

    def walk(o: Any) -> None:
        nonlocal usages, connectors, labels, missing_shape
        if isinstance(o, g.ShapeUsage):
            usages += 1
            missing_shape += o.shape is None
        elif isinstance(o, g.ConnectorLine):
            connectors += 1
        elif isinstance(o, g.Label):
            labels += 1
        for ch in (getattr(o, "groups", None) or []) + (getattr(o, "elements", None) or []):
            walk(ch)

    if dg is not None:
        for grp in dg.groups:
            walk(grp)
    out.append(("every placed symbol is a shape usage that resolves in the ShapeCatalogue", usages >= stats.get("placed", 0) and missing_shape == 0,
                f"{usages} shape usages (written {stats.get('placed', 0)}), {missing_shape} unresolved, {stats.get('shapes', 0)} catalogue shapes"))
    out.append(("every routed pipe is a connector line", connectors >= stats.get("centerlines", 0), f"{connectors} connector lines (written {stats.get('centerlines', 0)})"))
    seg = stats.get("segment_labels", 0)
    expected = stats.get("labels", 0) - seg + stats.get("drawing_labels", 0)
    out.append(("tags and texts are labels", labels >= expected,
                f"{labels} labels loaded (expected {expected}); the {seg} line-number labels sit on their PipingNetworkSegment as DEXPI "
                "specifies, which pyDEXPI 1.2 does not read back"))
    out.append(("pyDEXPI loader: no errors with graphics", not errs, f"{len(errs)} error(s)"))
    return out


def render_svg(xml_path: str | Path, svg_path: str | Path) -> Path:
    """pyDEXPI's own SVG rendering of the DEXPI drawing (independent check of the exported graphics)."""
    import warnings

    from pydexpi.loaders import ProteusSerializer
    from pydexpi.loaders.svg_loader import DrawDiagram

    xml_path, svg_path = Path(xml_path), Path(svg_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ProteusSerializer().load(xml_path.parent, xml_path.name)
    DrawDiagram(model.diagram).save_svg(svg_path.stem, str(svg_path))
    return svg_path
