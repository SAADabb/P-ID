# Enrichment log

What each rule did on its last run. “reused” means the requirement was already satisfied (nothing duplicated).

| Rule | Added | Reused | Blocked (prerequisite missing) | Skipped |
|---|---|---|---|---|
| `control_loop.from_requirement` | 0 | 1 | 2 | 0 |
| `control_valve.manifold` | 0 | 12 | 0 | 0 |
| `header.instrumentation` | 0 | 10 | 0 | 0 |
| `mode.isolation` | 0 | 9 | 0 | 0 |
| `pump.auxiliaries` | 0 | 18 | 0 | 0 |
| `unresolved.generated` | 0 | 0 | 0 | 0 |
| `vessel.auxiliaries` | 0 | 30 | 0 | 0 |

## Blocked or skipped

- `control_loop.from_requirement` — cr.spill_8_4: not instrumented – missing controlled variable, measurement location, setpoint
- `control_loop.from_requirement` — cr.spill_4_1: not instrumented – missing controlled variable, measurement location, setpoint
