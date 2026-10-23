"""The workflow an agent follows on a new specification, without any existing project:
pid new -> extraction with the kit (verbatim quotes) -> good-practice pack -> pid run."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pid_workflow.extract_kit import QuoteError, Spec
from pid_workflow.onesheet import onesheet_qa
from pid_workflow.pipeline import run_all
from pid_workflow.scaffold import check_project, new_project

from .conftest import ROOT

SPEC = """Cahier des charges – Station de pompage d'eau traitée

1. Description
La bâche de stockage T-10 (volume 30 m3) alimente deux pompes centrifuges P-11 et P-12 en configuration 1 + 1 secours, débit unitaire 40 m3/h.
Les pompes refoulent vers le ballon tampon sous pression B-20 qui dessert le réseau usine (limite de fourniture).
\f
2. Exigences
Chaque pompe sera équipée d'une vanne d'isolement à l'aspiration et au refoulement, d'un filtre à l'aspiration et d'un clapet anti-retour.
Le ballon B-20 sera protégé par une soupape de sécurité.
Les diamètres des lignes ne sont pas définis.
"""


def _extraction(s: Spec) -> None:
    q1 = s.src(1, "1. Description", "La bâche de stockage T-10 (volume 30 m3) alimente deux pompes centrifuges P-11 et P-12 en configuration 1 + 1 secours")
    q2 = s.src(1, "1. Description", "Les pompes refoulent vers le ballon tampon sous pression B-20 qui dessert le réseau usine (limite de fourniture).")
    s.area("ar.main", "Treated-water pumping station", q1)
    s.equipment("eq.t10", "Storage tank", "Tank", "ar.main", q1, tag="T-10", nozzles={"out": "outlet"}, attrs={"tank_volume": s.val(30, "m3", q1)})
    for t in ("P-11", "P-12"):
        s.equipment(f"eq.{t.lower().replace('-', '')}", f"Pump {t}", "CentrifugalPump", "ar.main", q1, tag=t,
                    nozzles={"suction": "suction", "discharge": "discharge"}, attrs={"design_volume_flow_rate": s.val(40, "m3/h", q1)})
    s.equipment("eq.b20", "Pressurised buffer vessel", "PressureVessel", "ar.main", q2, tag="B-20", nozzles={"in": "inlet", "out": "outlet"})
    s.bank("pumps", ["eq.p11", "eq.p12"], inlet="eq.t10:out", outlet="eq.b20:in", service="Eau traitée", src=q1)
    s.boundary("bc.net", "Plant network", "out", "Eau traitée", "ar.main", q2)
    s.line("eq.b20:out", "bc.net:port", "Eau traitée", q2)
    s.unresolved("ur.dn", "missing_value", "Line sizes are not defined.", [], s.src(2, "2. Exigences", "Les diamètres des lignes ne sont pas définis."))


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A repository copy without any project (no history)."""
    shutil.copytree(ROOT / "policies", tmp_path / "policies")
    (tmp_path / "projects").mkdir()
    (tmp_path / "spec.txt").write_text(SPEC, encoding="utf-8")
    return tmp_path


def test_new_spec_from_scratch(repo: Path):
    root = new_project("station", repo / "spec.txt", repo=repo)
    assert (root / "source" / "pages" / "page_002.txt").exists()
    s = Spec(root / "extraction" / "extract_station.py", drawing_id="PID-ST-001", title="Station", project="Station", language="fr")
    _extraction(s)
    s.save()
    assert not [p for p in check_project(root) if p[0] == "error"]
    res = run_all(root)
    t = res.topology
    assert res.validation.ok and res.roundtrip.ok and res.idempotent
    assert onesheet_qa(res.onesheet) == []
    # the good-practice pack populated the pumps and protected the pressure vessel
    kinds = {(c.kind, c.function) for c in t.components}
    assert {("strainer", "strainer"), ("check_valve", "check"), ("valve", "isolation"), ("relief", "relief")} <= kinds
    assert any(i.isa_code == "PI" for i in t.instruments)
    assert any(u.id == "ur.gen.relief" for u in t.unresolved_requirements)
    # every pack addition says it is not stated in the specification
    gen = [c for c in t.components if c.provenance.origin == "generated"]
    assert gen and all("not stated in the specification" in (c.provenance.explanation or "") for c in gen)
    assert (root / "output" / "pid_one_sheet_A0.pdf").exists() and (root / "output" / "engineering_lists.xlsx").exists()


def test_wrong_quote_is_rejected_with_the_right_page(repo: Path):
    root = new_project("station", repo / "spec.txt", repo=repo)
    s = Spec(root / "extraction" / "extract_station.py", drawing_id="X", title="X", project="X")
    with pytest.raises(QuoteError, match=r"page\(s\) \[2\]"):
        s.src(1, "2", "Le ballon B-20 sera protégé par une soupape de sécurité.")
    with pytest.raises(QuoteError, match="not in the document"):
        s.src(1, "1", "une phrase inventée")
    with pytest.raises(ValueError):
        s.interp(1, "1", note="")


def test_scaffolded_template_runs(repo: Path):
    root = new_project("tpl", repo / "spec.txt", repo=repo)
    script = root / "extraction" / "extract_tpl.py"
    txt = script.read_text(encoding="utf-8")
    assert "Spec(__file__" in txt and "{" not in txt.split("s = Spec")[0].split('"""')[-1]
    compile(txt, str(script), "exec")
    assert "process_good_practice" in (root / "project_rules.yaml").read_text(encoding="utf-8")


def test_unknown_service_gets_a_colour_and_a_line_number(repo: Path):
    root = new_project("station", repo / "spec.txt", repo=repo)
    s = Spec(root / "extraction" / "extract_station.py", drawing_id="PID-ST-001", title="Station", project="Station")
    _extraction(s)
    s.save()
    res = run_all(root, render=False)
    nums = {ln.line_number for ln in res.topology.process_lines if ln.service == "Eau traitée"}
    assert nums and all(n and n.startswith("ET-") for n in nums)


def test_pfd_from_the_same_extraction(repo: Path):
    from pid_workflow.pipeline import run_pfd

    root = new_project("station", repo / "spec.txt", repo=repo)
    s = Spec(root / "extraction" / "extract_station.py", drawing_id="PID-ST-001", title="Station – draft P&ID", project="Station")
    _extraction(s)
    s.save()
    r = run_pfd(root)
    t = r.pfd.topo
    assert r.roundtrip_ok and r.qa == []
    # P&ID detail is not on the PFD: no auxiliaries, no instruments; parallel pumps drawn once
    assert not [c for c in t.components if c.kind in ("strainer", "check_valve", "relief")] and not t.instruments
    assert len(r.pfd.banks) == 1 and r.pfd.banks[0].members == ["eq.p11", "eq.p12"]
    pump = next(e for e in t.equipment if e.id == "eq.p11")
    assert pump.tag == "P-11/12" and "2 units" in pump.name
    # streams: tank -> pumps -> vessel -> network, numbered in flow order, pump flow carried over (marked)
    assert [(x.frm, x.to) for x in r.pfd.streams] == [("T-10", "P-11/12"), ("P-11/12", "B-20"), ("B-20", "Plant network")]
    assert r.pfd.streams[1].values["Flow"].startswith("40 m3/h") and "Flow" in r.pfd.streams[1].derived
    assert t.metadata.drawing_id == "PFD-ST-001" and "PFD" in t.metadata.title
    assert all(f.exists() for f in r.files)
