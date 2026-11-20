---
type: llm
---

PASS if the plan runs the AISEF triage in code (`aisef_triage.py`, with paths/changes/size estimates) before choosing the path, and follows the lean path it yields: one vertical slice with tests first, no Engineering Blueprint, the triage output placed in the brief, and it stops for plan approval before implementing.
FAIL if the plan skips the triage and picks the path by itself, writes a blueprint or several slices for this one-file change, uses the quick/maintenance path for a behavior change, or starts implementing without plan approval.
