# Export to DEXPI Proteus XML — what is and is not carried over

File: `pid_draft.proteus.xml` (Proteus 4.1.1, written with pyDEXPI 1.2.0).

## Contents

| Element | Count |
|---|---|
| boundary:FlowInPipeOffPageConnector | 3 |
| boundary:FlowOutPipeOffPageConnector | 4 |
| control_loops | 1 |
| equipment:Boiler | 1 |
| equipment:CentrifugalPump | 6 |
| equipment:CustomCompressor | 3 |
| equipment:CustomEquipment | 14 |
| equipment:CustomHeatExchanger | 4 |
| equipment:PlateHeatExchanger | 7 |
| equipment:Tank | 8 |
| equipment:Vessel | 2 |
| instrument:ProcessControlFunction | 1 |
| instrument:ProcessInstrumentationFunction | 20 |
| manifold_tees | 61 |
| piping_network_segments | 104 |
| piping_network_systems | 21 |
| valve:CheckValve | 6 |
| valve:CustomOperatedValve | 50 |
| valve:GlobeValve | 3 |

## Limitations

1. Graphics: the one-sheet A0 drawing is written as a Proteus Drawing (border, title block, notes as DrawingBorder; area frames, holds and signal lines as drawing Labels), a ShapeCatalogue (symbols as PolyLine/Circle/Text primitives; fills are not representable except on circles), ComponentName + Position on equipment, valves, instruments and battery limits, and Presentation + Coordinates on every CenterLine. Nozzles and the pipes between the tees of a header carry no graphics (the header bar is a Label of its first tee). Line-number labels sit on their PipingNetworkSegment, which pyDEXPI 1.2 does not read back.
2. LifeCyclePhase, Service, provenance, review status, tag status and schematic nozzle names are written as custom string attributes; rendering future equipment as dashed lines depends on the target template reading LifeCyclePhase="Future".
3. Heat pumps, fermenters and the retained steam exchangers have no dedicated pyDEXPI class and are exported as CustomEquipment / CustomHeatExchanger / CustomCompressor.
4. Valves of unspecified technology use CustomOperatedValve with a 'technology to be selected' typeName; no specific valve type is chosen. Manual/automated actuation is a custom attribute because DEXPI 'operation' only classifies continuous/intermittent operation.
5. An n-branch manifold is exported as a chain of n-1 PipeTee items; the manifold identity is kept in the TopologyId/TeeIndex attributes.
6. Nozzle numbers (Nozzle.subTagName) are left empty because the source gives none; nozzle sizes and ratings are not exported (never invented).
7. Only flow rate, heat flow rate and tank volume are mapped to native typed attributes; all other quantities are exported as text custom attributes.
8. Battery limits are pipe off-page connectors without connectorReference (they lead off the plant, not to another sheet). The one-sheet drawing needs no inter-sheet connectors.
9. Control valves carry no failAction, instruments no ranges, and the controller is a ProcessControlFunction without tuning data (not specified).
10. Segment nominal diameter is exported only when the source gives a single DN; ranges and minima are text attributes.
11. The Proteus XML schema (XSD) is not available offline, so the file is not schema-validated; it is proven to load with pyDEXPI's own parser and its graph is compared with the topology (see the round-trip report). Validate it in the target CAD tool before relying on it.

## pyDEXPI 1.2.0 findings

- The stock Proteus **exporter** writes only equipment, nozzles and metadata. Piping networks and instrumentation are written by `pid_workflow/proteus_ext.py`, which plugs into pyDEXPI's exporter framework and follows the structure the pyDEXPI **parser** reads. The result is re-loaded with pyDEXPI to prove it parses.
- `PlantModelExporter` reads `self.metadata_exporter` even when a model has no metadata (AttributeError); the model therefore always carries a `MetaData` object.
- The pyDEXPI **loader** ignores custom attributes and `FromNode`/`ToNode` indices; those are verified at XML level (see the round-trip report).
- `equipmentDescription` (a multi-language string) is not written by the stock exporter; the description is kept in the custom attribute `Name`.

## Quantities mapped to native DEXPI attributes

- CentrifugalPump.designVolumeFlowRate <- design_volume_flow_rate
- PlateHeatExchanger.designHeatFlowRate <- design_heat_flow_rate
- Vessel.nominalCapacityVolume <- tank_volume

## Attributes carried as text custom attributes

`air_flow_rate`, `air_inlet_temperature`, `air_outlet_temperature`, `arrangement`, `capacity_fraction`, `cold_inlet_temperature`, `cold_outlet_temperature`, `cold_power`, `cold_regime`, `compressor_type`, `delivery_pressure`, `heating_medium_change`, `hot_power`, `hot_regime`, `label`, `manufacturer`, `members`, `minimum_technical_production`, `operating_temperature`, `refrigerant`, `required_water_regime`, `stage`, `steam_supply_pressure`, `variable_frequency_drive`, `water_flow_rate`, `water_inlet_temperature_max`, `water_outlet_temperature`
