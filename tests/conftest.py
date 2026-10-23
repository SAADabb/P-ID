from __future__ import annotations

import copy
import shutil
from pathlib import Path

import pytest
import yaml

from pid_workflow.enrich import enrich
from pid_workflow.policy import load_policy
from pid_workflow.topology_io import load_topology

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "lpf_bsst"


def _require_lpf() -> None:
    if not (PROJECT / "source_topology.json").exists():
        pytest.skip("LPF/BSST project not present (projects/ is git-ignored)")


@pytest.fixture(scope="session")
def policy():
    _require_lpf()
    return load_policy(ROOT / "policies" / "generic.yaml", PROJECT / "project_rules.yaml")


@pytest.fixture(scope="session")
def source():
    _require_lpf()
    return load_topology(PROJECT / "source_topology.json")


@pytest.fixture(scope="session")
def enriched(source, policy):
    topo = copy.deepcopy(source)
    res = enrich(topo, policy)
    return topo, res


@pytest.fixture()
def project_copy(tmp_path: Path) -> Path:
    """A throw-away copy of the LPF/BSST project (without outputs) with the shared policies."""
    _require_lpf()
    shutil.copytree(ROOT / "policies", tmp_path / "policies")
    dst = tmp_path / "projects" / "lpf_bsst"
    shutil.copytree(PROJECT, dst, ignore=shutil.ignore_patterns("output", "reports", "working_topology.json", "__pycache__"))
    return dst


@pytest.fixture(scope="session")
def hints():
    _require_lpf()
    return yaml.safe_load((PROJECT / "layout_hints.yaml").read_text(encoding="utf-8"))
