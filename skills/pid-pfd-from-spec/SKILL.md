---
name: pid-pfd-from-spec
description: Turn an engineering specification / cahier des charges / design basis (PDF, Word export or text) into a draft P&ID and PFD - one A0 sheet each in ISO 10628 / ISA 5.1 style, DEXPI Proteus XML with graphics, stream table, equipment / line / valve / instrument lists and a decision register of holds. Use this skill whenever the user gives a process or utility specification and asks for a P&ID, PFD, process flow diagram, piping and instrumentation diagram, schéma de principe, line list, stream table or DEXPI file - even if they only say "make the drawing from this spec" or "dessine le P&ID".
---

# P&ID and PFD from a specification

You read the document and do the engineering reasoning; the bundled engine (`scripts/engine`, Python package
`pid_workflow`) does everything structural: rule-based completion, validation, layout, drawing, DEXPI export, lists.
The split matters: your judgement goes where judgement is needed (what the text says, what it means, what is
missing), and every drawing is reproducible and checkable.

Two principles run through everything, because a P&ID is used to build and operate a plant:
* **Never invent a value the document does not give** (design pressures, relief set points/sizing, fail positions,
  materials, sizes, ranges, equipment the text does not mention). A gap becomes an open point, shown as a hold.
* **Every fact is traceable**: page, section and a verbatim quote. Interpretations are marked as such, with a note.

## 0. Set up (once per environment)

```bash
SKILL=<directory of this SKILL.md>
python3 -c "import pydexpi, reportlab, pypdf, lxml, openpyxl, yaml, pydantic" 2>/dev/null \
  || pip install pydexpi reportlab pypdf lxml openpyxl pyyaml pydantic networkx
```
Every command below goes through the wrapper `bash "$SKILL/scripts/pid"`, which puts the bundled engine on the Python path
by itself (nothing to install or export; shells may be fresh each time). Work in the user's directory: projects are
created under `./projects/<name>/`. `pdftoppm` (poppler) is used to look at the drawings.

## 1. Create the project

```bash
bash "$SKILL/scripts/pid" new <name> "<path/to/spec.pdf>"     # lowercase name, e.g. ... new usine_nord cdc.pdf
```
It copies the document, splits it into `projects/<name>/source/pages/page_NNN.txt` and writes `project.yaml`,
`project_rules.yaml` (includes the good-practice rule pack), `review_plan.yaml`, `layout_hints.yaml` and
`extraction/extract_<name>.py`. A scanned PDF without a text layer must be OCR'd first (`pid check` says so).
Pages: PDF pages; a text file is split at form feeds or `--- page N ---` lines (otherwise it is one page) - quotes
cite these page numbers.

## 2. Read everything, then plan

Read **every page file completely** before writing code. Make yourself a list of: plant areas; every equipment item
(tag if given, type, duty data); parallel units and spares ("2 + 1", "3 × 50 %"); every stream (from, to, fluid,
stated T/P/flow/size); valves, instruments and control actions the text names (with set points if stated); operating
modes; battery limits; and everything missing, ambiguous or contradictory. Check the reading physically (do flows,
temperatures and duties balance? does every loop have a driver?) - contradictions you find become holds, not fixes.
`references/engineering-notes.md` lists the traps seen on real specifications; read it now.

## 3. Write the extraction with the kit

Edit `projects/<name>/extraction/extract_<name>.py`; the API is in `references/extraction-kit.md`. In short:
`s.src / s.interp / s.structural` (provenance with a verbatim quote checked against the page), `s.area`,
`s.equipment` (any pyDEXPI class, or `CustomEquipment` + `symbol=`), `s.bank` (parallel units with headers),
`s.manifold`, `s.line` / `s.run` (in flow direction, with stated `props`), `s.valve`, `s.boundary`, `s.control`,
`s.mode`, `s.unresolved`, `s.save()`. Run it until it writes `source_topology.json`:
`bash "$SKILL/scripts/pid" py projects/<name>/extraction/extract_<name>.py`.

## 4. Choose the rules (`project_rules.yaml`)

The included good-practice pack proposes the usual P&ID auxiliaries (pump strainer/isolation/check + PI, compressor
isolation/check, exchanger isolation, vessel drain/vent/LT, relief on pressure vessels, control-valve stations,
control loops from stated requirements, ISA tags, line numbers) - all as proposals pending review. Then:
override a pack rule (same `id`) wherever the document states the requirement, citing page + verbatim quote and
adapting the parameters to the text; switch off what contradicts the document or does not apply (with a comment
saying why); give the document's fluid codes for line numbering. Details: `references/rules.md`.

## 5. Plant areas and review plan

* `layout_hints.yaml`: `sheets` = plant areas (globs of equipment / manifold / battery-limit ids) and `onesheet.rows` =
  arrangement read like the process (sources left/top, users right/bottom). Without it the arrangement is searched,
  which is usually worse - write it.
* `review_plan.yaml`, after the first run: put **every** open point either in `holds` (a decision that can change the
  drawing: `title`, `drawn_as` = what the drawing shows today, `answer: null`) or in `datasheet` (missing values
  only), and write the general `notes`. "Every" includes the points the engine generates (`ur.gen.valve_technology`,
  `ur.gen.fail_position`, `ur.gen.instrument_ranges`, `ur.gen.relief`, `ur.gen.nozzles`): list their ids with
  `grep -o '"ur\.gen\.[a-z_]*"' projects/<name>/working_topology.json | sort -u`. Without a plan the engine sorts
  by category (`missing_value` → datasheet, everything else → hold) and `pid check` warns; your plan always takes
  precedence. The engineer then reviews a handful of decisions instead of every object.

## 6. Run, check, look - and iterate

```bash
bash "$SKILL/scripts/pid" check projects/<name>   # verbatim quotes, structure, triage - every problem with its fix
bash "$SKILL/scripts/pid" run projects/<name>     # P&ID + PFD + DEXPI + lists + reports  (--rebuild after changing the extraction)
bash "$SKILL/scripts/pid" pfd projects/<name>     # PFD only
```
Done means: extraction check 0 errors, validation PASS, round trip PASS, idempotent=True and **0 geometric problems
on both one-sheet drawings**. Then look at the drawings yourself - the checks cannot judge readability.
Whole sheet: `pdftoppm -r 45 -png -singlefile projects/<name>/output/pid_one_sheet_A0.pdf /tmp/pid`.
Zoom: an A0 page is 46.8 × 33.1 in, so at `-r 120` it is 5616 × 3972 px; crop with
`pdftoppm -r 120 -x X -y Y -W 1600 -H 1000 -singlefile … /tmp/zoom` (X, Y in pixels from the top-left, at that
resolution). Look at every plant area of both sheets; read the PFD stream table from `output/pfd_stream_table.xlsx`.
Fix crowding, long detours or confusing areas through `layout_hints.yaml` or the extraction, never with coordinates.

The PFD comes from the same extraction (no extra work): major equipment, parallel units drawn once, numbered streams,
stream table, equipment summary. It is only as good as the stream data you recorded - put stated temperatures,
pressures, flows and sizes on the lines (`props`) and duties on the equipment (`attrs`). See `references/outputs.md`.

## 7. Report to the user

Give the files (`output/pid_one_sheet_A0.pdf`, `output/pfd_one_sheet_A0.pdf`, `output/pid_draft.proteus.xml`,
`output/pfd_stream_table.xlsx`, `output/engineering_lists.xlsx`, `reports/decision_register.md`) and say plainly: what
was extracted, the interpretations you made, the holds, what the rules added (all pending review), the checks, and
the limits in `reports/export_limitations.md`. Never present the result as approved engineering.
