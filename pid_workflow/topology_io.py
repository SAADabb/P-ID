"""Reading and writing topology JSON in a stable, diff-friendly form."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .schema import Topology


def load_topology(path: str | Path) -> Topology:
    return Topology.model_validate_json(Path(path).read_text(encoding="utf-8"))


def dumps_topology(topo: Topology) -> str:
    data = topo.model_dump(mode="json", by_alias=True, exclude_none=False)
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def save_topology(topo: Topology, path: str | Path) -> str:
    """Write the topology and return the SHA-256 of what was written."""
    text = dumps_topology(topo)
    Path(path).write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
