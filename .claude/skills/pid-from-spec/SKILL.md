---
name: pid-from-spec
description: Turn an engineering specification / cahier des charges (PDF or text) into a draft P&ID and PFD - one A0 sheet each, DEXPI Proteus XML with graphics, stream table, engineering lists and a decision register. Use whenever the user gives a specification and asks for a P&ID or a PFD (process flow diagram), or asks to process, extract, re-run or review a project under projects/.
---

# Draft P&ID from a specification

**You** read the document and do the engineering reasoning. **`pid` (Python)** does everything structural: rules,
validation, layout, drawing, DEXPI export, lists. Never invent a value the document does not give; record the gap instead.
Work through the steps in order and do not stop before step 6 is clean.

## 1. Create the project

```bash
pip install -e . 2>/dev/null || true          # once; otherwise use: python -m pid_workflow.cli ...
pid new <name> "<path/to/spec.pdf>"            # lowercase name, e.g. pid new usine_nord cdc.pdf
```
This copies the document, splits it into `projects/<name>/source/pages/page_NNN.txt`, and writes `project.yaml`,
`project_rules.yaml` (includes the good-practice rule pack), `review_plan.yaml`, `layout_hints.yaml` and
`extraction/extract_<name>.py`. A scanned PDF without text must be OCR'd first (`pid check` says so).

## 2. Read everything, then plan

Read **every page** file completely. Before writing code, list for yourself:
* plant areas / sections; every equipment item (tag if given, type, duty data); parallel units and spares ("2 + 1");
* every stream: where it comes from, where it goes, the fluid (service), stated sizes/temperatures/pressures;
* valves, instruments and control actions the text itself names (with setpoints if stated);
* operating modes; battery limits (what enters/leaves the scope);
* what is missing, ambiguous or contradictory.

## 3. Write the extraction (`extraction/extract_<name>.py`) with the kit

```python
q = s.src(page, "section title", "verbatim quote")                  # explicit fact; quote is checked against the page
i = s.interp(page, "section", note="what was inferred and why", quote="…")   # interpretation needed to draw it
t = s.structural(page, "section", note="why this tee/limit is needed", quote=q)  # structure only (header tees …)
s.area("ar.x", "Name", q)
s.equipment("eq.x", "Name", "<pyDEXPI class>", "ar.x", q, tag="P-101" or None, nozzles={"suction": "suction", "discharge": "discharge"},
            attrs={"design_volume_flow_rate": s.val(150, "m3/h", q)}, symbol=None, lifecycle="new|existing|modified|future")
s.bank("name", ["eq.p1", "eq.p2", "eq.p3"], inlet="eq.tank:out", outlet="mf.hdr:common", service="Fluid", src=q)  # parallel units
s.manifold("mf.hdr", "Supply header", "split|merge", n_branches, "ar.x", q)      # ports: common, b1..bn
s.line("eq.a:out", "eq.b:in", "Fluid", q, props={"nominal_diameter": s.val(250, None, q)}, header=False)  # flow direction!
s.run("Fluid", q, "eq.a:out", "pc.v1", "eq.b:in")                              # through inline valves (ports in/out)
s.valve("pc.v1", "Name", "isolation|control|check|…", "ar.x", q, kind="valve|check_valve|strainer|relief", tag=None)
s.boundary("bc.x", "Name", "in|out", "Fluid", "ar.x", q)                         # battery limit, port "port"
s.control("cr.x", "text", q, variable="temperature", measured_at_line="ln.012", final_element="pc.tv1",
          setpoint=s.val(22, "°C", q), controller_required=True)                # True ONLY if the text states automatic control
s.mode("mode.x", "Name", "text", q, [("isolate", ["pc.v1:in"], "text")])
s.unresolved("ur.x", "missing_value|ambiguity|conflict|selection|scope", "what is open", ["affected ids"], q, question="…")
s.save()
```
* **Classes**: any pyDEXPI class (`CentrifugalPump`, `Tank`, `PressureVessel`, `PlateHeatExchanger`, `WetCoolingTower`, `Compressor`,
  `ProcessColumn`, `Filter` …; list: `python -c "from pid_workflow.catalog import equipment_classes as e; print(sorted(e()))"`).
  No class fits → `CustomEquipment` with `symbol=` one of `heat_pump, box, pump, compressor, fan, hx, phx, tank, vessel, column, filter,
  boiler, heater, mixer, cooling_tower, air_cooler, turbine, motor`.
* **Nozzles**: only process connections (inlet/outlet/suction/discharge). Drains, vents, level taps and relief nozzles come from rules.
* **Quotes are verbatim** (copy from the page file; table cells may be joined with " … "). A wrong quote stops the script with the right page.
* **Never invent**: design pressures, relief sizing/set pressures, safety thresholds, fail positions, materials/piping classes, sizes, ranges,
  equipment or valves the text does not mention. Put each gap in `s.unresolved`.
* **Ambiguity**: draw the physically consistent reading as `interp(...)` and add an `ambiguity`/`conflict` open point naming the
  alternative. If no reading is defensible (e.g. "position to be confirmed"), leave the item unconnected with an open point.
* **Every line must make sense**: an outlet goes to an inlet, branches use manifolds (one line per port), loops close.

Run it: `python projects/<name>/extraction/extract_<name>.py` until it writes `source_topology.json`.

## 4. Project rules (`project_rules.yaml`)

The good-practice pack (`policies/rule_packs/process_good_practice.yaml`) already proposes: pump strainer/isolation/check + PI,
compressor isolation/check, exchanger isolation, vessel drain/vent/LT, relief on pressure vessels, control-valve stations,
control loops from stated requirements, ISA tags, line numbers. Then:
* For each requirement the document states (often a "Exigences P&ID" section), **override** the pack rule with the same `id`, cite
  `source: {page, section, quote}` and adapt `params` to the text (e.g. PI vs PT, which classes).
* **Switch off** what contradicts the document or does not apply: `- {id: control_valve.manifold, enabled: false}` (say why in a comment).
* Fluid codes for line numbers: `overrides: {line_numbering: {codes: [{prefix: "Eau glacée", code: "EG"}]}}` when the document gives them.
* Rule types: `equipment_template` (inline per nozzle role / open_ends / instruments, by DEXPI class incl. subclasses),
  `control_valve_manifold`, `header_instrumentation`, `mode_isolation`, `control_loop`, `tagging`, `line_numbering`, `unresolved_summary`.
  Something else needed → add a method to `Enricher` (pid_workflow/enrich.py) + a test.

## 5. Plant areas and review plan

* `layout_hints.yaml` (optional): `sheets` = plant areas (globs of equipment/manifold/boundary ids), `onesheet.rows` = arrangement
  reading like the process (sources left/top, users right/bottom). Without it each topology area is a zone and the arrangement is searched.
* `review_plan.yaml`: after the first `pid run`, put **every** open point either in `holds` (decision that can change the drawing:
  `title`, `drawn_as` = what the drawing shows today, `answer: null`) or in `datasheet` (missing values only). Add general `notes`.

## 6. Run, check, look

```bash
pid check projects/<name>        # quotes, structure, triage - each problem comes with its fix
pid run projects/<name>          # rules -> validation -> layout -> A0 sheet -> DEXPI (+graphics) -> lists -> reports
```
Done means: extraction check 0 errors, validation PASS, round trip PASS, idempotent=True, **0 geometric problems** on the one-sheet P&ID.
Then **look at the drawing**: `pdftoppm -r 45 -png output/pid_one_sheet_A0.pdf /tmp/s` (whole sheet) and zoom
(`-r 120 -x … -y … -W 1600 -H 1000`) on every area. Fix crowding or detours with `layout_hints.yaml` (areas, rows) or the extraction,
never with coordinates. Re-run after every change (`--rebuild` after changing the extraction).

## 6b. PFD (process flow diagram)

`pid run` also writes the PFD; `pid pfd projects/<name>` makes only the PFD. It uses the **same extraction**, without the P&ID rules:
major equipment and process streams, identical parallel units drawn once (`P-201/202/203 (3 units)`), control valves the document
names, numbered streams with a stream table (service, from, to, temperature, pressure, flow as stated; `*` = carried over from
equipment data such as pump design flow) and an equipment summary. A good PFD therefore needs: parallel units built with `s.bank`,
stream temperatures/pressures/flows recorded as line `props` when the document gives them, and duty data as equipment `attrs`.
Look at `output/pfd_one_sheet_A0.pdf` like the P&ID (0 geometric problems, readable stream table).

## 7. Report to the user

Outputs: `output/pid_one_sheet_A0.pdf` (the P&ID), `output/pid_draft.proteus.xml` (DEXPI with graphics),
`output/pfd_one_sheet_A0.pdf` + `output/pfd_stream_table.xlsx` + `output/pfd.proteus.xml` (the PFD),
`output/engineering_lists.xlsx`, `reports/decision_register.md`, `reports/summary.md`. Tell the user: what was extracted, the
interpretations you made, the holds, what the rules added (all pending review), and the limits in `reports/export_limitations.md`.
Never claim engineering approval.
