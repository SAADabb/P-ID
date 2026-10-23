"""Turn the open points and pending proposals into the few decisions an engineer actually has to make.

* **Holds** - questions whose answer can change the drawing.  Each one states what the drawing shows
  today (``drawn_as``) so the reviewer confirms or corrects instead of starting from a blank page.
* **Rule approvals** - the proposed additions are approved per project rule (one decision per rule,
  ``pid review --approve-rule``), not object by object.
* **Datasheet data** - missing values that do not change the drawing; listed once, not marked on it.

The triage lives in ``projects/<p>/review_plan.yaml`` (optional).  Without it every open point that is
not a plain missing value becomes a hold.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .render_onesheet import Hold, SheetContent
from .schema import Topology

DEFAULT_NOTES = [
    "Draft generated from the specification – not for construction.",
    "Orange items are additions proposed by the project rules; approval is per rule, see the decision register.",
    "Values the specification does not give (design pressures, relief sizing, fail positions, ranges, nozzle sizes) are not assumed.",
]


@dataclass
class HoldRow:
    hold: Hold
    drawn_as: str
    question: str
    answer: str | None
    category: str


@dataclass
class Register:
    holds: list[HoldRow] = field(default_factory=list)
    closed: list[HoldRow] = field(default_factory=list)
    rules: list[tuple[str, int, str]] = field(default_factory=list)  # rule id, pending objects, what it adds
    datasheet: list[tuple[str, str]] = field(default_factory=list)  # ur id, text
    notes: list[str] = field(default_factory=list)


def issue_date() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    d = dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc).date() if epoch else dt.date.today()
    return d.isoformat()


def _first_sentence(s: str, n: int = 70) -> str:
    s = re.split(r"(?<=[.;:])\s", s.strip())[0].rstrip(".;:")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def load_plan(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def build_register(topo: Topology, plan: dict[str, Any]) -> Register:
    reg = Register()
    open_urs = {u.id: u for u in topo.unresolved_requirements if u.status == "open"}
    planned = {h["ur"]: h for h in plan.get("holds", []) if h.get("ur") in open_urs}
    datasheet_ids = [x for x in plan.get("datasheet", []) if x in open_urs]
    if plan:
        rest = [u for u in open_urs if u not in planned and u not in datasheet_ids]
        # anything the plan forgot is a hold: never silently dropped
        hold_ids = list(planned) + rest
    else:
        hold_ids = [u.id for u in open_urs.values() if u.category != "missing_value"]
        datasheet_ids = [u.id for u in open_urs.values() if u.category == "missing_value"]
    num = 0
    for uid in hold_ids:
        u = open_urs[uid]
        h = planned.get(uid, {})
        title = h.get("title") or _first_sentence(u.description)
        drawn = h.get("drawn_as") or ""
        q = u.question or ""
        ans = h.get("answer")
        text = (f"Drawn: {drawn} " if drawn else "") + (f"Question: {q}" if q else ("" if drawn else u.description))
        row = HoldRow(Hold(0, uid, title, text.strip(), list(u.affects)), drawn, q, ans, u.category)
        if ans:
            reg.closed.append(row)
        else:
            num += 1
            row.hold.num = num
            reg.holds.append(row)
    for uid in datasheet_ids:
        reg.datasheet.append((uid, open_urs[uid].description))
    # rule approvals
    pending = Counter()
    what: dict[str, Counter] = defaultdict(Counter)
    for o in topo.objects().values():
        pv = o.provenance
        if pv.origin == "generated" and pv.status == "pending_review" and pv.rule:
            pending[pv.rule] += 1
            what[pv.rule][type(o).__name__] += 1
    for m in topo.modifications:
        pv = m.provenance
        if pv.status == "pending_review" and pv.rule and m.field not in ("line", "rejected", "split"):
            pending[pv.rule] += 1
            what[pv.rule][f"{m.field} on a source object"] += 1
    for rid in sorted(pending):
        desc = ", ".join(f"{n} × {k}" for k, n in what[rid].most_common())
        reg.rules.append((rid, pending[rid], desc))
    reg.notes = list(plan.get("notes") or DEFAULT_NOTES)
    return reg


def sheet_content(topo: Topology, reg: Register) -> SheetContent:
    labels: dict[str, str] = {}
    for ln in topo.process_lines:
        lab = ln.line_number or ""
        dn = ln.properties.get("nominal_diameter")
        rng = ln.properties.get("nominal_diameter_range")
        mn = ln.properties.get("nominal_diameter_min")
        size = ""
        if dn is not None and dn.value:
            size = f"DN{dn.value}"
        elif rng is not None:
            size = f"DN{rng.value['min']}–{rng.value['max']}"
        elif mn is not None:
            size = f"≥DN{mn.value}"
        labels[ln.id] = " · ".join(x for x in (lab, size) if x) or ln.service
    tbd = [_first_sentence(t, 160) for _, t in reg.datasheet]
    return SheetContent(holds=[r.hold for r in reg.holds], notes=reg.notes, tbd=tbd, line_labels=labels,
                        revision=[("A", issue_date(), "Draft generated from the specification – issued for engineering review")])


def register_md(reg: Register, topo: Topology) -> str:
    out = ["# Decision register", "",
           f"Everything an engineer has to decide before this drawing can be issued: **{len(reg.holds)} holds** and "
           f"**{len(reg.rules)} rule approvals**. Datasheet values ({len(reg.datasheet)} items) do not change the drawing.", "",
           "## 1. Holds (marked H1, H2 … on the drawing)", "",
           "Answer by setting `answer:` in `review_plan.yaml`, then `pid run`. The marker disappears; the answer stays here.", "",
           "| Hold | Decision | Drawn today | Question | Affects |", "|---|---|---|---|---|"]
    for r in reg.holds:
        out.append(f"| H{r.hold.num} | {r.hold.title} | {r.drawn_as or '–'} | {r.question or '–'} | {', '.join(r.hold.affects[:6])}{' …' if len(r.hold.affects) > 6 else ''} |")
    if reg.closed:
        out += ["", "### Closed holds", "", "| Decision | Answer |", "|---|---|"]
        out += [f"| {r.hold.title} | {r.answer} |" for r in reg.closed]
    out += ["", "## 2. Rule approvals (proposed additions, drawn in orange)", "",
            "One decision per rule: `pid review projects/<p> --approve-rule <rule>` (or `--reject` single objects).", "",
            "| Rule | Pending objects | Adds |", "|---|---|---|"]
    out += [f"| `{rid}` | {n} | {d} |" for rid, n, d in reg.rules]
    out += ["", "## 3. Data to complete on datasheets (not holds)", ""]
    out += [f"- **{uid}** – {t}" for uid, t in reg.datasheet]
    return "\n".join(out) + "\n"
