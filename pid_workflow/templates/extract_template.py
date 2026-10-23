"""Extraction record for {name}: what the specification says, as a topology.

Written by the agent after reading every page (source/pages/page_NNN.txt).  Run:

    python projects/{name}/extraction/extract_{name}.py      # writes ../source_topology.json

Every quote is checked against the document when the script runs; a wrong quote stops it with the page
where the text really is.  See pid_workflow/extract_kit.py for the full API.
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[3]
if (_repo / "pid_workflow").is_dir():  # inside the repository: no install needed (elsewhere: PYTHONPATH / scripts/pid)
    sys.path.insert(0, str(_repo))

from pid_workflow.extract_kit import Spec  # noqa: E402

s = Spec(__file__, drawing_id="PID-{NAME}-001", title="TITLE – draft P&ID", project="PROJECT", language="{language}")

# ---------------------------------------------------------------- 1. areas (plant sections named by the document)
# q = s.src(1, "1. Section title", "verbatim words from page 1")
# s.area("ar.main", "Main area", q)

# ---------------------------------------------------------------- 2. equipment (DEXPI class; real tags only if the text gives them)
# s.equipment("eq.tank", "Feed tank", "Tank", "ar.main", q, tag="T-001", nozzles={{"out": "outlet"}},
#             attrs={{"volume": s.val(50, "m3", q)}})
# Parallel units: create each unit, then s.bank("feed_pumps", [...], inlet=..., outlet=..., service=..., src=q)

# ---------------------------------------------------------------- 3. lines (flow direction, service name, stated properties)
# s.line("eq.tank:out", "eq.pump:suction", "Process water", q)

# ---------------------------------------------------------------- 4. valves / instruments the text itself names, control, modes
# s.valve("pc.xv1", "Isolation valve to the users", "isolation", "ar.main", q)
# s.control("cr.p", "Keep the header at 6 bar", q, variable="pressure", measured_at_line="ln.004", final_element="pc.pcv1",
#           setpoint=s.val(6, "bar g", q), controller_required=True)

# ---------------------------------------------------------------- 5. everything missing, ambiguous or conflicting
# s.unresolved("ur.sizes", "missing_value", "Line sizes are not given.", ["eq.pump"], q, question="Line sizes?")

if __name__ == "__main__":
    s.save()
