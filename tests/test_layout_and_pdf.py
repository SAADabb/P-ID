"""Layout is deterministic, collision-free and never leaks into the topology; the PDF renders."""

import json

from pypdf import PdfReader

from pid_workflow.layout import build_layouts, layout_qa
from pid_workflow.render_pdf import render_review_pdf
from pid_workflow.topology_io import dumps_topology

from .conftest import ROOT


def _snapshot(dl):
    return json.dumps([{n.id: (round(n.x, 3), round(n.y, 3)) for n in s.nodes.values()} for s in dl.sheets], sort_keys=True)


def test_layout_is_deterministic(enriched, hints):
    topo, _ = enriched
    assert _snapshot(build_layouts(topo, hints)) == _snapshot(build_layouts(topo, hints))


def test_layout_has_no_overlaps(enriched, hints):
    topo, _ = enriched
    dl = build_layouts(topo, hints)
    problems = [m for s in dl.sheets for m in layout_qa(s)]
    assert problems == []


def test_every_object_is_drawn_exactly_once(enriched, hints):
    topo, _ = enriched
    dl = build_layouts(topo, hints)
    drawn = {n.id for s in dl.sheets for n in s.nodes.values() if not n.id.startswith("x:")}
    expected = {e.id for e in topo.equipment} | {b.id for b in topo.boundaries} | {c.id for c in topo.components if c.kind == "manifold"}
    assert drawn == expected
    symbols = [c.id for s in dl.sheets for e in s.edges for c, *_ in e.symbols]
    valves = [c.id for c in topo.components if c.kind != "manifold"]
    assert sorted(symbols) == sorted(valves)  # each valve once
    lines = {lid for s in dl.sheets for e in s.edges for lid in e.line_ids}
    assert lines == {l.id for l in topo.process_lines}


def test_cross_sheet_lines_have_both_off_page_ends(enriched, hints):
    topo, _ = enriched
    dl = build_layouts(topo, hints)
    outs = {n.id[len("x:out:"):] for s in dl.sheets for n in s.nodes.values() if n.id.startswith("x:out:")}
    ins = {n.id[len("x:in:"):] for s in dl.sheets for n in s.nodes.values() if n.id.startswith("x:in:")}
    assert outs == ins and outs  # every outgoing reference has its matching incoming one


def test_topology_json_has_no_coordinates(enriched, hints):
    topo, _ = enriched
    before = dumps_topology(topo)
    build_layouts(topo, hints)
    assert dumps_topology(topo) == before  # laying out does not touch the topology
    for key in ('"x":', '"y":', '"coordinates"', '"position"'):
        assert key not in before


def test_pdf_renders_with_cover_overview_sheets_and_tables(enriched, hints, tmp_path):
    topo, _ = enriched
    dl = build_layouts(topo, hints)
    out = tmp_path / "review.pdf"
    scales = render_review_pdf(topo, dl, out, ROOT / "policies" / "rendering.yaml", {"validation_ok": True, "roundtrip_ok": True})
    r = PdfReader(str(out))
    assert len(r.pages) >= 2 + len(dl.sheets) + 3
    text = r.pages[0].extract_text()
    assert "Draft P&ID" in text and "NOT FOR CONSTRUCTION" in text
    # drawings are large enough to read: no sheet is shrunk below 65 %
    assert all(s >= 0.65 for s in scales.values()), scales
