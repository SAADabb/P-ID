"""Structural validation of a topology (schema, identifiers, connections, model classes).

Validation never changes the topology.  It returns a :class:`ValidationReport` that the
CLI prints and writes to ``reports/validation.md``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .catalog import SYMBOL_DIMS, component_class_ok, equipment_classes
from .schema import Boundary, Component, Equipment, Topology, logical, ports_of

# Accepted classes: every pyDEXPI equipment / piping-component class (see catalog.py).

IN_ROLES = {"inlet", "suction"}
OUT_ROLES = {"outlet", "discharge"}


@dataclass
class Issue:
    level: str  # error | warning | info
    code: str
    message: str
    objects: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    def add(self, level: str, code: str, message: str, *objects: str) -> None:
        self.issues.append(Issue(level, code, message, list(objects)))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _covered_by_unresolved(topo: Topology, obj_id: str) -> bool:
    return any(obj_id in u.affects and u.status == "open" for u in topo.unresolved_requirements)


def validate(topo: Topology) -> ValidationReport:
    rep = ValidationReport()

    # ---------------------------------------------------------------- identifiers
    seen: dict[str, str] = {}
    for coll_name in ("areas", "equipment", "components", "boundaries", "instruments", "process_lines",
                      "signals", "control_requirements", "control_loops", "operating_modes",
                      "unresolved_requirements", "modifications"):
        for o in getattr(topo, coll_name):
            if o.id in seen:
                rep.add("error", "ID_DUPLICATE", f"id '{o.id}' used in {seen[o.id]} and {coll_name}", o.id)
            seen[o.id] = coll_name
    area_ids = {a.id for a in topo.areas}

    tags: dict[str, str] = {}
    for coll in (topo.equipment, topo.components, topo.instruments):
        for o in coll:
            if o.tag:
                if o.tag in tags:
                    rep.add("error", "TAG_DUPLICATE", f"tag '{o.tag}' used by {tags[o.tag]} and {o.id}", o.id, tags[o.tag])
                tags[o.tag] = o.id
            if o.tag and o.tag_status == "none":
                rep.add("error", "TAG_STATUS", f"{o.id} has a tag but tag_status 'none'", o.id)
            if not o.tag and o.tag_status != "none":
                rep.add("error", "TAG_STATUS", f"{o.id} has no tag but tag_status '{o.tag_status}'", o.id)

    # ------------------------------------------------------------------ provenance
    for oid, o in topo.objects().items():
        p = o.provenance
        if p.origin == "source":
            if p.document is None or p.page is None or not p.section:
                rep.add("error", "PROV_SOURCE", f"source object {oid} lacks document/page/section", oid)
        else:
            if not p.rule or not p.triggers or not p.explanation or p.status is None:
                rep.add("error", "PROV_GENERATED", f"generated object {oid} lacks rule/triggers/explanation/status", oid)
        if getattr(o, "tag_status", None) == "proposed" and p.origin == "source" and not any(
            m.object_id == oid and m.field == "tag" for m in topo.modifications
        ):
            rep.add("error", "TAG_PROPOSED_UNTRACKED", f"{oid} carries a proposed tag but no tag modification is recorded", oid)

    # ---------------------------------------------------------------- model classes
    for e in topo.equipment:
        if e.model_class not in equipment_classes():
            rep.add("error", "CLASS_UNSUPPORTED", f"equipment {e.id}: '{e.model_class}' is not a pyDEXPI equipment class "
                    "(see catalog.equipment_classes(); use CustomEquipment + symbol for anything else)", e.id)
        if e.symbol and e.symbol not in SYMBOL_DIMS:
            rep.add("error", "SYMBOL_UNKNOWN", f"equipment {e.id}: symbol '{e.symbol}' unknown (choose from {sorted(SYMBOL_DIMS)})", e.id)
        if e.area not in area_ids:
            rep.add("error", "AREA_UNKNOWN", f"equipment {e.id}: unknown area '{e.area}'", e.id)
        names = [n.name for n in e.nozzles]
        if len(names) != len(set(names)):
            rep.add("error", "NOZZLE_DUPLICATE", f"equipment {e.id} has duplicate nozzle names", e.id)
    for c in topo.components:
        if not component_class_ok(c.kind, c.model_class):
            rep.add("error", "CLASS_UNSUPPORTED", f"component {c.id}: '{c.model_class}' is not a pyDEXPI class for kind '{c.kind}'", c.id)
        if c.kind == "manifold" and (not c.branches or c.branches < 2 or c.role is None):
            rep.add("error", "MANIFOLD_DEF", f"manifold {c.id} needs role and >= 2 branches", c.id)
        if c.technology_status == "unspecified_generic" and c.technology:
            rep.add("error", "TECH_STATUS", f"{c.id}: technology set but marked unspecified_generic", c.id)
        if c.technology_status == "specified" and c.kind == "valve" and not c.technology and c.model_class == "CustomOperatedValve":
            rep.add("error", "TECH_STATUS", f"{c.id}: generic valve class without 'unspecified_generic' marking", c.id)

    # --------------------------------------------------------------------- lines
    conn = topo.connectable()
    used: dict[tuple[str, str], str] = {}
    out_ports: dict[str, list[str]] = defaultdict(list)
    for ln in topo.process_lines:
        if not ln.service:
            rep.add("error", "LINE_SERVICE", f"line {ln.id} has no service", ln.id)
        for end, r in (("from", ln.from_), ("to", ln.to)):
            o = conn.get(r.ref)
            if o is None:
                rep.add("error", "LINE_ENDPOINT", f"line {ln.id}: {end} object '{r.ref}' does not exist", ln.id)
                continue
            if r.port not in ports_of(o):
                rep.add("error", "LINE_PORT", f"line {ln.id}: {end} port '{r.port}' not on {r.ref}", ln.id, r.ref)
                continue
            key = (r.ref, r.port)
            if key in used:
                rep.add("error", "PORT_REUSED", f"port {r.ref}:{r.port} is used by lines {used[key]} and {ln.id}", ln.id, used[key])
            used[key] = ln.id
            _check_direction(rep, topo, ln.id, end, r.ref, r.port, o)
        if ln.logical_line is None:
            rep.add("warning", "LINE_LOGICAL", f"line {ln.id} has no logical_line", ln.id)

    # open ports
    for oid, o in conn.items():
        for p in ports_of(o):
            if (oid, p) in used:
                continue
            if isinstance(o, Component) and o.open_end and p == "out":
                continue
            lvl = "info" if (_covered_by_unresolved(topo, oid) or getattr(o, "lifecycle", "") == "future") else "warning"
            rep.add(lvl, "PORT_OPEN", f"{oid}:{p} is not connected" + ("" if lvl == "warning" else " (documented as unresolved/future)"), oid)

    # --------------------------------------------------------------- instruments
    inst = {i.id: i for i in topo.instruments}
    logical_ids = {logical(l) for l in topo.process_lines}
    eq_ids = {e.id for e in topo.equipment}
    for i in topo.instruments:
        t = i.target
        if t:
            if t["kind"] == "line" and t["ref"] not in logical_ids:
                rep.add("error", "INSTR_TARGET", f"instrument {i.id}: target line '{t['ref']}' unknown", i.id)
            if t["kind"] == "equipment" and t["ref"] not in eq_ids:
                rep.add("error", "INSTR_TARGET", f"instrument {i.id}: target equipment '{t['ref']}' unknown", i.id)
    for s in topo.signals:
        for end in (s.from_, s.to):
            if end not in inst and end not in conn:
                rep.add("error", "SIGNAL_ENDPOINT", f"signal {s.id}: '{end}' unknown", s.id)
    for lp in topo.control_loops:
        for part in (lp.measurement, lp.controller):
            if part not in inst:
                rep.add("error", "LOOP_MEMBER", f"loop {lp.id}: instrument '{part}' unknown", lp.id)
        if lp.final_element not in conn:
            rep.add("error", "LOOP_MEMBER", f"loop {lp.id}: final element '{lp.final_element}' unknown", lp.id)
    loop_controllers = {lp.controller for lp in topo.control_loops}
    for i in topo.instruments:
        if i.function == "controller" and i.id not in loop_controllers:
            rep.add("error", "CONTROLLER_ORPHAN", f"controller {i.id} is not part of any control loop (a transmitter alone never implies a controller)", i.id)
    reqs = {r.id for r in topo.control_requirements}
    for lp in topo.control_loops:
        if lp.requirement and lp.requirement not in reqs:
            rep.add("error", "LOOP_REQUIREMENT", f"loop {lp.id} references unknown requirement {lp.requirement}", lp.id)

    # ------------------------------------------------------- unresolved references
    all_ids = set(seen)
    for u in topo.unresolved_requirements:
        for a in u.affects:
            if a not in all_ids:
                rep.add("warning", "UNRESOLVED_REF", f"unresolved {u.id} affects unknown id '{a}'", u.id)
    return rep


def _check_direction(rep: ValidationReport, topo: Topology, line_id: str, end: str, ref: str, port: str, o: Any) -> None:
    """A line must leave outlets and arrive at inlets (``from`` = flow start)."""
    arriving = end == "to"
    if isinstance(o, Equipment):
        nz = next((n for n in o.nozzles if n.name == port), None)
        if nz is None:
            return
        if nz.role in IN_ROLES and not arriving:
            rep.add("error", "FLOW_DIRECTION", f"line {line_id} leaves inlet nozzle {ref}:{port}", line_id, ref)
        if nz.role in OUT_ROLES and arriving:
            rep.add("error", "FLOW_DIRECTION", f"line {line_id} arrives at outlet nozzle {ref}:{port}", line_id, ref)
    elif isinstance(o, Boundary):
        if o.direction == "in" and arriving:
            rep.add("error", "FLOW_DIRECTION", f"line {line_id} arrives at inflow boundary {ref}", line_id, ref)
        if o.direction == "out" and not arriving:
            rep.add("error", "FLOW_DIRECTION", f"line {line_id} leaves outflow boundary {ref}", line_id, ref)
    elif isinstance(o, Component):
        if o.kind == "manifold":
            if port == "common":
                want_arrive = o.role == "split"
            else:
                want_arrive = o.role == "merge"
            if arriving != want_arrive:
                rep.add("error", "FLOW_DIRECTION", f"line {line_id} has wrong direction at {o.role} manifold {ref}:{port}", line_id, ref)
        else:
            if port == "in" and not arriving:
                rep.add("error", "FLOW_DIRECTION", f"line {line_id} leaves valve inlet {ref}:in", line_id, ref)
            if port == "out" and arriving:
                rep.add("error", "FLOW_DIRECTION", f"line {line_id} arrives at valve outlet {ref}:out", line_id, ref)


def render_markdown(rep: ValidationReport, title: str = "Validation report") -> str:
    lines = [f"# {title}", ""]
    lines.append(f"**Result: {'PASS' if rep.ok else 'FAIL'}** — {len(rep.errors)} error(s), {len(rep.warnings)} warning(s), "
                 f"{sum(1 for i in rep.issues if i.level == 'info')} info.")
    lines.append("")
    for level in ("error", "warning", "info"):
        items = [i for i in rep.issues if i.level == level]
        if not items:
            continue
        lines.append(f"## {level.capitalize()}s ({len(items)})")
        lines.append("")
        for i in items:
            lines.append(f"- `{i.code}` {i.message}")
        lines.append("")
    return "\n".join(lines)
