# Generated draft vs the reference drawing

The reference drawing (a Lesaffre Strasbourg PFD, “Décarbonation énergétique et Réduction des consommations d'eau de forage”)
was **not** used as a source of facts: the brief was to reassess the engineering interpretation directly from the 3-page PDF.
It was used as a visual target and as a cross-check. Where the two disagree, the model follows the PDF and the difference is
listed here and, where it changes engineering, in `reports/unresolved_requirements.md`.

## Agreement

| Topic | Reference drawing | This model |
|---|---|---|
| PAC 3A / 3B | dashed (future) | `lifecycle: future`, drawn dashed, exported with `LifeCyclePhase="Future"` |
| Internal loop PAC 2A/2B | labelled 55 °C / 50 °C | line `ln.pac2_internal`, 55/50 °C, DN “à définir” |
| Emergency exchanger position | between the 31 °C and the 20 °C buffer tank, in parallel with the PAC | placed in parallel with the evaporators (`ur.ech_position`) |
| Steam destinations | four VAP connectors: 8 bar BSST, 4 bar BSST Sud, 4 bar LPF, 1 bar BSST Nord | same four destinations (§2): two boundaries, two 4 bar network manifolds feeding the listed consumers |
| Control valves on the 4 bar / 1 bar lines | PCV symbols | spill PCVs 8→4 and 4→1 bar (+ boiler back-up PCV), each with a full manifold |
| Hot-water distribution 90 °C → 70 °C return | red lines through the buffer tanks | 90/70 °C loop through PAC 1A/1B, the 90 °C and 70 °C tanks, LPF tank exchangers, TGE coil, flash tank |
| Flash vessel and CMV | present | flash tank (70 °C) feeding a 3-stage CMV |

## Differences (and why)

| # | Reference drawing | PDF / this model | Treatment |
|---|---|---|---|
| 1 | six buffer tanks (31, 20, 105, 90, 85, 70 °C) | PDF lists five: TK-001 (20), TK-002 (31), 70, 90 and **one** “RCUA (85 °C / 105 °C)” | one RCUA tank; `ur.tank_count` |
| 2 | about seven compressor symbols for the CMV | “1 ligne … sur 3 étages” | three stages; staging in series is an interpretation (`ur.flash_tank`) |
| 3 | one “Echangeur Secours” symbol | three plate exchangers ECH-030..032 at 50 % each | three exchangers |
| 4 | pumps drawn as pairs; pumps in the hot-water loops | exactly P-030..P-035 are given | only those six; no circulation pumps invented for the hot-water loops or the TK-001 → fermenters leg (`ur.loop_pump_position`) |
| 5 | boundary connectors EC 001–003, 010, 014, 015, VAP 004–007, ERF 011, COND 016 with numbers | not in the PDF | not extracted; the PDF's own destinations are modelled instead; the RCUA battery limits are marked placeholder boundaries (`ur.rcua_limits`) |
| 6 | PAC 2A **and** 2B evaporators on the cooling water | §2 routes the 2A condenser into the 2B evaporator (55/50 °C), table gives both units a 31/20 °C cold regime | physical cascade: only the 2A evaporator is on the cooling loop; conflict recorded as `ur.cascade_2a_2b` |
| 7 | gas boiler absent | §4 describes a gas boiler back-up with a PCV at 7.5 bar eff. | boiler + PCV + PIC modelled, loop PT-104 → PIC-104 → PCV-104 |
| 8 | condensate return (“Taux de retour = 20 à 30 %”), demineralised/feed-water services | not in the PDF | not modelled |
| 9 | plate exchanger with pump near the CMV | not in the PDF | not modelled |
| 10 | “Bâche dégazeuse LPF” as a tank on the condensate line | PDF: new make-up water heater (12 → 80 °C) before the 44 m³ tank; steam supply “4 bar ou 1 bar (à définir)” | heater + 44 m³ degasser vessel; steam inlet left open (`ur.degasser_steam`) |

## What would bring the model closer to the reference

Answering these open points would, one by one, add what the reference shows: the circulation pumps (`ur.loop_pump_position`),
the 2A/2B cascade wiring (`ur.cascade_2a_2b`), the RCUA tank count (`ur.tank_count`) and the connector list of the plant
(`ur.rcua_limits`). Each is a change to `source_topology.json` (new extraction) followed by `pid run --rebuild`.
