# Extraction kit (`pid_workflow.extract_kit.Spec`)

The extraction script records what the document says. `Spec` checks every quote against the page it cites when the
script runs, so a mistyped quote fails immediately with the page where the text really is.

```python
from pid_workflow.extract_kit import Spec
s = Spec(__file__, drawing_id="PID-XYZ-001", title="Plant – draft P&ID", project="Project name", language="fr")
```

## Provenance

| call | use for | rule |
|---|---|---|
| `s.src(page, section, quote)` | what the text states | quote copied exactly from `source/pages/page_NNN.txt`; cells of one table row may be joined with `" … "`; case and accents matter |
| `s.interp(page, section, note, quote=…)` | an interpretation needed to draw it | `note` says what was inferred and why |
| `s.structural(page, section, note, quote=…)` | structure only (header tees, placeholder limits) | `note` says why |
| `s.val(value, unit, src)` | a value with its own provenance | |

A provenance dict can be passed where a quote is expected (its quote is reused).

## Objects

```python
s.area("ar.prod", "Production", q)
s.equipment("eq.p101", "Primary pump", "CentrifugalPump", "ar.prod", q, tag="P-101",
            nozzles={"suction": "suction", "discharge": "discharge"},
            attrs={"design_volume_flow_rate": s.val(172, "m3/h", q)},
            lifecycle="new",            # new | existing | modified | future (future = dashed, not populated by rules)
            symbol=None)                # only for CustomEquipment / to override the class symbol
s.bank("sec_pumps", ["eq.p201", "eq.p202", "eq.p203"], inlet="eq.bd01:sec_out", outlet="mf.sup:common",
       service="Eau glacée", src=q, unit_in="suction", unit_out="discharge")   # split header -> units -> merge header
s.manifold("mf.sup", "Supply header", "split", 4, "ar.users", q)              # ports: common, b1..b4
s.line("eq.a:out", "eq.b:in", "Fluid name", q, props={"temperature": s.val(6, "°C", q)}, header=False)
s.run("Fluid name", q, "eq.a:out", "pc.cv1", "eq.b:in")                        # through inline valves (ports in/out)
s.valve("pc.tv301", "Mixing valve", "control", "ar.cond", q, tag="TV-301",
        kind="valve")               # valve | check_valve | strainer | relief; technology unknown -> generic class
s.boundary("bc.city", "City water", "in", "Eau de ville", "ar.hr", q)          # battery limit, port "port"
s.control("cr.t", "Min. condenser water 22 °C", q, variable="temperature", measured_at_line=line_id,
          final_element="pc.tv301", setpoint=s.val(22, "°C", q), controller_required=True)
s.mode("mode.winter", "Free cooling", "text", q, [("isolate", ["pc.v1:in"], "text")])
s.unresolved("ur.x", "ambiguity", "What is open and what is drawn meanwhile.", ["eq.ech01"], q, question="…")
s.basis("ISA 5.1 tags", q)                                                     # engineering basis statements
s.save()                                                                       # validates, writes source_topology.json
```

`s.line`/`s.run` return the line id(s); keep them when a control requirement must name its measurement line.

## Ports and nozzles

* Equipment: the nozzle names you declare. Roles: `inlet`, `outlet`, `suction`, `discharge`. Only process
  connections - drains, vents, level taps and relief nozzles are added by rules.
* Valves / strainers / relief devices: `in`, `out`. Manifolds: `common`, `b1..bn` (split: common in; merge: common out).
* Battery limits: `port`. Lines always run in flow direction (outlet → inlet). One line per port: branches need a
  manifold.

## Line properties understood by the drawings

`temperature`, `temperature_supply`, `temperature_return`, `temperature_max` / `_min` (shown as ≤ / ≥),
`pressure` (same suffixes), `nominal_flow` / any key containing `flow`, `nominal_diameter`,
`nominal_diameter_range` (`{"min": 200, "max": 350}`), `nominal_diameter_min`.
Equipment attributes named `<side>_inlet_temperature`, `<side>_outlet_temperature`, `<side>_flow_rate`
(side = water, cold, hot, steam, process, product, evap, cond, primary, secondary, shell, tube, or a word contained in
the nozzle names) are put on that equipment's own streams in the PFD. Pump `design_volume_flow_rate` becomes the flow
of its discharge stream.

## Classes and symbols

Any pyDEXPI equipment class is accepted; the drawing symbol follows the class hierarchy:
`python -c "from pid_workflow.catalog import equipment_classes as e; print(sorted(e()))"`.
Common choices: `CentrifugalPump`, `ReciprocatingPump`, `Tank`, `Vessel`, `PressureVessel`, `Silo`, `ProcessColumn`,
`PlateHeatExchanger`, `TubularHeatExchanger`, `AirCoolingSystem`, `WetCoolingTower`, `Compressor`,
`CentrifugalCompressor`, `Blower`, `Fan`, `Filter`, `Boiler`, `Furnace`, `Mixer`, `Agitator`, `SteamTurbine`.
No class fits (heat pump, packaged unit, user/consumer) → `CustomEquipment` with `symbol=` one of
`heat_pump` (4 nozzles: names containing `evap` / `cond`), `box`, `pump`, `compressor`, `fan`, `hx`, `phx`, `tank`,
`vessel`, `column`, `filter`, `boiler`, `heater`, `mixer`, `cooling_tower`, `air_cooler`, `turbine`, `motor`.
Valve classes: `CustomOperatedValve` (generic, technology unknown), `GateValve`, `GlobeValve`, `BallValve`,
`ButterflyValve`, `PlugValve`, `CheckValve`, `SwingCheckValve`, `Strainer`, `SpringLoadedGlobeSafetyValve`,
`CustomSafetyValveOrFitting`.

## Open-point categories

`missing_value` (a value is not given), `ambiguity` (two readings), `conflict` (two statements disagree),
`selection` (a choice is left open), `scope` (not described / outside the document). `affects` lists object ids
(drawn as hold markers on equipment and battery limits).
