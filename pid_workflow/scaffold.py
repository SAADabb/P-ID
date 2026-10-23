"""``pid new``: set up a project folder for a new specification, and ``pid check``: tell the agent what to fix."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from .sourcedoc import SourceDocument, check_quotes
from .topology_io import load_topology
from .validate import validate

TEMPLATES = Path(__file__).parent / "templates"


def new_project(name: str, spec: str | Path, repo: str | Path = ".", language: str = "fr", force: bool = False) -> Path:
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError("project name: lowercase letters, digits and _ only")
    repo = Path(repo).resolve()
    spec = Path(spec).resolve()
    root = repo / "projects" / name
    if root.exists() and not force:
        raise FileExistsError(f"{root} exists (use --force to overwrite the scaffold files)")
    (root / "source").mkdir(parents=True, exist_ok=True)
    (root / "extraction").mkdir(exist_ok=True)
    dst = root / "source" / spec.name
    if spec != dst:
        shutil.copy2(spec, dst)
    doc = SourceDocument.load(dst)
    doc.write_pages(root / "source" / "pages")
    (root / "project.yaml").write_text(yaml.safe_dump({
        "name": name,
        "source_document": f"source/{spec.name}",
        "source_topology": "source_topology.json",
        "working_topology": "working_topology.json",
        "rules": "project_rules.yaml",
        "layout_hints": "layout_hints.yaml",
        "review_plan": "review_plan.yaml",
        "generic_policy": "../../policies/generic.yaml" if (repo / "policies" / "generic.yaml").exists() else "bundled",
        "rendering": "../../policies/rendering.yaml" if (repo / "policies" / "rendering.yaml").exists() else "bundled",
        "output_dir": "output",
        "reports_dir": "reports",
    }, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (root / "project_rules.yaml").write_text(f"""# Project rules for {name}.
# The good-practice pack adds the usual auxiliaries (pump valves and strainers, vessel drains/vents/level, relief devices,
# control-valve stations, tags, line numbers) as PROPOSALS.  For each thing the specification asks for explicitly,
# override the pack rule with the same id and cite the page + verbatim quote.  Switch off what does not fit:
#   - {{id: pump.auxiliaries, enabled: false}}
project: {name}
document: "{spec.name}"
language: en             # language of the drawings' generated texts (the document language is in the extraction)
include: [process_good_practice]

overrides: {{}}          # e.g. line_numbering: {{codes: [{{prefix: "Chilled water", code: "CHW"}}]}}

rules: []
# Example of a document-cited rule (replaces the pack rule with the same id):
#  - id: pump.auxiliaries
#    type: equipment_template
#    source: {{page: 3, section: "4.2 Pompes", quote: "verbatim text"}}
#    params:
#      applies_to: [Pump]
#      inline:
#        suction:   [{{function: isolation, operation: manual}}]
#        discharge: [{{function: check}}, {{function: isolation, operation: manual}}]
""", encoding="utf-8")
    (root / "layout_hints.yaml").write_text("""# Optional. Plant areas of the one-sheet drawing (globs of equipment / manifold / battery-limit ids) and their arrangement.
# Without 'sheets', every area of the topology is one plant area; without 'onesheet', the arrangement is searched.
# sheets:
#   - {id: S1, title: "Production", assign: ["eq.ch*", "mf.chw_*"]}
# onesheet:
#   rows: [[S1, S2], [S3]]
""", encoding="utf-8")
    (root / "review_plan.yaml").write_text("""# Triage of every open point (pid check lists the ones still missing). This is review organisation, not engineering data.
#
# holds: questions whose answer can change the drawing. Shown as H1, H2 ... on the sheet. Example:
#   - ur: ur.fc_position                         # id of the open point (s.unresolved in the extraction)
#     title: "Free-cooling exchanger – series or parallel?"
#     drawn_as: "Not connected until the position is decided."   # what the drawing shows today
#     answer: null                               # the reviewer writes the decision here; the marker then disappears
# datasheet: open points that are only missing values (sizes, ranges, tags, nozzle data) - listed once, not marked.
# notes: general notes printed on the sheet.
holds: []
datasheet: []
notes: []
""", encoding="utf-8")
    script = root / "extraction" / f"extract_{name}.py"
    if not script.exists() or force:
        txt = (TEMPLATES / "extract_template.py").read_text(encoding="utf-8")
        script.write_text(txt.replace("{name}", name).replace("{NAME}", name.upper()).replace("{language}", language)
                          .replace("{{", "{").replace("}}", "}"), encoding="utf-8")
    return root


def check_project(root: str | Path) -> list[tuple[str, str, str]]:
    """(level, what, how to fix) for a project whose source topology was written by the extraction."""
    root = Path(root)
    cfg = yaml.safe_load((root / "project.yaml").read_text(encoding="utf-8"))
    out: list[tuple[str, str, str]] = []
    doc_path = root / cfg["source_document"]
    doc = SourceDocument.load(doc_path) if doc_path.exists() else None
    if doc is not None and not doc.has_text():
        out.append(("error", "the document has no text layer", "OCR it (e.g. ocrmypdf in.pdf out.pdf) and run pid new again"))
    src = root / cfg["source_topology"]
    if not src.exists():
        out.append(("error", "source_topology.json missing", f"write and run extraction/extract_{root.name}.py"))
        return out
    topo = load_topology(src)
    for i in validate(topo).issues:
        if i.level in ("error", "warning"):
            out.append((i.level, f"{i.code}: {i.message}", _hint(i.code)))
    if doc is not None:
        for oid, msg in check_quotes(topo, doc):
            out.append(("error", f"{oid}: {msg}", "copy the words exactly from source/pages/page_NNN.txt and fix the page number"))
    # rules that cite the document must quote it verbatim
    rules = yaml.safe_load((root / cfg["rules"]).read_text(encoding="utf-8")) or {}
    for r in rules.get("rules", []) or []:
        q = (r.get("source") or {}).get("quote")
        if q and doc is not None and not doc.pages_with(q):
            out.append(("error", f"rule {r['id']}: quote not in the document", "quote the specification verbatim"))
    # every open point triaged
    plan_path = root / cfg.get("review_plan", "review_plan.yaml")
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
    planned = {h.get("ur") for h in (plan or {}).get("holds", [])} | set((plan or {}).get("datasheet", []))
    missing = [u.id for u in topo.unresolved_requirements if u.status == "open" and u.id not in planned]
    if missing:
        out.append(("warning", f"{len(missing)} open point(s) not in review_plan.yaml: {', '.join(missing[:6])}{' …' if len(missing) > 6 else ''}",
                    "add each to holds (with title + drawn_as) or to datasheet; generated ur.gen.* points appear after the first pid run"))
    n_explicit = sum(1 for e in topo.equipment if e.provenance.basis == "explicit")
    if topo.equipment and n_explicit / len(topo.equipment) < 0.5:
        out.append(("warning", f"only {n_explicit}/{len(topo.equipment)} equipment items are explicit in the text",
                    "equipment should come from the document; quote the sentence or table row that names it"))
    no_quote = [e.id for e in topo.equipment if e.provenance.basis == "explicit" and not e.provenance.quote]
    if no_quote:
        out.append(("warning", f"{len(no_quote)} explicit equipment item(s) without a quote: {', '.join(no_quote[:5])}",
                    "add the verbatim quote so the reviewer can find the statement"))
    return out


_HINTS = {
    "CLASS_UNSUPPORTED": "use a pyDEXPI class (python -c 'from pid_workflow.catalog import equipment_classes; print(sorted(equipment_classes()))') "
                         "or CustomEquipment with symbol=",
    "LINE_PORT": "the port name must be a nozzle name of the equipment, in/out for valves, common/b1..bn for manifolds, port for battery limits",
    "LINE_ENDPOINT": "the line refers to an object id that does not exist (typo?)",
    "LINE_SERVICE": "every line needs a service name (fluid), e.g. 'Chilled water'",
    "AREA_UNKNOWN": "declare the area with s.area(...) before using it",
    "ID_DUPLICATE": "ids must be unique across all objects",
    "TAG_DUPLICATE": "two objects carry the same tag: check the document",
    "PORT_REUSED": "a port takes one line: add a manifold (s.manifold / s.bank) where a line branches",
    "PORT_OPEN": "connect the nozzle, or record why it is open with s.unresolved(..., affects=[equipment id])",
    "FLOW_DIRECTION": "lines run in flow direction: from an outlet/discharge to an inlet/suction",
    "PROV_SOURCE": "every object needs page + section (s.src / s.interp / s.structural)",
    "MANIFOLD_DEF": "a manifold needs role split|merge and at least 2 branches",
    "UNRESOLVED_REF": "the open point names an object id that does not exist",
}


def _hint(code: str) -> str:
    for k, v in _HINTS.items():
        if code.startswith(k):
            return v
    return "see reports/validation.md and pid_workflow/validate.py"
