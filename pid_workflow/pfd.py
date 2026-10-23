"""Process flow diagram (PFD) derived from the same extraction as the P&ID.

A PFD shows the process, not the piping detail (ISO 10628-1 / common EPC practice):

* major equipment only - no drains, vents, isolation/check valves, strainers or local instruments; the
  *source* topology is used, so nothing added by P&ID rules appears;
* identical parallel units drawn once (``P-201/202/203 (3 units)``, ``ECH-030/031/032 (3 units)``), on every side
  of the units that is connected through common headers;
* control valves the specification names are nodes: the streams on either side are separate (pressure changes);
  a control requirement with a stated measurement is drawn as its controller (e.g. PIC) with the stated setpoint;
* every connection between two process nodes is a numbered **stream**; the stream table gives what the
  specification states - limits stay limits (``≤ 30 °C``), a stated flow appears on the first stream that carries
  it only, and values stated for an equipment's own inlet/outlet go on that equipment's streams (marked ``*``);
  nothing is calculated or invented.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from .schema import Attr, Component, Instrument, ProcessLine, Ref, Signal, Topology, logical


@dataclass
class Stream:
    no: int
    line_ids: list[str]
    service: str
    frm: str                            # display name of the source node
    to: str
    values: dict[str, str] = field(default_factory=dict)   # row -> value text
    derived: set[str] = field(default_factory=set)         # rows taken from equipment data (marked *)
    flow_src: tuple | None = None       # identity of the stated flow (to print it once)


@dataclass
class Bank:
    rep: str                            # representative equipment id (kept)
    members: list[str]
    headers: list[str]                  # manifolds removed with the bank


@dataclass
class PFD:
    topo: Topology
    streams: list[Stream]
    banks: list[Bank]
    equipment_summary: list[tuple[str, str, str]]   # tag, description, key data
    dropped: dict[str, int]
    control_notes: list[str] = field(default_factory=list)


STREAM_ROWS = ["Service", "From", "To", "Temperature", "Pressure", "Flow", "Size (stated)"]
_CTRL_CODE = {"pressure": "PIC", "temperature": "TIC", "level": "LIC", "flow": "FIC", "differential pressure": "PDIC"}


def build_pfd(source: Topology) -> PFD:
    t = copy.deepcopy(source)
    dropped: dict[str, int] = defaultdict(int)
    dropped["instruments"] = len(t.instruments)
    t.instruments, t.signals, t.control_loops = [], [], []
    for c in [c for c in t.components if c.kind != "manifold" and c.function != "control"]:
        _splice(t, c.id)
        dropped[c.kind] += 1
    banks = _collapse_banks(t)
    ids = set(t.objects()) | {e.id for e in t.equipment}
    t.process_lines = [ln for ln in t.process_lines if ln.from_.ref in ids and ln.to.ref in ids]
    for u in t.unresolved_requirements:  # one marker per item
        u.affects = list(dict.fromkeys(u.affects))
    control_notes = _control_functions(t)
    streams = _number_streams(t)
    _equipment_stream_data(t, streams)
    _flows_once(streams)
    summary = _equipment_summary(t)
    did = t.metadata.drawing_id
    t.metadata = t.metadata.model_copy(update={
        "title": t.metadata.title.replace("P&ID", "PFD") if "P&ID" in t.metadata.title else f"{t.metadata.title} – PFD",
        "drawing_id": did.replace("PID", "PFD", 1) if "PID" in did else f"{did}-PFD"})
    return PFD(t, streams, banks, summary, dict(dropped), control_notes)


# ------------------------------------------------------------------------------------- splicing
def _splice(t: Topology, comp_id: str) -> None:
    """Remove an inline 2-port component: line_in + line_out become one line (properties merged)."""
    lin = next((ln for ln in t.process_lines if ln.to.ref == comp_id), None)
    lout = next((ln for ln in t.process_lines if ln.from_.ref == comp_id), None)
    t.components = [c for c in t.components if c.id != comp_id]
    if lin is not None and lout is not None:
        merged = lin.model_copy(update={"to": lout.to, "properties": {**lout.properties, **lin.properties}})
        t.process_lines = [merged if ln.id == lin.id else ln for ln in t.process_lines if ln.id != lout.id]
        for cr in t.control_requirements:
            if cr.measured_at_line == lout.id:
                cr.measured_at_line = lin.id
    else:  # open end (drain / vent): the stub disappears with the component
        t.process_lines = [ln for ln in t.process_lines if ln.id not in {getattr(lin, "id", None), getattr(lout, "id", None)}]
    for u in t.unresolved_requirements:
        u.affects = [a for a in u.affects if a != comp_id]
    for m in t.operating_modes:
        for r in m.requirements:
            r.targets = [x for x in r.targets if x.ref != comp_id]


def _collapse_banks(t: Topology) -> list[Bank]:
    """Identical units whose every connected nozzle goes to its own branch of one shared header -> one unit.

    Works for one-sided banks (pumps: suction header -> units -> discharge header) and multi-sided ones
    (exchangers with a header on each side).
    """
    banks: list[Bank] = []
    changed = True
    while changed:
        changed = False
        eqs = {e.id: e for e in t.equipment}
        mans = {c.id: c for c in t.components if c.kind == "manifold"}
        for m in list(mans.values()):
            branch_lines = [ln for ln in t.process_lines
                            if (ln.from_.ref == m.id and ln.from_.port != "common") or (ln.to.ref == m.id and ln.to.port != "common")]
            ends = [(ln.to.ref if ln.from_.ref == m.id else ln.from_.ref) for ln in branch_lines]
            units = [eqs.get(x) for x in ends]
            if len(units) < 2 or any(u is None for u in units) or len(set(ends)) != len(ends):
                continue
            if len({(u.model_class, tuple(sorted(n.name for n in u.nozzles)), u.lifecycle) for u in units}) != 1:
                continue
            uid = {u.id for u in units}
            # every connected nozzle of every unit must go to a branch of a header shared by exactly these units
            headers: dict[str, str] = {}   # nozzle name -> manifold id
            ok = True
            for nz in units[0].nozzles:
                lines = [ln for ln in t.process_lines if (ln.from_.ref in uid and ln.from_.port == nz.name) or (ln.to.ref in uid and ln.to.port == nz.name)]
                if not lines:
                    continue
                others = {(ln.to.ref if ln.from_.ref in uid else ln.from_.ref) for ln in lines}
                if len(lines) != len(units) or len(others) != 1:
                    ok = False
                    break
                hid = next(iter(others))
                h = mans.get(hid)
                if h is None or (h.branches or 0) < len(units):
                    ok = False
                    break
                headers[nz.name] = hid
            if not ok or not headers:
                continue
            rep = units[0]
            # a header shared with other branches stays: only the extra units' branches go, ports are renumbered
            shared = {hid for hid in headers.values() if (mans[hid].branches or 0) > len(units)}
            removed_units = {u.id for u in units if u is not rep}
            for hid in shared:
                t.process_lines = [ln for ln in t.process_lines
                                   if not ((ln.from_.ref in removed_units and ln.to.ref == hid) or (ln.to.ref in removed_units and ln.from_.ref == hid))]
                _renumber_branches(t, hid)
            headers = {k: v for k, v in headers.items() if v not in shared}
            new_lines, drop = [], set()
            for nzname, hid in headers.items():
                common = next((ln for ln in t.process_lines if (ln.from_.ref == hid and ln.from_.port == "common") or
                               (ln.to.ref == hid and ln.to.port == "common")), None)
                if common is None:
                    ok = False
                    break
                drop |= {ln.id for ln in t.process_lines if ln.from_.ref == hid or ln.to.ref == hid}
                if common.to.ref == hid:
                    new_lines.append(common.model_copy(update={"to": Ref(ref=rep.id, port=nzname)}))
                else:
                    new_lines.append(common.model_copy(update={"from_": Ref(ref=rep.id, port=nzname)}))
            if not ok:
                continue
            t.process_lines = [ln for ln in t.process_lines if ln.id not in drop] + new_lines
            t.components = [c for c in t.components if c.id not in set(headers.values())]
            others_ids = {u.id for u in units if u is not rep}
            t.equipment = [e for e in t.equipment if e.id not in others_ids]
            tags = [u.tag for u in units if u.tag]
            rep.tag = _join_tags(tags) if tags else None
            rep.name = f"{_common_name([u.name or '' for u in units], tags)} ({len(units)} units)"
            cfg = next((a.value for u in units for k, a in u.attributes.items() if k in ("configuration", "arrangement")), None)
            if cfg and str(cfg) not in rep.name:
                rep.name += f" – {cfg}"
            for u_ in t.unresolved_requirements:
                u_.affects = list(dict.fromkeys(rep.id if a in others_ids else a for a in u_.affects))
            banks.append(Bank(rep.id, [u.id for u in units], sorted(set(headers.values()))))
            changed = True
            break
    return banks


def _renumber_branches(t: Topology, hid: str) -> None:
    """Compact b1..bn of a header after branches were removed; a header left with one branch becomes a plain line."""
    h = next(c for c in t.components if c.id == hid)
    blines = [ln for ln in t.process_lines if (ln.from_.ref == hid and ln.from_.port != "common") or (ln.to.ref == hid and ln.to.port != "common")]
    blines.sort(key=lambda ln: int((ln.from_.port if ln.from_.ref == hid else ln.to.port)[1:]))
    out = []
    for k, ln in enumerate(blines, 1):
        out.append(ln.model_copy(update={"from_": Ref(ref=hid, port=f"b{k}")}) if ln.from_.ref == hid else ln.model_copy(update={"to": Ref(ref=hid, port=f"b{k}")}))
    ids = {ln.id for ln in blines}
    t.process_lines = [ln for ln in t.process_lines if ln.id not in ids] + out
    h.branches = len(out)
    if len(out) == 1:  # pass-through: join the two lines
        common = next(ln for ln in t.process_lines if (ln.from_.ref == hid and ln.from_.port == "common") or (ln.to.ref == hid and ln.to.port == "common"))
        b = out[0]
        if common.to.ref == hid:
            merged = common.model_copy(update={"to": b.to, "properties": {**b.properties, **common.properties}})
        else:
            merged = b.model_copy(update={"to": common.to, "properties": {**common.properties, **b.properties}})
        t.process_lines = [ln for ln in t.process_lines if ln.id not in (common.id, b.id)] + [merged]
        t.components = [c for c in t.components if c.id != hid]


def _join_tags(tags: list[str]) -> str:
    """P-201, P-202, P-203 -> P-201/202/203."""
    m = [re.match(r"^(.*?)(\d+)([A-Z]?)$", x) for x in tags]
    if all(m) and len({x.group(1) for x in m}) == 1:
        return m[0].group(1) + "/".join(x.group(2) + x.group(3) for x in m)
    return "/".join(tags)


def _common_name(names: list[str], tags: list[str] | None = None) -> str:
    """Shared part of the unit names: tags, '1/3', '(stand-by)' and trailing numbers/letters removed."""
    base = []
    for n in names:
        for tg in tags or []:
            n = n.replace(tg, "")
        n = re.sub(r"\s*[\(\[]?\d+/\d+[\)\]]?|\s*\((stand-by|standby|secours|spare)\)|\s+[A-Z0-9]{1,3}$", "", n)
        base.append(re.sub(r"\s{2,}", " ", n).strip(" -–,"))
    if len(set(base)) == 1 and base[0]:
        return base[0]
    words = [b.split() for b in base]
    if len({len(w) for w in words}) == 1:  # same shape: keep the words all names share (PAC 1A/1B – heat pump -> PAC – heat pump)
        common = [col[0] for col in zip(*words) if len(set(col)) == 1]
    else:
        common = []
        for col in zip(*words):
            if len(set(col)) != 1:
                break
            common.append(col[0])
    return " ".join(common).strip(" -–,") or base[0]


# ------------------------------------------------------------------------------------- control
def _control_functions(t: Topology) -> list[str]:
    """A stated automatic control action with a measurement point becomes its controller on the PFD."""
    notes: list[str] = []
    lines = {ln.id: ln for ln in t.process_lines}
    by_logical = {logical(ln): ln for ln in t.process_lines}
    comps = {c.id for c in t.components}
    for cr in t.control_requirements:
        if not cr.controller_required:
            continue
        var = (cr.controlled_variable or "").lower()
        code = _CTRL_CODE.get(var)
        line = lines.get(cr.measured_at_line or "") or by_logical.get(cr.measured_at_line or "")
        sp = f" – setpoint {cr.setpoint.value} {cr.setpoint.unit or ''}".rstrip() if cr.setpoint is not None else ""
        if code is None or line is None or cr.final_element not in comps:
            notes.append(f"{cr.description}: control function not drawn (measurement point or variable not stated).")
            continue
        iid = f"in.pfd.{cr.id}"
        t.instruments.append(Instrument(id=iid, name=f"{code} – {cr.description}{sp}", isa_code=code, measured_variable=var,
                                        function="controller", target={"kind": "line", "ref": logical(line)}, tag=None, area=None,
                                        provenance=cr.provenance))
        t.signals.append(Signal.model_validate({"id": f"sg.pfd.{cr.id}", "kind": "control", "from": iid, "to": cr.final_element,
                                                "provenance": cr.provenance.model_dump()}))
        notes.append(f"{code} on {line.service}{sp} (stated).")
    return notes


# ------------------------------------------------------------------------------------- streams
def _node_name(t: Topology, ref: str, direction: str = "up") -> str:
    """Display name of a stream end; a header junction is named by the equipment it connects."""
    names = _resolve(t, ref, direction, 0)
    if len(names) > 3:
        return f"header ({len(names)} {'sources' if direction == 'up' else 'users'})"
    return " + ".join(names) if names else ref


def _resolve(t: Topology, ref: str, direction: str, depth: int) -> list[str]:
    o = t.objects().get(ref) or next((e for e in t.equipment if e.id == ref), None)
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
    """One stream per line between two process nodes (equipment, junction, control valve, battery limit), in flow order."""
    by_from: dict[str, list[ProcessLine]] = defaultdict(list)
    for ln in t.process_lines:
        by_from[ln.from_.ref].append(ln)
    incoming = {ln.to.ref for ln in t.process_lines}
    # follow the process from each inlet to its end before starting the next (depth first, extraction order)
    starts = [b.id for b in t.boundaries if b.direction == "in"]
    starts += [ln.from_.ref for ln in t.process_lines if ln.from_.ref not in incoming and ln.from_.ref not in starts]
    order: list[ProcessLine] = []
    taken: set[str] = set()

    def walk(n: str) -> None:
        for ln in by_from.get(n, []):
            if ln.id in taken:
                continue
            taken.add(ln.id)
            order.append(ln)
            walk(ln.to.ref)

    for n in starts:
        walk(n)
    for ln in t.process_lines:  # closed loops without an inlet
        if ln.id not in taken:
            walk(ln.from_.ref)
    streams = []
    for ln in order:
        s = Stream(len(streams) + 1, [ln.id], ln.service, _node_name(t, ln.from_.ref, "up"), _node_name(t, ln.to.ref, "down"))
        s.values = {"Service": ln.service, "From": s.frm, "To": s.to, **_stream_values(ln.properties)}
        if _size(ln.properties):
            s.values["Size (stated)"] = _size(ln.properties)
        s.flow_src = _flow_key(ln.properties)
        streams.append(s)
    return streams


def _fmt(a: Attr) -> str:
    v = a.value
    if isinstance(v, dict):
        v = "–".join(str(x) for x in v.values())
    return f"{v} {a.unit}".strip() if a.unit else str(v)


_QUAL = {"max": "≤ ", "min": "≥ ", "maximum": "≤ ", "minimum": "≥ "}


def _qualified(key: str, a: Attr) -> str:
    """temperature_max -> '≤ 30 °C'; temperature_supply -> 'supply 90 °C'."""
    parts = key.split("_")[1:]
    pre = "".join(_QUAL.get(p, "") for p in parts)
    tag = " ".join(p for p in parts if p not in _QUAL)
    return (f"{tag} " if tag else "") + pre + _fmt(a)


def _stream_values(props: dict[str, Attr]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row, stem in (("Temperature", "temperature"), ("Pressure", "pressure"), ("Flow", "flow")):
        keys = sorted(k for k in props if (k.startswith(stem) if stem != "flow" else "flow" in k) and props[k].value not in (None, ""))
        if keys:
            out[row] = " / ".join(_qualified(k, props[k]) if stem != "flow" else _fmt(props[k]) for k in keys)
    return out


def _size(props: dict[str, Attr]) -> str:
    a = props.get("nominal_diameter")
    if a is not None and a.value:
        return f"DN{a.value}"
    a = props.get("nominal_diameter_range")
    if a is not None and isinstance(a.value, dict):
        return f"DN{a.value.get('min')}–{a.value.get('max')}"
    a = props.get("nominal_diameter_min")
    if a is not None and a.value:
        return f"≥ DN{a.value}"
    return ""


def _flow_key(props: dict[str, Attr]) -> tuple | None:
    for k, a in props.items():
        if "flow" in k:
            q = a.provenance.quote if a.provenance else None
            return (k, str(a.value), a.unit, q)
    return None


def _flows_once(streams: list[Stream]) -> None:
    """A flow stated once in the document is printed on the first stream that carries it; the others refer to it."""
    first: dict[tuple, int] = {}
    for s in streams:
        if s.flow_src is None or "Flow" in s.derived:
            continue
        if s.flow_src in first:
            s.values["Flow"] = f"see {first[s.flow_src]}"
        else:
            first[s.flow_src] = s.no


_SIDES = ("water", "cold", "hot", "steam", "process", "product", "evap", "cond", "primary", "secondary", "shell", "tube")


def _equipment_stream_data(t: Topology, streams: list[Stream]) -> None:
    """Values stated for an equipment's own inlet/outlet go on that equipment's streams (marked * = equipment data)."""
    by_line = {lid: s for s in streams for lid in s.line_ids}
    for e in t.equipment:
        for key, a in e.attributes.items():
            parts = key.split("_")
            end = "inlet" if "inlet" in parts else ("outlet" if "outlet" in parts else None)
            row = "Temperature" if "temperature" in parts else ("Flow" if "flow" in parts else ("Pressure" if "pressure" in parts else None))
            generic = {"inlet", "outlet", "temperature", "flow", "pressure", "design", "operating", "nominal"}
            side = None if parts[0] in generic else parts[0]
            if row is None or (end is None and row != "Flow") or (row == "Flow" and side is None):
                continue
            if side and side not in _SIDES and not any(side in n.name.lower() for n in e.nozzles):
                continue  # a medium the drawing does not show (e.g. the air side of a coil)
            roles = {"inlet": ("inlet", "suction"), "outlet": ("outlet", "discharge")}
            noz = [n for n in e.nozzles if end is None or n.role in roles[end]]
            n_in = len([n for n in e.nozzles if n.role in ("inlet", "suction")])
            named = [n for n in noz if side and side in n.name.lower()]
            noz = named or (noz if n_in <= 1 else [])
            if end is None:  # a side flow without inlet/outlet: the inlet stream of that side
                noz = [n for n in noz if n.role in ("inlet", "suction")][:1]
            if len(noz) != 1:
                continue
            ln = next((x for x in t.process_lines if (x.to.ref == e.id and x.to.port == noz[0].name) or
                       (x.from_.ref == e.id and x.from_.port == noz[0].name)), None)
            s = by_line.get(ln.id) if ln is not None else None
            if s is None:
                continue
            qual = "≤ " if "max" in parts else ("≥ " if "min" in parts else "")
            s.values[row] = qual + _fmt(a)
            s.derived.add(row)
    # a pump's design flow is the flow of its discharge stream
    for e in t.equipment:
        a = e.attributes.get("design_volume_flow_rate")
        if a is None:
            continue
        ln = next((x for x in t.process_lines if x.from_.ref == e.id), None)
        s = by_line.get(ln.id) if ln is not None else None
        if s is not None and "Flow" not in s.values:
            s.values["Flow"] = f"{_fmt(a)} per unit" if "units)" in (e.name or "") else _fmt(a)
            s.derived.add("Flow")


def _equipment_summary(t: Topology) -> list[tuple[str, str, str]]:
    skip = {"label", "members"}
    rows = []
    for e in sorted(t.equipment, key=lambda x: (x.tag or "~", x.id)):
        data = [f"{k.replace('_', ' ')} {_fmt(a)}" for k, a in e.attributes.items()
                if k not in skip and a.value not in (None, "", False) and str(a.value) not in (e.name or "")]
        data = [d.replace(" True", "") for d in data]
        rows.append((e.tag or "–", e.name or e.id, "; ".join(data)))
    return rows


def stream_labels(pfd: PFD) -> dict[str, str]:
    """Topology line id -> stream number text (for the drawing)."""
    return {lid: str(s.no) for s in pfd.streams for lid in s.line_ids}
