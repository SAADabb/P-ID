"""Process flow diagram (PFD) derived from the same extraction as the P&ID.

A PFD shows the process, not the piping detail (ISO 10628-1 / common EPC practice):

* major equipment only - no drains, vents, isolation/check valves, strainers or local instruments; the
  *source* topology is used, so nothing added by P&ID rules appears;
* identical parallel units (duty/stand-by pumps, banks) drawn once: ``P-201/202/203 (3 units)``;
* control valves the specification names are kept (they define the process control);
* every connection between two process nodes is a numbered **stream**; the stream table gives what the
  specification states for it (service, temperature, pressure, flow) and, marked as such, values carried
  over from the equipment that drives it (pump flow) - nothing is calculated or invented;
* an equipment summary lists the stated duty data.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from .schema import Attr, Component, Equipment, ProcessLine, Ref, Topology, logical


@dataclass
class Stream:
    no: int
    line_ids: list[str]                 # PFD lines carrying this stream (control valves split a stream into pieces)
    service: str
    frm: str                            # display name of the source node
    to: str
    values: dict[str, str] = field(default_factory=dict)   # row -> value text
    derived: set[str] = field(default_factory=set)         # rows carried over from equipment data


@dataclass
class Bank:
    rep: str                            # representative equipment id (kept)
    members: list[str]
    split: str | None
    merge: str | None


@dataclass
class PFD:
    topo: Topology
    streams: list[Stream]
    banks: list[Bank]
    equipment_summary: list[tuple[str, str, str]]   # tag, description, key data
    dropped: dict[str, int]


STREAM_ROWS = ["Service", "From", "To", "Temperature", "Pressure", "Flow"]


def build_pfd(source: Topology) -> PFD:
    t = copy.deepcopy(source)
    dropped: dict[str, int] = defaultdict(int)
    # ---- instruments, signals and loops are P&ID detail
    dropped["instruments"] = len(t.instruments)
    t.instruments, t.signals, t.control_loops = [], [], []
    # ---- keep control valves, splice every other inline component out of its line
    for c in [c for c in t.components if c.kind != "manifold" and c.function != "control"]:
        _splice(t, c.id)
        dropped[c.kind] += 1
    # ---- parallel banks -> one node
    banks = _collapse_banks(t)
    # ---- open-ended lines (to a removed drain/vent) disappear
    ids = set(t.objects()) | {e.id for e in t.equipment}
    t.process_lines = [ln for ln in t.process_lines if ln.from_.ref in ids and ln.to.ref in ids]
    streams = _number_streams(t)
    summary = _equipment_summary(t, banks)
    did = t.metadata.drawing_id
    t.metadata = t.metadata.model_copy(update={
        "title": t.metadata.title.replace("P&ID", "PFD") if "P&ID" in t.metadata.title else f"{t.metadata.title} – PFD",
        "drawing_id": did.replace("PID", "PFD", 1) if "PID" in did else f"{did}-PFD"})
    return PFD(t, streams, banks, summary, dict(dropped))


# ------------------------------------------------------------------------------------- splicing
def _splice(t: Topology, comp_id: str) -> None:
    """Remove an inline 2-port component: line_in + line_out become one line (properties merged)."""
    lin = next((ln for ln in t.process_lines if ln.to.ref == comp_id), None)
    lout = next((ln for ln in t.process_lines if ln.from_.ref == comp_id), None)
    t.components = [c for c in t.components if c.id != comp_id]
    if lin is not None and lout is not None:
        merged = lin.model_copy(update={"to": lout.to, "properties": {**lout.properties, **lin.properties}})
        t.process_lines = [merged if ln.id == lin.id else ln for ln in t.process_lines if ln.id != lout.id]
    else:  # open end (drain / vent): the stub disappears with the component
        t.process_lines = [ln for ln in t.process_lines if ln.id not in {getattr(lin, "id", None), getattr(lout, "id", None)}]
    for u in t.unresolved_requirements:
        u.affects = [a for a in u.affects if a != comp_id]
    for m in t.operating_modes:
        for r in m.requirements:
            r.targets = [x for x in r.targets if x.ref != comp_id]


def _collapse_banks(t: Topology) -> list[Bank]:
    """split manifold -> n identical units -> merge manifold  ==>  one unit between the outer lines."""
    eqs = {e.id: e for e in t.equipment}
    banks: list[Bank] = []
    for sp in [c for c in t.components if c.kind == "manifold" and c.role == "split"]:
        outs = [ln for ln in t.process_lines if ln.from_.ref == sp.id and ln.from_.port != "common"]
        units = [eqs.get(ln.to.ref) for ln in outs]
        if len(units) < 2 or any(u is None for u in units):
            continue
        if len({(u.model_class, len(u.nozzles)) for u in units}) != 1:
            continue
        # every unit's other connections must all go to one merge manifold
        unit_ids = {u.id for u in units}
        downstream = [ln for ln in t.process_lines if ln.from_.ref in unit_ids]
        targets = {ln.to.ref for ln in downstream}
        if len(targets) != 1 or len(downstream) != len(units):
            continue
        mg = next((c for c in t.components if c.id in targets and c.kind == "manifold" and c.role == "merge"), None)
        if mg is None or (mg.branches or 0) != len(units):
            continue
        rep = units[0]
        lin = next((ln for ln in t.process_lines if ln.to.ref == sp.id and ln.to.port == "common"), None)
        lout = next((ln for ln in t.process_lines if ln.from_.ref == mg.id and ln.from_.port == "common"), None)
        if lin is None or lout is None:
            continue
        in_port = next(ln.to.port for ln in outs if ln.to.ref == rep.id)
        out_port = next(ln.from_.port for ln in downstream if ln.from_.ref == rep.id)
        new_in = lin.model_copy(update={"to": Ref(ref=rep.id, port=in_port)})
        new_out = lout.model_copy(update={"from_": Ref(ref=rep.id, port=out_port)})
        drop_lines = {ln.id for ln in outs} | {ln.id for ln in downstream} | {lin.id, lout.id}
        t.process_lines = [ln for ln in t.process_lines if ln.id not in drop_lines] + [new_in, new_out]
        t.components = [c for c in t.components if c.id not in (sp.id, mg.id)]
        others = [u for u in units if u is not rep]
        t.equipment = [e for e in t.equipment if e.id not in {u.id for u in others}]
        tags = [u.tag for u in units if u.tag]
        rep.tag = _join_tags(tags) if tags else None
        rep.name = f"{_common_name([u.name or '' for u in units])} ({len(units)} units)"
        cfg = next((a.value for u in units for k, a in u.attributes.items() if k in ("configuration", "arrangement")), None)
        if cfg:
            rep.name += f" – {cfg}"
        removed = {u.id for u in others}
        for u_ in t.unresolved_requirements:
            u_.affects = [rep.id if a in removed else a for a in u_.affects]
        banks.append(Bank(rep.id, [u.id for u in units], sp.id, mg.id))
    return banks


def _join_tags(tags: list[str]) -> str:
    """P-201, P-202, P-203 -> P-201/202/203."""
    m = [re.match(r"^(.*?)(\d+)([A-Z]?)$", x) for x in tags]
    if all(m) and len({x.group(1) for x in m}) == 1:
        return m[0].group(1) + "/".join(x.group(2) + x.group(3) for x in m)
    return "/".join(tags)


def _common_name(names: list[str]) -> str:
    base = [re.sub(r"\s*[\(\[]?\d+/\d+[\)\]]?|\s*\((stand-by|standby|secours)\)|\s+\d+$", "", n).strip() for n in names]
    return base[0] if len(set(base)) == 1 else names[0]


# ------------------------------------------------------------------------------------- streams
def _node_name(t: Topology, ref: str, direction: str = "up") -> str:
    """Display name of a stream end; a header junction is named by the equipment it connects (upstream or downstream)."""
    names = _resolve(t, ref, direction, 0)
    if len(names) > 3:
        return f"{len(names)} {'sources' if direction == 'up' else 'users'}"
    return " + ".join(names) if names else ref


def _resolve(t: Topology, ref: str, direction: str, depth: int) -> list[str]:
    objs = t.objects()
    o = objs.get(ref) or next((e for e in t.equipment if e.id == ref), None)
    if o is None:
        return [ref]
    if isinstance(o, Component) and o.kind == "manifold" and depth < 6:
        nxt = [ln.from_.ref for ln in t.process_lines if ln.to.ref == ref] if direction == "up" else \
              [ln.to.ref for ln in t.process_lines if ln.from_.ref == ref]
        out: list[str] = []
        for n in nxt:
            for x in _resolve(t, n, direction, depth + 1):
                if x not in out:
                    out.append(x)
        return out
    return [getattr(o, "tag", None) or (o.name or ref)]


def _number_streams(t: Topology) -> list[Stream]:
    """One stream per chain of lines between process nodes (control valves do not end a stream); numbered in flow order."""
    by_from: dict[str, list[ProcessLine]] = defaultdict(list)
    for ln in t.process_lines:
        by_from[ln.from_.ref].append(ln)
    ctrl = {c.id for c in t.components if c.kind != "manifold"}
    incoming = {ln.to.ref for ln in t.process_lines}
    starts = sorted({b.id for b in t.boundaries if b.direction == "in"}) + sorted(
        {ln.from_.ref for ln in t.process_lines if ln.from_.ref not in incoming})
    seen_nodes: set[str] = set()
    order: list[ProcessLine] = []
    q: deque[str] = deque(starts)
    pending = sorted({ln.from_.ref for ln in t.process_lines})
    while q or pending:
        if not q:
            nxt = next((n for n in pending if n not in seen_nodes), None)
            if nxt is None:
                break
            q.append(nxt)
        n = q.popleft()
        if n in seen_nodes:
            continue
        seen_nodes.add(n)
        for ln in sorted(by_from.get(n, []), key=lambda x: (x.from_.port, x.id)):
            if ln not in order:
                order.append(ln)
            q.append(ln.to.ref)
    streams: list[Stream] = []
    done: set[str] = set()
    for ln in order:
        if ln.id in done or ln.from_.ref in ctrl:
            continue
        chain = [ln]
        while chain[-1].to.ref in ctrl:
            nxt = next((x for x in by_from.get(chain[-1].to.ref, [])), None)
            if nxt is None:
                break
            chain.append(nxt)
        done |= {x.id for x in chain}
        props: dict[str, Attr] = {}
        for x in chain:
            props.update(x.properties)
        s = Stream(len(streams) + 1, [x.id for x in chain], ln.service, _node_name(t, ln.from_.ref, "up"), _node_name(t, chain[-1].to.ref, "down"))
        s.values = {"Service": ln.service, "From": s.frm, "To": s.to}
        s.values.update(_stream_values(props))
        _carry_equipment_flow(t, ln, s)
        streams.append(s)
    # any line not reached (closed loops without a start) gets a number too
    for ln in t.process_lines:
        if ln.id not in done and ln.from_.ref not in ctrl:
            s = Stream(len(streams) + 1, [ln.id], ln.service, _node_name(t, ln.from_.ref, "up"), _node_name(t, ln.to.ref, "down"))
            s.values = {"Service": ln.service, "From": s.frm, "To": s.to, **_stream_values(ln.properties)}
            streams.append(s)
            done.add(ln.id)
    return streams


def _fmt(a: Attr) -> str:
    v = a.value
    if isinstance(v, dict):
        v = "–".join(str(x) for x in v.values())
    return f"{v} {a.unit}".strip() if a.unit else str(v)


def _stream_values(props: dict[str, Attr]) -> dict[str, str]:
    out: dict[str, str] = {}
    temps = [k for k in props if k.startswith("temperature")]
    if temps:
        out["Temperature"] = " / ".join(_fmt(props[k]) for k in sorted(temps))
    pres = [k for k in props if k.startswith("pressure")]
    if pres:
        out["Pressure"] = " / ".join(_fmt(props[k]) for k in sorted(pres))
    flows = [k for k in props if "flow" in k]
    if flows:
        out["Flow"] = " / ".join(_fmt(props[k]) for k in sorted(flows))
    return out


def _carry_equipment_flow(t: Topology, ln: ProcessLine, s: Stream) -> None:
    """A pump's stated design flow is the flow of its discharge stream (per unit; marked as carried over)."""
    if "Flow" in s.values:
        return
    e = next((x for x in t.equipment if x.id == ln.from_.ref), None)
    if e is None:
        return
    a = e.attributes.get("design_volume_flow_rate")
    if a is not None:
        s.values["Flow"] = f"{_fmt(a)} per unit" if "units)" in (e.name or "") else _fmt(a)
        s.derived.add("Flow")


def _equipment_summary(t: Topology, banks: list[Bank]) -> list[tuple[str, str, str]]:
    keys = ("cooling_capacity", "cold_power", "hot_power", "design_heat_flow_rate", "heat_rejection", "recoverable_heat", "cooling_duty",
            "design_volume_flow_rate", "tank_volume", "delivery_pressure", "operating_temperature", "regime", "cold_regime", "hot_regime",
            "chilled_water_regime", "capacity_fraction", "configuration")
    rows = []
    for e in sorted(t.equipment, key=lambda x: (x.tag or "~", x.id)):
        data = [f"{k.replace('_', ' ')} {_fmt(e.attributes[k])}" for k in keys if k in e.attributes][:3]
        rows.append((e.tag or "–", e.name or e.id, "; ".join(data)))
    return rows


def stream_labels(pfd: PFD) -> dict[str, str]:
    """Topology line id -> stream number text (for the drawing)."""
    return {lid: str(s.no) for s in pfd.streams for lid in s.line_ids}
