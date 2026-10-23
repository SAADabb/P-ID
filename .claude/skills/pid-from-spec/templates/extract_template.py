"""Extraction record template: copy to projects/<name>/extraction/extract_<name>.py and fill in.

Every object needs provenance: S(page, section, "verbatim quote", basis="explicit|interpreted|structural", note=...).
Run:  PYTHONPATH=. python projects/<name>/extraction/extract_<name>.py
"""

from __future__ import annotations

from pathlib import Path

from pid_workflow.schema import Topology
from pid_workflow.topology_io import save_topology

DOC = "your_specification.pdf"
OUT = Path(__file__).resolve().parents[1] / "source_topology.json"


def S(page, section, quote=None, basis="explicit", note=None):
    return {"origin": "source", "document": DOC, "page": page, "section": section, "quote": quote, "basis": basis, "note": note}


def A(value, unit=None, prov=None):
    return {"value": value, "unit": unit, "provenance": prov}


topo: dict = {
    "schema_version": "1.0",
    "metadata": {"drawing_id": "PID-XXX-001", "title": "TITLE", "project": "PROJECT", "revision": "A (draft for review)", "language": "en",
                 "source_documents": [{"id": "spec", "file": DOC, "pages": 1, "language": "en"}],
                 "engineering_basis": []},  # e.g. {"statement": "ISA 5.1 tags", "provenance": S(1, "sec")}
    "areas": [], "equipment": [], "components": [], "boundaries": [], "instruments": [], "process_lines": [], "signals": [],
    "control_requirements": [], "control_loops": [], "operating_modes": [], "unresolved_requirements": [], "modifications": [],
}
_n = {"line": 0}


def area(id_, name, prov, desc=None):
    topo["areas"].append({"id": id_, "name": name, "description": desc, "provenance": prov})


def eq(id_, name, cls, area_, prov, tag=None, lifecycle="unspecified", nozzles=(), attrs=None):
    """nozzles: [(name, role)] with role inlet|suction|outlet|discharge (vent/drain are added by rules)."""
    topo["equipment"].append({
        "id": id_, "name": name, "tag": tag, "tag_status": "source" if tag else "none", "model_class": cls, "area": area_,
        "lifecycle": lifecycle, "nozzles": [{"name": n, "role": r, "number": None, "size": None, "service": None} for n, r in nozzles],
        "attributes": attrs or {}, "provenance": prov})


def manifold(id_, name, role, branches, area_, prov):
    topo["components"].append({"id": id_, "name": name, "kind": "manifold", "model_class": "PipeTee", "role": role, "branches": branches,
                               "area": area_, "provenance": prov})


def valve(id_, name, area_, prov, function, operation="unknown"):
    """A valve the document itself names. Technology unknown -> generic, never guessed."""
    topo["components"].append({"id": id_, "name": name, "kind": "valve", "model_class": "CustomOperatedValve", "function": function,
                               "technology": None, "technology_status": "unspecified_generic", "operation": operation, "tag": None,
                               "tag_status": "none", "area": area_, "attributes": {}, "provenance": prov})


def boundary(id_, name, direction, service, area_, prov):
    topo["boundaries"].append({"id": id_, "name": name, "direction": direction, "service": service, "area": area_, "attributes": {}, "provenance": prov})


def ref(s):  # "object:port"
    obj, port = s.rsplit(":", 1)
    return {"ref": obj, "port": port}


def line(frm, to, service, prov, name=None, props=None, header=False, id_=None):
    if id_ is None:
        _n["line"] += 1
        id_ = f"ln.{_n['line']:03d}"
    topo["process_lines"].append({"id": id_, "name": name, "service": service, "from": ref(frm), "to": ref(to), "logical_line": id_,
                                  "split_from": None, "line_number": None, "header": header, "properties": props or {}, "provenance": prov})
    return id_


def unresolved(id_, category, description, affects, prov, question=None):
    topo["unresolved_requirements"].append({"id": id_, "name": None, "category": category, "description": description, "affects": affects,
                                            "needed_for": None, "question": question, "status": "open", "provenance": prov})


# ------------------------------------------------------------------ fill in from the specification
area("ar.main", "Main area", S(1, "1"))
eq("eq.tank_a", "Feed tank", "Tank", "ar.main", S(1, "1", "…verbatim…"), tag="T-1", nozzles=[("out", "outlet")])
eq("eq.pump_a", "Feed pump", "CentrifugalPump", "ar.main", S(1, "1"), tag="P-1", nozzles=[("s", "suction"), ("d", "discharge")])
eq("eq.tank_b", "Receiver", "Tank", "ar.main", S(1, "1"), nozzles=[("in", "inlet")])
line("eq.tank_a:out", "eq.pump_a:s", "Water", S(1, "1"))
line("eq.pump_a:d", "eq.tank_b:in", "Water", S(1, "1"))

if __name__ == "__main__":
    t = Topology.model_validate(topo)
    print("wrote", OUT, save_topology(t, OUT)[:12])
