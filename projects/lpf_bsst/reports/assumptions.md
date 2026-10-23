# Assumptions, interpretations and conventions

## Engineering basis stated by the specification

- Standard CAD/ISA 5.1 look and tag nomenclature (e.g. PI-101, XV-201). _(p.3 §5. Règles topologiques génératives)_
- Every pipe carries a Service attribute (e.g. Service="Steam 8 bar"). _(p.3 §5. Conventions graphiques et attributs DEXPI)_
- Future equipment (PAC 3A/3B) carries LifeCyclePhase="Future" (dashed rendering). _(p.3 §5. Conventions graphiques et attributs DEXPI)_

## Precedence and prerequisites

- **precedence** — Explicit project requirements take precedence over generic defaults.
- **prerequisites** — A rule fires only when its prerequisites are established in the topology.
- **reuse** — Existing components are reused; nothing is duplicated.
- **review** — Every addition stays pending_review until an engineering review approves it.
- **idempotence** — Re-applying enrichment never duplicates a satisfied requirement.
- **inline insertion** — Inline components are inserted by splitting the original line; service and properties are preserved.
- **branches** — Branches and bypasses are modelled with explicit manifolds (tees).
- **control loop** — A control loop is measurement -> controller -> final element. A transmitter alone never implies a controller.

## Interpretations made while reading the specification

These are in `source_topology.json` with `basis: interpreted`; the diagram draws them like any other fact, so each needs engineering confirmation.

| Objects | Where | Interpretation |
|---|---|---|
| 4 | p.1 · 1.1 Zone de Captage et Boucle Fermenteurs | Well water is the cooling medium of the emergency exchangers (§4: 'les échangeurs de secours refroidissent l'eau des fermenteurs'). |
| 1 | p.1 · 1.2 Zone de Production de Chaleur (PAC) et Stockage | 'RCUA (85°C / 105°C)' read as ONE tank covering both temperatures of the RCUA loop (see ur.tank_count). |
| 1 | p.1 · 1.2 Zone de Production de Chaleur (PAC) et Stockage | Placeholder battery limit; the RCUA network itself is not described. |
| 3 | p.1 · 1.2 Zone de Production de Chaleur (PAC) et Stockage | “PAC RCUA (2A / 2B) ... 85°C / 105°C” |
| 4 | p.1 · 1.3 Zone de Production de Vapeur (CMV) | Three stages of one line are read as a series compression train (stage n outlet feeds stage n+1 inlet). |
| 1 | p.1 · 1.3 Zone de Production de Vapeur (CMV) | Vapour from the flash tank is the suction of CMV stage 1. |
| 1 | p.1 · 1.3 Zone de Production de Vapeur (CMV) | “Alimentée par l'eau chaude à 90°C des PAC via un Flash Tank (70°C)” |
| 3 | p.2 · 2. Lignes principales et réseaux de distribution | Condenser outlets (90 °C) collected in the 90 °C departure tank. |
| 1 | p.2 · 2. Lignes principales et réseaux de distribution | Emergency exchangers placed in PARALLEL with the evaporators (see ur.ech_position). |
| 3 | p.2 · 2. Lignes principales et réseaux de distribution | PAC process condensers fed from the 70 °C return tank. |
| 1 | p.2 · 2. Lignes principales et réseaux de distribution | Pumps P-033..035 are the 'Pompage Secondaire (Boucle PAC)'; their position on the loop is not stated (see ur.loop_pump_position). |
| 1 | p.2 · 2. Lignes principales et réseaux de distribution | Return leg of the internal loop is implied by the 55/50 °C regime, not drawn in the text. |
| 5 | p.2 · 2. Lignes principales et réseaux de distribution | Return side of the 90/70 °C regime, collected in the 70 °C tank. |
| 7 | p.2 · 2. Lignes principales et réseaux de distribution | “Eau de refroidissement DN 600 (minimum) Aller 20°C / Retour 31°C PAC (Évaporateurs) <-> Fermenteurs CF1-8” |
| 4 | p.2 · 3. Consommateurs process et modifications | Users listed under BSST are supplied from the BSST Sud 4 bar network. |
| 3 | p.2 · 3. Consommateurs process et modifications | Users listed under LPF are supplied from the LPF 4 bar network. |
| 1 | p.2 · 3. Maintien en température (Cuves LPF) | Existing steam exchanger kept in parallel as backup for BACAN1. |
| 1 | p.2 · 3. Maintien en température (Cuves LPF) | Existing steam exchanger kept in parallel as backup for BACS04. |
| 1 | p.2 · 3. Maintien en température (Cuves LPF) | Existing steam exchanger kept in parallel as backup for BACS05. |
| 1 | p.2 · 3. Maintien en température (Cuves LPF) | One new plate exchanger per listed LPF tank (BACAN1). |
| 1 | p.2 · 3. Maintien en température (Cuves LPF) | One new plate exchanger per listed LPF tank (BACS04). |
| 1 | p.2 · 3. Maintien en température (Cuves LPF) | One new plate exchanger per listed LPF tank (BACS05). |
| 18 | p.2 · 3. Maintien en température (Cuves LPF) | Process side of the new and the retained exchanger in parallel; the circulation arrangement is not described. |
| 1 | p.3 · 5. Instrumentation des Collecteurs (Headers) | The PDF names a 105 °C hot-water header but not its destination; placeholder boundary. |

## Conventions chosen where the specification is silent

- **Tags** are proposals (`tag_status: proposed`), ISA 5.1 style, numbered per prefix from PT 101, TT 301, LT 401, PIC 101, XV 201, NRV 251, PCV 501. Real tags from the specification are never overwritten and untagged source equipment stays untagged.
- **Isolation valves use the `XV` prefix** because the specification's own example is “XV-201 pour vanne d'isolement”, even though ISA 5.1 would normally call a manual valve `HV`. The project example takes precedence over the generic convention.
- **Check valves use `NRV`**: ISA 5.1 defines no check-valve letter code; 'NRV' is a placeholder convention to be confirmed.
- **Loop numbers** are shared: the header PT, its PIC and the PCV of one loop carry the same number.
- **Valve technology** is never chosen: unspecified valves use the explicit generic class `CustomOperatedValve` with the type name “technology to be selected” (see unresolved requirement `ur.gen.valve_technology`).
- **Control loop**: only the boiler back-up loop (explicit 7.5 bar eff. setpoint) is instrumented as measurement → controller → final element. A transmitter alone never creates a controller; the two spill valves have no stated controlled variable or setpoint and stay open points.
- **Existing equipment** is included in the capacitive-equipment rule (drain, vent, level transmitter); each such proposal says to verify the already installed devices.
