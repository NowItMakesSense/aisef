---
type: llm
---

PASS if the reply (1) says where the user is in the process and what comes next, (2) lays out the steps Grill (clarifying questions one at a time), Spec (solution, user stories and test seams confirmed with the user) and vertical slices (each slice cuts through the layers and is testable on its own), ending in plan approval, and (3) explains that /to-spec is done by the AISEF spec phase (stored in .aisef/), not by publishing to an issue tracker.
FAIL if it starts implementing code, splits the work into per-layer tasks (e.g. one backend task and one frontend task), skips the plan approval, or invents requirements beyond the ones given without flagging them as questions.
