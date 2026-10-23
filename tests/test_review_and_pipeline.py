"""Review workflow, end-to-end pipeline, and reuse with a project that has nothing to do with LPF/BSST."""

import json
from pathlib import Path

import yaml
from pypdf import PdfReader

from pid_workflow import review
from pid_workflow.enrich import enrich
from pid_workflow.pipeline import SourceChanged, load_project, run_all
from pid_workflow.policy import load_policy
from pid_workflow.schema import Topology
from pid_workflow.topology_io import dumps_topology, load_topology, save_topology
from pid_workflow.validate import validate

from .conftest import ROOT


def test_approve_then_reject_then_rerun(enriched, policy):
    import copy

    topo = copy.deepcopy(enriched[0])
    pend = review.pending_ids(topo, rule="pump.auxiliaries")
    assert pend
    res = review.approve(topo, rule="pump.auxiliaries")
    assert set(res.approved) == set(pend)
    assert review.pending_ids(topo, rule="pump.auxiliaries") == []
    # reject an inline valve: the source line comes back and the valve is not proposed again
    n_lines = len(topo.process_lines)
    r = review.reject(topo, ["pc.gen.well_pump_a.suction_isolation"])
    assert r.rejected == ["pc.gen.well_pump_a.suction_isolation"]
    assert len(topo.process_lines) == n_lines - 1
    assert validate(topo).ok
    enrich(topo, policy)
    assert "pc.gen.well_pump_a.suction_isolation" not in {c.id for c in topo.components}
    # approved items stay approved on re-application
    assert review.pending_ids(topo, rule="pump.auxiliaries") == []


def test_full_pipeline_writes_all_outputs(project_copy: Path):
    res = run_all(project_copy)
    assert res.validation.ok and res.roundtrip.ok and res.idempotent
    assert all(not v for v in res.qa.values())
    out, rep = project_copy / "output", project_copy / "reports"
    assert (out / "pid_review_draft.pdf").stat().st_size > 50_000
    assert (out / "pid_draft.proteus.xml").stat().st_size > 100_000
    assert len(PdfReader(str(out / "pid_review_draft.pdf")).pages) >= 12
    for name in ("summary", "validation", "roundtrip", "enrichment", "proposals", "unresolved_requirements", "assumptions", "operating_modes", "export_limitations", "layout"):
        assert (rep / f"{name}.md").read_text(encoding="utf-8").strip(), name
    assert "PASS" in (rep / "roundtrip.md").read_text(encoding="utf-8")
    assert (project_copy / "working_topology.json").exists()


def test_rerun_is_stable_and_source_change_is_detected(project_copy: Path):
    run_all(project_copy, render=False)
    first = (project_copy / "working_topology.json").read_text(encoding="utf-8")
    run_all(project_copy, render=False)
    assert (project_copy / "working_topology.json").read_text(encoding="utf-8") == first
    # editing the frozen source snapshot must be noticed
    src = project_copy / "source_topology.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    data["metadata"]["revision"] = "B"
    src.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        run_all(project_copy, render=False)
    except SourceChanged:
        pass
    else:
        raise AssertionError("a changed source snapshot must stop the run")
    run_all(project_copy, render=False, rebuild=True)


def test_source_snapshot_file_is_never_modified_by_the_pipeline(project_copy: Path):
    src = project_copy / "source_topology.json"
    before = src.read_bytes()
    run_all(project_copy, render=False)
    assert src.read_bytes() == before


# ---------------------------------------------------------------- a second, unrelated project
def _mini_source() -> dict:
    def prov(page=1, sec="1"):
        return {"origin": "source", "document": "mini.pdf", "page": page, "section": sec, "basis": "explicit"}

    def eq(id_, cls, tag, nozzles, area="a1"):
        return {"id": id_, "name": id_, "tag": tag, "tag_status": "source" if tag else "none", "model_class": cls, "area": area,
                "lifecycle": "new", "nozzles": [{"name": n, "role": r, "number": None, "size": None, "service": None} for n, r in nozzles],
                "attributes": {}, "provenance": prov()}

    def line(id_, a, b, svc="Water", header=False):
        return {"id": id_, "name": None, "service": svc, "from": {"ref": a[0], "port": a[1]}, "to": {"ref": b[0], "port": b[1]}, "logical_line": id_,
                "split_from": None, "line_number": None, "header": header, "properties": {}, "provenance": prov(), "attributes": {}}

    return {
        "schema_version": "1.0",
        "metadata": {"drawing_id": "MINI-1", "title": "Mini plant", "project": "Mini", "revision": "A", "language": "en",
                     "source_documents": [{"id": "d", "file": "mini.pdf", "pages": 1, "language": "en"}], "engineering_basis": []},
        "areas": [{"id": "a1", "name": "Mini area", "description": None, "provenance": prov()}],
        "equipment": [eq("eq.t1", "Tank", "T-1", [("out", "outlet")]), eq("eq.p1", "CentrifugalPump", "P-1", [("s", "suction"), ("d", "discharge")]),
                      eq("eq.t2", "Tank", None, [("in", "inlet")])],
        "components": [{"id": "pc.cv", "name": "Level control valve", "kind": "valve", "model_class": "CustomOperatedValve", "function": "control",
                        "technology": None, "technology_status": "unspecified_generic", "operation": "automated", "tag": None, "tag_status": "none",
                        "area": "a1", "provenance": prov(), "attributes": {}}],
        "boundaries": [], "instruments": [],
        "process_lines": [line("ln.1", ("eq.t1", "out"), ("eq.p1", "s")), line("ln.2", ("eq.p1", "d"), ("pc.cv", "in"), header=True), line("ln.3", ("pc.cv", "out"), ("eq.t2", "in"))],
        "signals": [], "control_requirements": [], "control_loops": [], "operating_modes": [], "unresolved_requirements": [], "modifications": [],
    }


MINI_RULES = [
    {"id": "pump.auxiliaries", "type": "pump_auxiliaries", "source": {"page": 1, "section": "1"},
     "params": {"applies_to_classes": ["CentrifugalPump"], "suction_nozzle_role": "suction", "discharge_nozzle_role": "discharge",
                "suction": [{"function": "isolation", "operation": "manual"}],
                "discharge": [{"function": "check", "operation": "unknown"}, {"function": "isolation", "operation": "manual"}]}},
    {"id": "control_valve.manifold", "type": "control_valve_manifold", "source": {"page": 1, "section": "1"},
     "params": {"applies_to_function": "control", "upstream_isolation": {"function": "isolation", "operation": "unknown"},
                "downstream_isolation": {"function": "isolation", "operation": "unknown"}, "purge": {"function": "purge", "operation": "unknown"},
                "bypass_valve": {"function": "bypass", "model_class": "GlobeValve", "operation": "unknown"}}},
    {"id": "vessel.auxiliaries", "type": "vessel_auxiliaries", "source": {"page": 1, "section": "1"},
     "params": {"applies_to_classes": ["Tank", "Vessel"], "include_existing": True, "drain": {"function": "drain", "operation": "unknown"},
                "vent": {"function": "vent", "operation": "unknown"}, "level": {"isa_code": "LT", "measured_variable": "level"}}},
    {"id": "control_loop.from_requirement", "type": "control_loop", "source": {"page": 1, "section": "1"},
     "params": {"controller_code": {"pressure": "PIC", "temperature": "TIC", "level": "LIC"}}},
    {"id": "tagging.isa", "type": "tagging", "source": {"page": 1, "section": "1"}, "params": {"tag_untagged_source_control_valves": True}},
    {"id": "unresolved.generated", "type": "unresolved_summary", "source": {}, "params": {}},
]


def _mini_project(tmp: Path) -> Path:
    shutil_policies = tmp / "policies"
    shutil_policies.mkdir()
    for f in ("generic.yaml", "rendering.yaml"):
        (shutil_policies / f).write_text((ROOT / "policies" / f).read_text(encoding="utf-8"), encoding="utf-8")
    proj = tmp / "projects" / "mini"
    proj.mkdir(parents=True)
    topo = Topology.model_validate(_mini_source())
    save_topology(topo, proj / "source_topology.json")
    (proj / "project.yaml").write_text(yaml.safe_dump({
        "name": "mini", "source_document": "mini.pdf", "source_topology": "source_topology.json", "working_topology": "working_topology.json",
        "rules": "project_rules.yaml", "layout_hints": "layout_hints.yaml", "generic_policy": "../../policies/generic.yaml",
        "rendering": "../../policies/rendering.yaml", "output_dir": "output", "reports_dir": "reports"}), encoding="utf-8")
    rules = {"project": "mini", "document": "mini.pdf", "rules": MINI_RULES}
    (proj / "project_rules.yaml").write_text(yaml.safe_dump(rules), encoding="utf-8")
    return proj


def test_the_workflow_is_reusable_for_another_specification(tmp_path):
    proj = _mini_project(tmp_path)
    res = run_all(proj)
    topo = res.topology
    assert res.validation.ok and res.roundtrip.ok and res.idempotent
    ids = {c.id for c in topo.components}
    assert {"pc.gen.p1.suction_isolation", "pc.gen.p1.discharge_check", "pc.gen.p1.discharge_isolation"} <= ids
    assert {"pc.gen.cv.iso_up", "pc.gen.cv.iso_dn", "pc.gen.cv.byp_valve", "pc.gen.cv.purge"} <= ids
    assert {"pc.gen.t1.drain", "pc.gen.t1.vent", "pc.gen.t2.drain"} <= ids
    assert [i.isa_code for i in topo.instruments if i.measured_variable == "level"] == ["LT", "LT"]
    # no control requirement in this spec -> no controller, however many transmitters exist
    assert not topo.control_loops and not any(i.function == "controller" for i in topo.instruments)
    assert (proj / "output" / "pid_review_draft.pdf").exists()
