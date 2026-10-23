# Instructions for coding agents

This repository turns an engineering specification (cahier des charges, PDF or text) into a draft P&ID:
one A0 sheet, a DEXPI Proteus XML file with the same drawing, engineering lists and a decision register.

**When the user gives you a specification, follow `.claude/skills/pid-from-spec/SKILL.md` step by step.**
You do the reading and engineering reasoning (the extraction); the `pid` command does everything else.

Rules that always apply:
* Never invent values the document does not give (pressures, relief sizing, fail positions, materials, sizes, ranges,
  equipment). Record every gap as an open point.
* Every fact carries its page, section and a verbatim quote; interpretations are marked as such with a note.
* No coordinates in the topology; layout is computed.
* Keep `python -m pytest -q` green.

Setup: `pip install -e .` (Python ≥ 3.11; needs pydexpi, reportlab, pypdf, lxml, openpyxl). Without installing,
use `python -m pid_workflow.cli <command>` from the repository root instead of `pid <command>`.
Project folders under `projects/` are local work and git-ignored.
