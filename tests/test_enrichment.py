"""Enrichment rules: what they add, what they must not add, and idempotence."""

import copy

from pid_workflow.enrich import enrich
from pid_workflow.topology_io import dumps_topology
from pid_workflow.validate import validate


def _chain_from(topo, ref, port):
    """Components met when walking away from a nozzle, in order."""
    by_from = {(l.from_.ref, l.from_.port): l for l in topo.process_lines}
    by_to = {(l.to.ref, l.to.port): l for l in topo.process_lines}
    comp = {c.id: c for c in topo.components}
    out = []
    if (ref, port) in by_from:
        cur = by_from[(ref, port)].to
        while cur.ref in comp and comp[cur.ref].kind != "manifold":
            out.append(comp[cur.ref])
            nxt = by_from.get((cur.ref, "out"))
            if not nxt:
                break
            cur = nxt.to
    else:
        cur = by_to[(ref, port)].from_
        while cur.ref in comp and comp[cur.ref].kind != "manifold":
            out.append(comp[cur.ref])
            nxt = by_to.get((cur.ref, "in"))
            if not nxt:
                break
            cur = nxt.from_
    return out


def test_enriched_topology_validates(enriched):
    topo, _ = enriched
    rep = validate(topo)
    assert rep.ok, [i.message for i in rep.errors]


def test_source_snapshot_object_is_untouched(source, enriched):
    topo, _ = enriched
    assert len(source.process_lines) == 110 and not source.instruments  # the fixture copy was enriched, not the source


def test_enrichment_is_idempotent(enriched, policy):
    topo, _ = enriched
    before = dumps_topology(topo)
    res = enrich(topo, policy)
    assert dumps_topology(topo) == before
    assert not any(e.action == "added" for e in res.log)


def test_pumps_get_suction_isolation_check_and_discharge_isolation(enriched):
    topo, _ = enriched
    pumps = [e for e in topo.equipment if e.model_class == "CentrifugalPump"]
    assert len(pumps) == 6
    for p in pumps:
        suction = _chain_from(topo, p.id, "suction")
        assert [c.function for c in suction] == ["isolation"], p.tag
        assert suction[0].operation == "manual"
        discharge = _chain_from(topo, p.id, "discharge")
        assert [c.function for c in discharge] == ["check", "isolation"], p.tag
        assert discharge[0].model_class == "CheckValve"


def test_every_control_valve_gets_a_full_manifold(enriched):
    topo, _ = enriched
    comp = {c.id: c for c in topo.components}
    cvs = [c for c in topo.components if c.function == "control"]
    assert len(cvs) == 3
    for cv in cvs:
        sl = cv.id.split(".", 1)[1]
        for part in ("iso_up", "iso_dn", "byp_valve", "purge", "byp_split", "byp_merge", "purge_tee"):
            assert f"pc.gen.{sl}.{part}" in comp, (cv.id, part)
        byp = comp[f"pc.gen.{sl}.byp_valve"]
        assert byp.model_class == "GlobeValve"
        assert comp[f"pc.gen.{sl}.purge"].open_end == "drain"
        # the bypass really connects the two bypass manifolds
        lines = {l.id: l for l in topo.process_lines}
        assert lines[f"ln.gen.{sl}.byp_in"].from_.ref == f"pc.gen.{sl}.byp_split"
        assert lines[f"ln.gen.{sl}.byp_out"].to.ref == f"pc.gen.{sl}.byp_merge"


def test_headers_get_pt_and_tt_without_duplicates(enriched):
    topo, _ = enriched
    headers = {"ln.h1", "ln.h4", "ln.h8", "ln.hw90", "ln.h105"}
    for h in headers:
        codes = [i.isa_code for i in topo.instruments if i.target == {"kind": "line", "ref": h}]
        assert sorted(codes) == ["PT", "TT"], h


def test_tanks_and_vessels_get_drain_vent_and_level(enriched):
    topo, _ = enriched
    caps = [e for e in topo.equipment if e.model_class in ("Tank", "Vessel") and e.lifecycle != "future"]
    assert len(caps) == 10
    for e in caps:
        sl = e.id.split(".", 1)[1]
        assert f"pc.gen.{sl}.drain" in {c.id for c in topo.components}
        assert f"pc.gen.{sl}.vent" in {c.id for c in topo.components}
        assert any(i.isa_code == "LT" and i.target and i.target["ref"] == e.id for i in topo.instruments)


def test_control_loop_only_where_the_source_states_one(enriched):
    topo, _ = enriched
    assert [lp.requirement for lp in topo.control_loops] == ["cr.boiler_backup"]
    lp = topo.control_loops[0]
    pt = next(i for i in topo.instruments if i.id == lp.measurement)
    pic = next(i for i in topo.instruments if i.id == lp.controller)
    assert pt.target == {"kind": "line", "ref": "ln.h8"} and pt.function == "transmitter"  # the header PT was reused
    assert pic.function == "controller" and lp.final_element == "pc.pcv_boiler"
    assert lp.setpoint.value == 7.5 and lp.setpoint.unit == "bar eff."
    # a transmitter alone never creates a controller: there is exactly one controller
    assert sum(1 for i in topo.instruments if i.function == "controller") == 1
    # the spill valves have no stated variable/setpoint -> no loop, but an unresolved requirement
    assert "ur.spill_control" in {u.id for u in topo.unresolved_requirements}
    assert not any(lp.final_element in ("pc.pcv_spill_8_4", "pc.pcv_spill_4_1") for lp in topo.control_loops)


def test_loop_numbers_are_shared(enriched):
    topo, _ = enriched
    pcv = next(c for c in topo.components if c.id == "pc.pcv_boiler")
    pt = next(i for i in topo.instruments if i.id == "in.h8.pt")
    pic = next(i for i in topo.instruments if i.function == "controller")
    assert pcv.tag.split("-")[1] == pt.tag.split("-")[1] == pic.tag.split("-")[1]


def test_additions_are_pending_review_with_full_provenance(enriched, source):
    topo, _ = enriched
    src_ids = set(source.objects())
    for oid, o in topo.objects().items():
        if oid in src_ids:
            continue
        p = o.provenance
        assert p.origin == "generated" and p.status == "pending_review", oid
        assert p.rule and p.triggers and p.explanation, oid


def test_nothing_forbidden_is_invented(enriched):
    topo, _ = enriched
    for c in topo.components:
        if c.provenance.origin == "generated":
            assert c.attributes.keys() <= {"type_name", "manifold_of"}  # no ratings, sizes, materials
        if c.technology_status == "unspecified_generic":
            assert c.technology is None and c.model_class == "CustomOperatedValve"
    for i in topo.instruments:
        assert not i.attributes  # no ranges
    for e in topo.equipment:
        for n in e.nozzles:
            if n.provenance and n.provenance.origin == "generated":
                assert n.number is None and n.size is None
    for ln in topo.process_lines:
        if ln.provenance.origin == "generated" and ln.split_from is None:
            assert not ln.properties  # new branch lines get no copied diameter
    ids = {u.id for u in topo.unresolved_requirements}
    assert {"ur.gen.valve_technology", "ur.gen.fail_position", "ur.gen.instrument_ranges", "ur.gen.nozzles"} <= ids


def test_splitting_preserves_service_and_properties(enriched, source):
    topo, _ = enriched
    originals = {l.id: l for l in source.process_lines}
    children = [l for l in topo.process_lines if l.split_from]
    assert children
    for ch in children:
        root = ch.split_from
        while root not in originals and "/" in root:
            root = root.rsplit("/", 1)[0]
        orig = originals[root]
        assert ch.service == orig.service
        assert {k: v.model_dump() for k, v in ch.properties.items()} == {k: v.model_dump() for k, v in orig.properties.items()}
        assert ch.header == orig.header and ch.logical_line == orig.logical_line


def test_existing_components_are_reused_not_duplicated(source, policy):
    """If a valid isolation valve already sits on a pump suction, the rule must reuse it."""
    topo = copy.deepcopy(source)
    pump = next(e for e in topo.equipment if e.id == "eq.well_pump_a")
    line = next(l for l in topo.process_lines if l.to.ref == pump.id and l.to.port == "suction")
    from pid_workflow.enrich import Enricher

    en = Enricher(topo, policy)
    rule = policy.rule("pump.auxiliaries")
    existing = en.make_valve("pc.manual_hv", "Existing hand valve", "isolation", "manual", rule, ["x"], "pre-existing", pump.area)
    existing.provenance = source.components[0].provenance  # looks like a source object
    en.insert_inline(line, existing, rule, "test")
    res = en.run()
    assert "pc.gen.well_pump_a.suction_isolation" not in {c.id for c in topo.components}
    assert any(e.action == "reused" and e.object_id == "pc.manual_hv" for e in res.log)


def test_rules_only_fire_when_prerequisites_hold(source, policy):
    topo = copy.deepcopy(source)
    # remove the discharge line of a pump: the rule must not invent connections
    pump = "eq.loop_pump_c"
    topo.process_lines = [l for l in topo.process_lines if not (l.from_.ref == pump and l.from_.port == "discharge")]
    res = enrich(topo, policy)
    assert any(e.action == "blocked" and e.object_id == pump for e in res.log)
    assert "pc.gen.loop_pump_c.discharge_check" not in {c.id for c in topo.components}


def test_tags_are_unique_proposed_and_leave_source_tags_alone(enriched, source):
    topo, _ = enriched
    tags = [o.tag for o in (*topo.equipment, *topo.components, *topo.instruments) if o.tag]
    assert len(tags) == len(set(tags))
    for e in source.equipment:
        assert next(x for x in topo.equipment if x.id == e.id).tag == e.tag
    for c in topo.components:
        if c.provenance.origin == "generated" and c.function:
            assert c.tag_status == "proposed"
    # tagging a source valve is recorded as a modification that keeps the old value
    mods = [m for m in topo.modifications if m.field == "tag"]
    assert {m.object_id for m in mods} >= {"pc.pcv_boiler", "pc.pcv_spill_8_4", "pc.pcv_spill_4_1"}
    assert all(m.old is None for m in mods)
