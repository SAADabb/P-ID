"""The skill's extraction template must produce a valid topology that runs through the pipeline."""

import runpy
import shutil
from pathlib import Path

import yaml

from pid_workflow.pipeline import run_all
from pid_workflow.topology_io import load_topology

from .conftest import ROOT


def test_template_runs_end_to_end(tmp_path: Path):
    proj = tmp_path / "projects" / "tpl"
    (proj / "extraction").mkdir(parents=True)
    shutil.copytree(ROOT / "policies", tmp_path / "policies")
    tpl = ROOT / ".claude/skills/pid-from-spec/templates/extract_template.py"
    script = proj / "extraction" / "extract_tpl.py"
    shutil.copy(tpl, script)
    runpy.run_path(str(script), run_name="__main__")
    assert load_topology(proj / "source_topology.json").equipment
    (proj / "project.yaml").write_text(yaml.safe_dump({
        "name": "tpl", "source_document": "x.pdf", "source_topology": "source_topology.json", "working_topology": "working_topology.json",
        "rules": "project_rules.yaml", "layout_hints": "layout_hints.yaml", "generic_policy": "../../policies/generic.yaml",
        "rendering": "../../policies/rendering.yaml", "output_dir": "output", "reports_dir": "reports"}), encoding="utf-8")
    shutil.copy(ROOT / "projects/lpf_bsst/project_rules.yaml", proj / "project_rules.yaml")
    res = run_all(proj, render=False)
    assert res.validation.ok and res.roundtrip.ok and res.idempotent
