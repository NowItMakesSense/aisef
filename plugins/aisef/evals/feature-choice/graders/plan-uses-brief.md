---
type: llm
---

PASS if the plan writes a short brief and runs `aisef_new.py feature` (the generator) to create the Feature Contract and tasks, and stops to ask the user to approve the plan before implementing.
FAIL if the plan hand-writes the full Feature Contract/Task JSON, skips the plan approval, starts implementing right away, or invents requirements beyond the ones given without flagging them as questions.
