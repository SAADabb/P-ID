# Instructions for agents

This repo turns engineering specifications into draft P&IDs. When the user gives a specification (cahier des charges),
use the skill `.claude/skills/pid-from-spec/SKILL.md` (extraction by you, everything else by `pid`). See also `AGENTS.md`.
Keep `python -m pytest -q` green, never invent values the document does not give, and never put coordinates in a topology.
