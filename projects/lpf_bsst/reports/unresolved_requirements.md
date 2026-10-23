# Unresolved requirements

Values, selections and decisions the specification does not give. They were **preserved, not assumed**. (Design pressures, relief sizing, safety thresholds, valve failure positions, material classes, nozzle sizes and instrument ranges are never invented.)

**24 open point(s).**

## Conflicts inside the specification

### 1. `ur.cascade_2a_2b`

PAC 2A/2B: the table gives both units a 31/20 °C cold regime and 85/105 °C hot regime, but §2 routes the 2A condenser outlet (55 °C) into the 2B evaporator inlet. Modelled as a physical cascade: 2A evaporator on the cooling loop; 2A condenser ⇄ 2B evaporator via the 55/50 °C internal loop; only 2B condenser on the 85/105 °C RCUA loop. The 2B evaporator therefore has no cooling-loop connection, contrary to its table row.

- **Source:** p.2 §2. Lignes principales et réseaux de distribution
- **Affects:** `eq.hp_2a`, `eq.hp_2b`, `ln.pac2_internal`
- **Question:** Confirm the 2A/2B cascade connections.
- **Needed for:** PAC 2A/2B nozzle connections

### 2. `ur.tge_coil`

Air-preheating coil: water inlet is limited to 85 °C (sanitary safety) while the process hot-water header is at 90 °C. No tempering/mixing arrangement is specified, so none is added. Only one example coil (TGE) is modelled; the number of coils per tower is not stated.

- **Source:** p.2 §3. Préchauffage Air Process (BSST) – Exemple Tour TGE — “Instancier de nouvelles batteries à eau chaude en amont des ventilateurs. Paramètres d'ingénierie : Entrée eau limitée à 85°C (sécurité sanitaire). Sortie eau 65°C. Débit d'eau: 20 769 l/h. Air process (40 000 m3/h) chauffé de -15°C à 20°C. Raccordements DN50.”
- **Affects:** `eq.bsst_tge_coil`, `ln.hw90`
- **Question:** How is the 85 °C inlet limit achieved, and how many coils are needed?

## Ambiguities (modelled one way, to be confirmed)

### 3. `ur.ech_position`

Position of the emergency exchangers (ECH-030..032) on the cooling loop is ambiguous. §4 'Mode Normal' reads like a series path (through the exchangers, then to the PAC); §4 'Secours Échangeurs' (PAC isolated, exchangers cooling) and 'Secours Ultime' (valves closed toward PAC *and* exchangers) need them as a separate parallel branch. Modelled in PARALLEL with the evaporators.

- **Source:** p.3 §4. Logiques de régulation et modes opératoires
- **Affects:** `eq.emerg_hx_a`, `eq.emerg_hx_b`, `eq.emerg_hx_c`, `mf.cw_s`, `mf.cw_m`
- **Question:** Confirm parallel arrangement and the well-water path in Normal mode.
- **Needed for:** cooling-loop topology

### 4. `ur.loop_pump_position`

Pumps P-033..035 are called 'Pompage Secondaire (Boucle PAC)'; no circulation driver is stated for the TK-001 → fermenters leg or for the hot-water loops (PAC condensers, 90 °C and RCUA distribution). Pumps were not invented; P-033..035 sit on the TK-002 outlet feeding the PAC/exchanger branches.

- **Source:** p.1 §1.1 Zone de Captage et Boucle Fermenteurs
- **Affects:** `eq.loop_pump_a`, `eq.loop_pump_b`, `eq.loop_pump_c`, `eq.tank_cold`, `eq.tank_70`, `eq.tank_90`, `eq.tank_rcua`
- **Question:** Where are the circulation pumps of the fermenter leg and of the hot-water loops?
- **Needed for:** pump auxiliaries, loop hydraulics

### 5. `ur.tank_count`

'RCUA (85°C / 105°C)' is read as a single buffer tank. The PDF lists five buffer tanks (TK-001, TK-002, 70 °C, 90 °C, RCUA).

- **Source:** p.1 §1.2 Zone de Production de Chaleur (PAC) et Stockage — “Bâches Tampon (Nodes de stockage) : TK-001 (Eau froide 20°C), TK-002 (Eau chaude retour 31°C), Retour PAC (70°C), Départ PAC Process (90°C), et RCUA (85°C / 105°C)”
- **Affects:** `eq.tank_rcua`
- **Question:** One RCUA tank or one per temperature level?

## Open selections

### 6. `ur.degasser_steam`

Degasser steam supply: '4 bar ou 1 bar eff. (à définir)'. The steam inlet is left unconnected until chosen.

- **Source:** p.2 §3. Consommateurs process et modifications — “Alimentation en 4 bar ou 1 bar eff. (à définir)”
- **Affects:** `eq.lpf_degasser`
- **Question:** Select 4 bar or 1 bar for the degasser.

### 7. `ur.gen.valve_technology`

Valve technology is not specified for these valves. They use the explicitly identified generic DEXPI representation (CustomOperatedValve, 'technology to be selected'); no specific valve type was chosen.

- **Source:** rule `unresolved.generated`
- **Affects:** `pc.gen.emerg_hx_a.hot_in_isolation`, `pc.gen.emerg_hx_b.hot_in_isolation`, `pc.gen.emerg_hx_c.hot_in_isolation`, `pc.gen.flash_tank.drain`, `pc.gen.flash_tank.vent`, `pc.gen.hp_1a.evap_in_isolation`, `pc.gen.hp_1b.evap_in_isolation`, `pc.gen.hp_2a.evap_in_isolation` … (+42)
- **Question:** Select the valve technology for each valve function.
- **Needed for:** valve selection

## Missing values

### 8. `ur.internal_loop`

Internal loop PAC 2A/2B: nominal diameter is 'À définir'; the 50 °C return leg is implied, not stated.

- **Source:** p.2 §2. Lignes principales et réseaux de distribution — “À définir”
- **Affects:** `ln.pac2_internal`
- **Question:** DN of the internal loop and confirmation of its return leg.

### 9. `ur.hw_dn`

Hot-water process lines: only a range 'DN 200 à DN 350' is given; per-line diameters are not defined. Branch lines of the cooling-water loop carry only the 'DN 600 minimum' of the main lines.

- **Source:** p.2 §2. Lignes principales et réseaux de distribution — “Eau Chaude Process DN 200 à DN 350 Aller 90°C / Retour 70°C PAC (Condenseurs) -> Cuves / Échangeurs air”
- **Affects:** `ln.hw90`
- **Question:** Line-by-line DN for hot-water and cooling-water branches.

### 10. `ur.degasser_hx_medium`

The heating medium and connection of the new make-up water heater (12 → 80 °C) are not stated; its hot side is left open.

- **Source:** p.2 §3. Dégazeur Thermique LPF — “Instancier un nouvel échangeur sur la ligne d'eau d'appoint (Eau Traitée) réchauffant le fluide de 12°C à 80°C avant la bâche de 44 m3”
- **Affects:** `eq.lpf_degasser_hx`
- **Question:** Heating medium of the make-up heater.

### 11. `ur.lpf_tank_loops`

LPF tank heating loops: the circulation pump, fluid and steam supply of the retained steam exchangers are not described; their steam/condensate nozzles are left open.

- **Source:** p.2 §3. Maintien en température (Cuves LPF) — “Les cuves sont équipées de nouveaux échangeurs à plaques à eau chaude. Les anciens échangeurs vapeur sont conservés et montés en parallèle pour un usage de secours”
- **Affects:** `eq.lpf_shx_s04`, `eq.lpf_shx_an1`, `eq.lpf_shx_s05`

### 12. `ur.flash_tank`

Flash tank: operating pressure and the destination of the 70 °C liquid are not stated; the liquid outlet is left open. The flash-vapour → CMV stage 1 and the inter-stage connections are INTERPRETED from '1 ligne ... sur 3 étages'.

- **Source:** p.1 §1.3 Zone de Production de Vapeur (CMV) — “Alimentée par l'eau chaude à 90°C des PAC via un Flash Tank (70°C)”
- **Affects:** `eq.flash_tank`, `eq.cmv_s1`, `eq.cmv_s2`, `eq.cmv_s3`
- **Question:** Flash-tank liquid destination and pressure; confirm series staging.

### 13. `ur.spill_control`

Spill valves 8 → 4 and 4 → 1 bar: controlled variable, measurement point, setpoint, valve technology and failure position are not stated, so no control loop is created for them.

- **Source:** p.3 §4. Logiques de régulation et modes opératoires — “une vanne déversante (PCV) route l'excédent de 8 bar vers le 4 bar, puis vers le 1 bar”
- **Affects:** `pc.pcv_spill_8_4`, `pc.pcv_spill_4_1`, `cr.spill_8_4`, `cr.spill_4_1`
- **Question:** Control philosophy of the overproduction cascade.

### 14. `ur.boiler`

Gas boiler: capacity, fuel/feed-water/flue connections, PCV technology and failure position are not stated.

- **Source:** p.3 §4. Logiques de régulation et modes opératoires — “La chaudière gaz fournit 100% de la vapeur”
- **Affects:** `eq.boiler`, `pc.pcv_boiler`

### 15. `ur.ultimate_feed`

Ultimate mode: how well water reaches the fermenters (feed line) is not described; only the post-fermenter discharge to DARSE is.

- **Source:** p.3 §4. Logiques de régulation et modes opératoires
- **Affects:** `mode.ultimate`, `mf.ferm_out`

### 16. `ur.tags`

Equipment tags are given only for P-030..035, ECH-030..032, TK-001/002, K3/MESSO/GEA and the LPF tanks. Heat pumps, 70/90/RCUA tanks, flash tank, CMV stages, boiler and the new exchangers have no tag.

- **Source:** p.1 §1.2 Zone de Production de Chaleur (PAC) et Stockage
- **Affects:** `eq.hp_1a`, `eq.hp_1b`, `eq.hp_2a`, `eq.hp_2b`, `eq.tank_70`, `eq.tank_90`, `eq.tank_rcua`, `eq.flash_tank`

### 17. `ur.nozzles`

No nozzle numbers or nozzle sizes are given for any equipment (except DN50 on the TGE coil). Nozzle names are schematic.

- **Source:** p.1 §1. Nouveaux équipements de production
- **Affects:** —
- **Question:** Nozzle schedule.

### 18. `ur.design_data`

No design pressures, relief devices/sizing, safety thresholds (other than 7.5 bar eff.), valve failure positions, material classes or instrument ranges are given. None are invented.

- **Source:** p.3 §5. Règles topologiques génératives
- **Affects:** —

### 19. `ur.gen.fail_position`

Failure position (fail open / close / retain) of the control valves is not specified and was not assumed.

- **Source:** rule `unresolved.generated`
- **Affects:** `pc.pcv_boiler`, `pc.pcv_spill_4_1`, `pc.pcv_spill_8_4`
- **Needed for:** safety philosophy

### 20. `ur.gen.instrument_ranges`

Measuring ranges and alarm/trip settings of the generated instruments are not specified and were not assumed.

- **Source:** rule `unresolved.generated`
- **Affects:** `in.boiler_backup.pic`, `in.flash_tank.lt`, `in.h1.pt`, `in.h1.tt`, `in.h105.pt`, `in.h105.tt`, `in.h4.pt`, `in.h4.tt` … (+13)
- **Needed for:** instrument datasheets

### 21. `ur.gen.nozzles`

Nozzles added for drain, vent and level tapping have no nozzle number and no size.

- **Source:** rule `unresolved.generated`
- **Affects:** `eq.flash_tank`, `eq.lpf_degasser`, `eq.lpf_tank_an1`, `eq.lpf_tank_s04`, `eq.lpf_tank_s05`, `eq.tank_70`, `eq.tank_90`, `eq.tank_cold` … (+2)
- **Needed for:** nozzle schedule

## Out of scope / future

### 22. `ur.future_hp`

PAC 3A/3B are future equipment with no capacity, regime or connection data. They are drawn dashed (LifeCyclePhase=Future) and left unconnected.

- **Source:** p.1 §1.2 Zone de Production de Chaleur (PAC) et Stockage — “PAC Extension (3A / 3B) 2 (cascade) – Équipement Futur (hors capacité)”
- **Affects:** `eq.hp_3a`, `eq.hp_3b`

### 23. `ur.hw_backup`

'Les réseaux Eau Chaude basculent sur le secours vapeur local' (emergency-exchanger mode): the local steam back-up equipment is not described.

- **Source:** p.3 §4. Logiques de régulation et modes opératoires
- **Affects:** `mode.emergency_hx`

### 24. `ur.rcua_limits`

RCUA network battery limits (destination of the 105 °C header and the 85 °C return) are not described; placeholder boundaries are used.

- **Source:** p.1 §1.2 Zone de Production de Chaleur (PAC) et Stockage
- **Affects:** `bc.rcua_out`, `bc.rcua_return`
