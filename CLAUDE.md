# Instructions for agents

This repo turns engineering specifications into draft P&IDs. To process a new specification, use the skill
`.claude/skills/pid-from-spec/SKILL.md` (extraction by you, everything else by `pid run`).
Keep `pytest -q` green, never invent values the document does not give, and never put coordinates in a topology.
