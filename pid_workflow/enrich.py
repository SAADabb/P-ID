"""Enrichment: apply project rules to complete the logical topology.

Every rule is idempotent and only fires when its prerequisites are established.  All
additions are generated objects with ``status: pending_review``.  Inline components are
inserted by *splitting* the original line (service and properties preserved); branches and
bypasses use explicit manifolds.  Nothing is invented that the generic policy lists under
``never_invent``: such gaps become unresolved requirements instead.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .catalog import is_a
from .policy import Policy, Rule
from .schema import (
    Attr,
    Component,
    ControlLoop,
    Equipment,
    Instrument,
    Modification,
    Nozzle,
    ProcessLine,
    Ref,
    Signal,
    Topology,
    Unresolved,
    generated_prov,
    logical,
)

SIMPLE_KINDS = {"valve", "check_valve", "strainer"}


@dataclass
class LogEntry:
    rule: str
    action: str  # added | reused | blocked | skipped | note
    object_id: str
    message: str


@dataclass
class EnrichResult:
    topology: Topology
    log: list[LogEntry] = field(default_factory=list)


# rules that summarise or label the result run after the rules that add objects
_PHASE = {"tagging": 2, "line_numbering": 2, "unresolved_summary": 3}


def slug(obj_id: str) -> str:
    return obj_id.split(".", 1)[1] if "." in obj_id else obj_id


class Enricher:
    def __init__(self, topo: Topology, policy: Policy):
        self.t = topo
        self.policy = policy
        self.log: list[LogEntry] = []
        self.rejected: set[str] = {m.object_id for m in topo.modifications if m.field == "rejected"}
        self._mod_counter: dict[str, int] = {}
        self._reindex()
        self.handlers: dict[str, Callable[[Rule], None]] = {
            "pump_auxiliaries": self.rule_pump_auxiliaries,
            "mode_isolation": self.rule_mode_isolation,
            "header_instrumentation": self.rule_header_instrumentation,
            "control_valve_manifold": self.rule_control_valve_manifold,
            "vessel_auxiliaries": self.rule_vessel_auxiliaries,
            "control_loop": self.rule_control_loop,
            "line_numbering": self.rule_line_numbering,
            "equipment_template": self.rule_equipment_template,
            "tagging": self.rule_tagging,
            "unresolved_summary": self.rule_unresolved_summary,
        }

    # ------------------------------------------------------------------ plumbing
    def _reindex(self) -> None:
        self.by_from = {(l.from_.ref, l.from_.port): l for l in self.t.process_lines}
        self.by_to = {(l.to.ref, l.to.port): l for l in self.t.process_lines}
        self.eq = {e.id: e for e in self.t.equipment}
        self.comp = {c.id: c for c in self.t.components}
        self.inst = {i.id: i for i in self.t.instruments}

    def run(self) -> EnrichResult:
        for rule in sorted(self.policy.rules, key=lambda r: _PHASE.get(r.type, 1)):
            if not rule.enabled:
                continue
            handler = self.handlers.get(rule.type)
            if handler is None:
                self.note(rule.id, "skipped", rule.id, f"unknown rule type '{rule.type}'")
                continue
            handler(rule)
            self._reindex()
        return EnrichResult(self.t, self.log)

    def note(self, rule: str, action: str, obj: str, msg: str) -> None:
        self.log.append(LogEntry(rule, action, obj, msg))

    def _expl(self, rule: Rule, text: str) -> str:
        src = rule.source or {}
        if src.get("page"):
            cite = f"PDF p.{src.get('page')} §{src.get('section')}"
        elif src.get("pack"):
            cite = f"good-practice pack '{src['pack']}' – not stated in the specification"
        else:
            cite = "generic policy"
        return f"Project rule '{rule.id}' ({cite}): {text}"

    def _record_mod(self, rule: Rule, obj_id: str, field_: str, old: Any, new: Any, why: str) -> None:
        key = f"mod.{obj_id}.{field_}"
        n = self._mod_counter.get(key, 0) + 1
        self._mod_counter[key] = n
        mid = key if n == 1 else f"{key}.{n}"
        if any(m.id == mid for m in self.t.modifications):  # idempotent
            self._mod_counter[key] = n
            return
        self.t.modifications.append(
            Modification(id=mid, object_id=obj_id, field=field_, old=old, new=new,
                         provenance=generated_prov(rule.id, [obj_id], why))
        )

    # ------------------------------------------------------------------- graph ops
    def attached(self, ref: str, port: str) -> ProcessLine | None:
        return self.by_from.get((ref, port)) or self.by_to.get((ref, port))

    def trace(self, ref: str, port: str) -> tuple[list[Component], str | None, str | None]:
        """Walk away from an equipment/component port through simple valves.

        Returns ``(chain, end_ref, end_port)`` with the chain ordered outward from the port.
        """
        chain: list[Component] = []
        line = self.by_to.get((ref, port))
        if line is not None:  # flow arrives here: go upstream
            cur = line.from_
            while True:
                c = self.comp.get(cur.ref)
                if c is not None and c.kind in SIMPLE_KINDS:
                    chain.append(c)
                    nxt = self.by_to.get((c.id, "in"))
                    if nxt is None:
                        return chain, c.id, "in"
                    cur = nxt.from_
                else:
                    return chain, cur.ref, cur.port
        line = self.by_from.get((ref, port))
        if line is not None:  # flow leaves here: go downstream
            cur = line.to
            while True:
                c = self.comp.get(cur.ref)
                if c is not None and c.kind in SIMPLE_KINDS:
                    chain.append(c)
                    nxt = self.by_from.get((c.id, "out"))
                    if nxt is None:
                        return chain, c.id, "out"
                    cur = nxt.to
                else:
                    return chain, cur.ref, cur.port
        return chain, None, None

    def _child(self, line: ProcessLine, suffix: str, frm: Ref, to: Ref, rule: Rule, trigger: str, why: str) -> ProcessLine:
        return ProcessLine.model_validate(
            {
                "id": f"{line.id}/{suffix}",
                "name": line.name,
                "service": line.service,
                "from": frm.model_dump(),
                "to": to.model_dump(),
                "logical_line": logical(line),
                "split_from": line.id,
                "line_number": line.line_number,
                "header": line.header,
                "properties": {k: v.model_dump() for k, v in line.properties.items()},
                "attributes": {},
                "provenance": generated_prov(
                    rule.id, [line.id, trigger],
                    f"{why} Part of source line {line.id} ({_src_cite(line)}); service and properties preserved.",
                ).model_dump(),
            }
        )

    def _replace_line(self, old: ProcessLine, new: list[ProcessLine]) -> None:
        i = self.t.process_lines.index(old)
        self.t.process_lines[i : i + 1] = new
        self._reindex()

    def insert_inline(self, line: ProcessLine, comp: Component, rule: Rule, why: str) -> tuple[ProcessLine, ProcessLine]:
        """Insert a two-port component by splitting ``line`` (A→B becomes A→comp→B)."""
        l1 = self._child(line, "1", line.from_, Ref(ref=comp.id, port="in"), rule, comp.id, why)
        l2 = self._child(line, "2", Ref(ref=comp.id, port="out"), line.to, rule, comp.id, why)
        self.t.components.append(comp)
        self._replace_line(line, [l1, l2])
        self._record_mod(rule, line.id, "split", self._orig_line(line),
                         {"inserted": comp.id, "children": [l1.id, l2.id]}, why)
        return l1, l2

    @staticmethod
    def _orig_line(line: ProcessLine) -> dict[str, Any]:
        d = line.model_dump(mode="json", by_alias=True)
        return {"from": d["from"], "to": d["to"], "line": d}

    def insert_manifold(self, line: ProcessLine, comp: Component, rule: Rule, why: str) -> tuple[ProcessLine, ProcessLine]:
        """Insert a 2-branch manifold into ``line``; the second branch (b2) is left free.

        split: A→common, b1→B      merge: A→b1, common→B
        """
        if comp.role == "split":
            a, b = Ref(ref=comp.id, port="common"), Ref(ref=comp.id, port="b1")
        else:
            a, b = Ref(ref=comp.id, port="b1"), Ref(ref=comp.id, port="common")
        l1 = self._child(line, "1", line.from_, a, rule, comp.id, why)
        l2 = self._child(line, "2", b, line.to, rule, comp.id, why)
        self.t.components.append(comp)
        self._replace_line(line, [l1, l2])
        self._record_mod(rule, line.id, "split", self._orig_line(line),
                         {"inserted": comp.id, "children": [l1.id, l2.id]}, why)
        return l1, l2

    def new_line(self, id_: str, frm: tuple[str, str], to: tuple[str, str], service: str, rule: Rule, triggers: list[str], why: str, name: str | None = None) -> ProcessLine:
        ln = ProcessLine.model_validate(
            {
                "id": id_, "name": name, "service": service,
                "from": {"ref": frm[0], "port": frm[1]}, "to": {"ref": to[0], "port": to[1]},
                "logical_line": id_, "split_from": None, "line_number": None, "header": False,
                "properties": {}, "attributes": {},
                "provenance": generated_prov(rule.id, triggers, why).model_dump(),
            }
        )
        self.t.process_lines.append(ln)
        self._reindex()
        return ln

    def make_valve(self, id_: str, name: str, function: str, operation: str, rule: Rule, triggers: list[str], why: str,
                   area: str | None, model_class: str | None = None, technology: str | None = None,
                   kind: str = "valve", open_end: str | None = None, extra: dict[str, Any] | None = None) -> Component:
        vd = self.policy.generic["valve_defaults"]
        generic = model_class is None
        attrs: dict[str, Any] = {}
        if generic:
            attrs["type_name"] = {"value": vd["generic_type_names"].get(function, vd["generic_type_name"]), "unit": None}
        attrs.update(extra or {})
        return Component.model_validate(
            {
                "id": id_, "name": name, "kind": kind,
                "model_class": model_class or vd["generic_class"],
                "function": function,
                "technology": None if generic else technology,
                "technology_status": "unspecified_generic" if generic else "specified",
                "operation": operation, "tag": None, "tag_status": "none", "area": area,
                "lifecycle": "new", "open_end": open_end, "attributes": attrs,
                "provenance": generated_prov(rule.id, triggers, why).model_dump(),
            }
        )

    def make_manifold(self, id_: str, name: str, role: str, rule: Rule, triggers: list[str], why: str, area: str | None, of: str) -> Component:
        return Component.model_validate(
            {
                "id": id_, "name": name, "kind": "manifold", "model_class": "PipeTee", "role": role, "branches": 2,
                "area": area, "lifecycle": "new",
                "attributes": {"manifold_of": {"value": of, "unit": None}},
                "provenance": generated_prov(rule.id, triggers, why).model_dump(),
            }
        )

    def _label(self, eq_id: str) -> str:
        e = self.eq.get(eq_id)
        return (e.tag or e.name or eq_id) if e else eq_id

    def _service_near(self, eq: Equipment) -> str:
        for n in eq.nozzles:
            ln = self.attached(eq.id, n.name)
            if ln is not None:
                return ln.service
        return "Utility"

    def _find_function(self, chain: list[Component], function: str) -> Component | None:
        return next((c for c in chain if c.function == function), None)

    def _add_trigger(self, comp: Component, trigger: str) -> None:
        if comp.provenance.origin == "generated" and trigger not in comp.provenance.triggers:
            comp.provenance.triggers.append(trigger)

    # =============================================================== R: pumps
    def rule_pump_auxiliaries(self, rule: Rule) -> None:
        p = rule.params
        classes = set(p["applies_to_classes"])
        for pump in [e for e in self.t.equipment if e.model_class in classes and e.lifecycle != "future"]:
            lab = self._label(pump.id)
            sl = slug(pump.id)
            # ---- suction: manual isolation valve
            for spec in p["suction"]:
                self._ensure_adjacent(rule, pump, p["suction_nozzle_role"], [spec], f"pc.gen.{sl}.suction_{spec['function']}", f"{lab} suction")
            # ---- discharge: check valve then isolation valve (outward from the nozzle)
            self._ensure_adjacent(rule, pump, p["discharge_nozzle_role"], p["discharge"], f"pc.gen.{sl}.discharge_", f"{lab} discharge")

    def _ensure_adjacent(self, rule: Rule, eq: Equipment, role: str, specs: list[dict[str, Any]], id_prefix: str, label: str,
                         trigger_extra: list[str] | None = None) -> None:
        """Make sure the given ordered valve functions exist next to the nozzle with ``role``."""
        nz = next((n for n in eq.nozzles if n.role == role), None)
        if nz is None:
            self.note(rule.id, "blocked", eq.id, f"{label}: no nozzle with role '{role}'")
            return
        if self.attached(eq.id, nz.name) is None:
            self.note(rule.id, "blocked", eq.id, f"{label}: nozzle '{nz.name}' has no line yet (prerequisite missing)")
            return
        triggers = [eq.id] + (trigger_extra or [])
        for idx, spec in enumerate(specs):
            chain, _, _ = self.trace(eq.id, nz.name)
            existing = self._find_function(chain, spec["function"])
            if existing is not None:
                self._add_trigger(existing, triggers[-1])
                self.note(rule.id, "reused", existing.id, f"{label}: existing {spec['function']} valve {existing.tag or existing.id} reused")
                continue
            # insertion point: after the last already-satisfied preceding item, else at the nozzle
            prev_fn = [s["function"] for s in specs[:idx]]
            anchor = None
            for c in chain:
                if c.function in prev_fn:
                    anchor = c
            if anchor is None:
                line = self.attached(eq.id, nz.name)
            else:
                line = self.by_from.get((anchor.id, "out")) if nz.role in {"discharge", "outlet"} else self.by_to.get((anchor.id, "in"))
            if line is None:
                self.note(rule.id, "blocked", eq.id, f"{label}: no line to split for {spec['function']} valve")
                continue
            fn = spec["function"]
            cid = f"{id_prefix}{fn}" if id_prefix.endswith("_") else id_prefix
            if cid in self.rejected:
                self.note(rule.id, "skipped", cid, f"{label}: {fn} valve was rejected by the reviewer")
                continue
            if fn == "check":
                comp = self.make_valve(cid, f"Check valve – {label}", fn, spec.get("operation", "unknown"), rule, triggers,
                                       self._expl(rule, f"{label} needs a check valve ('clapet anti-retour') after the pump."),
                                       eq.area, model_class="CheckValve", technology="check", kind="check_valve")
            else:
                op = spec.get("operation", "unknown")
                comp = self.make_valve(cid, f"{'Suction' if 'suction' in label else 'Discharge'} isolation valve – {label.split(' ')[0]}", fn, op, rule, triggers,
                                       self._expl(rule, f"{label} needs a {'manual ' if op == 'manual' else ''}isolation valve. Technology is not specified by the source, so a generic valve is used."),
                                       eq.area)
            self.insert_inline(line, comp, rule, comp.provenance.explanation or "")
            self.note(rule.id, "added", comp.id, f"{label}: {fn} valve inserted by splitting {line.id}")

    # ================================================== R: equipment template
    def rule_equipment_template(self, rule: Rule) -> None:
        """Declarative auxiliaries for every equipment of the given DEXPI classes (subclasses included).

        params:
          applies_to: [Pump]                      DEXPI class names; subclasses match (CentrifugalPump is a Pump)
          include_existing: true                  existing equipment is populated but flagged 'verify'
          inline: {suction: [{function: isolation, operation: manual}, {function: strainer}], ...}
                                                  per nozzle role, ordered outward from the nozzle; every nozzle with the role
          open_ends: [{nozzle_role: drain, function: drain}, {nozzle_role: relief, function: relief}]
          instruments: [{isa_code: PI, variable: pressure, at: {line_of: discharge}},
                        {isa_code: LT, variable: level, at: {nozzle_role: level_tap}}]
        """
        p = rule.params
        bases = list(p.get("applies_to", []))
        only, exclude = set(p.get("only") or []), set(p.get("exclude") or [])
        targets = [e for e in self.t.equipment if any(e.model_class == b or is_a(e.model_class, b) for b in bases)
                   and (not only or e.id in only) and e.id not in exclude]
        for e in targets:
            if e.lifecycle == "future":
                self.note(rule.id, "skipped", e.id, "future equipment: not populated")
                continue
            if e.lifecycle == "existing" and not p.get("include_existing", True):
                continue
            lab = self._label(e.id)
            sl = slug(e.id)
            verify = " Existing equipment: verify what is already installed before accepting." if e.lifecycle in {"existing", "modified"} else ""
            for role, specs in (p.get("inline") or {}).items():
                for nz in [n for n in e.nozzles if n.role == role]:
                    if self.attached(e.id, nz.name) is None:
                        self.note(rule.id, "blocked", e.id, f"{lab} {nz.name}: no line connected (prerequisite missing)")
                        continue
                    self._ensure_inline(rule, e, nz, specs, f"pc.gen.{sl}.{nz.name}_", f"{lab} {nz.name.replace('_', ' ')}", verify)
            for oe in p.get("open_ends") or []:
                self._ensure_open_end(rule, e, oe["nozzle_role"], oe.get("function", oe["nozzle_role"]), oe.get("operation", "unknown"), verify)
            for ins in p.get("instruments") or []:
                self._ensure_instrument(rule, e, ins, verify)

    def _ensure_inline(self, rule: Rule, eq: Equipment, nz: Nozzle, specs: list[dict[str, Any]], id_prefix: str, label: str, verify: str) -> None:
        outward = nz.role in {"discharge", "outlet"}
        for idx, spec in enumerate(specs):
            fn = spec["function"]
            chain, _, _ = self.trace(eq.id, nz.name)
            existing = self._find_function(chain, fn) if fn != "strainer" else next((c for c in chain if c.kind == "strainer"), None)
            if existing is not None:
                self._add_trigger(existing, eq.id)
                self.note(rule.id, "reused", existing.id, f"{label}: existing {fn} {existing.tag or existing.id} reused")
                continue
            prev = [s_["function"] for s_ in specs[:idx]]
            anchor = None
            for c in chain:
                if c.function in prev or (c.kind == "strainer" and "strainer" in prev):
                    anchor = c
            line = self.attached(eq.id, nz.name) if anchor is None else (
                self.by_from.get((anchor.id, "out")) if outward else self.by_to.get((anchor.id, "in")))
            if line is None:
                self.note(rule.id, "blocked", eq.id, f"{label}: no line to split for the {fn}")
                continue
            cid = f"{id_prefix}{fn}"
            if cid in self.rejected:
                self.note(rule.id, "skipped", cid, f"{label}: {fn} was rejected by the reviewer")
                continue
            why = self._expl(rule, f"{label} needs {'a ' + fn + ' valve' if fn not in ('check', 'strainer') else ('a check valve' if fn == 'check' else 'a strainer')}."
                             f"{verify} {'' if spec.get('model_class') else 'Technology not specified: generic representation.'}".strip())
            if fn == "check":
                comp = self.make_valve(cid, f"Check valve – {label}", fn, "unknown", rule, [eq.id], why, eq.area,
                                       model_class=spec.get("model_class", "CheckValve"), technology="check", kind="check_valve")
            elif fn == "strainer":
                comp = self.make_valve(cid, f"Strainer – {label}", fn, "unknown", rule, [eq.id], why, eq.area,
                                       model_class=spec.get("model_class", "Strainer"), technology="strainer", kind="strainer")
            else:
                comp = self.make_valve(cid, f"{fn.capitalize()} valve – {label}", fn, spec.get("operation", "unknown"), rule, [eq.id], why, eq.area,
                                       model_class=spec.get("model_class"), technology=spec.get("technology"))
            self.insert_inline(line, comp, rule, why)
            self.note(rule.id, "added", comp.id, f"{label}: {fn} inserted by splitting {line.id}")

    def _ensure_open_end(self, rule: Rule, e: Equipment, role: str, function: str, operation: str, verify: str) -> None:
        lab = self._label(e.id)
        sl = slug(e.id)
        nz = self._ensure_nozzle(rule, e, role, role)
        if self.attached(e.id, nz.name) is not None:
            chain, _, _ = self.trace(e.id, nz.name)
            if self._find_function(chain, function) is not None or (function == "relief" and any(c.kind == "relief" for c in chain)):
                self.note(rule.id, "reused", e.id, f"{lab}: {function} already present")
                return
            self.note(rule.id, "blocked", e.id, f"{lab}: nozzle {nz.name} already connected; no {function} added")
            return
        vid = f"pc.gen.{sl}.{role}"
        if vid in self.rejected:
            self.note(rule.id, "skipped", vid, f"{lab}: {function} rejected by the reviewer")
            return
        service = self._service_near(e)
        if function == "relief":
            why = self._expl(rule, f"{lab} needs an overpressure protection device.{verify} Set pressure, sizing, type and discharge "
                                   "destination are not given and are not assumed (see the relief open point).")
            v = self.make_valve(vid, f"Relief device – {lab}", "relief", "unknown", rule, [e.id], why, e.area,
                                model_class="CustomSafetyValveOrFitting", kind="relief", open_end="relief",
                                extra={"type_name": {"value": "Relief device - type and sizing to be determined", "unit": None}})
            line_service = f"Relief ({service})"
        else:
            kind_txt = {"drain": "low-point drain", "vent": "high-point vent"}.get(function, function)
            why = self._expl(rule, f"{lab} needs a {kind_txt} valve.{verify} Technology not specified: generic valve.")
            v = self.make_valve(vid, f"{function.capitalize()} valve – {lab}", function, operation, rule, [e.id], why, e.area,
                                open_end=function if function in ("drain", "vent") else "drain")
            line_service = f"{function.capitalize()} ({service})"
        self.t.components.append(v)
        self._reindex()
        self.new_line(f"ln.gen.{sl}.{role}", (e.id, nz.name), (v.id, "in"), line_service, rule, [e.id], why, name=f"{function.capitalize()} of {lab}")
        self.note(rule.id, "added", v.id, f"{lab}: {function} added")

    def _ensure_instrument(self, rule: Rule, e: Equipment, ins: dict[str, Any], verify: str) -> None:
        lab = self._label(e.id)
        sl = slug(e.id)
        at = ins.get("at", {})
        code = ins["isa_code"]
        if "nozzle_role" in at:
            nz = self._ensure_nozzle(rule, e, at["nozzle_role"], at["nozzle_role"])
            tgt = {"kind": "equipment", "ref": e.id, "port": nz.name}
            iid = f"in.{sl}.{code.lower()}"
        else:
            nz = next((n for n in e.nozzles if n.role == at.get("line_of")), None)
            line = self.attached(e.id, nz.name) if nz is not None else None
            if line is None:
                self.note(rule.id, "blocked", e.id, f"{lab}: no {at.get('line_of')} line for {code}")
                return
            # measure on the line beyond the inline auxiliaries
            chain, _, _ = self.trace(e.id, nz.name)
            if chain:
                last = chain[-1]
                line = (self.by_from.get((last.id, "out")) if nz.role in {"discharge", "outlet"} else self.by_to.get((last.id, "in"))) or line
            tgt = {"kind": "line", "ref": logical(line)}
            iid = f"in.{sl}.{nz.name}.{code.lower()}"
        if any(i.target == tgt and i.isa_code == code for i in self.t.instruments):
            self.note(rule.id, "reused", e.id, f"{lab}: {code} already present")
            return
        if iid in self.rejected:
            self.note(rule.id, "skipped", iid, f"{lab}: {code} rejected by the reviewer")
            return
        fn = "indicator" if code.endswith("I") and not code.endswith("IC") else "transmitter"
        self.t.instruments.append(Instrument.model_validate({
            "id": iid, "name": f"{ins.get('name', code)} – {lab}", "isa_code": code, "measured_variable": ins.get("variable", ""),
            "function": fn, "loop_id": None, "target": tgt, "tag": None, "tag_status": "none", "area": e.area, "attributes": {},
            "provenance": generated_prov(rule.id, [e.id], self._expl(rule, f"{lab} needs a {code} ({ins.get('variable', '')}).{verify} Range not specified.")).model_dump(),
        }))
        self.note(rule.id, "added", iid, f"{lab}: {code} added")

    # ======================================================= R: mode isolation
    def rule_mode_isolation(self, rule: Rule) -> None:
        modes = set(rule.params["modes"])
        vspec = rule.params["valve"]
        for mode in self.t.operating_modes:
            if mode.id not in modes:
                continue
            for req in mode.requirements:
                if req.action != "isolate":
                    continue
                for tgt in req.targets:
                    e = self.eq.get(tgt.ref)
                    if e is None:
                        continue
                    nz = next((n for n in e.nozzles if n.name == tgt.port), None)
                    if nz is None:
                        continue
                    sl = slug(e.id)
                    self._ensure_adjacent_port(rule, e, nz, vspec, f"pc.gen.{sl}.{nz.name}_isolation", f"{self._label(e.id)} {nz.name}", mode.id)

    def _ensure_adjacent_port(self, rule: Rule, eq: Equipment, nz: Nozzle, spec: dict[str, Any], cid: str, label: str, mode_id: str) -> None:
        if self.attached(eq.id, nz.name) is None:
            self.note(rule.id, "blocked", eq.id, f"{label}: nozzle has no line")
            return
        if cid in self.rejected:
            self.note(rule.id, "skipped", cid, f"{label}: isolation valve was rejected by the reviewer")
            return
        chain, _, _ = self.trace(eq.id, nz.name)
        existing = self._find_function(chain, spec["function"])
        if existing is not None:
            self._add_trigger(existing, mode_id)
            self.note(rule.id, "reused", existing.id, f"{label}: isolation valve already present ({existing.tag or existing.id}); mode {mode_id} added as trigger")
            return
        line = self.attached(eq.id, nz.name)
        comp = self.make_valve(cid, f"Isolation valve – {label}", spec["function"], spec.get("operation", "unknown"), rule, [eq.id, mode_id],
                               self._expl(rule, f"mode '{mode_id}' requires isolation toward {label}; no isolation valve exists there. Technology not specified: generic valve."),
                               eq.area)
        self.insert_inline(line, comp, rule, comp.provenance.explanation or "")
        self.note(rule.id, "added", comp.id, f"{label}: isolation valve inserted by splitting {line.id} (mode {mode_id})")

    # ========================================================== R: instruments
    def rule_header_instrumentation(self, rule: Rule) -> None:
        services = set(rule.params["services"])
        done: set[str] = set()
        for ln in list(self.t.process_lines):
            lg = logical(ln)
            if not ln.header or ln.service not in services or lg in done:
                continue
            done.add(lg)
            for spec in rule.params["instruments"]:
                tgt = {"kind": "line", "ref": lg}
                existing = next((i for i in self.t.instruments if i.target == tgt and i.isa_code == spec["isa_code"]), None)
                if existing is not None:
                    self.note(rule.id, "reused", existing.id, f"{spec['isa_code']} on header {lg} already present")
                    continue
                iid = f"in.{slug(lg)}.{spec['isa_code'].lower()}"
                if iid in self.rejected:
                    self.note(rule.id, "skipped", iid, "instrument was rejected by the reviewer")
                    continue
                inst = Instrument.model_validate(
                    {
                        "id": iid, "name": f"{spec['measured_variable'].capitalize()} transmitter – {ln.service} header",
                        "isa_code": spec["isa_code"], "measured_variable": spec["measured_variable"],
                        "function": "transmitter", "loop_id": None, "target": tgt,
                        "tag": None, "tag_status": "none", "area": self._area_of_line(ln),
                        "attributes": {},
                        "provenance": generated_prov(rule.id, [lg],
                                                     self._expl(rule, f"main header '{ln.service}' ({lg}) must carry a {spec['isa_code']}.")).model_dump(),
                    }
                )
                self.t.instruments.append(inst)
                self.note(rule.id, "added", iid, f"{spec['isa_code']} added on header {lg} ({ln.service})")

    def _area_of_line(self, ln: ProcessLine) -> str | None:
        for r in (ln.from_, ln.to):
            o = self.t.connectable().get(r.ref)
            a = getattr(o, "area", None)
            if a:
                return a
        return None

    # ===================================================== R: control-valve manifold
    def rule_control_valve_manifold(self, rule: Rule) -> None:
        p = rule.params
        for cv in [c for c in self.t.components if c.kind == "valve" and c.function == p["applies_to_function"]]:
            sl = slug(cv.id)
            lab = cv.tag or cv.name or cv.id
            l_in = self.by_to.get((cv.id, "in"))
            l_out = self.by_from.get((cv.id, "out"))
            if l_in is None or l_out is None:
                self.note(rule.id, "blocked", cv.id, f"{lab}: control valve is not connected on both sides (prerequisite missing)")
                continue
            why = lambda t: self._expl(rule, t)  # noqa: E731
            def dedicated(chain: list[Component]) -> list[Component]:
                """Leading isolation valves that belong to this control valve (source-given or generated for it)."""
                out: list[Component] = []
                for c_ in chain:
                    if c_.function == "isolation" and (c_.provenance.origin == "source" or cv.id in c_.provenance.triggers):
                        out.append(c_)
                    else:
                        break
                return out

            up_chain, _, _ = self.trace(cv.id, "in")
            dn_chain, _, _ = self.trace(cv.id, "out")
            # ---- isolation valves adjacent to the control valve (valves that serve other purposes, e.g. a pump's
            #      discharge isolation, are not reused: closing them would not isolate the control valve alone)
            for side, chain, spec_key, port, idn in (("upstream", up_chain, "upstream_isolation", "in", "iso_up"),
                                                      ("downstream", dn_chain, "downstream_isolation", "out", "iso_dn")):
                if f"pc.gen.{sl}.{idn}" in self.rejected:
                    self.note(rule.id, "skipped", f"pc.gen.{sl}.{idn}", f"{lab}: {side} isolation valve was rejected by the reviewer")
                    continue
                ex = (dedicated(chain) or [None])[0] or self.comp.get(f"pc.gen.{sl}.{idn}")
                if ex is not None:
                    self._add_trigger(ex, cv.id)
                    self.note(rule.id, "reused", ex.id, f"{lab}: existing {side} isolation valve reused")
                    continue
                spec = p[spec_key]
                comp = self.make_valve(f"pc.gen.{sl}.{idn}", f"{side.capitalize()} isolation valve – {lab}", "isolation",
                                       spec.get("operation", "unknown"), rule, [cv.id],
                                       why(f"control valve {lab} needs an {side} isolation valve. Technology not specified: generic valve."), cv.area)
                line = self.by_to[(cv.id, "in")] if port == "in" else self.by_from[(cv.id, "out")]
                self.insert_inline(line, comp, rule, comp.provenance.explanation or "")
                self.note(rule.id, "added", comp.id, f"{lab}: {side} isolation valve inserted")
            # ---- bypass: split upstream of the outermost isolation valve of this manifold, merge downstream of its outermost one
            if f"pc.gen.{sl}.byp_valve" in self.comp:
                self.note(rule.id, "reused", f"pc.gen.{sl}.byp_valve", f"{lab}: bypass already present")
            else:
                up_chain, _, _ = self.trace(cv.id, "in")
                dn_chain, _, _ = self.trace(cv.id, "out")
                up_iso, dn_iso = dedicated(up_chain), dedicated(dn_chain)
                up_line = self.by_to[((up_iso[-1].id if up_iso else cv.id), "in")]
                service = up_line.service
                t1 = self.make_manifold(f"pc.gen.{sl}.byp_split", f"Bypass split – {lab}", "split", rule, [cv.id],
                                        why(f"bypass branch point upstream of {lab}."), cv.area, cv.id)
                self.insert_manifold(up_line, t1, rule, t1.provenance.explanation or "")
                dn_line = self.by_from[((dn_iso[-1].id if dn_iso else cv.id), "out")]
                t2 = self.make_manifold(f"pc.gen.{sl}.byp_merge", f"Bypass merge – {lab}", "merge", rule, [cv.id],
                                        why(f"bypass return point downstream of {lab}."), cv.area, cv.id)
                self.insert_manifold(dn_line, t2, rule, t2.provenance.explanation or "")
                bv = p["bypass_valve"]
                byp = self.make_valve(f"pc.gen.{sl}.byp_valve", f"Bypass globe valve – {lab}", bv["function"], bv.get("operation", "unknown"), rule, [cv.id],
                                      why(f"bypass line of {lab} is equipped with a globe valve (technology explicit in the specification)."),
                                      cv.area, model_class=bv["model_class"], technology="globe")
                self.t.components.append(byp)
                self._reindex()
                self.new_line(f"ln.gen.{sl}.byp_in", (t1.id, "b2"), (byp.id, "in"), service, rule, [cv.id, t1.id], why("bypass line inlet."), name=f"Bypass of {lab}")
                self.new_line(f"ln.gen.{sl}.byp_out", (byp.id, "out"), (t2.id, "b2"), service, rule, [cv.id, t2.id], why("bypass line outlet."), name=f"Bypass of {lab}")
                self.note(rule.id, "added", byp.id, f"{lab}: bypass line with globe valve created (explicit manifold junctions)")
            # ---- purge valve between upstream isolation and control valve
            if f"pc.gen.{sl}.purge" in self.comp or self._find_function([c for c in self.t.components if c.attributes.get("manifold_of") and c.attributes["manifold_of"].value == cv.id], "purge"):
                self.note(rule.id, "reused", f"pc.gen.{sl}.purge", f"{lab}: purge valve already present")
            else:
                l_in = self.by_to[(cv.id, "in")]
                t3 = self.make_manifold(f"pc.gen.{sl}.purge_tee", f"Purge tee – {lab}", "split", rule, [cv.id],
                                        why(f"purge branch on the control-valve body side of {lab}."), cv.area, cv.id)
                self.insert_manifold(l_in, t3, rule, t3.provenance.explanation or "")
                sp = p["purge"]
                pv = self.make_valve(f"pc.gen.{sl}.purge", f"Purge valve – {lab}", sp["function"], sp.get("operation", "unknown"), rule, [cv.id],
                                     why(f"control-valve manifold of {lab} includes a purge valve ('soupape de purge'). Technology not specified: generic valve."),
                                     cv.area, open_end="drain",
                                     extra={"manifold_of": {"value": cv.id, "unit": None}})
                self.t.components.append(pv)
                self._reindex()
                self.new_line(f"ln.gen.{sl}.purge", (t3.id, "b2"), (pv.id, "in"), l_in.service, rule, [cv.id, t3.id],
                              why("purge line."), name=f"Purge of {lab}")
                self.note(rule.id, "added", pv.id, f"{lab}: purge valve added")

    # ============================================================= R: vessels
    def rule_vessel_auxiliaries(self, rule: Rule) -> None:
        p = rule.params
        classes = set(p["applies_to_classes"])
        for e in [e for e in self.t.equipment if e.model_class in classes]:
            if e.lifecycle == "future":
                self.note(rule.id, "skipped", e.id, "future equipment: not populated")
                continue
            if e.lifecycle == "existing" and not p.get("include_existing", True):
                continue
            lab = self._label(e.id)
            sl = slug(e.id)
            service = self._service_near(e)
            existing_note = " Existing equipment: verify the already installed drain/vent/level device before accepting." if e.lifecycle in {"existing", "modified"} else ""
            for key, role, nzname in (("drain", "drain", "drain"), ("vent", "vent", "vent")):
                nz = self._ensure_nozzle(rule, e, nzname, role)
                spec = p[key]
                ln = self.attached(e.id, nz.name)
                if ln is not None:
                    chain, _, _ = self.trace(e.id, nz.name)
                    ex = self._find_function(chain, spec["function"])
                    if ex is not None:
                        self.note(rule.id, "reused", ex.id, f"{lab}: {key} valve already present")
                        continue
                if f"pc.gen.{sl}.{key}" in self.rejected:
                    self.note(rule.id, "skipped", f"pc.gen.{sl}.{key}", f"{lab}: {key} valve was rejected by the reviewer")
                    continue
                label_txt = "low-point drain" if key == "drain" else "high-point vent"
                why = self._expl(rule, f"capacitive equipment {lab} needs a {label_txt} valve.{existing_note} Technology not specified: generic valve.")
                v = self.make_valve(f"pc.gen.{sl}.{key}", f"{key.capitalize()} valve – {lab}", spec["function"], spec.get("operation", "unknown"),
                                    rule, [e.id], why, e.area, open_end=key)
                self.t.components.append(v)
                self._reindex()
                self.new_line(f"ln.gen.{sl}.{key}", (e.id, nz.name), (v.id, "in"), f"{key.capitalize()} ({service})", rule, [e.id], why,
                              name=f"{key.capitalize()} of {lab}")
                self.note(rule.id, "added", v.id, f"{lab}: {key} valve added")
            # level transmitter
            lv = p["level"]
            nz = self._ensure_nozzle(rule, e, "level_tap", "level_tap")
            tgt = {"kind": "equipment", "ref": e.id, "port": nz.name}
            ex = next((i for i in self.t.instruments if i.target == tgt and i.isa_code == lv["isa_code"]), None)
            if ex is not None:
                self.note(rule.id, "reused", ex.id, f"{lab}: level transmitter already present")
            elif f"in.{sl}.{lv['isa_code'].lower()}" in self.rejected:
                self.note(rule.id, "skipped", f"in.{sl}.{lv['isa_code'].lower()}", f"{lab}: level transmitter was rejected by the reviewer")
            else:
                iid = f"in.{sl}.{lv['isa_code'].lower()}"
                self.t.instruments.append(Instrument.model_validate({
                    "id": iid, "name": f"Level transmitter – {lab}", "isa_code": lv["isa_code"],
                    "measured_variable": lv["measured_variable"], "function": "transmitter", "loop_id": None,
                    "target": tgt, "tag": None, "tag_status": "none", "area": e.area, "attributes": {},
                    "provenance": generated_prov(rule.id, [e.id], self._expl(rule, f"capacitive equipment {lab} needs a level transmitter.{existing_note}")).model_dump(),
                }))
                self.note(rule.id, "added", iid, f"{lab}: level transmitter added")

    def _ensure_nozzle(self, rule: Rule, e: Equipment, name: str, role: str) -> Nozzle:
        nz = next((n for n in e.nozzles if n.role == role), None)
        if nz is not None:
            return nz
        nz = Nozzle(name=name, role=role, number=None, size=None,
                    provenance=generated_prov(rule.id, [e.id], self._expl(rule, f"nozzle '{name}' ({role}) added to {self._label(e.id)}; number and size unknown.")))
        old = [n.name for n in e.nozzles]
        e.nozzles.append(nz)
        self._record_mod(rule, e.id, "nozzles", old, old + [name], f"added {role} nozzle (number and size not invented)")
        return nz

    # ======================================================== R: control loops
    def rule_control_loop(self, rule: Rule) -> None:
        codes = rule.params["controller_code"]
        for req in self.t.control_requirements:
            if not req.controller_required:
                continue
            sl = slug(req.id)
            if any(lp.requirement == req.id for lp in self.t.control_loops):
                self.note(rule.id, "reused", f"loop.{sl}", f"{req.id}: control loop already present")
                continue
            missing = []
            if not req.controlled_variable:
                missing.append("controlled variable")
            if not req.measured_at_line:
                missing.append("measurement location")
            if not req.final_element or req.final_element not in self.comp:
                missing.append("final element")
            if req.setpoint is None or req.setpoint.value is None:
                missing.append("setpoint")
            if missing:
                self.note(rule.id, "blocked", req.id, f"{req.id}: not instrumented – missing {', '.join(missing)}")
                covered = any(req.id in u.affects for u in self.t.unresolved_requirements if not u.id.startswith("ur.gen."))
                if not covered:
                    self._upsert_unresolved(Unresolved.model_validate({
                        "id": f"ur.gen.{sl}.prereq", "category": "missing_value",
                        "description": f"Control requirement {req.id} cannot be turned into a loop: missing {', '.join(missing)}.",
                        "affects": [req.id], "needed_for": "control loop", "status": "open",
                        "provenance": generated_prov(rule.id, [req.id], "prerequisites of the control-loop rule are not established").model_dump(),
                    }))
                continue
            var = req.controlled_variable
            tx = next((i for i in self.t.instruments if i.function == "transmitter" and i.measured_variable == var
                       and i.target == {"kind": "line", "ref": req.measured_at_line}), None)
            if tx is None:
                tid = f"in.{slug(req.measured_at_line)}.{var[0]}t"
                tx = Instrument.model_validate({
                    "id": tid, "name": f"{var.capitalize()} transmitter for {req.id}", "isa_code": var[0].upper() + "T",
                    "measured_variable": var, "function": "transmitter", "loop_id": None,
                    "target": {"kind": "line", "ref": req.measured_at_line}, "tag": None, "tag_status": "none", "area": None, "attributes": {},
                    "provenance": generated_prov(rule.id, [req.id], self._expl(rule, f"measurement of the loop for {req.id}.")).model_dump(),
                })
                self.t.instruments.append(tx)
                self.note(rule.id, "added", tx.id, f"{req.id}: transmitter created")
            else:
                self.note(rule.id, "reused", tx.id, f"{req.id}: existing {tx.isa_code} reused as loop measurement")
            loop_id = f"loop.{sl}"
            ctrl_code = codes[var]
            ctrl = Instrument.model_validate({
                "id": f"in.{sl}.{ctrl_code.lower()}", "name": f"{var.capitalize()} indicating controller for {req.id}",
                "isa_code": ctrl_code, "measured_variable": var, "function": "controller", "loop_id": loop_id,
                "target": None, "tag": None, "tag_status": "none", "area": None, "attributes": {},
                "provenance": generated_prov(rule.id, [req.id, tx.id],
                                             self._expl(rule, f"{req.id} states an automatic control action with an explicit setpoint "
                                                              f"({req.setpoint.value} {req.setpoint.unit}); a controller is therefore required between measurement and final element.")).model_dump(),
            })
            self.t.instruments.append(ctrl)
            if tx.loop_id is None:
                tx.loop_id = loop_id
                if tx.provenance.origin == "source":
                    self._record_mod(rule, tx.id, "loop_id", None, loop_id, "transmitter assigned to loop")
            sig_prov = lambda t: generated_prov(rule.id, [req.id], t).model_dump()  # noqa: E731
            self.t.signals.append(Signal.model_validate({"id": f"sg.{sl}.measurement", "name": "Measurement signal", "kind": "measurement",
                                                         "from": tx.id, "to": ctrl.id, "loop_id": loop_id, "attributes": {},
                                                         "provenance": sig_prov("measurement → controller")}))
            self.t.signals.append(Signal.model_validate({"id": f"sg.{sl}.control", "name": "Control signal", "kind": "control",
                                                         "from": ctrl.id, "to": req.final_element, "loop_id": loop_id, "attributes": {},
                                                         "provenance": sig_prov("controller → final element")}))
            self.t.control_loops.append(ControlLoop.model_validate({
                "id": loop_id, "name": f"{var.capitalize()} loop for {req.id}", "variable": var, "measurement": tx.id,
                "controller": ctrl.id, "final_element": req.final_element, "setpoint": req.setpoint.model_dump() if req.setpoint else None,
                "requirement": req.id, "attributes": {},
                "provenance": generated_prov(rule.id, [req.id], self._expl(rule, f"loop = measurement → controller → final element for {req.id}.")).model_dump(),
            }))
            self.note(rule.id, "added", loop_id, f"{req.id}: measurement → controller → final element loop created")

    # ================================================================== tagging
    def rule_tagging(self, rule: Rule) -> None:
        tg = self.policy.generic["tagging"]
        sep = tg["separator"]
        series = tg["series"]
        used: dict[str, set[int]] = {}
        for o in [*self.t.equipment, *self.t.components, *self.t.instruments]:
            m = re.match(r"^([A-Z]+)" + re.escape(sep) + r"(\d+)$", o.tag or "")
            if m:
                used.setdefault(m.group(1), set()).add(int(m.group(2)))

        def take(prefix: str, want: int | None = None) -> int:
            nums = used.setdefault(prefix, set())
            n = want if want is not None and want not in nums else series.get(prefix, 1)
            while n in nums:
                n += 1
            nums.add(n)
            return n

        def number_of(tag: str | None) -> int | None:
            m = re.search(r"(\d+)$", tag or "")
            return int(m.group(1)) if m else None

        # transmitters first (so loops can share their number)
        for i in sorted([i for i in self.t.instruments if i.tag is None and i.function == "transmitter"], key=lambda x: x.id):
            n = take(i.isa_code)
            self._set_tag(rule, i, f"{i.isa_code}{sep}{n}", "instrument")
        insts = {i.id: i for i in self.t.instruments}
        for lp in self.t.control_loops:
            tx, ctrl = insts[lp.measurement], insts[lp.controller]
            num = number_of(tx.tag)
            if ctrl.tag is None:
                self._set_tag(rule, ctrl, f"{ctrl.isa_code}{sep}{take(ctrl.isa_code, num)}", "controller")
            fe = self.comp.get(lp.final_element)
            if fe is not None and fe.tag is None and rule.params.get("tag_untagged_source_control_valves", True):
                pref = tg["by_function"].get(fe.function or "", "XV")
                n = take(pref, number_of(ctrl.tag) if pref == "PCV" else None)
                self._set_tag(rule, fe, f"{pref}{sep}{n}", "control valve of a loop (loop number shared with its transmitter/controller)")
        for i in sorted([i for i in self.t.instruments if i.tag is None], key=lambda x: x.id):  # indicators, switches...
            self._set_tag(rule, i, f"{i.isa_code}{sep}{take(i.isa_code)}", "instrument")
        for c in sorted([c for c in self.t.components if c.kind != "manifold" and c.tag is None and c.function], key=lambda x: x.id):
            if c.provenance.origin == "source" and not (c.function == "control" and rule.params.get("tag_untagged_source_control_valves", True)):
                continue
            pref = tg["by_function"].get(c.function or "", "XV")
            self._set_tag(rule, c, f"{pref}{sep}{take(pref)}", "valve")

    def rule_line_numbering(self, rule: Rule) -> None:
        """One proposed line number per logical line: <service code>-<sequence> (no size or class: never invented)."""
        cfg = self.policy.generic.get("line_numbering", {})
        codes: list[dict[str, Any]] = cfg.get("codes", [])
        start = int(cfg.get("start", 101))
        sep = cfg.get("separator", "-")

        auto: dict[str, str] = {}

        def code_of(service: str) -> str | None:
            for c in codes:
                if service.lower().startswith(c["prefix"].lower()):
                    return c.get("code")
            if not cfg.get("auto_codes", True) or service.split(" ")[0].lower() in {"drain", "vent", "relief", "purge"}:
                return None
            if service not in auto:  # initials of the service name (Chilled water -> CW), made unique
                words = [w for w in re.findall(r"[A-Za-zÀ-ÿ]+", service) if len(w) > 2 or w.isupper()]
                base = "".join(w[0] for w in words[:2]).upper() or "PL"
                code, k = base, 1
                taken = {c.get("code") for c in codes} | set(auto.values())
                while code in taken:
                    k += 1
                    code = f"{base}{k}"
                auto[service] = code
            return auto[service]

        groups: dict[str, list[ProcessLine]] = {}
        for ln in self.t.process_lines:
            groups.setdefault(logical(ln), []).append(ln)
        used: dict[str, set[int]] = {}
        for lines in groups.values():
            for ln in lines:
                m = re.match(r"^([A-Z]+)" + re.escape(sep) + r"(\d+)$", ln.line_number or "")
                if m:
                    used.setdefault(m.group(1), set()).add(int(m.group(2)))
        order = sorted(groups.items(), key=lambda kv: (code_of(kv[1][0].service) or "", kv[0]))
        for lg, lines in order:
            code = code_of(lines[0].service)
            if code is None:
                continue
            have = next((ln.line_number for ln in lines if ln.line_number), None)
            if have is None:
                nums = used.setdefault(code, set())
                n = start
                while n in nums:
                    n += 1
                nums.add(n)
                have = f"{code}{sep}{n}"
            for ln in lines:
                if ln.line_number:
                    continue
                if ln.provenance.origin == "source":
                    self._record_mod(rule, ln.id, "line_number", None, have, "proposed line number (service code + sequence); size and piping class are not given and are left out")
                ln.line_number = have
                ln.line_number_status = "proposed"
                self.note(rule.id, "added", ln.id, f"proposed line number {have}")

    def _set_tag(self, rule: Rule, obj: Component | Instrument, tag: str, what: str) -> None:
        if obj.provenance.origin == "source":
            self._record_mod(rule, obj.id, "tag", None, tag, f"proposed ISA 5.1 tag for source {what} that has no tag in the specification")
        obj.tag = tag
        obj.tag_status = "proposed"
        self.note(rule.id, "added", obj.id, f"proposed tag {tag}")

    # ============================================================ unresolved
    def _upsert_unresolved(self, u: Unresolved) -> None:
        for i, ex in enumerate(self.t.unresolved_requirements):
            if ex.id == u.id:
                self.t.unresolved_requirements[i] = u
                return
        self.t.unresolved_requirements.append(u)

    def rule_unresolved_summary(self, rule: Rule) -> None:
        gen = lambda affects, why: generated_prov(rule.id, sorted(affects), why).model_dump()  # noqa: E731
        generic_valves = sorted(c.id for c in self.t.components if c.kind == "valve" and c.technology_status == "unspecified_generic")
        if generic_valves:
            self._upsert_unresolved(Unresolved.model_validate({
                "id": "ur.gen.valve_technology", "category": "selection",
                "description": "Valve technology is not specified for these valves. They use the explicitly identified generic DEXPI representation "
                               "(CustomOperatedValve, 'technology to be selected'); no specific valve type was chosen.",
                "affects": generic_valves, "needed_for": "valve selection", "question": "Select the valve technology for each valve function.",
                "status": "open", "provenance": gen(generic_valves, "generic valve representation used because the technology is not specified"),
            }))
        ctrl_valves = sorted(c.id for c in self.t.components if c.function == "control")
        if ctrl_valves:
            self._upsert_unresolved(Unresolved.model_validate({
                "id": "ur.gen.fail_position", "category": "missing_value",
                "description": "Failure position (fail open / close / retain) of the control valves is not specified and was not assumed.",
                "affects": ctrl_valves, "needed_for": "safety philosophy", "status": "open",
                "provenance": gen(ctrl_valves, "valve failure positions are never invented"),
            }))
        instr = sorted(i.id for i in self.t.instruments if i.provenance.origin == "generated")
        if instr:
            self._upsert_unresolved(Unresolved.model_validate({
                "id": "ur.gen.instrument_ranges", "category": "missing_value",
                "description": "Measuring ranges and alarm/trip settings of the generated instruments are not specified and were not assumed.",
                "affects": instr, "needed_for": "instrument datasheets", "status": "open",
                "provenance": gen(instr, "instrument ranges are never invented"),
            }))
        reliefs = sorted(c.id for c in self.t.components if c.kind == "relief")
        if reliefs:
            self._upsert_unresolved(Unresolved.model_validate({
                "id": "ur.gen.relief", "category": "missing_value",
                "description": "Relief devices: set pressure, relieving case and capacity, type and discharge destination are not specified "
                               "and were not assumed. The devices are drawn as placeholders until the relief study is done.",
                "affects": reliefs, "needed_for": "relief study / PSV datasheets", "status": "open",
                "provenance": gen(reliefs, "relief sizing and set pressures are never invented"),
            }))
        gen_nz = sorted(e.id for e in self.t.equipment if any(n.provenance and n.provenance.origin == "generated" for n in e.nozzles))
        if gen_nz:
            self._upsert_unresolved(Unresolved.model_validate({
                "id": "ur.gen.nozzles", "category": "missing_value",
                "description": "Nozzles added for drain, vent and level tapping have no nozzle number and no size.",
                "affects": gen_nz, "needed_for": "nozzle schedule", "status": "open",
                "provenance": gen(gen_nz, "nozzle numbers and sizes are never invented"),
            }))
        self.note(rule.id, "note", "ur.gen", "generated unresolved-requirement summaries refreshed")


def _src_cite(line: ProcessLine) -> str:
    p = line.provenance
    if p.origin == "source":
        return f"PDF p.{p.page} §{p.section}"
    return f"generated by {p.rule}"


def enrich(topo: Topology, policy: Policy) -> EnrichResult:
    """Apply the project rules to ``topo`` in place and return the log."""
    return Enricher(topo, policy).run()
