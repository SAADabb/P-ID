# TODO — what to take from `pid-agent` v0.5

Source: `pid-agent-v0.5.zip`, a domain demonstrator ("P&ID from natural language", district heating and
energy plants, French). It was read in full: skill, references, docs 00–13, code, profiles, examples. Nothing has
been changed in this repository yet; this file is the plan.

Paths in **bold monospace** refer to the zip (`pid-agent/…`); plain `monospace` paths refer to this repository.

---

## 0. Summary

**What it is.** An agent writes a JSON "IR" (typed nodes, ports, edges, modules, control logic). A deterministic
compiler then produces DXF (AutoCAD, opened and audited in AutoCAD 2027), SVG/PNG, Excel lists, DEXPI and an
AutoCAD `.scr` script. Its strengths are domain knowledge, not engine logic:

| Their asset | Size | Value for us |
|---|---|---|
| Symbol catalogue (**`pid_agent/symbols/catalog.py`**, **`catalog_ext.py`**, reference **`skill/references/03_catalogue_symboles.md`**) | 217 types, 8 plant families, named ports, tag prefix per type | **High** – we draw ~17 equipment shapes and ~10 valve shapes |
| Domain anatomies (**`skill/references/01_domaine_reseaux-de-chaleur.md`**, **`08_domaine_production.md`**) | district heating stations; biomass, gas/oil, CHP, cold, geothermal, solar, biogas, H2, HVAC, electrical limits | **High** – becomes rule packs and engineering notes |
| Business rules (**`pid_agent/ir/validate.py`**, **`references/04_regles_validation.md`**) | 16 rules (6 structural, 10 domain) | **High** – several missing from our good-practice pack |
| Typical stations as modules (**`pid_agent/layout/rails.py`** `expand_modules`, `CHAIN_TEMPLATES`) | 5 modules | **High** – parameterised "postes types" |
| DXF output with blocks + attributes + layers (**`pid_agent/compilers/dxf.py`**, test results in **`docs/02_…`** part A) | proven in AutoCAD 2027 (audit 0 errors, 11/11 files) | **High** – we have no CAD output |
| Charter profiles (**`profiles/iso.yaml`**, **`isa.yaml`**, **`engie.yaml`**) | abstract id → block name, layer, tag prefix, title block | **Medium** |
| Synthetic test cases (**`examples/01…13`**, `description.md` with expected equipment and acceptance criteria) | 13 cases, 263 tagged items, robustness tests R1–R4 | **Medium–high** as an evaluation set |
| Questions for engineering (**`docs/05_Questions_Ingenierie_RD.md`**), blind spots (**`docs/12_…`**) | 21 closed questions, ~35 blind spots | **Medium** – becomes holds and notes |
| Their layout ("rails" placer, explicit x/y for reproductions) | — | **None** – our zones + A* router + repair router are stronger; do not import |

**What we keep from our side:**
- verbatim-quote provenance;
- zones / A* / repair layout;
- geometric QA;
- the pyDEXPI round trip with graphics;
- the PFD;
- the decision register;
- "never invent values".

Their agent writes the IR without quote checking, and their placer still fails on dense sheets (their doc 12, L1).

**Before copying anything** (code, symbol geometry, case texts), confirm the licence and permission with the author. The zip mentions a client (Engie) and is internal-looking, even though all data is marked synthetic. Plan: reimplement in our own form. Never commit the zip or its files.

---

## 1. Symbol library — extend `render_pdf.py` / `catalog.py` (priority P1)

### 1.1 Missing symbols, by family (their type id → what to add)

**District heating / steam basics** (their v0.2 base):
- Steam traps:
  - `steam_trap.thermodynamic`, `.float`, `.bimetallic`, `.inverted_bucket`;
  - symbol is square + circle + text TD/FT/BM. Their glossary §9 says it is **non-normative**, so state that in the legend.
- Inline accessories:
  - `sight_glass` (circle + 2 vertical bars);
  - `vessel.drip_leg` (drip leg / pot de purge, vertical rectangle on a steam main);
  - `air_vent.automatic`;
  - `dirt_pocket`;
  - `separator.air_dirt`;
  - `flexible`;
  - `reducer.concentric`;
  - `flange.blind`;
  - `flange.spectacle`;
  - `hose_connection`;
  - `sampling_point`.
- Valves and actuators:
  - `valve.control.self_actuated` (PCV, impulse line downstream);
  - `valve.gate.motorized` (circle "M");
  - `valve.gate.pneumatic` (dome);
  - `valve.solenoid` ("S");
  - `valve.three_way.manual` / `.motorized`;
  - `valve.balancing`;
  - `valve.thermostatic`;
  - `valve.quick_closing`;
  - `valve.knife_gate`;
  - `valve.needle`;
  - `valve.diaphragm`;
  - `valve.float`;
  - `valve.gate.manual.closed` (normally closed = filled body).

  This is a gap today: control valves only have a generic actuator, and the actuator type is not drawn.
- Relief: `rupture_disc`, `vacuum_breaker`, `silencer`.
- Equipment:
  - `expansion_vessel`;
  - `pressurisation_unit`;
  - `backflow_preventer`;
  - `water_treatment`;
  - `dosing_pump`;
  - `tank.chemical`;
  - `tank.buffer`;
  - `tank.stratified`;
  - `tank.storage_coil`;
  - `vessel.flash`;
  - `vessel.blowdown`;
  - `deaerator` / `deaerator.storage`;
  - `cooler.blowdown`;
  - `separator.steam`;
  - `pump.submersible`;
  - `pump.positive_displacement`.
- Meters:
  - `energy_meter` (FQ, flow + 2 temperature probes; the heat meter at a substation battery limit);
  - `water_meter`;
  - `flowmeter.inline` (FE).

**Biomass plants:**
- `silo`, `hopper`, `conveyor.screw` / `.chain` / `.belt`;
- `rotary_valve`, `damper.fire`, `feeder.hydraulic_ram`, `hydraulic_unit`;
- `boiler.biomass_grate` (ports air1/air2/air3, ash, flue, fuel, hyd, relief, win, wout);
- `air_preheater`, `cyclone`, `filter.bag`, `filter.electrostatic`;
- `exchanger.economizer`, `flue_gas_condenser`, `stack`;
- `ash_container`, `bigbag`, `fan.centrifugal`, `damper.control`;
- `compressor`, `air_receiver`, `air_dryer`.

**Gas / oil, CHP, steam cycle:**
- `burner`, `filter.gas`, `regulator.gas`, `valve.gas.solenoid_double`, `meter.gas`;
- `tank.fuel`, `boiler.gas`, `boiler.condensing`, `boiler.thermal_oil`;
- `engine.cogeneration`, `generator.electric`, `catalyst`;
- `turbine.gas`, `turbine.steam`, `condenser`, `desuperheater`, `vessel.steam_drum`;
- `ejector`, `vacuum_pump`, `orc_module`, `flame_arrestor`.

**Cold / geothermal / solar:**
- `chiller` (evaporator left, condenser right), `chiller.absorption`;
- `dry_cooler`, `cooling_tower` (ports blowdown, makeup), `ice_storage`;
- `well.production`, `well.injection`, `borehole_field`, `glycol_fill_unit`;
- `solar_collector_field`, `heat_dissipator`, `coil.terminal`.

**Biogas / H2:** `digester`, `gasholder`, `gas_treatment`, `flare`, `electrolyser`, `fuel_cell`, `tank.pressurized_gas`.

**HVAC:** `ahu`, `filter.air`, `heat_recovery`, `humidifier`, `fan.axial`, `air_diffuser`.

**Electrical limits** (P&ID representation only): `transformer`, `cabinet.electrical`, `drive.vsd`, `motor.electric`, `generator.diesel`, `ups`.

**Annotation:** `equipment.package` (dashed box around a vendor package), `equipment.generic` (box with a mandatory designation).

### 1.2 How to add them

- [ ] For each type, map it to a **pyDEXPI class** first (`python -c "from pid_workflow.catalog import equipment_classes …"`):
  - DEXPI already has many of them: `Silo`, `Cyclone`, `Stack`, `Burner`, `Boiler`, `SteamTurbine`, `GasTurbine`, `Fan`, `Conveyor`, `RotaryValve`, `Filter`, `HeatExchanger` subclasses, `Chimney`, `Agitator`, and others;
  - use `CustomEquipment` + `symbol=` only where no class fits.
- [ ] Extend `valve_symbol()` in `render_pdf.py` with actuator variants from `operation` / `model_class`: motor (circle M), pneumatic diaphragm (dome), solenoid (S), self-actuated (impulse line), hand (bar). Add 3-way bodies, and "normally closed" as a filled body.
- [ ] Draw **instrument location** per ISA-5.1:
  - local field = plain circle (PI/TI gauges, local switches);
  - main control room / DCS = circle with a horizontal line (what we draw today for everything);
  - PLC / shared display = circle in a square.

  Their catalogue separates `….indicator.local`, `….dcs` and `instrument.controller.plc`. Add a `location` attribute to `Instrument` (local | panel | dcs | plc). Default: local for PI/TI/LG, dcs otherwise.
- [ ] Line classes and linetypes, from their `EDGE_LAYER` / `LAYERS`:

  | Line class | Drawn as |
  |---|---|
  | solid fuel / ash | heavy line |
  | flue / exhaust gas | dash-dot |
  | combustion / compressed air | dashed |
  | refrigerant | dashed |
  | hydraulic oil | thin dash-dot |
  | electric power | blue dashed |
  | electric signal | dashed |
  | pneumatic signal | double hatch |
  | data link | fine dotted |

  Put it in `policies/rendering.yaml` (keyword → colour **and** linetype), and draw the legend entries only when used.
- [ ] Symbols, the legend and the DEXPI `ShapeCatalogue` must stay in sync (`proteus_graphics.py`). Add a test that every symbol used on a sheet has a legend entry and a shape.
- [ ] Generate a **symbol sheet** (their `scripts/render_library_png.py`, `docs/planches/*.png`) as a review artifact, e.g. `pid catalog --sheet`. Engineers validate the shapes there, not on a project drawing.
- [ ] Record the conformity notes from their glossary §9 in the legend or notes: purgeur non-normative; check valve = triangle + bar; ISO 14617-9 (pumps) withdrawn on 2025-04-25.

---

## 2. Domain knowledge → rule packs (priority P1)

Our `policies/rule_packs/process_good_practice.yaml` already has:
- pump auxiliaries (strainer, check, isolation, PI);
- compressor auxiliaries;
- exchanger isolation;
- vessel drain / vent / LT;
- pressure-vessel relief;
- control-valve manifold;
- loops from requirements;
- tagging;
- line numbers.

Add new packs in the same "proposal, pending review, never a value" style. Each item is a
`[HYPOTHÈSE-MÉTIER]` in their source, so ours stays a proposal with an explanation.

### 2.1 New pack `district_heating.yaml` (steam / superheated water / hot water / chilled water)

- [ ] **Steam trap station** around a steam trap (`drain_station.steam` in their `CHAIN_TEMPLATES`):
  - order: (drip leg) → isolation → Y-strainer → trap → sight glass → check → isolation;
  - plus a bypass / test valve (globe), and a drain valve on the drip leg;
  - source: their ref 01 §5.

  Open points: H1 (is a drip leg a tagged item?) and H6 (is the test valve mandatory everywhere?).
- [ ] **Pressure-reducing station**: a relief valve (PSV) downstream of every self-actuated PRV (their R-M-020), and a silencer on the PSV discharge to atmosphere for steam. The set pressure is always an open point.
- [ ] **Valve station** (sectioning): isolation valves with a drain at low points and a vent at high points on both sides. Their case 02 expected list shows vents/drains and PIs on **both** sides; the dictation usually forgets them.
- [ ] **Substation (hot / cold)**:
  - control valve on the primary;
  - energy meter at the battery limit (FQ, flow + T supply/return);
  - balancing valve, dirt separator, isolation of the exchanger on all four nozzles;
  - make-up via a backflow preventer;
  - expansion vessel with its isolation valve.
- [ ] **Pumping station**:
  - "N pumps" without more detail means **parallel** (duty/standby) between common headers;
  - per pump: isolation, pump, check, isolation, plus a discharge PI;
  - common suction and discharge PIs;
  - level switches LSLL/LSL/LSH/LSHH on the suction vessel only when stated.

  Their case 05: "three pumps in series" in a dictation is almost always parallel. Write it as an interpretation with an open point; never silently.
- [ ] **Condensate return**: flash vessel → atmospheric tank → pumps; vent on the tank; cooler before discharge to sewer (H4: always or above a threshold?).
- [ ] **Underground chamber**: water-detection switch (MSH) and a submersible lift pump when the chamber is below the gravity sewer (H9). Proposal only.

### 2.2 New pack `combustion.yaml` (boilers, burners, engines)

- [ ] **Gas train** upstream of every burner, gas boiler, CHP engine or gas turbine (their R-M-070/071 and `gas_train.standard`):
  - manual isolation → gas filter → (meter) → regulator → PSL → **double safety shut-off valve** with leak test → PSH → burner;
  - plus a flame detector (BE) on the burner;
  - plus gas detection (AAH) in the boiler room and a manual-reset main shut-off at the room entry.
- [ ] **Boiler safeties**: PSV, low-water switch (LSL / LSLL), overheat switch (TSH), pressure switch (PSH), flow switch (FSL), drain / blowdown. Condensing boiler: acid condensate neutralisation (open point).
- [ ] **Biomass**:
  - fire damper or rotary valve between storage and furnace (their R-M-080);
  - position switch (ZS) on it;
  - quench water (open point);
  - spark detector on the conveyor;
  - primary / secondary air fans + dampers;
  - furnace pressure (PDT) and O2 (AT);
  - flue-gas train: cyclone → (economiser) → bag / ESP filter + PDT → ID fan → stack + analyser (their `flue_gas_train.biomass`);
  - de-ashing: screw → container.
- [ ] **Compressed air**: compressor → receiver (drain, PSV) → dryer → distribution; PSL.
- [ ] **CHP**: heat recovery on jacket water and exhaust, emergency dry cooler, catalyst, silencer, stack.

### 2.3 New pack `cold_geo_solar.yaml`

- [ ] **Chiller**: flow switch (FSL) and antifreeze (TSL) on the evaporator; flexible connections on the pumps.
- [ ] **Open cooling tower**: make-up with a backflow preventer, blowdown (bleed), water treatment.
- [ ] **Groundwater doublet**: production well + submersible pump → strainer → intermediate plate exchanger → heat pump → injection well. Instruments: level and temperature in the aquifer, flow, injection pressure.
- [ ] **Borehole field**: glycol fill unit, expansion vessel, air vents.
- [ ] **Solar thermal**: PSV, expansion vessel sized for vaporisation (open point), high-point air vent, overheat dissipator, differential temperature controller (TDC).

### 2.4 Check-only rules (report, never add)

Add a rule type `check` that writes findings into the decision register / QA report without adding objects:
- [ ] a trap without an upstream strainer (R-M-010), or without a bypass / test valve (R-M-011, info);
- [ ] a PRV without a downstream PSV (R-M-020);
- [ ] an exchanger not isolable within 4 objects (R-M-060/061);
- [ ] a pump without isolation / check (R-M-001/002/003);
- [ ] a burner without a double shut-off or filter (R-M-070/071);
- [ ] a biomass furnace without a fire damper or rotary valve (R-M-080);
- [ ] mixed fluid classes entering a node, except at an exchanger or tank (R-M-050, info);
- [ ] a control / interlock text that references a tag not on the drawing (R-M-040);
- [ ] `CustomEquipment` without a designation, and a list of the symbols still to create (R-M-090).

These give a **verify mode** on an existing topology: their case 10 shows a duplicate tag and a non-isolable
exchanger being caught before the drawing is accepted.

---

## 3. Typical stations as macros in the extraction kit (priority P1)

Their modules expand into nodes with stable ids (`MOD_SUFFIX`). We have `s.bank(...)` for parallel units. Add:

- [ ] `s.station("bypass.manual", around=[ids], valve="GlobeValve", with_isolation=False)`. With isolation it becomes the 3-valve bypass (their case 10). Today `control_valve.manifold` only covers control valves.
- [ ] `s.station("drain_station.steam", upstream="ln.steam_main", downstream=…, trap="thermodynamic", with_pot=True, with_bypass=True)`.
- [ ] `s.station("gas_train.standard", upstream=…, downstream="eq.burner:fuel", with_meter=…)`.
- [ ] `s.station("flue_gas_train.biomass", upstream="eq.boiler:flue", filter="bag|electrostatic|none", with_economizer=…)`.
- [ ] `s.station("pumpset.parallel", …)`: alias of `s.bank` with per-pump check/isolation, kept for the domain vocabulary.

Rules for all station macros:
- every expanded object carries the station's provenance (`s.interp`, "typical station X; parts not stated in the specification");
- objects the text **states** stay `src`;
- documented in `skills/pid-pfd-from-spec/references/extraction-kit.md`;
- their parameters (DN, trap type) are taken **only** from the text.

---

## 4. Control logic beyond loops (priority P2)

Their IR carries `control[]` with the kinds alarm | interlock | sequence | regulation | timer | operating_note, and a
threshold written as "à définir" when it is not stated. We only model regulation loops (`s.control`).

- [ ] Add `s.interlock(id, when, then, src, threshold=None)` and `s.alarm(...)`. Example: "LSLL-101 → stop pumps, manual reset". These are stored in the topology.
- [ ] Output:
  - a "Logic" sheet in `engineering_lists.xlsx`;
  - numbered notes on the P&ID (like holds);
  - DEXPI where a class exists (otherwise a custom attribute).
- [ ] Check (R-M-040): every tag named in a logic text exists on the drawing.
- [ ] Switch symbols (LSH/LSL/LSHH/LSLL, PSH/PSL, TSH, FSL, ZS) drawn as bubbles with their ISA letters. They exist in our ISA tagging but are not produced from stated alarms today.

---

## 5. CAD output: DXF with blocks + attributes (priority P2)

The most requested format in their context (AutoCAD). Their test results (doc 02, part A) give the recipe:

- [ ] `pid dxf projects/<name>` (or part of `run`): write `output/pid_one_sheet.dxf` with `ezdxf` from the **recorded drawing** (`graphics.Recorder` primitives).
  - It should come from the same prims as the PDF and the DEXPI graphics, so the three never diverge.
  - One **block per symbol type**, inserted with ATTRIBs `TAG`, `FUNC`, `NUM`, `DESC`, so tags are extractable data (DATAEXTRACTION / CSV).
- [ ] Layers per function (PROCESS, CONDENSATE, WATER, EQUIPMENT, INSTRUMENT, SIGNAL, TEXT, TITLE, FRAME, SOLIDS, FLUEGAS, AIR, GAS, ELECTRIC…) with ACI colour, lineweight and linetype. Values are in their `LAYERS` dict and `profiles/*.yaml`.
- [ ] Compatibility lessons:
  - write R2018 by default and offer R2000;
  - `setup=["linetypes"]` only (no TrueType styles → no font substitutions);
  - style `Standard` / `txt.shx` → sanitise texts to Latin-1 (em dash, curly quotes and "≤ ≥" render as "?"; map them to "-", '"', "<=", ">=");
  - keep attributes horizontal on rotated blocks.
- [ ] Optional: a DXF library of all blocks (`pid_symbols_library.dxf`) for `DXFIN`. AutoLISP `.scr` script output is low priority: AutoCAD-only and fragile over COM.
- [ ] Verification: re-read with `ezdxf.audit()` in tests, and count blocks / attributes against the lists. AutoCAD itself is not available here, so say "opened in AutoCAD" only with evidence (their absolute rule).

---

## 6. Charter profiles (priority P2)

- [ ] `policies/profiles/{iso,isa}.yaml`, plus an empty, commented `client.yaml`:
  - tag separator and number format;
  - **prefix overrides** (e.g. ISA school `PG` instead of `PI` for a local pressure gauge);
  - instrument syntax;
  - DXF block names and an external block library;
  - layers;
  - text heights;
  - title-block fields and sheet numbering;
  - sheet size.

  Selected per project (`profile: iso`); empty fields fall back to iso.
- [ ] Their table "12 adaptation points" (**`references/06_adaptation_engie.md`**) is a good template for documenting what to ask a client for each field, and how to test it.
- [ ] Title block: add a **revision table** (`revisions[]`: index, date, description, drawn / checked / approved), which their case 11 showed is expected.

---

## 7. Agent / skill procedure (priority P1, cheap)

Add to `skills/pid-pfd-from-spec/SKILL.md` and `references/engineering-notes.md`:

- [ ] **Qualify the request first.** Is the mode generate, instantiate a typical station, modify an existing topology (keep tags stable, never renumber silently) or verify?
- [ ] **Physically contradictory request** ("pressure reduction from 6 to 18 bar", "check valve fitted against the service flow"): do not draw. Return the contradictions and closed questions. Today we would draw with open points; for *impossible* physics, stopping is the better answer.
- [ ] **Reading rules:**
  - "N pumps" = parallel duty/standby unless series is explicit (booster + main);
  - two mains (supply / return, steam / condensate) = two lines with different services;
  - ISA letters qualify **instruments**, never valves or equipment;
  - « eau surchauffée » (pressurised liquid > 100 °C) ≠ « vapeur surchauffée » (gas): never mix them;
  - « doublage » convention unknown (2×100 % or 2×50 %): open point (Q12).
- [ ] **"What the dictation almost always forgets"** checklist (their ref 08 §6). Ask about these, or propose them as holds:
  - boiler safeties;
  - flame-arrest device;
  - gas PSL/PSH and leak test;
  - evaporator flow switch;
  - make-up with a backflow preventer;
  - expansion vessel with its isolation;
  - drains and vents;
  - energy metering at battery limits;
  - filter dampers / by-pass;
  - CHP emergency cooler.
- [ ] **Domain reference:** add `references/domain-utilities.md`, a condensed English version of their ref 01 + 08. Cover the anatomies in flow order, the typical fluid ranges (stated as typical, never used as values), and the station compositions. Load it only for utility / energy specs.
- [ ] **Steam-main facts** (for notes and open points only, never drawn values): drain points every 30–50 m and at low points; slope ≥ 1:100; velocity > 30 m/s → water hammer if not drained. Their glossary gives the sources.
- [ ] **Other input modes.** An **equipment list in Excel** (their R3) gets a small importer into `extract_kit` calls, with provenance = sheet/row. **English input** (R1) already works.

---

## 8. PFD scope check (priority P2, decision)

Their glossary (ISO 10628-1 via ifluids.com) notes that **adding control valves to a PFD is a frequent scope error**.
Our PFD keeps control valves as stream nodes.

- [ ] Decide which is right for our users:
  - keep them (common in EPC PFDs, and they split streams); or
  - add an option `pfd.control_valves: hide|show` (default show) that merges the streams across the valve.

  Document the choice in `references/outputs.md`.

---

## 9. Evaluation set and metrics (priority P2)

- [ ] With permission, reuse their synthetic cases **01–10, 12, 13** as a blind evaluation set: dictated description with deliberate imprecisions, plus expected equipment list and acceptance criteria. Case 11 is a reproduction and needs coordinates; skip it.
  - One folder per case under `skills/pid-pfd-from-spec/evals/` (`claude plugin eval` format), with graders built from their acceptance criteria (e.g. case 05: "3 pumps in parallel, never in series", "each pump has its own check valve", "LSLL → pump stop documented").
- [ ] Their metric **concordance by type** (expected vs produced per tag prefix) is a good complement to our QA. Add `pid eval <case>` that counts objects per ISA / tag family against an expected list.
- [ ] Robustness tests:
  - R1: English input;
  - R2: contradictory input → no drawing, questions;
  - R3: Excel list;
  - R4: "standard trap station, automatic, DN50".
- [ ] Their measured weak points to compare against:
  - completeness tracks what is dictated (52–87 %), not complexity;
  - layout broke first on large sheets.

  We should report the same two numbers per case.

---

## 10. Holds and questions library (priority P3)

- [ ] Turn their closed questions into ready-made open-point templates, used when the situation occurs:
  - Q10 (drip leg tagged?);
  - Q11 (trap sizing rule, default variant, test valve);
  - Q12 (pump doubling convention);
  - Q13 (chamber lift pump);
  - Q20 (ISA vs ISO school, trap symbol);
  - Q21 (as-built of buried sections);
  - H2/H7 (drip-leg sizing rule, supervised start-up).
- [ ] Generic project-level questions for the decision register's "data to complete" section:
  - Q1–Q4: tool and format;
  - Q5–Q8: charter, tag rule, typical stations, sample P&IDs;
  - Q15–Q16: status and approval, confidentiality.

---

## 11. Not to take

- Their "rails" layout and explicit `x/y` coordinates. Our layout is already better, and CLAUDE.md forbids coordinates in a topology.
- An IR written without quote provenance. Our `Spec` with verbatim quotes stays the extraction contract.
- Copilot M365 bundles, PowerShell install kit, AutoCAD COM automation scripts: these are client deployment specifics.
- `engie.yaml` content and any client-specific naming.
- Their DEXPI exporter: ours is more complete (round trip + Proteus graphics). Their noted gap (`Equipment` not in `taggedPlantItems`) does not apply to us.

---

## 12. Suggested order

1. §7: skill / notes checklist, reading rules, contradiction stop. Cheap and immediate value.
2. §1: symbols for district heating + steam + valve actuators + instrument location. Then biomass / gas / cold families.
3. §2 + §3: rule packs and station macros (steam trap station, gas train, PRV + PSV, substation, pumping station), plus check-only rules (verify mode).
4. §4: interlocks / alarms as data, "Logic" sheet.
5. §5 + §6: DXF output from the recorded drawing, profiles, revision table.
6. §9: evaluation set and concordance metric. Run it after each step above.
7. §8 decision, §10 holds library.

Keep `python -m pytest -q` green at every step. Re-run `lpf_bsst` and `chw_nord`; geometric problems must stay at 0.
