"""Proteus XML writer for piping and instrumentation, built on pyDEXPI's exporter framework.

pyDEXPI 1.2.0 serialises only equipment, nozzles and metadata to Proteus XML.  Its *parser*
reads piping networks and instrumentation, so this module adds the missing export modules
following the structure the parser expects (verified by loading the result back with
``ProteusSerializer.load``).  The classes plug into pyDEXPI's own
``ExporterModule`` / ``GenericAttributeExporter`` machinery; nothing in pyDEXPI is patched.

XML structure written here (Proteus 4.1.1 / DEXPI P&ID):

``PipingNetworkSystem`` > ``PipingNetworkSegment`` > ordered ``PipingComponent`` /
``PipeOffPageConnector`` items separated by ``CenterLine`` pipes; segment ends that are
nozzles or tee branches of other segments are written as ``<Connection FromID= FromNode=
ToID= ToNode=>`` (1-based node indices).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from pydexpi.dexpi_classes import pydantic_classes as pc
from pydexpi.loaders import ProteusSerializer
from pydexpi.loaders.proteus_serializer.proteus_exporter.core import ExporterModule, ModuleContext
from pydexpi.loaders.proteus_serializer.proteus_exporter.exporter_modules import (
    GenericAttributeExporter,
    PlantModelExporter,
)
from pydexpi.loaders.proteus_serializer.proteus_exporter.exporter_utils import (
    add_association_elements,
    make_default_component_class_uri,
)
from pydexpi.loaders.proteus_serializer.proteus_exporter.proteus_exporter import ProteusExporter


# --------------------------------------------------------------------------------- piping
class PipingNodeXml:
    @staticmethod
    def element(module: ExporterModule, node: pc.PipingNode, name: str | None = None) -> ET.Element:
        el = ET.Element("Node")
        el.set("ID", module.make_id_attribute(node))
        el.set("Type", "process")
        if name:
            el.set("Name", name)
        module.register_object(node.id, el)
        return el


class PipingComponentExporter(ExporterModule):
    """``PipingComponent`` / ``PipeOffPageConnector`` item of a segment."""

    def __init__(self, context: ModuleContext, component: pc.PipingNetworkSegmentItem, flow_in: int | None = 1, flow_out: int | None = 2):
        super().__init__(context)
        self.component = component
        self.flow_in = flow_in
        self.flow_out = flow_out
        self.attrs = GenericAttributeExporter(context, component)

    def compositional_pass(self) -> ET.Element:
        c = self.component
        is_opc = isinstance(c, pc.PipeOffPageConnector)
        el = ET.Element("PipeOffPageConnector" if is_opc else "PipingComponent")
        el.set("ID", self.make_id_attribute(c))
        el.set("ComponentClass", type(c).__name__)
        el.set(*make_default_component_class_uri(type(c).__name__))
        cp = ET.SubElement(el, "ConnectionPoints")
        cp.set("NumPoints", str(len(c.nodes)))
        if self.flow_in is not None:
            cp.set("FlowIn", str(self.flow_in))
        if self.flow_out is not None:
            cp.set("FlowOut", str(self.flow_out))
        for i, n in enumerate(c.nodes, 1):
            cp.append(PipingNodeXml.element(self, n, f"N{i}"))
        self.attrs.compose_and_add_attributes(el)
        self.register_object(c.id, el)
        return el


def _ordered_elements(seg: pc.PipingNetworkSegment) -> list[tuple[str, object]]:
    """Items and *pipes* of a segment in flow order (direct connections are implicit)."""
    out: list[tuple[str, object]] = []
    items = list(seg.items)
    conns = list(seg.connections)
    # find first element: a connection whose source is not an item of this segment, else the first item
    by_source = {c.sourceItem.id: c for c in conns if c.sourceItem is not None}
    by_target = {c.targetItem.id: c for c in conns if c.targetItem is not None}
    item_ids = {i.id for i in items}
    start_conn = next((c for c in conns if c.sourceItem is None or c.sourceItem.id not in item_ids), None)
    if start_conn is not None:
        cur_conn = start_conn
        while True:
            if isinstance(cur_conn, pc.Pipe):
                out.append(("pipe", cur_conn))
            tgt = cur_conn.targetItem
            if tgt is None or tgt.id not in item_ids:
                break
            out.append(("item", tgt))
            nxt = by_source.get(tgt.id)
            if nxt is None:
                break
            cur_conn = nxt
    else:  # segment begins with an item
        cur = next((i for i in items if i.id not in by_target), items[0] if items else None)
        while cur is not None:
            out.append(("item", cur))
            c = by_source.get(cur.id)
            if c is None:
                break
            if isinstance(c, pc.Pipe):
                out.append(("pipe", c))
            cur = c.targetItem if c.targetItem is not None and c.targetItem.id in item_ids else None
    return out


class PipingNetworkSegmentExporter(ExporterModule):
    def __init__(self, context: ModuleContext, segment: pc.PipingNetworkSegment):
        super().__init__(context)
        self.segment = segment
        self.attrs = GenericAttributeExporter(context, segment)
        self.item_exporters: dict[str, PipingComponentExporter] = {}
        for it in segment.items:
            if isinstance(it, pc.PipeOffPageConnector):
                fin, fout = (None, 1) if isinstance(it, pc.FlowInPipeOffPageConnector) else (1, None)
            else:
                fin, fout = 1, 2
            self.item_exporters[it.id] = PipingComponentExporter(context, it, fin, fout)
        self.register_submodule_list(list(self.item_exporters.values()))

    @staticmethod
    def _node_index(item: object, node: object) -> str | None:
        if node is None or item is None or not hasattr(item, "nodes"):
            return None
        for i, n in enumerate(item.nodes, 1):
            if n is node:
                return str(i)
        return None

    def compositional_pass(self) -> ET.Element:
        s = self.segment
        el = ET.Element("PipingNetworkSegment")
        el.set("ID", self.make_id_attribute(s))
        el.set("ComponentClass", "PipingNetworkSegment")
        el.set(*make_default_component_class_uri("PipingNetworkSegment"))
        item_ids = {i.id for i in s.items}
        # external connection (nozzle or tee branch of another segment)
        conn = ET.SubElement(el, "Connection")
        if s.sourceItem is not None and s.sourceItem.id not in item_ids:
            conn.set("FromID", self.make_id_attribute(s.sourceItem))
            idx = self._node_index(s.sourceItem, s.sourceNode)
            if idx:
                conn.set("FromNode", idx)
        if s.targetItem is not None and s.targetItem.id not in item_ids:
            conn.set("ToID", self.make_id_attribute(s.targetItem))
            idx = self._node_index(s.targetItem, s.targetNode)
            if idx:
                conn.set("ToNode", idx)
        if len(conn.attrib) == 0:
            el.remove(conn)
        self.attrs.compose_and_add_attributes(el)
        for kind, obj in _ordered_elements(s):
            if kind == "item":
                el.append(self.item_exporters[obj.id].compositional_pass())
            else:
                cl = ET.SubElement(el, "CenterLine")
                cl.set("ID", self.make_id_attribute(obj))
                cl.set("ComponentClass", "Pipe")
                ga = GenericAttributeExporter(self.module_context, obj)
                ga.compose_and_add_attributes(cl)
        self.register_object(s.id, el)
        return el


class PipingNetworkSystemExporter(ExporterModule):
    def __init__(self, context: ModuleContext, system: pc.PipingNetworkSystem):
        super().__init__(context)
        self.system = system
        self.attrs = GenericAttributeExporter(context, system)
        self.segment_exporters = [PipingNetworkSegmentExporter(context, s) for s in system.segments]
        self.register_submodule_list(self.segment_exporters)

    def compositional_pass(self) -> ET.Element:
        el = ET.Element("PipingNetworkSystem")
        el.set("ID", self.make_id_attribute(self.system))
        el.set("ComponentClass", "PipingNetworkSystem")
        el.set(*make_default_component_class_uri("PipingNetworkSystem"))
        self.attrs.compose_and_add_attributes(el)
        for se in self.segment_exporters:
            el.append(se.compositional_pass())
        self.register_object(self.system.id, el)
        return el


# ------------------------------------------------------------------------ instrumentation
def _assoc(el: ET.Element, typ: str, item_id: str) -> None:
    a = ET.SubElement(el, "Association")
    a.set("Type", typ)
    a.set("ItemID", item_id)


class InstrumentationExporter(ExporterModule):
    """Process instrumentation functions, signal-generating and actuating systems, loops."""

    def __init__(self, context: ModuleContext, conceptual: pc.ConceptualModel):
        super().__init__(context)
        self.cm = conceptual

    def _generic(self, el: ET.Element, obj: object) -> None:
        GenericAttributeExporter(self.module_context, obj).compose_and_add_attributes(el)

    def _cls(self, el: ET.Element, obj: object, tag_class: str | None = None) -> None:
        name = tag_class or type(obj).__name__
        el.set("ID", self.make_id_attribute(obj))
        el.set("ComponentClass", name)
        el.set(*make_default_component_class_uri(name))

    def compositional_pass(self) -> list[ET.Element]:  # type: ignore[override]
        out: list[ET.Element] = []
        # systems first (referenced by functions)
        for sys_ in self.cm.processSignalGeneratingSystems:
            el = ET.Element("ProcessSignalGeneratingSystem")
            self._cls(el, sys_)
            self._generic(el, sys_)
            if sys_.transmitter is not None:
                comp = ET.SubElement(el, "ProcessSignalGeneratingSystemComponent")
                self._cls(comp, sys_.transmitter)
                self._generic(comp, sys_.transmitter)
                self.register_object(sys_.transmitter.id, comp)
            self.register_object(sys_.id, el)
            out.append(el)
        for sys_ in self.cm.actuatingSystems:
            el = ET.Element("ActuatingSystem")
            self._cls(el, sys_)
            self._generic(el, sys_)
            if sys_.operatedValveReference is not None:
                comp = ET.SubElement(el, "ActuatingSystemComponent")
                self._cls(comp, sys_.operatedValveReference)
                self._generic(comp, sys_.operatedValveReference)
                self.register_object(sys_.operatedValveReference.id, comp)
                valve = sys_.operatedValveReference.valve
                if valve is not None:
                    _assoc(comp, "refers to", self.make_id_attribute(valve))
            self.register_object(sys_.id, el)
            out.append(el)
        for pif in self.cm.processInstrumentationFunctions:
            el = self._pif(pif)
            out.append(el)
        for loop in self.cm.instrumentationLoopFunctions:
            el = ET.Element("InstrumentationLoopFunction")
            self._cls(el, loop)
            self._generic(el, loop)
            for member in loop.processInstrumentationFunctions:
                _assoc(el, "is a collection including", self.make_id_attribute(member))
                member_el = self.get_object_from_registry(member.id)
                if member_el is not None:
                    _assoc(member_el, "is a part of", self.make_id_attribute(loop))
            out.append(el)
            self.register_object(loop.id, el)
        return out

    def _pif(self, pif: pc.ProcessInstrumentationFunction) -> ET.Element:
        tag = "ProcessInstrumentationFunction"
        el = ET.Element(tag)
        self._cls(el, pif)
        self._generic(el, pif)
        for psgf in pif.processSignalGeneratingFunctions:
            c = ET.SubElement(el, "ProcessSignalGeneratingFunction")
            self._cls(c, psgf)
            self._generic(c, psgf)
            loc = psgf.sensingLocation
            if loc is not None:
                _assoc(c, "is located in", self.make_id_attribute(loc))
            if psgf.systems is not None:
                _assoc(c, "is fulfilled by", self.make_id_attribute(psgf.systems))
            self.register_object(psgf.id, c)
        for af in pif.actuatingFunctions:
            c = ET.SubElement(el, "ActuatingFunction")
            self._cls(c, af)
            self._generic(c, af)
            if af.actuatingLocation is not None:
                _assoc(c, "is located in", self.make_id_attribute(af.actuatingLocation))
            if af.systems is not None:
                _assoc(c, "is fulfilled by", self.make_id_attribute(af.systems))
            self.register_object(af.id, c)
        for flow in pif.signalConveyingFunctions:
            c = ET.SubElement(el, "InformationFlow")
            self._cls(c, flow)
            self._generic(c, flow)
            if flow.source is not None:
                _assoc(c, "has logical start", self.make_id_attribute(flow.source))
            if flow.target is not None:
                _assoc(c, "has logical end", self.make_id_attribute(flow.target))
            self.register_object(flow.id, c)
        self.register_object(pif.id, el)
        return el


# ---------------------------------------------------------------------------- top level
class ExtendedPlantModelExporter(PlantModelExporter):
    def __init__(self, context: ModuleContext, dexpi_model: pc.DexpiModel, override_export_info: bool = False) -> None:
        if not dexpi_model.conceptualModel.metaData:
            # pyDEXPI 1.2.0 reads ``self.metadata_exporter`` even when there is no metadata
            self.metadata_exporter = None
        super().__init__(context, dexpi_model, override_export_info)
        cm = dexpi_model.conceptualModel
        self.system_exporters = [PipingNetworkSystemExporter(context, s) for s in cm.pipingNetworkSystems]
        self.register_submodule_list(self.system_exporters)
        self.instrumentation_exporter = InstrumentationExporter(context, cm)

    def compositional_pass(self) -> ET.Element:
        root = super().compositional_pass()
        for se in self.system_exporters:
            root.append(se.compositional_pass())
        for el in self.instrumentation_exporter.compositional_pass():
            root.append(el)
        return root


class ExtendedProteusExporter(ProteusExporter):
    def export_xml_element(self, dexpi_model: pc.DexpiModel) -> ET.Element:
        from pydexpi.loaders.proteus_serializer.proteus_exporter.core import ElementRegistry

        registry = ElementRegistry()
        self.context = ModuleContext(element_registry=registry, override_proteus_id=self.override_proteus_id)
        exporter = ExtendedPlantModelExporter(self.context, dexpi_model, override_export_info=self.override_export_info)
        root = exporter.compositional_pass()
        exporter.reference_pass()
        return root


class ExtendedProteusSerializer(ProteusSerializer):
    """``ProteusSerializer`` whose exporter also writes piping and instrumentation."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.proteus_exporter = ExtendedProteusExporter(
            override_export_info=kwargs.get("override_export_info", False),
            override_proteus_id=kwargs.get("override_proteus_id", False),
        )


def save_proteus(model: pc.DexpiModel, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ExtendedProteusSerializer().save(model, path.parent, path.name)
