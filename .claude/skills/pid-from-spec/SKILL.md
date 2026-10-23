---
name: pid-from-spec
description: Turn an engineering specification (PDF/text) into a draft P&ID with this repo's pipeline. Use when asked to process a new specification, extract a source topology, write project rules, or regenerate the P&ID/DEXPI outputs for a project under projects/.
---

# Draft P&ID from a specification

You (the AI) do **extraction and engineering reasoning**. Python does everything structural.
Never skip the checks at the end. Never invent values the document does not give.

## 0. Set up the project

```bash
cp -r projects/lpf_bsst projects/<name>          # then clean it:
rm -rf projects/<name>/{output,reports,working_topology.json,docs,source/*}
cp <spec.pdf> projects/<name>/source/
```
Edit `project.yaml` (name, source_document). Keep `generic_policy` / `rendering` paths.

## 1. Read the document completely, then extract

Read every page (`pdftotext -layout`, or the Read tool for PDFs; look at figures/tables too).
Write `projects/<name>/extraction/extract_<name>.py` starting from
`.claude/skills/pid-from-spec/templates/extract_template.py`. It emits `source_topology.json`.

Capture, each with page + section + a **verbatim quote**:

| Thing | Where it goes | Notes |
|---|---|---|
| Equipment | `equipment` | `model_class` must be in `validate.SUPPORTED_CLASSES`; real tag in `tag` (else `null`); nozzles with schematic `name` + `role`; `number`/`size` stay `null` unless stated |
| Valves/known inline parts | `components` (`kind: valve|check_valve|strainer`) | unknown technology → `technology: null`, `technology_status: unspecified_generic`, class `CustomOperatedValve` |
| Parallel banks / branches | `components` `kind: manifold` (`role` split/merge, `branches` n) | basis `structural`; ports `common`, `b1..bn` |
| Battery limits / off-page | `boundaries` (`direction` in/out) | placeholders must say so in the note |
| Process lines | `process_lines` | explicit `from`/`to` `{ref, port}`, mandatory `service`, supplied properties as `attributes` with provenance; `header: true` for main headers |
| Operating conditions | `properties` of lines / `attributes` of equipment | value + unit + provenance |
| Control requirements | `control_requirements` | `controller_required: true` **only** if the text states automatic control; give `measured_at_line`, `final_element`, `setpoint` only if stated |
| Operating modes | `operating_modes` | requirements with `action` (isolate/discharge/operate/note) and port targets |
| Everything missing/ambiguous/conflicting | `unresolved_requirements` | category `missing_value|ambiguity|conflict|selection|scope`, `affects`, a question |

### Rules for you

* **Explicit vs interpreted.** `basis: explicit` only for what the text states. Anything you had to infer to draw a connected
  graph is `interpreted` with a `note` saying what and why. Needed-for-structure items are `structural`.
* **Quotes are verbatim.** Table cells of one row may be joined with ` … `. `tests/test_provenance_quotes.py` checks this against the PDF.
  Page numbers must be the page holding the quote.
* **Never invent**: design pressures, relief sizing, safety thresholds, valve failure positions, material classes, nozzle sizes,
  instrument ranges, pumps/valves the text does not mention. Put the gap in `unresolved_requirements`.
* **Conflicts**: if two statements disagree, extract both faithfully, pick the physically consistent reading, mark it
  `interpreted`, and add a `conflict` unresolved requirement naming the alternative.
* **Reference drawings** (if supplied) are a cross-check, not a source. Record differences in `docs/reference_drawing_comparison.md`.
* **Identifiers**: `id` is schematic (`eq.well_pump_a`), never the tag. No coordinates anywhere (schema rejects them).
* Do not add instruments, controllers or generated valves to the source topology: enrichment does that.

## 2. Write the project rules

`projects/<name>/project_rules.yaml`: enable the rule types the document asks for (see `pid_workflow/enrich.py` handlers:
`pump_auxiliaries`, `mode_isolation`, `header_instrumentation`, `control_valve_manifold`, `vessel_auxiliaries`, `control_loop`,
`tagging`, `line_numbering`, `unresolved_summary`). Every rule cites `source: {page, section, quote}` and its parameters come from the text
(service names, which headers, which classes). If the document asks for something no rule type does, add a small method to
`Enricher` + handler entry + a test; do not special-case it elsewhere.

## 3. Plant areas and the one-sheet drawing

Optional `layout_hints.yaml` (see `projects/lpf_bsst/layout_hints.yaml`): which equipment/boundary/manifold ids (globs) form each
plant area (`sheets`). Aim for 10–25 macro objects per area. Without hints each topology area is one plant area.
The main deliverable is **one A0 sheet**: the areas become zones; `onesheet: rows:` fixes their arrangement so the sheet reads like
the process (sources left/top, users right/bottom). Without it the arrangement is searched automatically. Connections between
areas are routed as continuous pipes. The same areas also give the A3 review pack.

## 3b. Review plan (keeps the engineer's work to a few decisions)

`projects/<name>/review_plan.yaml` (see the LPF/BSST one) sorts every open point:
* `holds`: questions that can change the drawing. For each, write a short `title` and `drawn_as` — what the drawing shows today —
  so the reviewer only confirms or corrects. These become H1, H2 … markers and the hold list on the sheet.
* `datasheet`: missing values that do not change the drawing (sizes, ranges, tags, nozzles…).
* `notes`: the general notes printed on the sheet.
Every open point must land in one of the two lists (anything forgotten becomes a hold automatically). Proposed additions are
approved per rule (`pid review --approve-rule`), never object by object.

## 4. Run and check

```bash
python projects/<name>/extraction/extract_<name>.py     # writes source_topology.json
pid run projects/<name> --rebuild
pytest -q                                              # keep green
```
`pid run` must report validation PASS, round trip PASS (includes the DEXPI graphics checks), idempotent=True, 0 geometric problems
on the one-sheet P&ID and the review pack. Then:

1. Open `reports/validation.md` — fix errors in the extraction (unknown classes, port reuse, wrong flow direction, open ports without an unresolved requirement).
2. Look at `output/pid_one_sheet_A0.pdf` (`pdftoppm -r 45 -png` for the whole sheet, `-r 120 -x … -y … -W … -H …` to zoom) and
   **look at every area**: overlaps, unreadable labels, lines through equipment, long detours between areas. Fix with `layout_hints.yaml`
   (area membership, `onesheet.rows`) or the extraction — never with coordinates in the topology.
   `output/pid_one_sheet_from_dexpi.svg` is pyDEXPI's own rendering of the XML: it must show the same drawing.
3. Read `reports/unresolved_requirements.md` and `reports/assumptions.md`; each interpretation must be defensible from the text.
4. Never edit `source_topology.json` by hand after the run; change the extraction script and rebuild.
   `working_topology.json` is protected by a source hash; `pid run --rebuild` discards approvals.

## 5. Report to the user

State: what was extracted, the conflicts/ambiguities you resolved and how, the holds (from `reports/decision_register.md`), the rule
approvals pending, and the known export limits (pyDEXPI 1.2.0 exports piping/instrumentation/graphics only through `proteus_ext.py` and
`proteus_graphics.py`; XML not XSD-validated; see `reports/export_limitations.md`).
Do not claim engineering approval: everything generated is `pending_review`.

## Pitfalls seen on the first project

* Parallel units ("3 pumps at 50 %") need a split and a merge manifold, one branch per unit, in port order.
* A closed loop (tank → exchangers → tank) is fine; the layout draws the return around the loop.
* A table row that gives per-unit values for a *pair* (e.g. a cascade) may contradict the prose; check connections against the prose.
* Valves added by rules must not be reused by other rules for a different purpose (a pump's isolation valve is not a control valve's).
* Statements like "à définir" / "TBD" are unresolved requirements, not values.
