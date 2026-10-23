"""Extraction kit: the small API an agent uses to record what a specification says.

Example (``projects/<name>/extraction/extract_<name>.py``)::

    from pid_workflow.extract_kit import Spec

    s = Spec(__file__, drawing_id="PID-CHW-001", title="Chilled-water plant – draft P&ID", project="…")
    q = s.src(2, "3.1 Production", "deux groupes froids de 1 200 kW")      # quote checked against the PDF now
    s.area("ar.prod", "Chilled-water production", q)
    s.equipment("eq.ch1", "Chiller 1", "CustomEquipment", "ar.prod", q, tag="GF-01", symbol="heat_pump",
                nozzles={"evap_in": "inlet", "evap_out": "outlet"}, attrs={"cooling_capacity": s.val(1200, "kW", q)})
    s.bank("chw_pumps", ["eq.p1", "eq.p2"], inlet="eq.tank:out", outlet="eq.ch1:evap_in", service="Chilled water", src=q)
    s.unresolved("ur.dn", "missing_value", "Pipe sizes are not given.", ["eq.p1"], q, question="Line sizes?")
    s.save()

Rules the kit enforces so the result can be trusted:

* every quote must be verbatim in the document, on the stated page (fragments of a table row may be joined by " … ");
* ``src`` is ``explicit``; ``interp`` (an interpretation, with a note saying what was inferred) and ``structural``
  (needed to draw a connected graph) must be used for anything the text does not state;
* the file is validated (schema + structure) before it is written; problems are printed with the fix to apply.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from .schema import Topology
from .sourcedoc import SourceDocument
from .topology_io import save_topology
from .validate import validate


class QuoteError(ValueError):
    pass


class Spec:
    def __init__(self, script: str | Path, *, drawing_id: str, title: str, project: str, revision: str = "A (draft for review)",
                 language: str = "en", document: str | None = None, strict: bool = True) -> None:
        here = Path(script).resolve()
        self.root = here.parent.parent if here.parent.name == "extraction" else here.parent
        cfg = yaml.safe_load((self.root / "project.yaml").read_text(encoding="utf-8")) if (self.root / "project.yaml").exists() else {}
        doc_rel = document or cfg.get("source_document")
        if not doc_rel:
            raise ValueError("no source document: set source_document in project.yaml or pass document=")
        self.doc_path = (self.root / doc_rel).resolve()
        self.doc = SourceDocument.load(self.doc_path)
        self.doc_name = self.doc_path.name
        self.strict = strict
        self.problems: list[str] = []
        self.t: dict[str, Any] = {
            "schema_version": "1.0",
            "metadata": {"drawing_id": drawing_id, "title": title, "project": project, "revision": revision, "language": "en",
                         "source_documents": [{"id": "spec", "file": self.doc_name, "pages": len(self.doc.pages), "language": language}],
                         "engineering_basis": []},
            "areas": [], "equipment": [], "components": [], "boundaries": [], "instruments": [], "process_lines": [], "signals": [],
            "control_requirements": [], "control_loops": [], "operating_modes": [], "unresolved_requirements": [], "modifications": [],
        }
        self._n_line = 0

    # ------------------------------------------------------------------ provenance
    def _prov(self, page: int, section: str, quote: str | dict[str, Any] | None, basis: str, note: str | None) -> dict[str, Any]:
        if isinstance(quote, dict):  # an existing src(...) may be passed: reuse its quote
            quote = quote.get("quote")
        if quote:
            found = self.doc.pages_with(quote)
            if page not in found:
                where = f"it is on page(s) {found}" if found else "it is not in the document verbatim (copy it exactly; join table cells with ' … ')"
                msg = f"quote on page {page} §{section}: {where}: “{quote[:100]}”"
                if self.strict:
                    raise QuoteError(msg)
                self.problems.append(msg)
        if basis != "explicit" and not note:
            raise ValueError(f"{basis} provenance needs a note saying what was inferred and why (page {page} §{section})")
        return {"origin": "source", "document": self.doc_name, "page": page, "section": section, "quote": quote, "basis": basis, "note": note}

    def src(self, page: int, section: str, quote: str | None = None, note: str | None = None) -> dict[str, Any]:
        """What the text states (quote verbatim)."""
        return self._prov(page, section, quote, "explicit", note)

    def interp(self, page: int, section: str, note: str, quote: str | None = None) -> dict[str, Any]:
        """An interpretation of the text; the note says what was inferred and why."""
        return self._prov(page, section, quote, "interpreted", note)

    def structural(self, page: int, section: str, note: str, quote: str | None = None) -> dict[str, Any]:
        """Needed to draw a connected graph (a header tee, a battery limit); the note says why."""
        return self._prov(page, section, quote, "structural", note)

    @staticmethod
    def val(value: Any, unit: str | None, src: dict[str, Any]) -> dict[str, Any]:
        return {"value": value, "unit": unit, "provenance": src}

    # ------------------------------------------------------------------ objects
    def basis(self, statement: str, src: dict[str, Any]) -> None:
        self.t["metadata"]["engineering_basis"].append({"statement": statement, "provenance": src})

    def area(self, id_: str, name: str, src: dict[str, Any], description: str | None = None) -> str:
        self.t["areas"].append({"id": id_, "name": name, "description": description, "provenance": src})
        return id_

    def equipment(self, id_: str, name: str, model_class: str, area: str, src: dict[str, Any], *, tag: str | None = None,
                  lifecycle: str = "new", nozzles: dict[str, str] | list[tuple[str, str]] = (), attrs: dict[str, Any] | None = None,
                  symbol: str | None = None) -> str:
        """nozzles: {name: role} with role inlet|outlet|suction|discharge (drain/vent/level/relief nozzles are added by rules)."""
        items = list(nozzles.items()) if isinstance(nozzles, dict) else list(nozzles)
        self.t["equipment"].append({
            "id": id_, "name": name, "tag": tag, "tag_status": "source" if tag else "none", "model_class": model_class, "area": area,
            "lifecycle": lifecycle, **({"symbol": symbol} if symbol else {}),
            "nozzles": [{"name": n, "role": r, "number": None, "size": None, "service": None} for n, r in items],
            "attributes": attrs or {}, "provenance": src})
        return id_

    def valve(self, id_: str, name: str, function: str, area: str, src: dict[str, Any], *, model_class: str | None = None,
              operation: str = "unknown", tag: str | None = None, kind: str = "valve") -> str:
        """A valve / check valve / strainer / relief device the document itself names. Technology unknown -> generic, never guessed."""
        generic = model_class is None and kind == "valve"
        cls = model_class or {"valve": "CustomOperatedValve", "check_valve": "CheckValve", "strainer": "Strainer",
                              "relief": "CustomSafetyValveOrFitting"}[kind]
        self.t["components"].append({
            "id": id_, "name": name, "kind": kind, "model_class": cls, "function": function, "technology": None if generic else cls,
            "technology_status": "unspecified_generic" if generic else "specified", "operation": operation, "tag": tag,
            "tag_status": "source" if tag else "none", "area": area, "attributes": {}, "provenance": src})
        return id_

    def manifold(self, id_: str, name: str, role: str, branches: int, area: str, src: dict[str, Any]) -> str:
        """role split (common in, b1..bn out) or merge (b1..bn in, common out)."""
        self.t["components"].append({"id": id_, "name": name, "kind": "manifold", "model_class": "PipeTee", "role": role,
                                     "branches": branches, "area": area, "provenance": src})
        return id_

    def boundary(self, id_: str, name: str, direction: str, service: str, area: str, src: dict[str, Any]) -> str:
        """Battery limit: direction 'in' (stream enters the plant) or 'out'. Its port is 'port'."""
        self.t["boundaries"].append({"id": id_, "name": name, "direction": direction, "service": service, "area": area,
                                     "attributes": {}, "provenance": src})
        return id_

    @staticmethod
    def _ref(s: str) -> dict[str, str]:
        obj, port = s.rsplit(":", 1)
        return {"ref": obj, "port": port}

    def line(self, frm: str, to: str, service: str, src: dict[str, Any], *, name: str | None = None, props: dict[str, Any] | None = None,
             header: bool = False, id_: str | None = None) -> str:
        """A pipe from 'object:port' to 'object:port' in flow direction. props: {'nominal_diameter': s.val(200, None, q), ...}."""
        if id_ is None:
            self._n_line += 1
            id_ = f"ln.{self._n_line:03d}"
        self.t["process_lines"].append({"id": id_, "name": name, "service": service, "from": self._ref(frm), "to": self._ref(to),
                                        "logical_line": id_, "split_from": None, "line_number": None, "header": header,
                                        "properties": props or {}, "provenance": src})
        return id_

    def run(self, service: str, src: dict[str, Any], *points: str, props: dict[str, Any] | None = None, header: bool = False) -> list[str]:
        """Pipe through a sequence: 'eq.a:out', 'pc.v1', 'pc.v2', 'eq.b:in' (inline components without a port use in/out)."""
        ids = []
        for a, b in zip(points, points[1:]):
            fa = a if ":" in a else f"{a}:out"
            tb = b if ":" in b else f"{b}:in"
            ids.append(self.line(fa, tb, service, src, props=props, header=header))
        return ids

    def bank(self, name: str, units: list[str], *, inlet: str, outlet: str, service: str, src: dict[str, Any], area: str | None = None,
             unit_in: str = "suction", unit_out: str = "discharge", props: dict[str, Any] | None = None) -> tuple[str, str]:
        """Parallel identical units (e.g. '3 pumps 2+1'): split manifold -> each unit -> merge manifold.

        inlet/outlet are 'object:port' upstream and downstream of the bank. Returns (split id, merge id).
        """
        area = area or next(e["area"] for e in self.t["equipment"] if e["id"] == units[0])
        note = "header tees for parallel units (structure needed to draw the parallel arrangement)"
        st = {**src, "basis": "structural", "note": note}
        sp = self.manifold(f"mf.{name}_s", f"{name} suction header", "split", len(units), area, st)
        mg = self.manifold(f"mf.{name}_m", f"{name} discharge header", "merge", len(units), area, st)
        self.line(inlet, f"{sp}:common", service, src, props=props, header=True)
        for i, u in enumerate(units, 1):
            self.line(f"{sp}:b{i}", f"{u}:{unit_in}", service, src, props=props)
            self.line(f"{u}:{unit_out}", f"{mg}:b{i}", service, src, props=props)
        self.line(f"{mg}:common", outlet, service, src, props=props, header=True)
        return sp, mg

    def control(self, id_: str, description: str, src: dict[str, Any], *, variable: str | None = None, measured_at_line: str | None = None,
                final_element: str | None = None, setpoint: dict[str, Any] | None = None, controller_required: bool = False,
                action: str | None = None) -> str:
        """A stated control requirement. controller_required=True ONLY when the text states automatic control."""
        self.t["control_requirements"].append({"id": id_, "name": None, "description": description, "controlled_variable": variable,
                                               "measured_at_line": measured_at_line, "final_element": final_element, "setpoint": setpoint,
                                               "controller_required": controller_required, "action": action, "attributes": {}, "provenance": src})
        return id_

    def mode(self, id_: str, name: str, description: str, src: dict[str, Any], requirements: list[tuple[str, list[str], str]] = ()) -> str:
        """requirements: [(action isolate|discharge|operate|note, ['object:port', ...], text)]."""
        self.t["operating_modes"].append({"id": id_, "name": name, "description": description, "attributes": {}, "provenance": src,
                                          "requirements": [{"action": a, "targets": [self._ref(x) for x in tg], "text": tx} for a, tg, tx in requirements]})
        return id_

    def unresolved(self, id_: str, category: str, description: str, affects: list[str], src: dict[str, Any], *,
                   question: str | None = None, needed_for: str | None = None) -> str:
        """category: missing_value | ambiguity | conflict | selection | scope."""
        self.t["unresolved_requirements"].append({"id": id_, "name": None, "category": category, "description": description,
                                                  "affects": affects, "needed_for": needed_for, "question": question, "status": "open",
                                                  "provenance": src})
        return id_

    # ------------------------------------------------------------------ output
    def save(self) -> Path:
        topo = Topology.model_validate(self.t)
        rep = validate(topo)
        out = self.root / "source_topology.json"
        for i in rep.issues:
            if i.level in ("error", "warning"):
                print(f"{i.level.upper():7} {i.code}: {i.message}", file=sys.stderr)
        for p in self.problems:
            print(f"QUOTE   {p}", file=sys.stderr)
        if not rep.ok:
            raise SystemExit(f"{len(rep.errors)} validation error(s): fix the extraction (nothing written)")
        sha = save_topology(topo, out)
        print(f"wrote {out}  sha256={sha[:12]}…  equipment={len(topo.equipment)} components={len(topo.components)} "
              f"lines={len(topo.process_lines)} open points={len(topo.unresolved_requirements)} warnings={len(rep.warnings)}")
        return out
