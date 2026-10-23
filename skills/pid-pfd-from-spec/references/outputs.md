# Outputs, review and limits

## Files (`projects/<name>/`)

| file | content |
|---|---|
| `output/pid_one_sheet_A0.pdf` | the P&ID: plant areas, symbols, line numbers, legend, notes, holds, title block |
| `output/pid_draft.proteus.xml` | DEXPI Proteus XML: model + the same drawing (ShapeCatalogue, positions, labels, routed pipes) |
| `output/pid_one_sheet_from_dexpi.svg` | pyDEXPI's own rendering of the XML (proof the graphics are in the DEXPI file) |
| `output/pfd_one_sheet_A0.pdf` | the PFD: major equipment, parallel units once, numbered streams, stream table, equipment summary |
| `output/pfd_stream_table.xlsx`, `output/pfd.proteus.xml` | stream table + equipment summary; PFD as DEXPI |
| `output/engineering_lists.xlsx` | equipment, line, valve, instrument lists; holds; rule approvals; datasheet data |
| `output/pid_review_draft.pdf` | A3 review pack: one sheet per area + provenance tables |
| `reports/decision_register.md` | what the engineer must decide: holds, rule approvals, datasheet items |
| `reports/summary.md`, `validation.md`, `roundtrip.md`, `layout.md`, `pfd.md`, `export_limitations.md`, … | checks and logs |
| `source_topology.json` | the extraction (frozen; protected by a hash) |
| `working_topology.json` | extraction + rule proposals with provenance and review status |

## Review commands

```bash
pid review projects/<name> --list                         # pending proposals
pid review projects/<name> --approve-rule pump.auxiliaries
pid review projects/<name> --reject pc.gen.p101.suction_strainer   # removed, line restored, never re-proposed
pid run projects/<name>                                    # redraw
```
Holds are answered in `review_plan.yaml` (`answer:`); the marker disappears and the answer stays in the register.

## PFD conventions used

Source topology only (no P&ID rule additions); valves spliced out except control valves (which separate streams);
identical units collapsed; streams numbered depth-first from each inlet; stream table rows: service, from, to,
temperature, pressure, flow, size - only stated values (`≤/≥` limits, `*` = stated for the connected equipment,
`see n` = same stated value as stream n); stated control actions with a measurement drawn as their controller with the
set point in the notes. No mass or heat balance is computed.

## Known limits (say them to the user)

* Extraction is AI work; check the interpretations listed in the holds.
* Proteus XSD validation is not available offline; the XML is reloaded with pyDEXPI and compared with the topology.
* 3-way valves, multi-port valve bodies and package internals are not modelled.
* The PFD does not compute a mass/heat balance; every header segment is a stream (more streams than a hand-drawn PFD).
* Mode-dependent lines (emergency, stand-by) are not drawn dashed.
* Layout is automatic, checked for overlaps; it is a review draft, not a drafting-office drawing.
