## AISEF

This project is governed by AISEF. Its state lives in `.aisef/` (contracts, blueprints, approvals,
authorizations, reports and a signed audit log). Inside Claude Code the `aisef` plugin enforces the
rules below with hooks; in any other tool they are **instructions you must follow**, because nothing
blocks you technically.

- **Do not invent requirements or business rules.** Investigate the repository first; ask when something is missing.
- **Work only inside an approved plan.** Features have a Feature Contract (`.aisef/contracts/features/`) and
  task contracts (`.aisef/contracts/tasks/`). Do not change scope or approved decisions on your own.
- **Small changes** (typo, text, trivial fix, non-breaking dependency patch) may skip the full cycle, but still
  need a maintenance task (`FEAT-MAINT`).
- **Never** commit, push, merge, tag or publish without the user's explicit approval for that specific operation.
  Approving a commit does not approve a push.
- **Never** read or write `.env`, keys, credentials or secrets, and never connect to a database or run migrations
  against one. Never deploy.
- **Never edit** `.aisef/audit/`, `.aisef/keys/`, `.aisef/approvals/` or `.aisef/authorizations/` by hand:
  only the user decides approvals.
- Whoever implements a task does not validate it; acceptance criteria need evidence (tests run, output read).
- Never write secrets or your internal reasoning into logs, reports or docs.
