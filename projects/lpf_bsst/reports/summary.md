# Décarbonation énergétique LPF & BSST – draft P&ID

Drawing `PID-LPF-BSST-001` · revision A (draft for review) · **DRAFT — pending engineering review**

Source: `Cahier des Charges P&ID Consolidé.pdf` (3 pages). The AI extracted it into `source_topology.json` (read-only snapshot, sha256 `917fb248fccf…`); rules produced `working_topology.json`.

## Status

- Structural validation: **PASS** (0 errors, 0 warnings)
- Proteus XML round trip: **PASS** (12 checks)
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
| Enrichment idempotent | yes |

## What to review first

1. `reports/unresolved_requirements.md` — conflicts and ambiguities in the specification (start with the first section).
2. `reports/proposals.md` — everything the rules added, grouped by rule, all pending.
3. `reports/assumptions.md` — interpretations and conventions that need a yes/no.
4. `output/pid_review_draft.pdf` — the drawings; orange = proposed, red dots = open points.

## Files

| File | Purpose |
|---|---|
| `source_topology.json` | unchanged snapshot of the extracted source facts, with page/section provenance |
| `working_topology.json` | active graph: source + proposed additions (provenance: rule, triggers, explanation, status) |
| `output/pid_review_draft.pdf` | review set: cover, overview, one sheet per area, review tables |
| `output/pid_draft.proteus.xml` | DEXPI Proteus XML (pyDEXPI) |
| `reports/validation.md` · `roundtrip.md` · `enrichment.md` · `export_limitations.md` · `operating_modes.md` · `layout.md` | checks and logs |
