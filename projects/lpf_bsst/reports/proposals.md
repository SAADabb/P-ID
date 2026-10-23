# Proposed additions pending review

Everything below was created by a project rule and is `pending_review`. Approve with `pid review <project> --approve-rule <rule>` or per id; reject with `--reject <id>`.

**181 generated objects are pending review** (0 approved).

## `control_loop.from_requirement` — 2 object(s)

| Tag (proposed) | Item | Technology | Triggered by | Status |
|---|---|---|---|---|
| `PIC-104` | Pressure indicating controller for cr.boiler_backup |  | cr.boiler_backup, in.h8.pt | pending_review |
| `—` | Pressure loop for cr.boiler_backup |  | cr.boiler_backup | pending_review |

## `control_valve.manifold` — 21 object(s)

| Tag (proposed) | Item | Technology | Triggered by | Status |
|---|---|---|---|---|
| `XV-223` | Bypass globe valve – Boiler back-up pressure control valve (PCV) | globe | pc.pcv_boiler | pending_review |
| `XV-224` | Downstream isolation valve – Boiler back-up pressure control valve (PCV) | generic (technology to be selected) | pc.pcv_boiler | pending_review |
| `XV-225` | Upstream isolation valve – Boiler back-up pressure control valve (PCV) | generic (technology to be selected) | pc.pcv_boiler | pending_review |
| `XV-226` | Purge valve – Boiler back-up pressure control valve (PCV) | generic (technology to be selected) | pc.pcv_boiler | pending_review |
| `XV-227` | Bypass globe valve – Overproduction spill valve 4 → 1 bar (PCV) | globe | pc.pcv_spill_4_1 | pending_review |
| `XV-228` | Downstream isolation valve – Overproduction spill valve 4 → 1 bar (PCV) | generic (technology to be selected) | pc.pcv_spill_4_1 | pending_review |
| `XV-229` | Upstream isolation valve – Overproduction spill valve 4 → 1 bar (PCV) | generic (technology to be selected) | pc.pcv_spill_4_1 | pending_review |
| `XV-230` | Purge valve – Overproduction spill valve 4 → 1 bar (PCV) | generic (technology to be selected) | pc.pcv_spill_4_1 | pending_review |
| `XV-231` | Bypass globe valve – Overproduction spill valve 8 → 4 bar (PCV) | globe | pc.pcv_spill_8_4 | pending_review |
| `XV-232` | Downstream isolation valve – Overproduction spill valve 8 → 4 bar (PCV) | generic (technology to be selected) | pc.pcv_spill_8_4 | pending_review |
| `XV-233` | Upstream isolation valve – Overproduction spill valve 8 → 4 bar (PCV) | generic (technology to be selected) | pc.pcv_spill_8_4 | pending_review |
| `XV-234` | Purge valve – Overproduction spill valve 8 → 4 bar (PCV) | generic (technology to be selected) | pc.pcv_spill_8_4 | pending_review |
| `—` | Bypass merge – Boiler back-up pressure control valve (PCV) | PipeTee | pc.pcv_boiler | pending_review |
| `—` | Bypass split – Boiler back-up pressure control valve (PCV) | PipeTee | pc.pcv_boiler | pending_review |
| `—` | Purge tee – Boiler back-up pressure control valve (PCV) | PipeTee | pc.pcv_boiler | pending_review |
| `—` | Bypass merge – Overproduction spill valve 4 → 1 bar (PCV) | PipeTee | pc.pcv_spill_4_1 | pending_review |
| `—` | Bypass split – Overproduction spill valve 4 → 1 bar (PCV) | PipeTee | pc.pcv_spill_4_1 | pending_review |
| `—` | Purge tee – Overproduction spill valve 4 → 1 bar (PCV) | PipeTee | pc.pcv_spill_4_1 | pending_review |
| `—` | Bypass merge – Overproduction spill valve 8 → 4 bar (PCV) | PipeTee | pc.pcv_spill_8_4 | pending_review |
| `—` | Bypass split – Overproduction spill valve 8 → 4 bar (PCV) | PipeTee | pc.pcv_spill_8_4 | pending_review |
| `—` | Purge tee – Overproduction spill valve 8 → 4 bar (PCV) | PipeTee | pc.pcv_spill_8_4 | pending_review |

## `header.instrumentation` — 10 object(s)

| Tag (proposed) | Item | Technology | Triggered by | Status |
|---|---|---|---|---|
| `PT-101` | Pressure transmitter – Steam 1 bar header |  | ln.h1 | pending_review |
| `PT-102` | Pressure transmitter – Hot water RCUA 85/105 header |  | ln.h105 | pending_review |
| `PT-103` | Pressure transmitter – Steam 4 bar header |  | ln.h4 | pending_review |
| `PT-104` | Pressure transmitter – Steam 8 bar header |  | ln.h8 | pending_review |
| `PT-105` | Pressure transmitter – Hot water 90/70 header |  | ln.hw90 | pending_review |
| `TT-301` | Temperature transmitter – Steam 1 bar header |  | ln.h1 | pending_review |
| `TT-302` | Temperature transmitter – Hot water RCUA 85/105 header |  | ln.h105 | pending_review |
| `TT-303` | Temperature transmitter – Steam 4 bar header |  | ln.h4 | pending_review |
| `TT-304` | Temperature transmitter – Steam 8 bar header |  | ln.h8 | pending_review |
| `TT-305` | Temperature transmitter – Hot water 90/70 header |  | ln.hw90 | pending_review |

## `mode.isolation` — 6 object(s)

| Tag (proposed) | Item | Technology | Triggered by | Status |
|---|---|---|---|---|
| `XV-201` | Isolation valve – ECH-030 hot_in | generic (technology to be selected) | eq.emerg_hx_a, mode.ultimate | pending_review |
| `XV-202` | Isolation valve – ECH-031 hot_in | generic (technology to be selected) | eq.emerg_hx_b, mode.ultimate | pending_review |
| `XV-203` | Isolation valve – ECH-032 hot_in | generic (technology to be selected) | eq.emerg_hx_c, mode.ultimate | pending_review |
| `XV-206` | Isolation valve – PAC 1A – process heat pump evap_in | generic (technology to be selected) | eq.hp_1a, mode.emergency_hx, mode.ultimate | pending_review |
| `XV-207` | Isolation valve – PAC 1B – process heat pump evap_in | generic (technology to be selected) | eq.hp_1b, mode.emergency_hx, mode.ultimate | pending_review |
| `XV-208` | Isolation valve – PAC 2A – RCUA heat pump evap_in | generic (technology to be selected) | eq.hp_2a, mode.emergency_hx, mode.ultimate | pending_review |

## `pump.auxiliaries` — 18 object(s)

| Tag (proposed) | Item | Technology | Triggered by | Status |
|---|---|---|---|---|
| `NRV-251` | Check valve – P-033 discharge | check | eq.loop_pump_a | pending_review |
| `NRV-252` | Check valve – P-034 discharge | check | eq.loop_pump_b | pending_review |
| `NRV-253` | Check valve – P-035 discharge | check | eq.loop_pump_c | pending_review |
| `NRV-254` | Check valve – P-030 discharge | check | eq.well_pump_a | pending_review |
| `NRV-255` | Check valve – P-031 discharge | check | eq.well_pump_b | pending_review |
| `NRV-256` | Check valve – P-032 discharge | check | eq.well_pump_c | pending_review |
| `XV-209` | Discharge isolation valve – P-033 | generic (technology to be selected) | eq.loop_pump_a | pending_review |
| `XV-210` | Suction isolation valve – P-033 | generic (technology to be selected) | eq.loop_pump_a | pending_review |
| `XV-211` | Discharge isolation valve – P-034 | generic (technology to be selected) | eq.loop_pump_b | pending_review |
| `XV-212` | Suction isolation valve – P-034 | generic (technology to be selected) | eq.loop_pump_b | pending_review |
| `XV-213` | Discharge isolation valve – P-035 | generic (technology to be selected) | eq.loop_pump_c | pending_review |
| `XV-214` | Suction isolation valve – P-035 | generic (technology to be selected) | eq.loop_pump_c | pending_review |
| `XV-245` | Discharge isolation valve – P-030 | generic (technology to be selected) | eq.well_pump_a | pending_review |
| `XV-246` | Suction isolation valve – P-030 | generic (technology to be selected) | eq.well_pump_a | pending_review |
| `XV-247` | Discharge isolation valve – P-031 | generic (technology to be selected) | eq.well_pump_b | pending_review |
| `XV-248` | Suction isolation valve – P-031 | generic (technology to be selected) | eq.well_pump_b | pending_review |
| `XV-249` | Discharge isolation valve – P-032 | generic (technology to be selected) | eq.well_pump_c | pending_review |
| `XV-250` | Suction isolation valve – P-032 | generic (technology to be selected) | eq.well_pump_c | pending_review |

## `vessel.auxiliaries` — 30 object(s)

| Tag (proposed) | Item | Technology | Triggered by | Status |
|---|---|---|---|---|
| `LT-401` | Level transmitter – Flash tank (70 °C) |  | eq.flash_tank | pending_review |
| `LT-402` | Level transmitter – LPF thermal degasser with 44 m³ tank |  | eq.lpf_degasser | pending_review |
| `LT-403` | Level transmitter – BACAN1 |  | eq.lpf_tank_an1 | pending_review |
| `LT-404` | Level transmitter – BACS04 |  | eq.lpf_tank_s04 | pending_review |
| `LT-405` | Level transmitter – BACS05 |  | eq.lpf_tank_s05 | pending_review |
| `LT-406` | Level transmitter – Buffer tank – PAC return 70 °C |  | eq.tank_70 | pending_review |
| `LT-407` | Level transmitter – Buffer tank – PAC process supply 90 °C |  | eq.tank_90 | pending_review |
| `LT-408` | Level transmitter – TK-001 |  | eq.tank_cold | pending_review |
| `LT-409` | Level transmitter – Buffer tank – RCUA 85/105 °C |  | eq.tank_rcua | pending_review |
| `LT-410` | Level transmitter – TK-002 |  | eq.tank_warm | pending_review |
| `XV-204` | Drain valve – Flash tank (70 °C) | generic (technology to be selected) | eq.flash_tank | pending_review |
| `XV-205` | Vent valve – Flash tank (70 °C) | generic (technology to be selected) | eq.flash_tank | pending_review |
| `XV-215` | Drain valve – LPF thermal degasser with 44 m³ tank | generic (technology to be selected) | eq.lpf_degasser | pending_review |
| `XV-216` | Vent valve – LPF thermal degasser with 44 m³ tank | generic (technology to be selected) | eq.lpf_degasser | pending_review |
| `XV-217` | Drain valve – BACAN1 | generic (technology to be selected) | eq.lpf_tank_an1 | pending_review |
| `XV-218` | Vent valve – BACAN1 | generic (technology to be selected) | eq.lpf_tank_an1 | pending_review |
| `XV-219` | Drain valve – BACS04 | generic (technology to be selected) | eq.lpf_tank_s04 | pending_review |
| `XV-220` | Vent valve – BACS04 | generic (technology to be selected) | eq.lpf_tank_s04 | pending_review |
| `XV-221` | Drain valve – BACS05 | generic (technology to be selected) | eq.lpf_tank_s05 | pending_review |
| `XV-222` | Vent valve – BACS05 | generic (technology to be selected) | eq.lpf_tank_s05 | pending_review |
| `XV-235` | Drain valve – Buffer tank – PAC return 70 °C | generic (technology to be selected) | eq.tank_70 | pending_review |
| `XV-236` | Vent valve – Buffer tank – PAC return 70 °C | generic (technology to be selected) | eq.tank_70 | pending_review |
| `XV-237` | Drain valve – Buffer tank – PAC process supply 90 °C | generic (technology to be selected) | eq.tank_90 | pending_review |
| `XV-238` | Vent valve – Buffer tank – PAC process supply 90 °C | generic (technology to be selected) | eq.tank_90 | pending_review |
| `XV-239` | Drain valve – TK-001 | generic (technology to be selected) | eq.tank_cold | pending_review |
| `XV-240` | Vent valve – TK-001 | generic (technology to be selected) | eq.tank_cold | pending_review |
| `XV-241` | Drain valve – Buffer tank – RCUA 85/105 °C | generic (technology to be selected) | eq.tank_rcua | pending_review |
| `XV-242` | Vent valve – Buffer tank – RCUA 85/105 °C | generic (technology to be selected) | eq.tank_rcua | pending_review |
| `XV-243` | Drain valve – TK-002 | generic (technology to be selected) | eq.tank_warm | pending_review |
| `XV-244` | Vent valve – TK-002 | generic (technology to be selected) | eq.tank_warm | pending_review |

## Source lines split to insert components

39 source lines were split; every child line keeps its service and properties (`split_from` points to the source line).

## Changes to source objects (source value preserved)

| Object | Field | Source value | Proposed | Rule |
|---|---|---|---|---|
| `eq.tank_cold` | nozzles | ['inlet', 'outlet'] | ['inlet', 'outlet', 'drain'] | `vessel.auxiliaries` |
| `eq.tank_cold` | nozzles | ['inlet', 'outlet', 'drain'] | ['inlet', 'outlet', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.tank_cold` | nozzles | ['inlet', 'outlet', 'drain', 'vent'] | ['inlet', 'outlet', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.tank_warm` | nozzles | ['inlet', 'outlet'] | ['inlet', 'outlet', 'drain'] | `vessel.auxiliaries` |
| `eq.tank_warm` | nozzles | ['inlet', 'outlet', 'drain'] | ['inlet', 'outlet', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.tank_warm` | nozzles | ['inlet', 'outlet', 'drain', 'vent'] | ['inlet', 'outlet', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.tank_70` | nozzles | ['inlet', 'outlet'] | ['inlet', 'outlet', 'drain'] | `vessel.auxiliaries` |
| `eq.tank_70` | nozzles | ['inlet', 'outlet', 'drain'] | ['inlet', 'outlet', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.tank_70` | nozzles | ['inlet', 'outlet', 'drain', 'vent'] | ['inlet', 'outlet', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.tank_90` | nozzles | ['inlet', 'outlet'] | ['inlet', 'outlet', 'drain'] | `vessel.auxiliaries` |
| `eq.tank_90` | nozzles | ['inlet', 'outlet', 'drain'] | ['inlet', 'outlet', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.tank_90` | nozzles | ['inlet', 'outlet', 'drain', 'vent'] | ['inlet', 'outlet', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.tank_rcua` | nozzles | ['inlet', 'outlet'] | ['inlet', 'outlet', 'drain'] | `vessel.auxiliaries` |
| `eq.tank_rcua` | nozzles | ['inlet', 'outlet', 'drain'] | ['inlet', 'outlet', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.tank_rcua` | nozzles | ['inlet', 'outlet', 'drain', 'vent'] | ['inlet', 'outlet', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.flash_tank` | nozzles | ['hot_water_in', 'steam_out', 'liquid_out'] | ['hot_water_in', 'steam_out', 'liquid_out', 'drain'] | `vessel.auxiliaries` |
| `eq.flash_tank` | nozzles | ['hot_water_in', 'steam_out', 'liquid_out', 'drain'] | ['hot_water_in', 'steam_out', 'liquid_out', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.flash_tank` | nozzles | ['hot_water_in', 'steam_out', 'liquid_out', 'drain', 'vent'] | ['hot_water_in', 'steam_out', 'liquid_out', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.lpf_tank_s04` | nozzles | ['proc_out', 'proc_in'] | ['proc_out', 'proc_in', 'drain'] | `vessel.auxiliaries` |
| `eq.lpf_tank_s04` | nozzles | ['proc_out', 'proc_in', 'drain'] | ['proc_out', 'proc_in', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.lpf_tank_s04` | nozzles | ['proc_out', 'proc_in', 'drain', 'vent'] | ['proc_out', 'proc_in', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.lpf_tank_an1` | nozzles | ['proc_out', 'proc_in'] | ['proc_out', 'proc_in', 'drain'] | `vessel.auxiliaries` |
| `eq.lpf_tank_an1` | nozzles | ['proc_out', 'proc_in', 'drain'] | ['proc_out', 'proc_in', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.lpf_tank_an1` | nozzles | ['proc_out', 'proc_in', 'drain', 'vent'] | ['proc_out', 'proc_in', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.lpf_tank_s05` | nozzles | ['proc_out', 'proc_in'] | ['proc_out', 'proc_in', 'drain'] | `vessel.auxiliaries` |
| `eq.lpf_tank_s05` | nozzles | ['proc_out', 'proc_in', 'drain'] | ['proc_out', 'proc_in', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.lpf_tank_s05` | nozzles | ['proc_out', 'proc_in', 'drain', 'vent'] | ['proc_out', 'proc_in', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `eq.lpf_degasser` | nozzles | ['water_in', 'steam_in'] | ['water_in', 'steam_in', 'drain'] | `vessel.auxiliaries` |
| `eq.lpf_degasser` | nozzles | ['water_in', 'steam_in', 'drain'] | ['water_in', 'steam_in', 'drain', 'vent'] | `vessel.auxiliaries` |
| `eq.lpf_degasser` | nozzles | ['water_in', 'steam_in', 'drain', 'vent'] | ['water_in', 'steam_in', 'drain', 'vent', 'level_tap'] | `vessel.auxiliaries` |
| `pc.pcv_boiler` | tag | None | PCV-104 | `tagging.isa` |
| `pc.pcv_spill_4_1` | tag | None | PCV-501 | `tagging.isa` |
| `pc.pcv_spill_8_4` | tag | None | PCV-502 | `tagging.isa` |
