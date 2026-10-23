# Operating modes

States are shown only where the specification states them. “—” means the specification does not say.

## Normal mode (`mode.normal`)

Cooling water passes the (inactive) emergency exchangers and then the PAC 1A/1B and 2A/2B; the CMV produces steam.

_Source: p.3 §4. Logiques de régulation et modes opératoires_

- **operate** — Emergency exchangers inactive; PAC 1A/1B/2A/2B and CMV in operation.

## Emergency-exchanger mode (PAC stopped) (`mode.emergency_hx`)

PAC are isolated; emergency exchangers cool the fermenter water; the gas boiler supplies 100 % of the steam; hot-water networks fall back to local steam.

_Source: p.3 §4. Logiques de régulation et modes opératoires_

- **isolate** — PAC isolated. (`eq.hp_1a:evap_in`, `eq.hp_1b:evap_in`, `eq.hp_2a:evap_in`)
- **operate** — Emergency exchangers cool the fermenter water. (`eq.emerg_hx_a:hot_in`, `eq.emerg_hx_b:hot_in`, `eq.emerg_hx_c:hot_in`)
- **operate** — Gas boiler supplies 100 % of the steam. (`eq.boiler:steam_out`)
- **note** — Hot-water networks switch to local steam back-up (equipment not described).

## Ultimate emergency mode (total shutdown) (`mode.ultimate`)

Isolation valves toward PAC and exchangers closed; post-fermenter well water is discharged directly to DARSE.

_Source: p.3 §4. Logiques de régulation et modes opératoires_

- **isolate** — Isolation valves toward PAC and emergency exchangers closed. (`eq.hp_1a:evap_in`, `eq.hp_1b:evap_in`, `eq.hp_2a:evap_in`, `eq.emerg_hx_a:hot_in`, `eq.emerg_hx_b:hot_in`, `eq.emerg_hx_c:hot_in`)
- **discharge** — Post-fermenter well water discharged directly to DARSE. (`mf.ferm_out:b2`)

## Gas boiler standby (`mode.boiler_standby`)

Boiler starts through the PCV when the 8 bar header drops below 7.5 bar eff.

_Source: p.3 §4. Logiques de régulation et modes opératoires_

- **operate** — PCV opens below 7.5 bar eff. on the 8 bar header. (`pc.pcv_boiler:in`)

## 8 bar overproduction management (`mode.overproduction`)

CMV minimum 5.8 t/h at 8 bar; the surplus is spilled by cascade 8 → 4 → 1 bar through PCVs.

_Source: p.3 §4. Logiques de régulation et modes opératoires_

- **operate** — Spill cascade 8 → 4 → 1 bar. (`pc.pcv_spill_8_4:in`, `pc.pcv_spill_4_1:in`)

## Isolation valves per mode

| Valve | Normal mode | Emergency-exchanger mode (PAC stopped) | Ultimate emergency mode (total shutdown) | Gas boiler standby | 8 bar overproduction management |
|---|---|---|---|---|---|
| XV-201 — Isolation valve – ECH-030 hot_in | — | — | closed | — | — |
| XV-202 — Isolation valve – ECH-031 hot_in | — | — | closed | — | — |
| XV-203 — Isolation valve – ECH-032 hot_in | — | — | closed | — | — |
| XV-206 — Isolation valve – PAC 1A – process heat pump evap_in | — | closed | closed | — | — |
| XV-207 — Isolation valve – PAC 1B – process heat pump evap_in | — | closed | closed | — | — |
| XV-208 — Isolation valve – PAC 2A – RCUA heat pump evap_in | — | closed | closed | — | — |
