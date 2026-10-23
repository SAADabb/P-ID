"""DEXPI export: the XML must re-load with pyDEXPI and preserve the intended graph."""

import re
from pathlib import Path

import pytest
from pydexpi.loaders import ProteusSerializer

from pid_workflow.export_dexpi import LIFECYCLE_ATTR, export_topology, manifold_layout
from pid_workflow.roundtrip import verify_roundtrip


@pytest.fixture(scope="module")
def exported(enriched, tmp_path_factory):
    topo, _ = enriched
    path = tmp_path_factory.mktemp("xml") / "pid.xml"
    res = export_topology(topo, path)
    return topo, res, path


def test_roundtrip_passes(exported):
    topo, _, path = exported
    rep = verify_roundtrip(topo, path)
    failed = [c for c in rep.checks if not c.ok]
    assert rep.ok and not failed, [(c.name, c.detail) for c in failed] + rep.loader_errors
    assert rep.stats["lines"] == len(topo.process_lines)


def test_pydexpi_loads_equipment_piping_and_instrumentation(exported):
    topo, _, path = exported
    ser = ProteusSerializer()
    model = ser.load(path.parent, path.name)
    cm = model.conceptualModel
    assert len(cm.taggedPlantItems) == len(topo.equipment)
    assert sum(len(s.segments) for s in cm.pipingNetworkSystems) > 50
    assert len(cm.processInstrumentationFunctions) == len(topo.instruments)
    assert len(cm.instrumentationLoopFunctions) == 1
    assert not [e for e in ser.proteus_loader.get_error_registry().errors if "ERROR" in str(e.level)]


def test_every_pipe_segment_has_a_service_and_future_pacs_are_dashed_via_lifecycle(exported):
    _, _, path = exported
    xml = path.read_text(encoding="utf-8")
    segs = re.findall(r"<PipingNetworkSegment .*?</PipingNetworkSegment>", xml, flags=re.S)
    assert segs and all('Name="Service"' in s for s in segs)
    assert xml.count(f'Name="{LIFECYCLE_ATTR}"') >= 45
    assert len(re.findall(rf'Name="{LIFECYCLE_ATTR}"[^>]*Value="Future"', xml)) == 2  # PAC 3A / 3B


def test_unknown_values_stay_empty_in_the_xml(exported):
    _, _, path = exported
    xml = path.read_text(encoding="utf-8")
    assert "SubTagNameAssignmentClass" not in xml  # no nozzle numbers
    assert "FailAction" not in xml and "failAction" not in xml  # no failure positions
    assert 'Name="NominalSize"' in xml  # only the DN50 nozzles of the TGE coil


def test_roundtrip_detects_a_corrupted_file(exported, tmp_path):
    topo, _, path = exported
    xml = path.read_text(encoding="utf-8")
    # point one external segment end at the wrong tee node
    bad = xml.replace('ToNode="3"', 'ToNode="2"', 1)
    assert bad != xml
    p2 = tmp_path / "bad.xml"
    p2.write_text(bad, encoding="utf-8")
    assert not verify_roundtrip(topo, p2).ok


def test_roundtrip_detects_a_missing_component(exported, tmp_path):
    topo, _, path = exported
    xml = path.read_text(encoding="utf-8")
    bad = xml.replace('Value="eq.well_pump_a"', 'Value="eq.renamed"', 1)
    p2 = tmp_path / "bad2.xml"
    p2.write_text(bad, encoding="utf-8")
    rep = verify_roundtrip(topo, p2)
    assert not rep.ok


def test_manifold_tee_chain_layout():
    assert manifold_layout("split", 3) == [
        {"run_in": "common", "run_out": "tee:2", "branch": "b1"},
        {"run_in": "tee:1", "run_out": "b3", "branch": "b2"},
    ]
    assert manifold_layout("merge", 3) == [
        {"run_in": "b1", "run_out": "tee:2", "branch": "b2"},
        {"run_in": "tee:1", "run_out": "common", "branch": "b3"},
    ]
    assert manifold_layout("split", 2) == [{"run_in": "common", "run_out": "b2", "branch": "b1"}]


def test_export_limitations_are_reported(exported):
    _, res, _ = exported
    text = " ".join(res.report.limitations)
    assert "LifeCyclePhase" in text and "CustomEquipment" in text and "nozzle" in text.lower()


def test_export_is_reproducible_and_ids_are_traceable(enriched, tmp_path, monkeypatch):
    topo, _ = enriched
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1760000000")
    a, b = tmp_path / "a.xml", tmp_path / "b.xml"
    export_topology(topo, a)
    export_topology(topo, b)
    assert a.read_bytes() == b.read_bytes()
    xml = a.read_text(encoding="utf-8")
    assert 'ID="CentrifugalPump-eq.well_pump_a"' in xml and 'ID="PipeTee-mf.wp_s.tee1"' in xml
