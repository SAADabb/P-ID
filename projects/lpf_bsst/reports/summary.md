# Décarbonation énergétique LPF & BSST – draft P&ID

Drawing `PID-LPF-BSST-001` · revision A (draft for review) · **DRAFT — pending engineering review**

Source: `Cahier des Charges P&ID Consolidé.pdf` (3 pages). The AI extracted it into `source_topology.json` (read-only snapshot, sha256 `917fb248fccf…`); rules produced `working_topology.json`.

## Status

- Structural validation: **PASS** (0 errors, 0 warnings)
- Proteus XML round trip: **PASS** (17 checks)
- Layout checks: **clean** (0 geometric problems on 8 sheets)

## The model

| Item | Count |
|---|---|
| Equipment | 45 |
| Process lines | 178 |
| Manifolds (tees) | 38 |
| Valves from the source / proposed | 3 / 56 |
| Instruments (proposed) | 21 |
| Control loops | 1 |
| Pending review | 181 |
| Open points | 24 |
| Decisions needed | 14 holds + 8 rule approvals (10 datasheet items do not change the drawing) |
| Enrichment idempotent | yes |

## What to review first

1. `output/pid_one_sheet_A0.pdf` — the P&ID on one A0 sheet; orange = proposed, red hexagons H1… = holds (listed on the sheet).
2. `reports/decision_register.md` — the only decisions needed: the holds (each says what is drawn today) and one approval per rule.
3. `output/engineering_lists.xlsx` — equipment, line, valve and instrument lists; holds; datasheet data.
4. `reports/unresolved_requirements.md`, `proposals.md`, `assumptions.md` — the full detail behind the register.

## Files

| File | Purpose |
|---|---|
| `source_topology.json` | unchanged snapshot of the extracted source facts, with page/section provenance |
| `working_topology.json` | active graph: source + proposed additions (provenance: rule, triggers, explanation, status) |
| `output/pid_one_sheet_A0.pdf` | the P&ID: one A0 sheet, plant areas, legend, notes, holds, title block |
| `output/pid_draft.proteus.xml` | DEXPI Proteus XML (pyDEXPI) with the same drawing as DEXPI graphics |
| `output/pid_one_sheet_from_dexpi.svg` | pyDEXPI's own rendering of the XML — independent proof that the graphics are in the DEXPI file |
| `output/engineering_lists.xlsx` | equipment list, line list, valve list, instrument index, holds, rule approvals, datasheet data |
| `output/pid_review_draft.pdf` | review pack: cover, one A3 sheet per area, review tables with provenance |
| `reports/validation.md` · `roundtrip.md` · `enrichment.md` · `export_limitations.md` · `operating_modes.md` · `layout.md` | checks and logs |
