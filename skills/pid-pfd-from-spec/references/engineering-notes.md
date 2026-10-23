# Engineering notes - traps seen on real specifications

These come from processing real cahiers des charges (utilities, heat pumps, steam, chilled water) with independent
agents and a process-engineering review. Read them before extracting.

## Reading

* **Check the physics of your reading.** Do duties and flows balance (Q = ṁ·cp·ΔT)? Does each closed loop have a
  driver (pump, compressor)? Does each steam user have a supply and a condensate return? Does each vessel have an
  outlet per phase? A specification often describes the process in words that, read literally, contradict its own
  tables. Draw the physically consistent reading with `s.interp`, and record the literal one as an `ambiguity`/
  `conflict` open point - that is a decision for the engineer, not for you.
* **Two circuits through one exchanger**: e.g. "the well water passes through the exchangers then to the heat pumps"
  may mean an open circuit (well → exchanger → discharge) and a closed loop (tank → exchanger → evaporators → tank). The
  temperature regimes usually decide; say which you chose and why.
* **Tables vs prose**: a table row can give per-unit values for a pair of machines that the prose describes as a
  cascade. Connections follow the prose; the table conflict is an open point.
* **"À définir", "TBD", "à confirmer", "position exacte à confirmer"** are open points, never values. If no reading is
  defensible, leave the item unconnected (it gets dashed TBC stubs) with an open point.
* **Limits are not values**: "< 30 °C", "limited to 85 °C", "minimum 5.8 t/h" go into `*_max` / `*_min` properties or
  attributes, not into the operating value.
* **Network flows**: a flow stated for a whole network (e.g. "4 bar: 9.1 t/h") belongs to the network battery limit or
  its main header line - not to every branch. The PFD prints a repeated stated flow once and writes "see n" elsewhere,
  but record it once anyway.
* **Pumps the document does not mention are not drawn.** A loop without a stated driver is an open point
  ("no circulation pump stated"). The same for condensate returns, boiler fuel/feed water, make-up.
* **One valve named, two needed?** ("une vanne déversante 8→4→1 bar") - draw what is needed with `s.interp` and an
  open point, or draw what is written and raise the question. Never silently.
* **Users and networks**: consumers outside the scope are best drawn as battery limits (with their stated
  consumption); consumers inside the scope as equipment. Out-of-scope items that must appear ("à représenter en limite
  de fourniture") get a `scope` open point.
* **3-way valves** are not modelled as such: draw a control valve on the by-pass/mixing branch with `s.interp` and an
  open point; the rule pack's control-valve station should then be switched off for it.

## Modelling

* Parallel identical units (duty/stand-by pumps, 3 × 50 % exchangers, identical heat pumps) → build them with
  `s.bank` or with split/merge manifolds on every connected side. The P&ID shows every unit with its auxiliaries; the
  PFD draws them once ("P-201/202/203 (3 units)").
* Keep unit names free of tags and numbering ("Primary chilled-water pump", tag "P-101") - names become labels.
* Give `header=True` only to real headers/collectors: the header-instrumentation rule puts a PT/TT set on each one.
* Record stated temperatures/pressures/flows/sizes on lines, duties and regimes on equipment: the stream table and the
  equipment summary of the PFD are built only from them.
* Ids: `eq.*`, `pc.*`, `mf.*`, `bc.*`, `ln.*` are conventions, not requirements; keep them short and stable - review
  answers and hints refer to them.

## Layout

* Write `layout_hints.yaml`. 4-8 plant areas of 10-25 objects; rows in process order (sources/production left and top,
  users right and bottom). Put a header in the area of its users when its return lines would otherwise loop around.
* Look at both sheets after every run. Typical fixes: move an item to the area it connects to most; split a crowded
  area; reorder rows to shorten long cross-sheet runs.
