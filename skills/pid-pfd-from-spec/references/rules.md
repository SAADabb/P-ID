# Rules (`project_rules.yaml`)

Rules complete the P&ID with what a drafting office adds: valves around equipment, drains and vents, instruments,
tags, line numbers. Everything a rule adds is a **proposal** (`pending_review`) with its rule, trigger and explanation;
an engineer approves rules as a whole (`bash "$SKILL/scripts/pid" review projects/<name> --approve-rule <id>`) or rejects single objects.
Rules are idempotent and never duplicate what the document already shows.

```yaml
project: <name>
include: [process_good_practice]      # policies/rule_packs/process_good_practice.yaml (in the engine)
overrides:
  line_numbering:
    codes: [{prefix: "Eau glacée", code: "EG"}, {prefix: "Eau de condensation", code: "EC"}]
rules:
  - id: pump.auxiliaries               # same id as the pack rule -> replaces it
    type: equipment_template
    source: {page: 2, section: "7. Exigences P&ID", quote: "<verbatim sentence that asks for it>"}
    params: {...}
  - {id: control_valve.manifold, enabled: false}    # say why in a comment
```

**When the document asks for only part of a pack rule** (e.g. pump valves and strainer, but no pressure gauge):
override the rule with the stated part and its citation, and move the rest into a separate rule with its own id and
no `source.page` (e.g. `pump.pressure_gauge`), so nothing unstated is attributed to the document.

A rule with `source.page` is cited as a requirement of the document; a pack rule without one says in every
explanation "good-practice pack – not stated in the specification". Override pack rules the document confirms, adapt
their parameters to the text (e.g. PI vs PT, which classes), switch off what does not apply.

## The good-practice pack

| id | type | adds |
|---|---|---|
| `pump.auxiliaries` | equipment_template | suction: strainer then isolation; discharge: check then isolation; PI on discharge |
| `compressor.auxiliaries` | equipment_template | suction isolation; discharge check + isolation; PI |
| `exchanger.isolation` | equipment_template | isolation on every inlet and outlet of HeatExchanger / CoolingTower / AirCoolingSystem |
| `vessel.auxiliaries` | equipment_template | drain, vent, LT on Vessel / Tank / Separator |
| `pressure_vessel.relief` | equipment_template | relief device on PressureVessel / Boiler / SteamGenerator (sizing never invented: open point) |
| `control_valve.manifold` | control_valve_manifold | block valves, purge, globe-valve by-pass around each control valve |
| `control_loop.from_requirement` | control_loop | measurement → controller → final element, only for `controller_required=True` with a stated measurement |
| `tagging.isa` | tagging | ISA 5.1 tags for generated valves and instruments (XV, NRV, PCV, PSV, STR, PT, TT, LT, PI …) |
| `lines.numbering` | line_numbering | `<fluid code>-<sequence>` per logical line; codes from overrides, else initials of the service name |
| `unresolved.generated` | unresolved_summary | open points for generic valve technology, fail positions, ranges, relief sizing, nozzle data |

## `equipment_template` parameters

```yaml
params:
  applies_to: [Pump]                 # DEXPI classes; subclasses match (CentrifugalPump is a Pump)
  only: [eq.bc01]                    # optional: restrict to these equipment ids
  exclude: [eq.ve01]                 # optional: skip these
  include_existing: true             # existing/modified equipment is populated with a "verify" note
  inline:                            # per nozzle role, ordered OUTWARD from the nozzle, every nozzle with that role
    suction:   [{function: strainer}, {function: isolation, operation: manual}]
    discharge: [{function: check}, {function: isolation, operation: manual, model_class: ButterflyValve}]
  open_ends:                         # nozzle created if missing, valve with open end
    - {nozzle_role: drain, function: drain}
    - {nozzle_role: vent, function: vent}
    - {nozzle_role: relief, function: relief}
  instruments:
    - {isa_code: PI, variable: pressure, name: Discharge pressure gauge, at: {line_of: discharge}}
    - {isa_code: LT, variable: level, at: {nozzle_role: level_tap}}
```
A project rule without `source` is labelled like a pack rule ("not stated in the specification"). Conditions on line
size (e.g. "butterfly valves from DN 100") cannot be encoded while sizes are unknown: keep generic valves and raise a
`selection` open point.

**Tag numbers** come from series per prefix in the engine's `policies/generic.yaml` (`tagging.series`: XV 201, NRV 251,
PT 101, PI 151, TT 301, LT 401, PCV 501, PSV 601, STR 701, …), allocated in id order; a loop's transmitter, controller
and valve share one number. They are proposals, not tied to equipment numbers; a project may change the series with
`overrides: {tagging: {series: {PI: 101}}}`.

`model_class` only when the document names the valve type; otherwise the generic class is used and listed as an open
point.

## Other rule types

* `control_valve_manifold`: `applies_to_function: control`, `upstream_isolation`, `downstream_isolation`, `purge`,
  `bypass_valve` (each `{function, operation, model_class?}`).
* `header_instrumentation`: `services: [<service names>]`, `instruments: [{isa_code: PT, measured_variable: pressure}]`
  - one set per header line (`header=True` lines of those services).
* `mode_isolation`: `modes: [<mode ids>]`, `valve: {function: isolation, operation: unknown}` - isolation valves at the
  ports named by the operating modes' `isolate` requirements.
* `control_loop`: `controller_code: {pressure: PIC, temperature: TIC, level: LIC, flow: FIC}`.
* `tagging`: `tag_untagged_source_control_valves: true|false`. `line_numbering`, `unresolved_summary`: no params.

Something the document asks for that no type covers → a new method on `Enricher` in `pid_workflow/enrich.py`
registered in `Enricher.handlers`, with a test.
