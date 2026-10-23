"""Round-trip verification: does the exported Proteus XML preserve the intended graph?

Two independent readers are used:

* **lxml** reads the XML itself and rebuilds, from the written elements only, the connection
  graph in topology terms (object + port).  This checks that the XML encodes the topology.
* **pyDEXPI** (``ProteusSerializer.load``) re-loads the same file.  Its connectivity (items and
  pipes) is compared with what lxml read, which checks that a real DEXPI parser interprets the
  file the way it was written, and that classes, tags and nozzles survive.

pyDEXPI 1.2.0 ignores custom attributes and the ``FromNode``/``ToNode`` indices when loading, so
everything that depends on them (topology ids, tee branches, services, provenance) is verified
at XML level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree
from pydexpi.dexpi_classes import pydantic_classes as pc
from pydexpi.loaders import ProteusSerializer

from .export_dexpi import LIFECYCLE_ATTR, SERVICE_ATTR, TOPO_ID_ATTR, manifold_layout
from .schema import Topology


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class RoundTripReport:
    checks: list[Check] = field(default_factory=list)
    loader_errors: list[str] = field(default_factory=list)
    loader_warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks) and not self.loader_errors

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, ok, detail))


def _custom(el: etree._Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for ga in el.findall("GenericAttributes"):
        if ga.get("Set") == "CustomAttributes":
            for a in ga:
                out[a.get("Name")] = a.get("Value", "")
    return out


def _dexpi(el: etree._Element, name: str) -> str | None:
    for ga in el.findall("GenericAttributes"):
        if ga.get("Set") == "DexpiAttributes":
            for a in ga:
                if a.get("Name") == name:
                    return a.get("Value")
    return None


def verify_roundtrip(topo: Topology, xml_path: str | Path) -> RoundTripReport:
    """Verify the exported XML; a damaged file yields failing checks, never an exception."""
    rep = RoundTripReport()
    try:
        _verify(topo, xml_path, rep)
    except Exception as exc:  # noqa: BLE001 - a corrupt file must be reported, not crash the pipeline
        rep.add("XML could be read and compared completely", False, f"{type(exc).__name__}: {exc}")
    return rep


def _verify(topo: Topology, xml_path: str | Path, rep: RoundTripReport) -> RoundTripReport:
    xml_path = Path(xml_path)
    tree = etree.parse(str(xml_path))
    root = tree.getroot()
    by_id = {e.get("ID"): e for e in root.iter() if e.get("ID")}

    # ================================================================ lxml reader
    parent_of_nozzle: dict[str, etree._Element] = {}
    for eq in root.findall("Equipment"):
        for nz in eq.findall("Nozzle"):
            parent_of_nozzle[nz.get("ID")] = eq

    def port_of(ref_id: str, node: str | None, as_source: bool, external: bool) -> tuple[str, str]:
        el = by_id[ref_id]
        cls = el.get("ComponentClass")
        c = _custom(el)
        if el.tag == "Nozzle":
            return _custom(parent_of_nozzle[ref_id])[TOPO_ID_ATTR], c["SchematicName"]
        if el.tag == "PipeOffPageConnector":
            return c[TOPO_ID_ATTR], "port"
        if cls == "PipeTee":
            k = int(c["TeeIndex"])
            lay = manifold_layout(c["ManifoldRole"], int(c["ManifoldBranches"]))[k - 1]
            idx = int(node) if (external and node) else (2 if as_source else 1)
            return c[TOPO_ID_ATTR], lay[("run_in", "run_out", "branch")[idx - 1]]
        return c[TOPO_ID_ATTR], "out" if as_source else "in"

    pipes: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {}
    pipe_item_edges: set[tuple[str, str]] = set()   # (source element ID, target element ID) for the loader comparison
    seg_services: dict[str, str] = {}
    seg_count = 0
    dup_pipes = []
    for seg in root.iter("PipingNetworkSegment"):
        seg_count += 1
        seq = [c for c in seg if c.tag in ("PipingComponent", "PipeOffPageConnector", "CenterLine")]
        conn = seg.find("Connection")
        f_id, f_node = (conn.get("FromID"), conn.get("FromNode")) if conn is not None else (None, None)
        t_id, t_node = (conn.get("ToID"), conn.get("ToNode")) if conn is not None else (None, None)
        sc = _custom(seg)
        for k, el in enumerate(seq):
            if el.tag != "CenterLine":
                continue
            lid = _custom(el)[TOPO_ID_ATTR]
            if k == 0:
                if f_id is None:
                    rep.add("pipe has a source", False, f"{lid} is first in its segment but the segment has no external source")
                    continue
                src_id, src = f_id, port_of(f_id, f_node, True, True)
            else:
                prev = seq[k - 1]
                src_id = prev.get("ID")
                src = port_of(src_id, None, True, False)
            if k == len(seq) - 1:
                if t_id is None:  # open end on the previous item
                    tgt_id, tgt = None, ("<open end>", "")
                else:
                    tgt_id, tgt = t_id, port_of(t_id, t_node, False, True)
            else:
                nxt = seq[k + 1]
                tgt_id = nxt.get("ID")
                tgt = port_of(tgt_id, None, False, False)
            if lid in pipes:
                dup_pipes.append(lid)
            pipes[lid] = (src, tgt)
            if tgt_id:
                pipe_item_edges.add((src_id, tgt_id))
            seg_services[lid] = sc.get(SERVICE_ATTR, "")
    exp_pipes = {l.id: ((l.from_.ref, l.from_.port), (l.to.ref, l.to.port)) for l in topo.process_lines}
    # open-ended valves have a pipe whose target is the valve itself -> handled by ports above
    missing = sorted(set(exp_pipes) - set(pipes))
    extra = sorted(set(pipes) - set(exp_pipes))
    wrong = sorted(l for l in set(exp_pipes) & set(pipes) if exp_pipes[l] != pipes[l])
    rep.add("XML graph: every topology line is exactly one pipe with the right endpoints", not (missing or extra or wrong or dup_pipes),
            f"{len(exp_pipes)} lines in {seg_count} segments; missing {len(missing)}, unexpected {len(extra)}, wrong endpoints {len(wrong)}"
            + (f" e.g. {wrong[:2]}" if wrong else ""))
    rep.stats.update(lines=len(exp_pipes), segments=seg_count)

    # services
    line_by_id = {l.id: l for l in topo.process_lines}
    bad_svc = [lid for lid, s in seg_services.items() if lid in line_by_id and s and False]
    seg_first_service = {}
    for seg in root.iter("PipingNetworkSegment"):
        c = _custom(seg)
        ids = [x.strip() for x in c.get("TopologyLineIds", "").split(",") if x.strip()]
        if not c.get(SERVICE_ATTR):
            bad_svc.append(f"segment of {ids[:1]} has no Service")
        elif ids and line_by_id[ids[0]].service != c[SERVICE_ATTR]:
            bad_svc.append(f"{ids[0]}: {c[SERVICE_ATTR]!r} != {line_by_id[ids[0]].service!r}")
    rep.add("every pipe segment carries the Service attribute of its line", not bad_svc, f"{seg_count} segments; " + ("; ".join(map(str, bad_svc[:3])) if bad_svc else "all match"))

    # tees
    tee_els = [e for e in root.iter("PipingComponent") if e.get("ComponentClass") == "PipeTee"]
    bad_tee = [t.get("ID") for t in tee_els if (lambda cp: cp.get("NumPoints") != "3" or cp.get("FlowIn") != "1" or cp.get("FlowOut") != "2")(t.find("ConnectionPoints"))]
    tees_by_manifold: dict[str, int] = {}
    for t in tee_els:
        tees_by_manifold[_custom(t)[TOPO_ID_ATTR]] = tees_by_manifold.get(_custom(t)[TOPO_ID_ATTR], 0) + 1
    bad_m = [c.id for c in topo.components if c.kind == "manifold" and tees_by_manifold.get(c.id, 0) != (c.branches or 2) - 1]
    rep.add("manifolds exported as PipeTee chains (n-1 tees, 3 nodes, run 1→2)", not bad_tee and not bad_m,
            f"{len(tee_els)} tees for {sum(1 for c in topo.components if c.kind == 'manifold')} manifolds" + (f"; bad {bad_m[:3] + bad_tee[:3]}" if bad_m or bad_tee else ""))
    rep.stats["tees"] = len(tee_els)

    # equipment / components / boundaries (XML + class)
    xml_topo_els: dict[str, etree._Element] = {}
    for e in root.iter():
        if e.tag in ("Equipment", "PipingComponent", "PipeOffPageConnector") and e.get("ComponentClass") != "PipeTee":
            tid = _custom(e).get(TOPO_ID_ATTR)
            if tid:
                xml_topo_els[tid] = e
    bad = []
    for e in topo.equipment:
        el = xml_topo_els.get(e.id)
        if el is None:
            bad.append(f"{e.id} missing")
            continue
        if el.get("ComponentClass") != e.model_class:
            bad.append(f"{e.id} class")
        if (_dexpi(el, "TagNameAssignmentClass") or None) != e.tag:
            bad.append(f"{e.id} tag")
        names = {_custom(n)["SchematicName"] for n in el.findall("Nozzle")}
        if names != {n.name for n in e.nozzles}:
            bad.append(f"{e.id} nozzles")
        if (e.lifecycle == "future") != (_custom(el).get(LIFECYCLE_ATTR) == "Future"):
            bad.append(f"{e.id} lifecycle")
    for c in topo.components:
        if c.kind == "manifold":
            continue
        el = xml_topo_els.get(c.id)
        if el is None or el.get("ComponentClass") != c.model_class:
            bad.append(f"{c.id} missing/class")
        elif (_dexpi(el, "PipingComponentNameAssignmentClass") or None) != c.tag:
            bad.append(f"{c.id} tag")
    for b in topo.boundaries:
        el = xml_topo_els.get(b.id)
        want = "FlowInPipeOffPageConnector" if b.direction == "in" else "FlowOutPipeOffPageConnector"
        if el is None or el.get("ComponentClass") != want:
            bad.append(f"{b.id} connector")
    rep.add("equipment, valves and boundaries: class, tag, nozzles preserved", not bad,
            f"{len(topo.equipment)} equipment, {len([c for c in topo.components if c.kind != 'manifold'])} valves, {len(topo.boundaries)} boundaries; " + ("; ".join(bad[:3]) if bad else "all match"))
    future = [e.id for e in topo.equipment if e.lifecycle == "future"]
    rep.add('future equipment carries LifeCyclePhase="Future"', all(_custom(xml_topo_els[i]).get(LIFECYCLE_ATTR) == "Future" for i in future), ", ".join(future))

    # instrumentation (XML)
    pif_els = {_custom(e)[TOPO_ID_ATTR]: e for e in root.findall("ProcessInstrumentationFunction")}
    bad_i = []
    seg_with_logical = lambda lg: [s for s in root.iter("PipingNetworkSegment") if lg in [x.strip() for x in _custom(s).get("LogicalLines", "").split(",")]]  # noqa: E731
    for i in topo.instruments:
        pe = pif_els.get(i.id)
        if pe is None:
            bad_i.append(f"{i.id} missing")
            continue
        if _custom(pe).get("Tag", "") != (i.tag or ""):
            bad_i.append(f"{i.id} tag")
        if i.function == "transmitter":
            loc = next((a.get("ItemID") for ps in pe.findall("ProcessSignalGeneratingFunction") for a in ps.findall("Association") if a.get("Type") == "is located in"), None)
            t = i.target or {}
            if loc is None:
                bad_i.append(f"{i.id} no sensing location")
            elif t.get("kind") == "equipment":
                nz = by_id.get(loc)
                ok = nz is not None and nz.tag == "Nozzle" and port_of(loc, None, True, True) == (t["ref"], t["port"])
                if not ok:
                    bad_i.append(f"{i.id} wrong nozzle")
            else:
                if by_id.get(loc) not in seg_with_logical(t["ref"]):
                    bad_i.append(f"{i.id} wrong segment")
    rep.add("instruments: tag and sensing location preserved", not bad_i, f"{len(topo.instruments)} instruments; " + ("; ".join(bad_i[:3]) if bad_i else "all match"))

    bad_l = []
    loops = {_custom(e)[TOPO_ID_ATTR]: e for e in root.findall("InstrumentationLoopFunction")}
    for lp in topo.control_loops:
        le = loops.get(lp.id)
        if le is None:
            bad_l.append(f"{lp.id} missing")
            continue
        members = {a.get("ItemID") for a in le.findall("Association") if a.get("Type") == "is a collection including"}
        pt_, pc_ = pif_els[lp.measurement], pif_els[lp.controller]
        flows_ok = any(f.find("Association[@Type='has logical start']").get("ItemID") == pt_.get("ID") and
                       f.find("Association[@Type='has logical end']").get("ItemID") == pc_.get("ID") for f in pt_.findall("InformationFlow"))
        valve_ok = False
        for f in pc_.findall("InformationFlow"):
            end = by_id.get(f.find("Association[@Type='has logical end']").get("ItemID"))
            if end is not None and end.tag == "ActuatingFunction":
                sysid = next(a.get("ItemID") for a in end.findall("Association") if a.get("Type") == "is fulfilled by")
                for comp in by_id[sysid].findall("ActuatingSystemComponent"):
                    ref = next((a.get("ItemID") for a in comp.findall("Association") if a.get("Type") == "refers to"), None)
                    if ref and _custom(by_id[ref]).get(TOPO_ID_ATTR) == lp.final_element:
                        valve_ok = True
        if not (members == {pt_.get("ID"), pc_.get("ID")} and flows_ok and valve_ok):
            bad_l.append(f"{lp.id}: members {members == {pt_.get('ID'), pc_.get('ID')}}, measurement→controller {flows_ok}, controller→valve {valve_ok}")
    rep.add("control loops: measurement → controller → final element preserved", not bad_l,
            f"{len(topo.control_loops)} loop(s); " + ("; ".join(bad_l) if bad_l else "all match"))

    # external segment ends use the right node
    bad_nodes, n_ends = [], 0
    for conn in root.iter("Connection"):
        for side in ("From", "To"):
            ref = conn.get(f"{side}ID")
            if ref is None:
                continue
            el = by_id.get(ref)
            node = conn.get(f"{side}Node")
            n_ends += 1
            if el is None:
                bad_nodes.append(f"{ref} missing")
            elif el.get("ComponentClass") == "PipeTee" and node != "3":
                bad_nodes.append(f"tee end {ref} node={node}")
            elif el.tag == "Nozzle" and node is not None:
                bad_nodes.append(f"nozzle end {ref} node={node}")
    rep.add("external segment ends: tee branch = node 3, nozzle = no node", not bad_nodes, f"{n_ends} ends; " + ("; ".join(bad_nodes[:3]) if bad_nodes else "all match"))

    # ================================================================ pyDEXPI reader
    ser = ProteusSerializer()
    model = ser.load(xml_path.parent, xml_path.name)
    for e in ser.proteus_loader.get_error_registry().errors:
        (rep.loader_errors if ("ERROR" in str(e.level) or "CRITICAL" in str(e.level)) else rep.loader_warnings).append(str(e.message)[:200])
    cm = model.conceptualModel
    segs = [s for sysm in cm.pipingNetworkSystems for s in sysm.segments]
    loaded_edges: set[tuple[str, str]] = set()
    for s in segs:
        for c in s.connections:
            if isinstance(c, pc.Pipe) and c.sourceItem is not None and c.targetItem is not None:
                loaded_edges.add((c.sourceItem.proteusId, c.targetItem.proteusId))
    # pipes that end on an open valve have no target item in XML terms; compare the rest
    comparable = {e for e in pipe_item_edges}
    rep.add("pyDEXPI loader sees the same item-to-item pipe connectivity as written", comparable == loaded_edges,
            f"{len(comparable)} item edges written, {len(loaded_edges)} loaded" + ("" if comparable == loaded_edges else f"; only written {len(comparable - loaded_edges)}, only loaded {len(loaded_edges - comparable)}"))
    eq_loaded = {e.proteusId: e for e in cm.taggedPlantItems}
    bad_loaded = []
    for e in topo.equipment:
        el = xml_topo_els[e.id]
        lo = eq_loaded.get(el.get("ID"))
        if lo is None or type(lo).__name__ != e.model_class or (lo.tagName or None) != e.tag or len(lo.nozzles) != len(e.nozzles):
            bad_loaded.append(e.id)
    rep.add("pyDEXPI loader: equipment classes, tags and nozzle counts", not bad_loaded, f"{len(topo.equipment)} items; " + (f"differ: {bad_loaded[:3]}" if bad_loaded else "all match"))
    rep.add("pyDEXPI loader: piping systems/segments and instrumentation counts",
            len(segs) == seg_count and len(cm.processInstrumentationFunctions) == len(topo.instruments) and len(cm.instrumentationLoopFunctions) == len(topo.control_loops),
            f"{len(segs)} segments (XML {seg_count}), {len(cm.processInstrumentationFunctions)} instrument functions, {len(cm.instrumentationLoopFunctions)} loops")
    rep.add("pyDEXPI loader: no errors when re-reading the XML", not rep.loader_errors, f"{len(rep.loader_errors)} error(s), {len(rep.loader_warnings)} warning(s)")
    return rep


def render_markdown(rep: RoundTripReport, xml_name: str) -> str:
    out = [f"# Round-trip verification — `{xml_name}`", "",
           f"**Result: {'PASS' if rep.ok else 'FAIL'}** — the XML was read back twice (lxml and pyDEXPI's own loader) and compared with the working topology.", "",
           "| Check | Result | Detail |", "|---|---|---|"]
    for c in rep.checks:
        out.append(f"| {c.name} | {'PASS' if c.ok else 'FAIL'} | {c.detail} |")
    out.append("")
    if rep.loader_warnings:
        seen: dict[str, int] = {}
        for w in rep.loader_warnings:
            seen[w.split(" with ID ")[0]] = seen.get(w.split(" with ID ")[0], 0) + 1
        out += ["## Loader warnings", "", "pyDEXPI's loader warns about drawing references because the file carries no graphical information; the graph is unaffected:", ""]
        out += [f"- {k} ({n}×)" for k, n in seen.items()] + [""]
    if rep.loader_errors:
        out += ["## Loader errors", ""] + [f"- {e}" for e in rep.loader_errors] + [""]
    out += ["## Method and known pyDEXPI 1.2.0 limits", "",
            "- Edges are compared as `(object, port) → (object, port)`; manifold ports are recovered from the tee chain recorded in the XML (`TopologyId`, `TeeIndex`).",
            "- pyDEXPI's Proteus **exporter** writes only equipment, nozzles and metadata; piping and instrumentation are written by `pid_workflow/proteus_ext.py`, which plugs into pyDEXPI's exporter framework and follows the structure its **parser** reads.",
            "- pyDEXPI's loader ignores custom attributes and the `FromNode`/`ToNode` indices, so those are verified in the XML directly.", ""]
    return "\n".join(out)
