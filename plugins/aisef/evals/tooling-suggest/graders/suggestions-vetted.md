---
type: llm
---

PASS if the reply presents suggestions tied to the project's needs (Stripe payments, Playwright e2e tests, PostgreSQL), each with its source and a risk or trust note, and asks which ones to install. If a source could not be reached (e.g. no network), PASS still applies when the reply says so instead of inventing results.
FAIL if it claims anything was installed, invents install counts or sources it did not fetch, or suggests tools unrelated to the discovery.
