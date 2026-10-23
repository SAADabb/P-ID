# P-ID — draft P&IDs from engineering specifications

A reusable workflow that turns a written engineering specification into

1. a **traceable topology** of the source facts (`source_topology.json`),
2. an **enriched topology** with clearly marked proposals (`working_topology.json`),
3. **the P&ID on one A0 sheet** — plant areas, ISO 10628 / ISA 5.1 symbols, line numbers, legend, notes, hold list, title block,
4. a **DEXPI Proteus XML** file built with [pyDEXPI](https://github.com/process-intelligence-research/pyDEXPI) that carries the model
   *and the same drawing* (Drawing, ShapeCatalogue, symbol positions, labels, routed pipe coordinates),
5. a **decision register** and **engineering lists** (equipment, line, valve, instrument lists) so the review is a handful of decisions,
6. **reports** on checks, assumptions, open points and export limitations, plus an A3 review pack per area.

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
| **Layout** — plant-area zones, one-sheet arrangement, pipe routing (never stored in the topology) | deterministic | computed |
| **Export** — pyDEXPI model + drawing → Proteus XML | deterministic | `output/pid_draft.proteus.xml` |
| **Review** — A0 P&ID, decision register, lists; round-trip check of model *and* graphics | deterministic | `output/pid_one_sheet_A0.pdf`, `reports/decision_register.md`, `output/engineering_lists.xlsx` |

The AI does the extraction and the engineering reasoning (which facts are explicit, which are interpretations, what is missing);
Python does everything structural.

## Quick start

```bash
pip install -e ".[dev]"            # pydexpi, pydantic, reportlab, lxml, networkx, pyyaml
pid run projects/lpf_bsst          # enrich → validate → lay out → draw → export (model + graphics) → verify → lists → reports
                                   # (set SOURCE_DATE_EPOCH for a byte-reproducible XML)
python -m pytest -q                # 55 tests, including a second, unrelated project
```

Outputs of the LPF/BSST project:

```
projects/lpf_bsst/
  source_topology.json             unchanged snapshot of what was read from the PDF (page + section on every object)
  working_topology.json            source + proposed additions (rule, triggers, explanation, status)
  output/pid_one_sheet_A0.pdf      THE P&ID: one A0 sheet
  output/pid_draft.proteus.xml     DEXPI Proteus XML: model + the same drawing as DEXPI graphics
  output/pid_one_sheet_from_dexpi.svg   pyDEXPI's own rendering of that XML (independent proof the graphics are in it)
  output/engineering_lists.xlsx    equipment / line / valve / instrument lists, holds, rule approvals, datasheet data
  reports/decision_register.md     the decisions the engineer has to make
  output/pid_review_draft.pdf      A3 review pack: one sheet per area + provenance tables
  reports/summary.md               start here
```

### Reading the drawing

* Eight **plant areas** (dashed frames) arranged like the process: water side on top (well water → cooling loop → heat pumps →
  hot water), steam side below, LPF tanks under the hot-water area that feeds them. Pipes between areas are drawn through —
  no off-page connectors.
* Black = from the specification. **Orange = proposed** by a project rule, waiting for approval. Dashed grey = future equipment.
* Red hexagons **H1 … H14 = holds**: decisions needed before issue, listed on the right with what the drawing shows today.
* Lines are coloured by service and carry a proposed **line number** (`CW-115`, `HS-101` … service code + sequence; DN only where the
  specification gives it). Valve and instrument tags on orange items are proposed ISA 5.1 tags.
* Right-hand column: legend, general notes, hold list, data to complete on datasheets, revision block, title block.

### Minimal engineering intervention

The review is reduced to what only an engineer can decide (`reports/decision_register.md`):

1. **14 holds** — each states what is drawn today; answer by setting `answer:` in `projects/lpf_bsst/review_plan.yaml`.
2. **8 rule approvals** — one decision per rule instead of 181 objects: `pid review projects/lpf_bsst --approve-rule pump.auxiliaries`.
3. **10 datasheet items** — values that do not change the drawing (sizes, ranges, nozzle data), collected for the datasheets.

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
  layout.py          layered layout of one plant area, orthogonal routing, instrument placement, geometric QA
  onesheet.py        areas → zones on one sheet: terminals on the facing side, row arrangement, A* pipe router with rip-up
  graphics.py        canvas recorder: the drawing is recorded once as primitives
  render_onesheet.py the A0 sheet (grid, areas, symbols, legend, notes, holds, title block) → PDF
  proteus_graphics.py  the same primitives → Proteus Drawing / ShapeCatalogue / positions / labels / centre lines; pyDEXPI check
  decisions.py       holds, rule approvals, datasheet items (review_plan.yaml) → decision register
  lists.py           equipment / line / valve / instrument lists (xlsx)
  render_pdf.py      A3 review pack: per-area sheets and tables
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
| `lines.numbering` | one proposed line number per logical line (`<service code>-<sequence>`); size and piping class are never invented |

Valves whose technology the source does not give use the explicitly marked generic class (`CustomOperatedValve`,
“technology to be selected”); the choice is listed in `ur.gen.valve_technology`, never made silently.

### Using it for another specification

1. Copy `projects/lpf_bsst` to `projects/<name>`; put the document in `source/`.
2. Have the AI read it into `source_topology.json` (see `extraction/extract_lpf_bsst.py` for the shape; every object needs page/section).
   Record unknowns as `unresolved_requirements`, stated control actions as `control_requirements`, modes as `operating_modes`.
3. Write `project_rules.yaml`: enable the rule types the document asks for, parameterise them, cite the section.
4. Optionally add `layout_hints.yaml` (plant areas and their arrangement on the sheet) and `review_plan.yaml`
   (holds with what is drawn today, datasheet items, notes). Without them every topology area is a plant area, the
   arrangement is searched, and every non-trivial open point is a hold.
5. `pid run projects/<name>`. `tests/test_review_and_pipeline.py::test_the_workflow_is_reusable_for_another_specification` shows a complete second project.

New rule types are small methods on `Enricher` registered in `Enricher.handlers`.

## Agent skill

An agent can process a new specification by following `.claude/skills/pid-from-spec/SKILL.md` (with a runnable extraction template).
The extraction step is still done by the agent, not by `pid run`.

## Known limits (details in `reports/export_limitations.md`)

* **pyDEXPI 1.2.0 exports only equipment, nozzles and metadata to Proteus XML.** Piping and instrumentation are written by
  `proteus_ext.py`, which follows the structure pyDEXPI's *parser* reads; the file is re-loaded with pyDEXPI to prove it parses.
  pyDEXPI's loader also ignores custom attributes and segment-end node indices, so those are verified directly in the XML.
* Graphics are written as Proteus primitives (PolyLine, Circle, Text); fills other than on circles are not representable, nozzles and
  the short pipes between header tees carry no graphics, and pyDEXPI does not read back the line-number labels on segments
  (they are in the file). Future equipment also carries `LifeCyclePhase="Future"`.
* Heat pumps, fermenters and the retained steam exchangers have no dedicated pyDEXPI class (`CustomEquipment` / `CustomHeatExchanger`).
* The layout is automatic and checked for overlaps; the A0 sheet is drawn at scale 0.84 of the designed symbol size (smallest text
  ≈ 2 mm). It is a draft for review, not a drafting-office drawing.
* The reading of the specification contains interpretations (see `reports/assumptions.md`) and conflicts inside the document
  (`reports/unresolved_requirements.md`); they need an engineer's yes/no.
