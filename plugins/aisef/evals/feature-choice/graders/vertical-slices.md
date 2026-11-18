---
type: llm
---

PASS if the plan breaks the feature into vertical slices (each one a thin end-to-end path that is testable on its own, with tests written before the code at agreed test seams).
FAIL if the plan splits the work by layer or role (e.g. a database task, then a backend task, then a frontend task) or does not mention writing tests first.
