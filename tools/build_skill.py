"""Build the transferable skill: skills/pid-pfd-from-spec + the engine -> dist/pid-pfd-from-spec.skill.

    python tools/build_skill.py            # bundle the engine into the skill folder and write the .skill package

The .skill file is a zip of the skill folder (SKILL.md, references/, scripts/engine/). It installs as a Claude skill
(upload it, or unzip it into ~/.claude/skills/ or <project>/.claude/skills/) and needs nothing from this repository.
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "pid-pfd-from-spec"
ENGINE = SKILL / "scripts" / "engine"
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache"}


def bundle_engine() -> None:
    if ENGINE.exists():
        shutil.rmtree(ENGINE)
    ENGINE.mkdir(parents=True)
    shutil.copytree(ROOT / "pid_workflow", ENGINE / "pid_workflow", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "policies", ENGINE / "policies")
    shutil.copy2(ROOT / "pyproject.toml", ENGINE / "pyproject.toml")
    (ENGINE / "README.md").write_text(
        "Engine of the pid-pfd-from-spec skill (Python package `pid_workflow` + policies and rule packs).\n"
        "Use with `PYTHONPATH=<this folder>` and `python -m pid_workflow.cli`, or `pip install -e <this folder>`.\n",
        encoding="utf-8")


def validate() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: pid-pfd-from-spec\ndescription: "), "SKILL.md front matter"
    assert len(text.splitlines()) < 500, "SKILL.md should stay under 500 lines"
    for ref in ("extraction-kit.md", "rules.md", "engineering-notes.md", "outputs.md"):
        assert (SKILL / "references" / ref).exists(), ref
        assert f"references/{ref}" in text, f"SKILL.md does not point to references/{ref}"


def package(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{SKILL.name}.skill"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(SKILL.rglob("*")):
            rel = f.relative_to(SKILL.parent)
            if not f.is_file() or EXCLUDE_PARTS & set(rel.parts) or f.suffix == ".pyc":
                continue
            if len(rel.parts) > 1 and rel.parts[1] == "evals":  # test cases stay in the repository
                continue
            z.write(f, rel.as_posix())
    return target


def main() -> int:
    validate()
    bundle_engine()
    target = package(ROOT / "dist")
    n = len(zipfile.ZipFile(target).namelist())
    print(f"wrote {target} ({target.stat().st_size // 1024} kB, {n} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
