"""Geometric checks and the repair router on small hand-made sheets."""

from __future__ import annotations

from pid_workflow import geomqa
from pid_workflow.graphics import Owner, Prim
from pid_workflow.layout import MEdge, MNode, SheetLayout
from pid_workflow.repair import bad_edges, repair_sheet


def _box(id_: str, x: float, y: float, ports: dict[str, tuple[str, float]]) -> MNode:
    return MNode(id_, "equipment", w=50, h=40, x=x, y=y, ports=ports, symbol="box")


def _sheet() -> SheetLayout:
    """A -> C drawn straight through B, which sits in between."""
    a = _box("eq.a", 0, 0, {"out": ("R", 0.0)})
    b = _box("eq.b", 150, 0, {})
    c = _box("eq.c", 300, 0, {"in": ("L", 0.0)})
    e = MEdge("ln.1", ("eq.a", "out"), ("eq.c", "in"), path=[(25, 0), (275, 0)])
    return SheetLayout("ONE", "t", nodes={n.id: n for n in (a, b, c)}, edges=[e])


def test_pipe_through_equipment_is_found_and_rerouted():
    sl = _sheet()
    assert [i.kind for i in geomqa.check(sl)] == ["crosses"]
    assert bad_edges(sl) == sl.edges
    assert repair_sheet(sl) == 1
    assert geomqa.check(sl) == []
    e = sl.edges[0]
    # still orthogonal, still from nozzle to nozzle, leaving and entering horizontally
    assert e.path[0] == (25, 0) and e.path[-1] == (275, 0)
    assert all(abs(p[0] - q[0]) < 1e-6 or abs(p[1] - q[1]) < 1e-6 for p, q in zip(e.path, e.path[1:]))
    assert abs(e.path[1][1]) < 1e-6 and abs(e.path[-2][1]) < 1e-6


def test_shared_track_is_an_overlap():
    sl = _sheet()
    sl.nodes.pop("eq.b")
    sl.edges.append(MEdge("ln.2", ("eq.a", "out"), ("eq.c", "in"), path=[(60, 0), (200, 0)]))
    assert any(i.kind == "overlap" for i in geomqa.check(sl))


def test_text_on_a_foreign_pipe_and_on_text():
    pipe = Prim("poly", Owner("line", "ln.1", "line"), pts=[(0, 10), (200, 10)])
    tag = Prim("text", Owner("valve", "v1", "label"), pts=[(100, 12)], text="XV-1", size=6.6, font="Helvetica", align="c")
    other = Prim("text", Owner("valve", "v2", "label"), pts=[(104, 13)], text="XV-2", size=6.6, font="Helvetica", align="c")
    own = Prim("text", Owner("line", "ln.1", "label"), pts=[(30, 12)], text="DN100", size=6.4, font="Helvetica", align="c")
    found = [i.other for i in geomqa.text_check([pipe, tag, other, own])]
    assert "'XV-1' / line ln.1" in found and "'XV-1' / 'XV-2'" in found
    assert not any("DN100" in f for f in found)  # a line's own number may sit on it
    clear = Prim("text", Owner("valve", "v3", "label"), pts=[(100, 2)], text="XV-3", size=6.6, font="Helvetica", align="c")
    assert geomqa.text_check([pipe, clear]) == []  # text above the pipe (y down) does not touch it
