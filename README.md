# P-ID — draft P&IDs from engineering specifications

Give a coding agent (Claude Code or any agent that reads `AGENTS.md`) a specification / cahier des charges and it produces:

1. **the P&ID on one A0 sheet** — plant areas, ISO 10628 / ISA 5.1 symbols, line numbers, legend, notes, hold list, title block;
2. a **DEXPI Proteus XML** file (built with [pyDEXPI](https://github.com/process-intelligence-research/pyDEXPI)) carrying the model *and the
   same drawing* (Drawing, ShapeCatalogue, symbol positions, labels, routed pipe coordinates);
3. **the PFD on one A0 sheet** from the same extraction — major equipment, parallel units drawn once, numbered streams with a stream
   table and an equipment summary (`pid pfd`), also as DEXPI;
4. **engineering lists** (equipment, line, valve, instrument) and a **decision register** that reduces the review to a few decisions;
5. a **traceable topology**: every fact with page, section and verbatim quote; every addition with the rule that made it, pending review.

> **Draft, not for construction.** Values the specification does not give (design pressures, relief sizing, fail positions, materials,
> sizes, ranges) are never invented — they become open points.

## How to use it

Open a coding agent in this repository and say: *"here is my cahier des charges `<file.pdf>`, make the P&ID"*.
The agent follows `.claude/skills/pid-from-spec/SKILL.md`:

| Step | Who | Command / file |
|---|---|---|
| Set up the project, split the PDF into page texts | `pid` | `pid new <name> <spec.pdf>` |
| Read every page; record equipment, streams, valves, controls, modes, battery limits, open points — with verbatim quotes | **the agent** | `projects/<name>/extraction/extract_<name>.py` (extraction kit) |
| Choose the rules: the good-practice pack, overridden where the document states requirements | **the agent** | `projects/<name>/project_rules.yaml` |
| Check quotes, structure, triage — each problem with its fix | `pid` | `pid check projects/<name>` |
| Rules → validation → layout → A0 sheet → DEXPI (+graphics) → lists → reports | `pid` | `pid run projects/<name>` |
| Sort open points into holds (with what is drawn today) and datasheet data | **the agent** | `projects/<name>/review_plan.yaml` |

Without installing: `python -m pid_workflow.cli <command>`. Install: `pip install -e ".[dev]"`; tests: `python -m pytest -q`.
Project folders under `projects/` are local work and git-ignored.

### The engineer's part

`reports/decision_register.md` lists only what an engineer must decide:
* **holds** — questions that can change the drawing, each stating what is drawn today (answer them in `review_plan.yaml`);
* **rule approvals** — one decision per rule (`pid review projects/<name> --approve-rule pump.auxiliaries`), not per object;
* **datasheet data** — missing values that do not change the drawing.

## What it covers

* **Equipment**: every pyDEXPI equipment class (125), symbol chosen by class hierarchy; `CustomEquipment` + `symbol=` for the rest.
* **Valves**: generic, gate, globe, ball, butterfly, plug, check, strainer, relief device, control valve with actuator.
* **Rules** (`policies/rule_packs/process_good_practice.yaml`, all proposals): pump strainer / isolation / check + PI, compressor isolation /
  check, exchanger isolation, vessel drain / vent / LT, relief device on pressure vessels, control-valve stations, control loops only
  where the document states automatic control, ISA 5.1 tags, line numbers. Declarative `equipment_template` rules cover new cases.
* **Layout**: plant areas laid out as zones of one sheet, pipes between areas routed through (no off-page connectors), geometric QA.

## Architecture

```
pid_workflow/
  extract_kit.py, sourcedoc.py   extraction API for the agent; verbatim-quote checking against the document
  scaffold.py                    pid new / pid check
  schema.py, validate.py         topology model (no coordinates) and structural validation
  catalog.py                     pyDEXPI classes -> symbols
  policy.py, enrich.py           generic policy + rule packs + project rules; idempotent rule engine
  layout.py, onesheet.py         layered layout per area; zones, arrangement and A* pipe routing on one sheet
  graphics.py, render_onesheet.py  the drawing is recorded once as primitives -> A0 PDF
  export_dexpi.py, proteus_ext.py, proteus_graphics.py   pyDEXPI model -> Proteus XML with piping, instrumentation and graphics
  roundtrip.py                   re-reads the XML (lxml + pyDEXPI) and compares it with the topology and the drawing
  pfd.py                         PFD from the source topology: valves spliced out, banks collapsed, streams numbered, stream table
  decisions.py, lists.py, reports.py, review.py, pipeline.py, cli.py
policies/   generic.yaml (never-invent list, valve defaults, tagging, line numbering), rendering.yaml, rule_packs/
```

## Known limits

* The extraction is done by the agent (reading the document is an AI task); everything after it is deterministic.
* The XML is not schema-validated (Proteus XSD not available offline); it is reloaded with pyDEXPI and compared with the topology.
* 3-way valves, valve bodies with more than two ports and package internals are not modelled; the agent records them as interpretations.
* The layout is automatic and checked for overlaps; it is a draft for review, not a drafting-office drawing.
