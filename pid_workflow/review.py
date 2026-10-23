"""Engineering review of proposed additions: approve or reject, never silently.

Approving flips ``provenance.status`` to ``approved`` (the object stays in the graph and is
drawn in normal ink).  Rejecting removes inline valves, drain/vent valves and instruments,
restores the original source line when no inserted component is left, and records the
rejection so that re-running enrichment does not propose the same object again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import Modification, Nozzle, ProcessLine, Topology, generated_prov


@dataclass
class ReviewResult:
    approved: list[str]
    rejected: list[str]
    skipped: list[tuple[str, str]]
    modifications: int = 0  # approved changes to source objects (line numbers, tags, nozzles, splits)


def _generated(topo: Topology) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for oid, o in topo.objects().items():
        if o.provenance.origin == "generated":
            out[oid] = o
    for e in topo.equipment:
        for n in e.nozzles:
            if n.provenance is not None and n.provenance.origin == "generated":
                out[f"{e.id}:{n.name}"] = n
    return out


def pending_ids(topo: Topology, rule: str | None = None) -> list[str]:
    out = []
    for oid, o in _generated(topo).items():
        p = o.provenance
        if p.status == "pending_review" and (rule is None or p.rule == rule):
            out.append(oid)
    return sorted(out)


def approve(topo: Topology, ids: list[str] | None = None, rule: str | None = None) -> ReviewResult:
    gen = _generated(topo)
    targets = ids if ids is not None else pending_ids(topo, rule)
    done, skipped = [], []
    for oid in targets:
        o = gen.get(oid)
        if o is None:
            skipped.append((oid, "not a generated object"))
            continue
        if o.provenance.status == "approved":
            continue
        o.provenance.status = "approved"
        for m in topo.modifications:
            if m.object_id == oid and m.provenance.status == "pending_review":
                m.provenance.status = "approved"
        if getattr(o, "tag_status", None) == "proposed":
            pass  # the tag stays 'proposed' until a real tag is issued; approval is of the object
        done.append(oid)
    for m in topo.modifications:  # keep modification records in step with approved objects
        if m.provenance.origin == "generated" and m.object_id in {d for d in done}:
            m.provenance.status = "approved"
    n_mod = 0
    if ids is None:  # a rule's changes to source objects (tags, line numbers, nozzles, splits) go with it
        for m in topo.modifications:
            if (rule is None or m.provenance.rule == rule) and m.provenance.status == "pending_review":
                m.provenance.status = "approved"
                n_mod += 1
    return ReviewResult(done, [], skipped, n_mod)


def reject(topo: Topology, ids: list[str]) -> ReviewResult:
    rejected, skipped = [], []
    for oid in ids:
        comp = next((c for c in topo.components if c.id == oid), None)
        inst = next((i for i in topo.instruments if i.id == oid), None)
        if comp is not None and comp.provenance.origin == "generated" and comp.kind in ("valve", "check_valve"):
            why = _reject_valve(topo, comp.id)
            if why:
                skipped.append((oid, why))
                continue
        elif inst is not None and inst.provenance.origin == "generated":
            topo.instruments = [i for i in topo.instruments if i.id != oid]
            topo.signals = [s for s in topo.signals if oid not in (s.from_, s.to)]
            dead = [l.id for l in topo.control_loops if oid in (l.measurement, l.controller)]
            topo.control_loops = [l for l in topo.control_loops if l.id not in dead]
        else:
            skipped.append((oid, "only generated valves and instruments can be rejected here; "
                                 "disable the rule in project_rules.yaml to remove a whole manifold"))
            continue
        topo.modifications.append(Modification(
            id=f"mod.{oid}.rejected", object_id=oid, field="rejected", old="pending_review", new="rejected",
            provenance=generated_prov("review.reject", [oid], "rejected by the engineering review; enrichment will not propose it again", status="approved")))
        rejected.append(oid)
    return ReviewResult([], rejected, skipped)


def _reject_valve(topo: Topology, vid: str) -> str | None:
    l_in = next((l for l in topo.process_lines if l.to.ref == vid and l.to.port == "in"), None)
    l_out = next((l for l in topo.process_lines if l.from_.ref == vid and l.from_.port == "out"), None)
    comp = next(c for c in topo.components if c.id == vid)
    if l_in is None:
        return "valve is not connected"
    if l_out is None:  # open-ended drain / vent valve: remove it with its stub line and generated nozzle
        topo.components = [c for c in topo.components if c.id != vid]
        topo.process_lines = [l for l in topo.process_lines if l.id != l_in.id]
        eq = next((e for e in topo.equipment if e.id == l_in.from_.ref), None)
        if eq is not None:
            nz = next((n for n in eq.nozzles if n.name == l_in.from_.port), None)
            if nz is not None and nz.provenance is not None and nz.provenance.origin == "generated":
                eq.nozzles = [n for n in eq.nozzles if n.name != nz.name]
        else:
            return "open-ended valve hangs on a manifold: reject the manifold via its rule"
        return None
    # inline valve: merge the two lines again
    base = l_in.split_from
    if base is None or base != l_out.split_from:
        return "the lines around this valve do not come from one split; cannot merge safely"
    mod = next((m for m in topo.modifications if m.field == "split" and m.object_id == base and (m.new or {}).get("inserted") == vid), None)
    merged = l_in.model_copy(deep=True)
    merged.to = l_out.to
    merged.id = f"{base}"
    topo.components = [c for c in topo.components if c.id != vid]
    i = topo.process_lines.index(l_in)
    topo.process_lines = [l for l in topo.process_lines if l.id not in (l_in.id, l_out.id)]
    topo.process_lines.insert(i, merged)
    # restore the source line object when nothing else was inserted into it
    orig = (mod.old or {}).get("line") if mod is not None else None
    if orig is not None and orig["from"] == merged.from_.model_dump() and orig["to"] == merged.to.model_dump():
        restored = ProcessLine.model_validate(orig)
        topo.process_lines[topo.process_lines.index(merged)] = restored
        topo.modifications = [m for m in topo.modifications if not (m.field == "split" and m.object_id == base)]
    elif mod is not None:
        topo.modifications = [m for m in topo.modifications if m is not mod]
    return None
