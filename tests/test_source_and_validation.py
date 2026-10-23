"""The extracted source topology: provenance, identifiers, and the validator itself."""

import copy

import pytest

from pid_workflow.schema import Topology
from pid_workflow.topology_io import dumps_topology
from pid_workflow.validate import validate


def test_source_topology_is_valid(source):
    rep = validate(source)
    assert rep.ok, [i.message for i in rep.errors]


def test_every_source_object_points_to_page_and_section(source):
    for oid, o in source.objects().items():
        p = o.provenance
        assert p.origin == "source", oid
        assert p.document and p.page in (1, 2, 3) and p.section, oid


def test_source_has_no_generated_content_or_coordinates(source):
    text = dumps_topology(source)
    for forbidden in ('"x":', '"y":', '"position"', '"coordinates"'):
        assert forbidden not in text
    assert not source.instruments and not source.signals and not source.control_loops
    assert all(o.provenance.origin == "source" for o in source.objects().values())


def test_real_tags_from_the_pdf_are_present_and_unmodified(source):
    tags = {e.tag for e in source.equipment if e.tag}
    assert {"P-030", "P-031", "P-032", "P-033", "P-034", "P-035", "ECH-030", "ECH-031", "ECH-032", "TK-001", "TK-002"} <= tags
    assert all(e.tag_status == "source" for e in source.equipment if e.tag)


def test_nozzle_numbers_and_sizes_are_never_invented(source):
    for e in source.equipment:
        for n in e.nozzles:
            assert n.number is None
    coil = next(e for e in source.equipment if e.id == "eq.bsst_tge_coil")
    assert all(n.size and n.size.value == "DN50" for n in coil.nozzles)  # the only sizes the PDF gives


def test_unknowns_are_unresolved_requirements(source):
    ids = {u.id for u in source.unresolved_requirements}
    for needed in ("ur.degasser_steam", "ur.spill_control", "ur.cascade_2a_2b", "ur.ech_position", "ur.future_hp", "ur.design_data"):
        assert needed in ids


def test_validator_detects_broken_topologies(source):
    topo = copy.deepcopy(source)
    topo.process_lines[1].from_ = topo.process_lines[0].from_  # two lines leave the same port
    codes = {i.code for i in validate(topo).errors}
    assert "PORT_REUSED" in codes

    topo = copy.deepcopy(source)
    topo.process_lines[0].to.ref = "eq.does_not_exist"
    assert "LINE_ENDPOINT" in {i.code for i in validate(topo).errors}

    topo = copy.deepcopy(source)
    topo.equipment[0].model_class = "FluxCapacitor"
    assert "CLASS_UNSUPPORTED" in {i.code for i in validate(topo).errors}

    topo = copy.deepcopy(source)
    topo.equipment[1].id = topo.equipment[0].id
    assert "ID_DUPLICATE" in {i.code for i in validate(topo).errors}

    topo = copy.deepcopy(source)
    ln = next(l for l in topo.process_lines if l.from_.ref == "eq.well_pump_a")
    ln.from_.port, ln.to.port = ln.to.port, ln.from_.port  # swap directions on a pump line
    assert "FLOW_DIRECTION" in {i.code for i in validate(topo).errors} or "LINE_PORT" in {i.code for i in validate(topo).errors}


def test_schema_rejects_unknown_fields(source):
    data = source.model_dump(mode="json", by_alias=True)
    data["equipment"][0]["x"] = 10  # coordinates do not belong in the topology
    with pytest.raises(Exception):
        Topology.model_validate(data)
