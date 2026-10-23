"""Loading of the generic policy and the project rule file.

The generic policy holds defaults that apply to any project.  The project rule file
selects rule types, parameterises them and cites the specification sections that make them
explicit project requirements.  Explicit project values override generic defaults.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Rule:
    id: str
    type: str
    enabled: bool
    source: dict[str, Any]
    params: dict[str, Any]


@dataclass
class Policy:
    generic: dict[str, Any]
    project: str
    document: str
    language: str
    rules: list[Rule] = field(default_factory=list)

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    def rules_of_type(self, rtype: str) -> list[Rule]:
        return [r for r in self.rules if r.type == rtype and r.enabled]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_policy(generic_path: str | Path, project_rules_path: str | Path) -> Policy:
    generic = yaml.safe_load(Path(generic_path).read_text(encoding="utf-8"))
    proj = yaml.safe_load(Path(project_rules_path).read_text(encoding="utf-8"))
    # project-level overrides of generic defaults (if present) take precedence
    generic = _deep_merge(generic, proj.get("overrides", {}))
    rules = [
        Rule(
            id=r["id"],
            type=r["type"],
            enabled=r.get("enabled", True),
            source=r.get("source", {}),
            params=r.get("params", {}),
        )
        for r in proj.get("rules", [])
    ]
    return Policy(
        generic=generic,
        project=proj["project"],
        document=proj.get("document", ""),
        language=proj.get("language", "en"),
        rules=rules,
    )
