"""Export a working topology to a pyDEXPI model and Proteus XML.

The exporter is purely structural: it never invents values.  Where DEXPI has no native
slot (provenance, review status, schematic nozzle names, ranges of values) the data is
kept as custom string attributes so nothing is lost on the way to the CAD tool.

Mapping conventions
-------------------
* equipment            -> pyDEXPI equipment class (``Custom*`` classes get a ``typeName``)
* nozzle               -> ``Nozzle`` (``subTagName`` = real nozzle number, ``None`` when unknown;
                          the schematic name travels as custom attribute ``SchematicName``)
* inline valve         -> valve class; generic selections use ``CustomOperatedValve``
* manifold (n branches)-> chain of n-1 ``PipeTee`` (see :func:`manifold_layout`)
* boundary             -> ``FlowIn/FlowOutPipeOffPageConnector``
* process lines        -> ``PipingNetworkSegment`` chains grouped in one ``PipingNetworkSystem`` per service
* transmitter          -> ``ProcessInstrumentationFunction`` + ``ProcessSignalGeneratingFunction``
* control loop         -> transmitter PIF -> ``ProcessControlFunction`` -> ``ActuatingFunction``
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydexpi.dexpi_classes import pydantic_classes as pc
from pydexpi.toolkits import instrumentation_toolkit as it
from pydexpi.toolkits import piping_toolkit as pt

from .proteus_ext import save_proteus
from .schema import Boundary, Component, Equipment, Instrument, ProcessLine, Topology, logical

ATTR_URI = "http://pid-workflow.local/attributes/"
SERVICE_ATTR = "Service"
LIFECYCLE_ATTR = "LifeCyclePhase"
TOPO_ID_ATTR = "TopologyId"


# ---------------------------------------------------------------------------- manifolds
def manifold_layout(role: str, n: int) -> list[dict[str, str]]:
    """Port wiring of the PipeTee chain that realises an n-branch manifold.

    Returns one dict per tee (k = 1..n-1) with the topology port bound to each tee node:
    ``run_in`` (node 0), ``run_out`` (node 1), ``branch`` (node 2).  A value that is not a
    manifold port name is an internal link to the neighbouring tee (``tee:<k>``).
    """
    tees = []
    for k in range(1, n):
        if role == "split":
            run_in = "common" if k == 1 else f"tee:{k - 1}"
            run_out = f"b{n}" if k == n - 1 else f"tee:{k + 1}"
            branch = f"b{k}"
        else:  # merge: b1 enters the run, b2..bn join as branches, common leaves the last tee
            run_in = "b1" if k == 1 else f"tee:{k - 1}"
            run_out = "common" if k == n - 1 else f"tee:{k + 1}"
            branch = f"b{k + 1}"
        tees.append({"run_in": run_in, "run_out": run_out, "branch": branch})
    return tees


# ----------------------------------------------------------------------------- helpers
def _attr(name: str, value: Any) -> pc.CustomStringAttribute:
    return pc.CustomStringAttribute(attributeName=name, attributeURI=f"{ATTR_URI}{name}", value="" if value is None else str(value))


def _prov_attrs(obj: Any) -> list[pc.CustomStringAttribute]:
    p = obj.provenance
    out = [_attr("Origin", p.origin)]
    if p.origin == "source":
        out += [_attr("SourceDocument", p.document), _attr("SourcePage", p.page), _attr("SourceSection", p.section),
                _attr("SourceBasis", p.basis)]
    else:
        out += [_attr("GeneratedByRule", p.rule), _attr("ReviewStatus", p.status), _attr("Triggers", ", ".join(p.triggers))]
    return out


def _fmt(a: Any) -> str:
    v = a.value
    if isinstance(v, dict):
        v = ", ".join(f"{k}={x}" for k, x in v.items())
    elif isinstance(v, list):
        v = ", ".join(map(str, v))
    return f"{v} {a.unit}".strip() if a.unit else str(v)


_LIFECYCLE = {"future": "Future", "new": "New", "existing": "Existing", "modified": "Modified"}


@dataclass
class ExportReport:
    counts: dict[str, int] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    native_attributes: list[str] = field(default_factory=list)
    custom_only_attributes: set[str] = field(default_factory=set)

    def bump(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n


@dataclass
class ExportResult:
    model: pc.DexpiModel
    report: ExportReport
    xml_path: Path | None = None
    # bookkeeping used by the round-trip check
    expected_edges: set[tuple[tuple[str, str], tuple[str, str]]] = field(default_factory=set)
    segment_lines: dict[str, list[str]] = field(default_factory=dict)  # segment id -> topology line ids


class Exporter:
    def __init__(self, topo: Topology):
        self.t = topo
        self.rep = ExportReport()
        self.objects: dict[str, Any] = {}       # topology id -> pyDEXPI object (equipment, valve, boundary)
        self.nozzles: dict[tuple[str, str], pc.Nozzle] = {}
        self.tees: dict[str, list[pc.PipeTee]] = {}
        self.by_from = {(l.from_.ref, l.from_.port): l for l in topo.process_lines}
        self.by_to = {(l.to.ref, l.to.port): l for l in topo.process_lines}
        self.conn = topo.connectable()
        self.expected_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()
        self.segments: list[tuple[pc.PipingNetworkSegment, list[ProcessLine], str]] = []
        self.line_segment: dict[str, pc.PipingNetworkSegment] = {}

    # ------------------------------------------------------------------- equipment
    def _equipment(self, e: Equipment) -> Any:
        cls = getattr(pc, e.model_class)
        nozzles = []
        for n in e.nozzles:
            nz = pc.Nozzle(
                subTagName=n.number,
                customAttributes=[_attr("SchematicName", n.name), _attr("NozzleRole", n.role), _attr(TOPO_ID_ATTR, f"{e.id}:{n.name}"),
                                  _attr("NozzleNumberStatus", "real" if n.number else "unknown (schematic name only)")]
                + ([_attr("NominalSize", _fmt(n.size))] if n.size else [])
                + (_prov_attrs(_Prov(n.provenance)) if n.provenance else []),
            )
            self.nozzles[(e.id, n.name)] = nz
            nozzles.append(nz)
        kw: dict[str, Any] = {
            "tagName": e.tag,
            "equipmentDescription": pc.MultiLanguageString(
                singleLanguageStrings=[pc.SingleLanguageString(language="en", value=e.name or e.id)]),
            "nozzles": nozzles,
        }
        custom = [_attr(TOPO_ID_ATTR, e.id), _attr("TagStatus", e.tag_status), _attr("Area", e.area), _attr("Name", e.name)]
        if e.lifecycle in _LIFECYCLE:
            custom.append(_attr(LIFECYCLE_ATTR, _LIFECYCLE[e.lifecycle]))
        custom += _prov_attrs(e)
        native: dict[str, Any] = {}
        for k, a in e.attributes.items():
            mapped = self._native_attr(e.model_class, k, a)
            if mapped:
                native.update(mapped)
                self.rep.native_attributes.append(f"{e.model_class}.{next(iter(mapped))} <- {k}")
            else:
                custom.append(_attr(k, _fmt(a)))
                self.rep.custom_only_attributes.add(k)
        kw.update(native)
        if e.model_class.startswith("Custom"):
            kw["typeName"] = e.name
        kw["customAttributes"] = custom
        self.rep.bump(f"equipment:{e.model_class}")
        return cls(**kw)

    @staticmethod
    def _native_attr(model_class: str, key: str, a: Any) -> dict[str, Any] | None:
        try:
            if key == "design_volume_flow_rate" and model_class == "CentrifugalPump" and a.unit == "m3/h":
                return {"designVolumeFlowRate": pc.VolumeFlowRate(value=float(a.value), unit=pc.VolumeFlowRateUnit.MetreCubedPerHour)}
            if key == "design_heat_flow_rate" and model_class == "PlateHeatExchanger" and a.unit == "kW":
                return {"designHeatFlowRate": pc.Power(value=float(a.value), unit=pc.PowerUnit.Kilowatt)}
            if key == "tank_volume" and model_class in {"Tank", "Vessel"} and a.unit == "m3":
                if "nominalCapacityVolume" in getattr(pc, model_class).model_fields:
                    return {"nominalCapacityVolume": pc.Volume(value=float(a.value), unit=pc.VolumeUnit.MetreCubed)}
        except Exception:  # pragma: no cover - fall back to custom attribute
            return None
        return None

    # ----------------------------------------------------------------- components
    def _valve(self, c: Component) -> Any:
        cls = getattr(pc, c.model_class)
        custom = [_attr(TOPO_ID_ATTR, c.id), _attr("TagStatus", c.tag_status), _attr("ValveFunction", c.function),
                  _attr("Actuation", c.operation), _attr("TechnologyStatus", c.technology_status), _attr("Name", c.name)]
        if c.technology:
            custom.append(_attr("Technology", c.technology))
        if c.open_end:
            custom.append(_attr("OpenEnd", c.open_end))
        if c.lifecycle in _LIFECYCLE:
            custom.append(_attr(LIFECYCLE_ATTR, _LIFECYCLE[c.lifecycle]))
        for k, a in c.attributes.items():
            custom.append(_attr(k, _fmt(a)))
        custom += _prov_attrs(c)
        kw: dict[str, Any] = {"nodes": [pc.PipingNode(), pc.PipingNode()], "pipingComponentName": c.tag, "customAttributes": custom}
        if c.model_class.startswith("Custom"):
            kw["typeName"] = (c.attributes["type_name"].value if "type_name" in c.attributes else c.name) or "Valve"
        self.rep.bump(f"valve:{c.model_class}")
        return cls(**kw)

    def _manifold(self, c: Component) -> list[pc.PipeTee]:
        tees = []
        for k in range(1, (c.branches or 2)):
            tees.append(pc.PipeTee(
                nodes=[pc.PipingNode(), pc.PipingNode(), pc.PipingNode()],
                customAttributes=[_attr(TOPO_ID_ATTR, c.id), _attr("TeeIndex", k), _attr("ManifoldRole", c.role), _attr("ManifoldBranches", c.branches),
                                  _attr("Name", c.name)] + _prov_attrs(c),
            ))
        self.rep.bump("manifold_tees", len(tees))
        return tees

    def _boundary(self, b: Boundary) -> Any:
        cls = pc.FlowInPipeOffPageConnector if b.direction == "in" else pc.FlowOutPipeOffPageConnector
        self.rep.bump(f"boundary:{cls.__name__}")
        return cls(nodes=[pc.PipingNode()], customAttributes=[_attr(TOPO_ID_ATTR, b.id), _attr("Name", b.name), _attr(SERVICE_ATTR, b.service),
                                                              _attr("Direction", b.direction), _attr("Area", b.area)] + _prov_attrs(b))

    # ------------------------------------------------------------------ port access
    def _port_item(self, ref: str, port: str) -> tuple[Any, int | None]:
        """Return the pyDEXPI item (nozzle / tee / valve / connector) and node index for a topology port."""
        o = self.conn[ref]
        if isinstance(o, Equipment):
            return self.nozzles[(ref, port)], None
        if isinstance(o, Boundary):
            return self.objects[ref], 0
        if o.kind == "manifold":
            lay = manifold_layout(o.role or "split", o.branches or 2)
            for k, t in enumerate(lay):
                for node_idx, key in enumerate(("run_in", "run_out", "branch")):
                    if t[key] == port:
                        return self.tees[ref][k], node_idx
            raise KeyError(f"{ref}:{port}")
        return self.objects[ref], (0 if port == "in" else 1)

    # --------------------------------------------------------------------- piping
    def _build_segments(self) -> None:
        lines = self.t.process_lines
        used: set[str] = set()

        def is_start(l: ProcessLine) -> bool:
            o = self.conn[l.from_.ref]
            if isinstance(o, (Equipment, Boundary)):
                return True
            if o.kind == "manifold" and o.role == "split":
                return l.from_.port not in ("common", f"b{o.branches or 2}")
            return False

        for l0 in lines:
            if is_start(l0):
                self._walk(l0, used)
        missing = [l.id for l in lines if l.id not in used]
        if missing:
            raise RuntimeError(f"lines not part of any segment: {missing[:10]}")

    def _walk(self, first: ProcessLine, used: set[str]) -> None:
        """Follow ``first`` downstream until a nozzle, boundary, tee branch or open end is reached.

        ``chain`` holds ``(object, node_index, external)`` triples in flow order; the pipe between two
        consecutive entries is one topology line (or a direct link between tees of one manifold).
        """
        chain: list[tuple[Any, int | None, bool]] = []
        pipes: list[tuple[ProcessLine | None, tuple[int | None, int | None]]] = []
        seg_lines: list[ProcessLine] = [first]
        used.add(first.id)
        fo = self.conn[first.from_.ref]
        s_item, s_node = self._port_item(first.from_.ref, first.from_.port)
        # boundaries are in-segment items (off-page connectors); nozzles and tee branches are external
        chain.append((s_item, s_node, not isinstance(fo, Boundary)))
        cur = first
        ends_on_item = False
        while True:
            to = cur.to
            o = self.conn[to.ref]
            if isinstance(o, Equipment):
                t_item, t_node = self._port_item(to.ref, to.port)
                pipes.append((cur, (None, None)))
                chain.append((t_item, t_node, True))
                break
            if isinstance(o, Boundary):
                t_item, t_node = self._port_item(to.ref, to.port)
                pipes.append((cur, (None, None)))
                chain.append((t_item, t_node, False))
                break
            if o.kind != "manifold":
                item = self.objects[o.id]
                pipes.append((cur, (None, None)))
                chain.append((item, 0, False))
                nxt = self.by_from.get((o.id, "out"))
                if nxt is None:
                    ends_on_item = True
                    break
                cur = nxt
                seg_lines.append(nxt)
                used.add(nxt.id)
                continue
            lay = manifold_layout(o.role or "split", o.branches or 2)
            entering = next((k for k, t in enumerate(lay) if t["run_in"] == to.port), None)
            if entering is None:  # arrives on a branch node: the segment ends on that tee (external)
                for k, t in enumerate(lay):
                    if t["branch"] == to.port:
                        pipes.append((cur, (None, None)))
                        chain.append((self.tees[o.id][k], 2, True))
                break
            k = entering
            first_tee = True
            while True:
                if first_tee:
                    pipes.append((cur, (None, None)))
                else:
                    pipes.append((None, (None, None)))  # direct link inside the manifold
                chain.append((self.tees[o.id][k], 0, False))
                first_tee = False
                run_out = lay[k]["run_out"]
                if run_out.startswith("tee:"):
                    k = int(run_out.split(":")[1]) - 1
                    continue
                break
            nxt = self.by_from.get((o.id, run_out))
            if nxt is None:
                raise RuntimeError(f"manifold {o.id} port {run_out} has no outgoing line")
            cur = nxt
            seg_lines.append(nxt)
            used.add(nxt.id)
        self._make_segment(chain, pipes, ends_on_item, seg_lines)

    def _make_segment(self, chain: list[tuple[Any, int | None, bool]], pipes: list[tuple[ProcessLine | None, Any]], ends_on_item: bool,
                      seg_lines: list[ProcessLine]) -> None:
        items = [obj for obj, _, ext in chain if not ext]
        conns: list[Any] = []
        pipe_lines = [l for l, _ in pipes]
        for k, (line, _) in enumerate(pipes):
            a_obj, a_node, a_ext = chain[k]
            b_obj, b_node, b_ext = chain[k + 1]
            # node used on the source side: external tee branch / nozzle given; internal items use their outflow node
            if a_ext:
                a_n = None if not hasattr(a_obj, "nodes") or isinstance(a_obj, pc.Nozzle) else a_obj.nodes[a_node]
            elif isinstance(a_obj, pc.PipeOffPageConnector):
                a_n = a_obj.nodes[0]
            else:
                a_n = a_obj.nodes[1]
            if b_ext:
                b_n = None if isinstance(b_obj, pc.Nozzle) else b_obj.nodes[b_node]
            elif isinstance(b_obj, pc.PipeOffPageConnector):
                b_n = b_obj.nodes[0]
            else:
                b_n = b_obj.nodes[0]
            if line is None:
                c: Any = pc.DirectPipingConnection(sourceItem=a_obj, sourceNode=a_n, targetItem=b_obj, targetNode=b_n)
            else:
                c = pc.Pipe(sourceItem=a_obj, sourceNode=a_n, targetItem=b_obj, targetNode=b_n,
                            customAttributes=[_attr(TOPO_ID_ATTR, line.id)])
            conns.append(c)
        seg = pc.PipingNetworkSegment(items=items, connections=conns)
        src_obj, src_node, src_ext = chain[0]
        seg.sourceItem = src_obj
        if src_ext and not isinstance(src_obj, pc.Nozzle):
            seg.sourceNode = src_obj.nodes[src_node]
        elif not src_ext:
            seg.sourceNode = src_obj.nodes[0] if isinstance(src_obj, pc.PipeOffPageConnector) else None
        if ends_on_item:
            seg.targetItem = items[-1]
        else:
            t_obj, t_node, t_ext = chain[-1]
            seg.targetItem = t_obj
            if t_ext and not isinstance(t_obj, pc.Nozzle):
                seg.targetNode = t_obj.nodes[t_node]
            elif not t_ext and isinstance(t_obj, pc.PipeOffPageConnector):
                seg.targetNode = t_obj.nodes[0]
        real_lines = [l for l in pipe_lines if l is not None]
        service = seg_lines[0].service
        services = sorted({l.service for l in seg_lines})
        seg.fluidCode = service
        p = seg_lines[0].properties
        dn = p.get("nominal_diameter")
        if dn is not None and dn.value is not None and isinstance(dn.value, (int, float)):
            seg.nominalDiameterRepresentation = f"DN{int(dn.value)}"
        seg.customAttributes = [
            _attr(SERVICE_ATTR, service),
            _attr("TopologyLineIds", ", ".join(l.id for l in real_lines)),
            _attr("LogicalLines", ", ".join(sorted({logical(l) for l in seg_lines}))),
        ] + ([_attr("AllServices", ", ".join(services))] if len(services) > 1 else []) + [
            _attr(k, _fmt(a)) for k, a in p.items() if k != "nominal_diameter" or not seg.nominalDiameterRepresentation
        ] + _prov_attrs(seg_lines[0]) + ([_attr("HasGeneratedParts", "true")] if any(l.provenance.origin == "generated" for l in seg_lines) else [])
        self.segments.append((seg, seg_lines, service))
        for l in real_lines:
            self.line_segment[l.id] = seg
            e = (pipe_lines.index(l))
        # expected topology edges (checked after reload)
        for l in real_lines:
            self.expected_edges.add(((l.from_.ref, l.from_.port), (l.to.ref, l.to.port)))

    # ---------------------------------------------------------------- instruments
    def _instrumentation(self, model: pc.DexpiModel) -> None:
        pifs: dict[str, Any] = {}
        insts = {i.id: i for i in self.t.instruments}
        sys_by_service: dict[str, pc.PipingNetworkSegment] = {}
        for i in self.t.instruments:
            letters = i.isa_code
            num = (i.tag or "").split("-")[-1] if i.tag else None
            cat = letters[0]
            mod = letters[1:] if len(letters) > 1 else None
            common = dict(
                processInstrumentationFunctionCategory=cat,
                processInstrumentationFunctionModifier=mod,
                processInstrumentationFunctionNumber=num,
            )
            custom = [_attr(TOPO_ID_ATTR, i.id), _attr("Tag", i.tag), _attr("TagStatus", i.tag_status), _attr("MeasuredVariable", i.measured_variable),
                      _attr("Area", i.area)] + _prov_attrs(i)
            if i.function == "controller":
                pif = pc.ProcessControlFunction(customAttributes=custom, **common)
                self.rep.bump("instrument:ProcessControlFunction")
            else:
                sensing = self._sensing_location(i)
                psgf = pc.ProcessSignalGeneratingFunction(sensingLocation=sensing,
                                                          customAttributes=[_attr(TOPO_ID_ATTR, i.id + "#sensing")])
                system = pc.ProcessSignalGeneratingSystem(transmitter=pc.Transmitter(customAttributes=[_attr(TOPO_ID_ATTR, i.id + "#transmitter")]))
                psgf.systems = system
                model.conceptualModel.processSignalGeneratingSystems.append(system)
                pif = pc.ProcessInstrumentationFunction(customAttributes=custom, **common)
                it.add_signal_generating_function_to_instrumentation_function(pif, psgf, pc.MeasuringLineFunction())
                self.rep.bump("instrument:ProcessInstrumentationFunction")
            pifs[i.id] = pif
            model.conceptualModel.processInstrumentationFunctions.append(pif)
        # signals
        for s in self.t.signals:
            src = pifs.get(s.from_)
            if s.kind == "measurement":
                it.connect_instrumentation_functions(pifs[s.from_], pifs[s.to], pc.SignalLineFunction())
            else:
                valve = self.objects[s.to]
                seg = self._segment_of_item(valve)
                af = pc.ActuatingFunction(actuatingLocation=seg, customAttributes=[_attr(TOPO_ID_ATTR, s.id + "#actuating")])
                asys = pc.ActuatingSystem(operatedValveReference=pc.OperatedValveReference(valve=valve), customAttributes=[_attr(TOPO_ID_ATTR, s.id + "#system")])
                af.systems = asys
                model.conceptualModel.actuatingSystems.append(asys)
                it.add_actuating_function_to_instrumentation_function(pifs[s.from_], af, pc.SignalLineFunction())
        for lp in self.t.control_loops:
            loop = pc.InstrumentationLoopFunction(
                instrumentationLoopFunctionNumber=lp.id.split(".", 1)[-1],
                processInstrumentationFunctions=[pifs[lp.measurement], pifs[lp.controller]],
                customAttributes=[_attr(TOPO_ID_ATTR, lp.id), _attr("Setpoint", _fmt(lp.setpoint) if lp.setpoint else ""),
                                  _attr("Requirement", lp.requirement), _attr("FinalElement", lp.final_element)] + _prov_attrs(lp),
            )
            model.conceptualModel.instrumentationLoopFunctions.append(loop)
            self.rep.bump("control_loops")

    def _sensing_location(self, i: Instrument) -> Any:
        t = i.target or {}
        if t.get("kind") == "equipment":
            return self.nozzles[(t["ref"], t["port"])]
        # line: first segment carrying that logical line
        for seg, lines, _ in self.segments:
            if any(logical(l) == t["ref"] for l in lines):
                return seg
        raise KeyError(f"no segment for {t}")

    def _segment_of_item(self, item: Any) -> pc.PipingNetworkSegment:
        for seg, _, _ in self.segments:
            if item in seg.items:
                return seg
        raise KeyError("item not in any segment")

    # ------------------------------------------------------------------------ run
    def build(self) -> ExportResult:
        t = self.t
        md = t.metadata
        conceptual = pc.ConceptualModel(metaData=pc.MetaData(
            drawingName=md.title, drawingNumber=md.drawing_id, projectName=md.project, revisionNumber=md.revision,
            customAttributes=[_attr("SourceSnapshotSha256", md.source_snapshot_sha256 or ""), _attr("Status", "DRAFT - pending engineering review")]))
        # objects
        for e in t.equipment:
            obj = self._equipment(e)
            self.objects[e.id] = obj
            conceptual.taggedPlantItems.append(obj)
        for c in t.components:
            if c.kind == "manifold":
                self.tees[c.id] = self._manifold(c)
            else:
                self.objects[c.id] = self._valve(c)
        for b in t.boundaries:
            self.objects[b.id] = self._boundary(b)
        self._build_segments()
        # one piping network system per service
        by_service: dict[str, list[pc.PipingNetworkSegment]] = {}
        for seg, _, service in self.segments:
            by_service.setdefault(service, []).append(seg)
        for service, segs in sorted(by_service.items()):
            system = pc.PipingNetworkSystem(fluidCode=service, segments=segs, customAttributes=[_attr(SERVICE_ATTR, service)])
            conceptual.pipingNetworkSystems.append(system)
        self.rep.bump("piping_network_systems", len(by_service))
        self.rep.bump("piping_network_segments", len(self.segments))
        model = pc.DexpiModel(conceptualModel=conceptual, originatingSystemName="pid_workflow", originatingSystemVendorName="P-ID project",
                              originatingSystemVersion="0.1.0",
                              exportDateTime=_export_time())
        self._instrumentation(model)
        self._stable_ids(model)
        self._limitations()
        return ExportResult(model=model, report=self.rep, expected_edges=self.expected_edges,
                            segment_lines={seg.id: [l.id for l in lines] for seg, lines, _ in self.segments})

    def _stable_ids(self, model: pc.DexpiModel) -> None:
        """Give every object a deterministic Proteus ID so that re-exports are identical and diff-friendly.

        IDs are ``<Class>-<topology id>`` where the object carries one, otherwise ``<Class>-<counter>``
        (traversal order is deterministic).
        """
        import re

        from pydexpi.dexpi_classes.pydantic_classes import DexpiBaseModel
        from pydexpi.toolkits import model_toolkit as mt

        seen: set[str] = set()
        counters: dict[str, int] = {}
        for obj in mt.get_all_instances_in_model(model.conceptualModel, None):
            if not isinstance(obj, DexpiBaseModel) or getattr(obj, "proteusId", None):
                continue
            cls = type(obj).__name__
            attrs = {a.attributeName: a.value for a in (getattr(obj, "customAttributes", None) or []) if hasattr(a, "attributeName")}
            base = attrs.get(TOPO_ID_ATTR)
            if base and "TeeIndex" in attrs:
                base = f"{base}.tee{attrs['TeeIndex']}"
            if base:
                pid = f"{cls}-{re.sub(r'[^A-Za-z0-9_.-]', '_', base)}"
            else:
                counters[cls] = counters.get(cls, 0) + 1
                pid = f"{cls}-{counters[cls]:05d}"
            while pid in seen:
                counters[cls] = counters.get(cls, 0) + 1
                pid = f"{pid}_{counters[cls]}"
            seen.add(pid)
            obj.proteusId = pid

    def _limitations(self) -> None:
        r = self.rep
        r.limitations = [
            "No graphical information is exported (no Proteus Drawing / ShapeCatalogue): symbols, coordinates and routing exist only in the review PDF. "
            "The target CAD tool must lay the drawing out itself.",
            "LifeCyclePhase, Service, provenance, review status, tag status and schematic nozzle names are written as custom string attributes; "
            "rendering future equipment as dashed lines depends on the target template reading LifeCyclePhase=\"Future\".",
            "Heat pumps, fermenters and the retained steam exchangers have no dedicated pyDEXPI class and are exported as CustomEquipment / CustomHeatExchanger / CustomCompressor.",
            "Valves of unspecified technology use CustomOperatedValve with a 'technology to be selected' typeName; no specific valve type is chosen. "
            "Manual/automated actuation is a custom attribute because DEXPI 'operation' only classifies continuous/intermittent operation.",
            "An n-branch manifold is exported as a chain of n-1 PipeTee items; the manifold identity is kept in the TopologyId/TeeIndex attributes.",
            "Nozzle numbers (Nozzle.subTagName) are left empty because the source gives none; nozzle sizes and ratings are not exported (never invented).",
            "Only flow rate, heat flow rate and tank volume are mapped to native typed attributes; all other quantities are exported as text custom attributes.",
            "Pipe off-page connectors carry no connectorReference: the sheet references of the review PDF are not part of the model.",
            "Control valves carry no failAction, instruments no ranges, and the controller is a ProcessControlFunction without tuning data (not specified).",
            "Segment nominal diameter is exported only when the source gives a single DN; ranges and minima are text attributes.",
            "The Proteus XML schema (XSD) is not available offline, so the file is not schema-validated; it is proven to load with pyDEXPI's own parser and "
            "its graph is compared with the topology (see the round-trip report). Validate it in the target CAD tool before relying on it.",
        ]


def _export_time() -> datetime:
    """Export timestamp; honours SOURCE_DATE_EPOCH so that exports can be made byte-reproducible."""
    import os

    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    return datetime.fromtimestamp(int(epoch), timezone.utc) if epoch else datetime.now(timezone.utc)


class _Prov:
    """Adapter so nozzle provenance can reuse :func:`_prov_attrs`."""

    def __init__(self, provenance: Any):
        self.provenance = provenance


def export_topology(topo: Topology, xml_path: str | Path | None = None) -> ExportResult:
    """Build the pyDEXPI model for ``topo`` and optionally serialise it to Proteus XML."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = Exporter(topo).build()
    if xml_path is not None:
        xml_path = Path(xml_path)
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        save_proteus(res.model, xml_path)
        res.xml_path = xml_path
    return res
