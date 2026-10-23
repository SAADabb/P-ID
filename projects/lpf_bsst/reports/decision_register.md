# Decision register

Everything an engineer has to decide before this drawing can be issued: **14 holds** and **8 rule approvals**. Datasheet values (10 items) do not change the drawing.

## 1. Holds (marked H1, H2 … on the drawing)

Answer by setting `answer:` in `review_plan.yaml`, then `pid run`. The marker disappears; the answer stays here.

| Hold | Decision | Drawn today | Question | Affects |
|---|---|---|---|---|
| H1 | Emergency exchangers ECH-030..032 – parallel or series? | Parallel branch of the cooling-water loop, beside the heat-pump evaporators. | Confirm parallel arrangement and the well-water path in Normal mode. | eq.emerg_hx_a, eq.emerg_hx_b, eq.emerg_hx_c, mf.cw_s, mf.cw_m |
| H2 | PAC 2A/2B – physical cascade? | 2A condenser feeds the 2B evaporator through the 55/50 °C internal loop; only 2B delivers 85/105 °C to RCUA. | Confirm the 2A/2B cascade connections. | eq.hp_2a, eq.hp_2b, ln.pac2_internal |
| H3 | Circulation pumps of the fermenter leg and hot-water loops | Only P-033..035 (TK-002 outlet). No other pump drawn – the specification names none. | Where are the circulation pumps of the fermenter leg and of the hot-water loops? | eq.loop_pump_a, eq.loop_pump_b, eq.loop_pump_c, eq.tank_cold, eq.tank_70, eq.tank_90 … |
| H4 | RCUA buffer – one tank or one per temperature level? | One RCUA buffer tank (85/105 °C). | One RCUA tank or one per temperature level? | eq.tank_rcua |
| H5 | Spill valves 8→4 and 4→1 bar – control philosophy | Control valves with manifolds, no control loop (variable, setpoint and fail position not given). | Control philosophy of the overproduction cascade. | pc.pcv_spill_8_4, pc.pcv_spill_4_1, cr.spill_8_4, cr.spill_4_1 |
| H6 | Flash tank – liquid destination and CMV staging | Flash vapour → CMV stages 1-2-3 in series; 70 °C liquid outlet left open. | Flash-tank liquid destination and pressure; confirm series staging. | eq.flash_tank, eq.cmv_s1, eq.cmv_s2, eq.cmv_s3 |
| H7 | Air-preheating coil – 85 °C limit on a 90 °C header | One coil (TGE example) fed directly from the 90/70 °C header; no tempering arrangement. | How is the 85 °C inlet limit achieved, and how many coils are needed? | eq.bsst_tge_coil, ln.hw90 |
| H8 | Thermal degasser – 4 bar or 1 bar steam? | Steam inlet left unconnected. | Select 4 bar or 1 bar for the degasser. | eq.lpf_degasser |
| H9 | Make-up water heater (12→80 °C) – heating medium | Hot side left open. | Heating medium of the make-up heater. | eq.lpf_degasser_hx |
| H10 | LPF tank heating loops – pump and steam supply | Plate exchangers on the tank loops; retained steam exchangers on standby with open steam/condensate nozzles. | – | eq.lpf_shx_s04, eq.lpf_shx_an1, eq.lpf_shx_s05 |
| H11 | Ultimate mode – well-water feed to the fermenters | Only the post-fermenter discharge to DARSE is drawn. | – | mode.ultimate, mf.ferm_out |
| H12 | Hot-water networks – local steam back-up equipment | Not drawn (not described). | – | mode.emergency_hx |
| H13 | RCUA network battery limits | Placeholder battery-limit flags for the 105 °C supply and 85 °C return. | – | bc.rcua_out, bc.rcua_return |
| H14 | Valve technology of the generic valves | Generic valve symbol, DEXPI CustomOperatedValve 'technology to be selected'. | Select the valve technology for each valve function. | pc.gen.emerg_hx_a.hot_in_isolation, pc.gen.emerg_hx_b.hot_in_isolation, pc.gen.emerg_hx_c.hot_in_isolation, pc.gen.flash_tank.drain, pc.gen.flash_tank.vent, pc.gen.hp_1a.evap_in_isolation … |

## 2. Rule approvals (proposed additions, drawn in orange)

One decision per rule: `pid review projects/<p> --approve-rule <rule>` (or `--reject` single objects).

| Rule | Pending objects | Adds |
|---|---|---|
| `control_loop.from_requirement` | 4 | 2 × Signal, 1 × Instrument, 1 × ControlLoop |
| `control_valve.manifold` | 51 | 30 × ProcessLine, 21 × Component |
| `header.instrumentation` | 10 | 10 × Instrument |
| `lines.numbering` | 86 | 86 × line_number on a source object |
| `mode.isolation` | 18 | 12 × ProcessLine, 6 × Component |
| `pump.auxiliaries` | 48 | 30 × ProcessLine, 18 × Component |
| `tagging.isa` | 3 | 3 × tag on a source object |
| `vessel.auxiliaries` | 80 | 30 × nozzles on a source object, 20 × Component, 20 × ProcessLine, 10 × Instrument |

## 3. Data to complete on datasheets (not holds)

- **ur.hw_dn** – Hot-water process lines: only a range 'DN 200 à DN 350' is given; per-line diameters are not defined. Branch lines of the cooling-water loop carry only the 'DN 600 minimum' of the main lines.
- **ur.internal_loop** – Internal loop PAC 2A/2B: nominal diameter is 'À définir'; the 50 °C return leg is implied, not stated.
- **ur.boiler** – Gas boiler: capacity, fuel/feed-water/flue connections, PCV technology and failure position are not stated.
- **ur.tags** – Equipment tags are given only for P-030..035, ECH-030..032, TK-001/002, K3/MESSO/GEA and the LPF tanks. Heat pumps, 70/90/RCUA tanks, flash tank, CMV stages, boiler and the new exchangers have no tag.
- **ur.nozzles** – No nozzle numbers or nozzle sizes are given for any equipment (except DN50 on the TGE coil). Nozzle names are schematic.
- **ur.design_data** – No design pressures, relief devices/sizing, safety thresholds (other than 7.5 bar eff.), valve failure positions, material classes or instrument ranges are given. None are invented.
- **ur.future_hp** – PAC 3A/3B are future equipment with no capacity, regime or connection data. They are drawn dashed (LifeCyclePhase=Future) and left unconnected.
- **ur.gen.fail_position** – Failure position (fail open / close / retain) of the control valves is not specified and was not assumed.
- **ur.gen.instrument_ranges** – Measuring ranges and alarm/trip settings of the generated instruments are not specified and were not assumed.
- **ur.gen.nozzles** – Nozzles added for drain, vent and level tapping have no nozzle number and no size.
