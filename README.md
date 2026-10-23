# P-ID — draft P&IDs from engineering specifications

A reusable workflow that turns a written engineering specification into

1. a **traceable topology** of the source facts (`source_topology.json`),
2. an **enriched topology** with clearly marked proposals (`working_topology.json`),
3. a **review PDF** — cover, overview, one drawing sheet per area, review tables,
4. a **DEXPI Proteus XML** file built with [pyDEXPI](https://github.com/process-intelligence-research/pyDEXPI),
5. **reports** on checks, assumptions, open points and export limitations.

The first project is `projects/lpf_bsst`, built from *“Cahier des Charges P&ID Consolidé.pdf”*
(Décarbonation énergétique LPF & BSST, 3 pages). How the result compares with the reference drawing that accompanied the brief:
[`projects/lpf_bsst/docs/reference_drawing_comparison.md`](projects/lpf_bsst/docs/reference_drawing_comparison.md).

> **Draft, not for construction.** Every addition is `pending_review`. Nothing the specification does not state
> (design pressures, relief sizing, safety thresholds, valve failure positions, material classes, nozzle sizes,
> instrument ranges) was invented — those gaps are kept as **unresolved requirements**.

## Who does what

| Stage | Done by | Output |
|---|---|---|
| **Extraction** — read the document, identify equipment, lines, instruments, connections, operating conditions, control requirements, modes | **the AI** (record: `projects/<p>/extraction/`) | `source_topology.json` (frozen) |
| **Enrichment** — apply the project rules to complete the logical topology | deterministic rules, parameterised by the project | `working_topology.json` |
| **Validation** — schema, identifiers, connections, flow directions, supported model classes | deterministic | `reports/validation.md` |
| **Layout** — positions and routing (never stored in the topology) | deterministic | computed per sheet |
| **Export** — pyDEXPI model → Proteus XML | deterministic | `output/pid_draft.proteus.xml` |
| **Review** — PDF and a round-trip check that the XML keeps the graph | deterministic | `output/pid_review_draft.pdf`, `reports/roundtrip.md` |

The AI does the extraction and the engineering reasoning (which facts are explicit, which are interpretations, what is missing);
Python does everything structural.

## Quick start

```bash
pip install -e ".[dev]"            # pydexpi, pydantic, reportlab, lxml, networkx, pyyaml
pid run projects/lpf_bsst          # enrich → validate → export → verify → lay out → PDF → reports
                                   # (set SOURCE_DATE_EPOCH for a byte-reproducible XML)
pytest                             # 42 tests, including a second, unrelated project
```

Outputs of the LPF/BSST project:

```
projects/lpf_bsst/
  source_topology.json             unchanged snapshot of what was read from the PDF (page + section on every object)
  working_topology.json            source + proposed additions (rule, triggers, explanation, status)
  output/pid_review_draft.pdf      the drawings
  output/pid_draft.proteus.xml     DEXPI Proteus XML
  reports/summary.md               start here
```

### Reading the PDF

* Black = from the specification. **Orange = proposed** by a project rule, waiting for approval. Dashed grey = future equipment.
* Red numbered dots = **open points**; the same numbers are listed on each sheet and in the tables at the end.
* Lines are coloured by service; every valve/instrument tag on an orange item is a *proposed* ISA 5.1 tag.
* Sheets are connected by off-page references (`from Sh.2`, `to Sh.4`); page 2 shows which sheets exchange which services.

### Reviewing proposals

```bash
pid review projects/lpf_bsst --list                          # what is pending
pid review projects/lpf_bsst --approve-rule pump.auxiliaries # approve a whole rule's output
pid review projects/lpf_bsst --approve pc.gen.loop_pump_a.suction_isolation
pid review projects/lpf_bsst --reject  pc.gen.loop_pump_a.suction_isolation   # removes it, restores the source line, never re-proposed
pid run projects/lpf_bsst                                    # regenerate PDF, XML and reports
```

Approved items are drawn in normal ink and stay approved when enrichment is re-applied.

## Architecture

```
pid_workflow/
  schema.py          topology models (pydantic): equipment, components, boundaries, instruments, lines, signals,
                     control requirements/loops, operating modes, unresolved requirements, provenance
  policy.py          generic policy (policies/generic.yaml) + project rules (projects/<p>/project_rules.yaml)
  enrich.py          idempotent rule engine (pump auxiliaries, mode isolation, header instrumentation,
                     control-valve manifold, vessel auxiliaries, control loops, ISA tagging, unresolved summary)
  validate.py        structural validation
  layout.py          layered layout, row folding, orthogonal routing, instrument placement, geometric QA
  render_pdf.py      ReportLab drawings and tables
  export_dexpi.py    topology → pyDEXPI model
  proteus_ext.py     Proteus XML writer for piping + instrumentation (plugs into pyDEXPI's exporter framework)
  roundtrip.py       re-reads the XML with lxml and with pyDEXPI and compares it with the topology
  review.py          approve / reject
  reports.py         Markdown reports
  pipeline.py, cli.py
policies/            generic.yaml (principles, never-invent list, valve defaults, tagging), rendering.yaml (colours)
projects/<name>/     project.yaml, source_topology.json, project_rules.yaml, layout_hints.yaml, source/, extraction/
```

### Topology data model

* **Identifiers.** `id` is a schematic identifier (`eq.well_pump_a`); `tag` is the real engineering tag (`P-030`) or `null`;
  `tag_status` is `source`, `proposed` or `none`. Nozzles have a schematic `name` and a real `number` that stays `null` until the source gives one.
* **Provenance.** Source objects: `document`, `page`, `section`, `quote`, `basis` (`explicit` / `interpreted` / `structural`).
  Generated objects: `rule`, `triggers`, `explanation`, `status` (`pending_review` → `approved` | rejected and removed).
  Values carry their own provenance too (`attributes.*.provenance`).
* **No coordinates.** Layout lives only in the computed sheets. `layout_hints.yaml` only says which objects go on which sheet.
* **Lines** have explicit endpoints (`{ref, port}`), a mandatory `service`, supplied properties, and — after enrichment —
  `split_from` pointing to the source line they came from. Inline valves are inserted by **splitting** the line; branches and bypasses use explicit **manifolds** (tees).
* **Modifications** record every change to a source object (old value kept) and the original of every split line.

### Engineering rules

Explicit project requirements take precedence over generic defaults; a rule fires only when its prerequisites hold; existing
components are reused; applying the rules twice changes nothing. In the LPF/BSST project (all cited to the PDF):

| Rule | Does |
|---|---|
| `pump.auxiliaries` | manual suction isolation; discharge check valve then isolation valve |
| `mode.isolation` | isolation valves “toward PAC and exchangers” required by the ultimate/emergency modes |
| `header.instrumentation` | PT and TT on the 1/4/8 bar steam and 90/105 °C hot-water headers |
| `control_valve.manifold` | upstream/downstream isolation, purge valve, bypass with a globe valve (explicit junctions) |
| `vessel.auxiliaries` | drain, vent and LT on tanks and vessels (flagged “verify” for existing ones) |
| `control_loop.from_requirement` | measurement → controller → final element **only** when the source states an automatic control action with a setpoint (the boiler back-up PCV at 7.5 bar eff.); a transmitter alone never creates a controller |
| `tagging.isa` | unique proposed ISA 5.1 tags; the PT, PIC and PCV of a loop share their loop number |

Valves whose technology the source does not give use the explicitly marked generic class (`CustomOperatedValve`,
“technology to be selected”); the choice is listed in `ur.gen.valve_technology`, never made silently.

### Using it for another specification

1. Copy `projects/lpf_bsst` to `projects/<name>`; put the document in `source/`.
2. Have the AI read it into `source_topology.json` (see `extraction/extract_lpf_bsst.py` for the shape; every object needs page/section).
   Record unknowns as `unresolved_requirements`, stated control actions as `control_requirements`, modes as `operating_modes`.
3. Write `project_rules.yaml`: enable the rule types the document asks for, parameterise them, cite the section.
4. Optionally add `layout_hints.yaml` (sheet organisation). Without it every area becomes one sheet.
5. `pid run projects/<name>`. `tests/test_review_and_pipeline.py::test_the_workflow_is_reusable_for_another_specification` shows a complete second project.

New rule types are small methods on `Enricher` registered in `Enricher.handlers`.

## Agent skill

An agent can process a new specification by following `.claude/skills/pid-from-spec/SKILL.md` (with a runnable extraction template).
The extraction step is still done by the agent, not by `pid run`.

## Known limits (details in `reports/export_limitations.md`)

* **pyDEXPI 1.2.0 exports only equipment, nozzles and metadata to Proteus XML.** Piping and instrumentation are written by
  `proteus_ext.py`, which follows the structure pyDEXPI's *parser* reads; the file is re-loaded with pyDEXPI to prove it parses.
  pyDEXPI's loader also ignores custom attributes and segment-end node indices, so those are verified directly in the XML.
* The XML carries no graphics (no Proteus drawing/shape catalogue); symbols and routing exist only in the PDF. Future equipment
  carries `LifeCyclePhase="Future"` so a CAD template can render it dashed.
* Heat pumps, fermenters and the retained steam exchangers have no dedicated pyDEXPI class (`CustomEquipment` / `CustomHeatExchanger`).
* The layout is automatic and checked for overlaps, but it is a draft layout, not a drafting-office drawing.
* The reading of the specification contains interpretations (see `reports/assumptions.md`) and conflicts inside the document
  (`reports/unresolved_requirements.md`); they need an engineer's yes/no.
