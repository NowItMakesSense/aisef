---
type: llm
---

PASS if the plan ties the search to the project's discovery (e.g. Stripe, Playwright, PostgreSQL from .aisef/discovery.md), uses ready-made sources (find-skills / `npx skills find` / skills.sh for skills, the MCP Registry for MCP servers, `claude plugin list --available` or a plugin marketplace for plugins), vets candidates (source, adoption, risk) and says nothing is installed until the user chooses.
FAIL if it proposes installing anything without the user's choice, uses global or confirmation-skipping installs (`-g` with `-y`) as the plan, or recommends tools from memory without searching any source.
