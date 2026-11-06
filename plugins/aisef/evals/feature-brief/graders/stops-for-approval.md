---
type: llm
---

PASS if the final reply presents the plan (requirements and tasks) and asks the user to approve it, without claiming the plan is already approved and without starting implementation.
FAIL if it says the code was implemented, approves the plan itself, or invents requirements beyond the two the user gave (percent range 1-50% and invalid coupon rejected) without flagging them as questions.
