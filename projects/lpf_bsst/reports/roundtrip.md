# Round-trip verification — `pid_draft.proteus.xml`

**Result: PASS** — the XML was read back twice (lxml and pyDEXPI's own loader) and compared with the working topology.

| Check | Result | Detail |
|---|---|---|
| XML graph: every topology line is exactly one pipe with the right endpoints | PASS | 178 lines in 104 segments; missing 0, unexpected 0, wrong endpoints 0 |
| every pipe segment carries the Service attribute of its line | PASS | 104 segments; all match |
| manifolds exported as PipeTee chains (n-1 tees, 3 nodes, run 1→2) | PASS | 61 tees for 38 manifolds |
| equipment, valves and boundaries: class, tag, nozzles preserved | PASS | 45 equipment, 59 valves, 7 boundaries; all match |
| future equipment carries LifeCyclePhase="Future" | PASS | eq.hp_3a, eq.hp_3b |
| instruments: tag and sensing location preserved | PASS | 21 instruments; all match |
| control loops: measurement → controller → final element preserved | PASS | 1 loop(s); all match |
| external segment ends: tee branch = node 3, nozzle = no node | PASS | 178 ends; all match |
| pyDEXPI loader sees the same item-to-item pipe connectivity as written | PASS | 178 item edges written, 178 loaded |
| pyDEXPI loader: equipment classes, tags and nozzle counts | PASS | 45 items; all match |
| pyDEXPI loader: piping systems/segments and instrumentation counts | PASS | 104 segments (XML 104), 21 instrument functions, 1 loops |
| pyDEXPI loader: no errors when re-reading the XML | PASS | 0 error(s), 3 warning(s) |

## Loader warnings

pyDEXPI's loader warns about drawing references because the file carries no graphical information; the graph is unaffected:

- Source node (3×)

## Method and known pyDEXPI 1.2.0 limits

- Edges are compared as `(object, port) → (object, port)`; manifold ports are recovered from the tee chain recorded in the XML (`TopologyId`, `TeeIndex`).
- pyDEXPI's Proteus **exporter** writes only equipment, nozzles and metadata; piping and instrumentation are written by `pid_workflow/proteus_ext.py`, which plugs into pyDEXPI's exporter framework and follows the structure its **parser** reads.
- pyDEXPI's loader ignores custom attributes and the `FromNode`/`ToNode` indices, so those are verified in the XML directly.
