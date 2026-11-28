<p align="center"><img src="docs/img/banner.svg" width="100%" alt="AISEF. Fast agents are easy. Agents you can audit are not."></p>

<p align="center"><b>English</b> · <a href="README.pt-BR.md">Português</a> · <a href="README.zh-CN.md">简体中文</a></p>

<h3 align="center">The evidence trail for AI-assisted engineering. Rules enforced in code, every step in a signed log, every requirement traced to its proof, and a package your auditor can verify on their own.</h3>

AISEF is a Claude Code plugin for teams that must show what the AI did, not just ship faster. A plain-language request becomes a specified feature: triaged in code, split into vertical slices, built test-first by agents in parallel, reviewed by specialists, validated by a different agent and accepted by you. Every tool call goes through a policy enforced in code, and every step lands in a signed, tamper-evident log that CI can verify on each pull request.

| **175** | **2,800+** | **207** | **66** | **~0.2 s** |
|---|---|---|---|---|
| consistency rules in `aisef-check` | automated checks, CI on Linux and Windows | gateway cases, 80 of them bypass attempts, all blocked ([limits](#what-the-gateway-does-not-guarantee)) | specialist agents (15 active on a new Python project) | gateway cost per tool call on Windows ([measured](tools/bench_hooks.py)) |

<p align="center"><img src="docs/img/panel-now.gif" width="100%" alt="The AISEF live panel: the Now screen with a pending decision and process health, then the execution map, a slice drawer, a subagent drawer, the parallel lanes and who spawned whom"></p>
<p align="center"><sub>The live panel on demo data: who is running, who is waiting and why, which subagent each agent spawned, and the lanes over time.</sub></p>

## What only AISEF covers

| Need | What AISEF gives you |
|---|---|
| **Rules that hold** | An Execution Gateway decides allow, ask or deny on every tool call, in code. It reads commands token by token (`bash -c`, `eval`, `$(...)`, inline code), keeps the signing key out of reach, and caps each agent with its own permission ceiling. |
| **A log nobody can quietly edit** | Each event is hash-chained and signed with Ed25519; the head lives outside the repository. In a team, each person writes to their own stream with their own key, so merges never conflict and every approval carries the signature of whoever gave it. |
| **Every requirement traced to its proof** | Requirement → slice → acceptance criterion → test → evidence, checked by 175 rules. `aisef_sysgraph.py` answers "what does this requirement touch?" without a model. |
| **Proof on every pull request** | The `aisef-verify` GitHub Action fails the PR if the log was tampered with, if the log shrank since the base branch, if `aisef-check` finds an error, or if the PR touches a task nobody validated. |
| **Evidence your auditor can verify** | `aisef_evidence.py` packs a feature (contracts, reports, approvals, signed events, public keys) with a controls table for SOC 2 CC8.1, ISO/IEC 27001:2022 A.8.32 and A.5.3, ISO/IEC 42001, EU AI Act art. 12 and NIST AI RMF. With `--in-toto`, each task gets a signed in-toto attestation (DSSE). The package verifies itself, without the project. |
| **Observability you already use** | `aisef_otel.py` exports each feature as OpenTelemetry traces (OTLP/JSON) with the GenAI conventions: one span per agent attempt, one per tool call. |

AISEF is for teams in regulated settings and for anyone who has to show how an AI-made change was authorized, tested and approved. If you only want the fastest possible agent, plain Claude Code is cheaper; the "Measured" section below has the numbers.

## The toolbox

Everything below ships in one plugin, runs locally with the Python standard library, and works on Windows, macOS and Linux.

| | Tool | What it gives you | How you reach it |
|---|---|---|---|
| 🧭 | **Triage in code** | Picks the path for each change (quick, lean or full) from sensitive paths, change kinds, size and risk. The lean path is one TDD slice with no blueprint. Profiles (solo, team, regulated) set the defaults. You can move up a path, never down. | `aisef_triage.py` |
| 👥 | **Agent team** | 66 specialists: executors, reviewers, fixers and advisors, each with a signed permission ceiling. A new project starts with the core team plus your stack; the rest join on request. | automatic delegation, `aisef:<agent>` |
| 🧭 | **Architecture radar** | It finds your stack and your style (Clean, hexagonal, DDD, CQRS, modular monolith, microservices, MVC, vertical slices…). It checks the dependency rule and module boundaries from your imports, then recommends improvements. | `aisef_project.py detect` |
| 📚 | **Best-practice library** | 33 rules: common ones (Clean Code, SOLID, testing, security, Git), one per architecture style with a "when not to use it" section, and one per language. | `aisef_setup.py --apply` (during init) |
| 🔍 | **Review gate** | Reviewers are picked in code for each task: general, language, database, security, architecture and tests. All of them must approve before the validator runs. High-risk tasks get two independent reviews. | automatic in every wave |
| ✅ | **verify-loop** | Build → types → lint → tests → secrets in the diff → diff summary, ending in PASS or FAIL, with evidence saved for the task. | `aisef_project.py verify-loop` |
| 🛡️ | **Execution Gateway** | Every tool call gets allow, ask or deny, enforced in code. Each Git operation needs its own approval. No `--no-verify`. Databases and deploys are denied. Agents cannot loosen lint configs. | always on (hook) |
| 🧾 | **Signed audit log** | Lifecycle, decisions, shell commands and every blocked or questioned call go into a hash-chained log signed with Ed25519; file edits go to a hash-chained telemetry. One stream per person in a team. | `aisef-check`, `aisef_streams.py` |
| ✔️ | **CI verification** | The `aisef-verify` Action checks the log, the consistency rules and the tasks touched by each pull request, with a job summary. | `.github/actions/aisef-verify` |
| 📦 | **Evidence package** | A self-verifying package per feature, with SOC 2, ISO 27001, ISO 42001, EU AI Act and NIST AI RMF controls mapped to the evidence, and in-toto attestations. | `aisef_evidence.py build` |
| 🔭 | **OpenTelemetry export** | Features as traces with GenAI attributes, for the observability stack you already run. | `aisef_otel.py export` |
| 🗳️ | **Approval Center** | Each decision shows its impact, diff, rollback and risk. Only you decide, through the native prompt. | `aisef-approve` |
| 📊 | **Live panel** | Execution map, who spawned whom, decisions waiting for you, traceability, parallel lanes. | `aisef-panel` |
| 💸 | **Model router and budget** | Haiku → Sonnet → Opus, chosen by risk and complexity. The continuous loop stops on a feature budget (time, tokens, dispatches), on the same failure twice, and on a stalled agent. | automatic |
| 🌳 | **Worktree per slice** | Slices that touch the same file run side by side, each in its own worktree; the merge goes through the feature scope and a conflict becomes a new attempt. | `parallel.mode = worktree` |
| 🧠 | **Reviewed learning** | Lessons drawn from errors already on record. They apply only after you approve them and lose confidence when they stop helping. | `aisef_learn.py` |
| 🎨 | **Design authority** | One approved typography, palette and component set per project, checked in the code. | `aisef-design` |
| ❓ | **Ask mode** | Answers questions without changing anything, researching the web with cited sources. | `/aisef:ask` |

## Meet the team

Agents load only when they apply. A new project starts with the core team (13 subagents: the builders, the reviewers that run on every task, the validator and three advisors) plus the language and framework agents the radar detects, so a Python project starts with 15 and never pays for the Swift reviewer. The extended team joins when you ask or when the work calls for it.

| Kind | What they do | Agents |
|---|---|---|
| **Builders** (7) | Implement inside the task contract, test-first | `implementer` (whole vertical slices with TDD), `backend`, `frontend`, `database`, `devops`, `doc-updater`, `e2e-runner` |
| **Reviewers** (10) | Report with proof; never touch the code | `code-reviewer`, `architecture-reviewer`, `database-reviewer`, `security`, `qa`, `pr-test-analyzer`, `silent-failure-hunter`, `type-design-analyzer`, `comment-analyzer`, `agent-evaluator` |
| **Language reviewers** (19) | Idioms, security and pitfalls of your stack | Python, Django, FastAPI, TypeScript/JavaScript, React, Vue, Go, Rust, Java (Spring/Quarkus), Kotlin, Swift, C#, F#, C++, PHP/Laravel, Ruby/Rails, Flutter, Godot, plus `a11y-architect` (WCAG 2.2) |
| **Fixers** (16) | Smallest diff that works; never loosen a rule to pass | `code-simplifier`, `refactor-cleaner`, `performance-optimizer`, and 13 build resolvers (TS/JS, Python, Django, Go, Rust, Java, Kotlin, Swift, Dart/Flutter, C++, PyTorch, HarmonyOS, React) |
| **Advisors** (10) | Investigate and propose; you decide | `planner`, `architect`, `code-architect`, `code-explorer`, `spec-miner` (specs out of legacy code), `domain`, `docs-lookup`, `commit-reviewer`, `conversation-analyzer`, `harness-optimizer` |
| **Domain reviewers** (3) | Switched on when the domain shows up | `rag-pipeline-reviewer`, `mle-reviewer`, `healthcare-reviewer` |
| **Validator** (1) | Independent; never validates its own work; read-only Git | `validator` |

Every reviewer follows the same discipline:
- it reports only findings it is more than 80% sure of;
- CRITICAL and HIGH findings need the line, the failure scenario and the reason existing guards miss it;
- zero findings is a valid result.

Every fixer works under one rule: no `any`, no `# noqa`, no skipped tests to make the build pass.

## The architecture radar

```
$ python aisef_project.py detect --project .
Stacks: TypeScript, React, C# / .NET (manager: npm)
Architecture (heuristic, confirm with the user):
  - DDD strategic: confidence 0.89 (folder backend/src/Shop.SharedKernel; file docs/glossary.md)
  - Modular monolith: confidence 0.80 (3 modules in backend/src/Modules/; module with layers: Orders)
  - Clean Architecture / Onion: confidence 0.67 (folder .../Shop.Orders.Domain; folder .../Shop.Orders.Application)
  - Vertical slices: confidence 0.67 (folder frontend/src/features; folder frontend/src/shared)
Module boundaries: 3 module(s), 204 file(s) scanned, 2 cross-module dependencies:
  suggestions -> accounts (application); suggestions -> accounts (domain, VIOLATION)
Recommendations (your decision):
  - REC-DEPENDENCY-RULE: Fix the dependency rule. Suggestions.Infrastructure/EfCatalog.cs:2 imports Shop.Accounts.Domain
Applicable practices: common, lang/typescript, lang/web, lang/csharp, architecture/modular-monolith, architecture/clean-architecture, ...
```

The radar was measured on 10 public reference repositories (Clean Architecture templates, eShop, modular-monolith-with-ddd, domain-driven-hexagon and others). It got 9 of them right, with no false dependency violations.

It never changes anything on its own. You adopt a style through the Approval Center, and from then on the `architecture-reviewer` holds every delivery to it. Each practice says when **not** to use it, so AISEF will not push DDD or CQRS onto a simple CRUD app.

## Measured, not claimed

`tools/bench_outcomes.py` runs the same task three ways. The tests are hidden from the agent and only run after it finishes. Results for `feat-slugify`, Sonnet, 3 repetitions:

| Arm | Hidden tests | Median cost | Median time |
|---|---|---|---|
| Plain Claude Code | 3/3 runs at 7/7 | US$ 0.13 | 26 s |
| AISEF with the review gate | 3/3 runs at 7/7 | US$ 1.49 | 335 s |
| AISEF without reviewers | 3/3 runs at 7/7 | US$ 1.32 | 333 s |

The review gate adds about 13% per slice, which is within run-to-run noise. On a task this small, the full process costs about 11× more than plain Claude Code. What you pay for is the spec, the TDD evidence, independent validation, review and the signed record. Quality gains on larger, real features are being measured next.

Features from 0.13 on are covered by CI, including a test that runs a whole feature cycle through all 48 combinations of profile, path, parallelism, telemetry and per-person log. They have not run in a real project yet. The [maturity table](docs/reference/maturity.md) shows the level of each one, whether it is on by default, and how to turn it back.

## What's new

- **0.17.2, authorizations that actually end.** A scope authorization now closes when its feature is accepted and expires when its time runs out, with an event in the signed log, instead of staying active forever. The check stops warning about things there is nothing to do about, and truncated text in the panel is readable by keyboard and touch.
- **0.17.1, features linked and a panel that works on any screen.** New features must declare which features they depend on, and the check flags the ones that do not. The panel shows every screen on phones, keeps keyboard focus visible, returns focus when the drawer closes, lets you drag the feature pills sideways, and explains an integrity failure: what changed, which event, how it was caught and when it could have happened.
- **0.17.0, closing what this README promises.** The gateway closes 13 more bypasses (inline interpreter code, the whole home folder, packages fetched and run on the spot), asks before adding a new dependency, and tightens data egress once a session has read untrusted web or MCP content; `team` and `regulated` get a strict sandbox. TDD red and green are checked against the signed log, the validator works blind to the executor's claims, milestones can get an RFC 3161 timestamp and the signing key can live in the OS vault (both opt-in). The evidence package adds signed in-toto attestations and ISO/IEC 42001, EU AI Act art. 12 and NIST AI RMF controls. Reviewers can now be scored on planted bugs, and the outcome benchmark has a lean arm; the paid runs are still to come.
- **0.16.0, a panel you can trust and another session in the same project.** The panel shows accepted features as accepted, maps agents to the slice they worked on with a per-feature timeline and an overview in cards, and only raises the gateway alarm when it matters. Two Claude Code sessions in the same project now see each other, reserve separate areas, and get warned before editing or committing over the other's work.

Full history in the [CHANGELOG](CHANGELOG.md) (Portuguese).

## One feature, two ways

Request: *"password reset by email; the link is valid for 30 minutes and can be used only once"*.

| With a bare prompt | With AISEF |
|---|---|
| The agent starts writing code right away. | AISEF states the phase: "We are in Specify. Next: Grill → Spec → Slices." |
| Table, endpoint and screen all at once; no test before the code. | **Grill:** three questions, one at a time, each with a recommendation (link lifetime? response for unknown emails? reusable link?). Nothing is invented. |
| It decides on its own that "the link lasts 24 h" and that "the response differs when the email does not exist". Neither was asked for, and the second leaks who has an account. | **Spec** with the test seams you confirmed (`POST /auth/reset`, `POST /auth/reset/confirm`). |
| It runs a command against the local database "to check the table". Nothing stops it, nothing records it. | Three **vertical slices**; you approve the plan. One call dispatches the wave: two slices in parallel to the `implementer`. |
| "Done, all tests pass": the tests were written after the code. | The agent tries `psql` and gets **deny** (a database from a session is treated as production). It is logged. |
| `git push` goes along, because the agent assumed you wanted it. | The `tdd_evidence` shows the test **failing before it passed**, and the check verifies the order. Specialist reviewers approve, then a different model validates. Your acceptance, and `git push` goes through the native prompt that only you can answer. |

On the left, the work is fast and opaque. On the right, every decision was yours, every requirement has a test and evidence, and six months from now the panel and the log show exactly what happened.

## How it works

Skills tell the model what to do. The **gateway** decides what it **may** do.

### What the gateway does not guarantee

The gateway is a hook that runs as your own OS user. It reads each tool call, so it catches what it can read: it does not see what a script written now does when it runs later, and a command it cannot read becomes a question, not an allow. The hard boundary is the OS: turn on Claude Code's native sandbox (Linux, macOS, WSL2) or run the agents in a devcontainer. The `team` and `regulated` profiles write a strict sandbox into the project settings (no `dangerouslyDisableSandbox` escape, no reads of `~/.aisef`), and the doctor warns while it is not in effect. On native Windows the sandbox does not exist: use WSL2 or a devcontainer.

```mermaid
flowchart TD
  A[Agent requests a tool<br/>Bash · PowerShell · Edit · MCP] --> G{Execution Gateway<br/>PreToolUse}
  G -->|Ask mode and a write| D[deny]
  G -->|outside the agent ceiling| D
  G -->|policy: free| OK[runs]
  G -->|policy: approval| ASK[native prompt<br/>only you answer]
  G -->|reinforced, not recorded| D
  ASK --> OK
  OK --> L[(Hash-chained log<br/>signed with Ed25519)]
  D --> L
  ASK --> L
```

The work follows Matt Pocock's method (grill → spec → tickets → TDD), with end-to-end traceability:

```mermaid
flowchart LR
  RD[Architecture radar<br/>+ best practices] --> DS[Discovery]
  DS --> GR[Grill]
  GR --> SP[Spec<br/>+ test seams]
  SP --> FT[Vertical slices]
  FT -->|you approve| ON[Parallel wave<br/>TDD per slice]
  ON --> VL[verify-loop]
  VL --> PC{precheck<br/>no model}
  PC -->|failed| ON
  PC --> RV[Review gate<br/>specialists in parallel]
  RV -->|WARNING or BLOCK| ON
  RV --> VA[Independent<br/>validator]
  VA -->|rejected| ON
  VA --> AC[Your acceptance]
```

## The panel

<p align="center"><img src="docs/img/panel-tour.gif" width="100%" alt="Tour of the eight panel screens and the global search"></p>

Eight screens on an icon rail. Each one is derived from the contracts and the signed log, and none is a source of truth:

| Screen | What you see |
|---|---|
| **Now** | What runs right now and what waits, the decision waiting for you with the command to copy, and the process health: attention cost, how each slice was proven, first-pass validation and pace, cost in your local currency (per day, model and feature) and shortcuts to proof gaps, risks and decisions |
| **Agent map** | The feature graph (which feature depends on or derives from which), each feature's waves and agents, and the agents in time or as the tree of who spawned whom |
| **Features and slices** | Each feature on a timeline from the first agent to acceptance, with the slices that came back from the validator or skipped the TDD red; open a feature for its slices, attempts, TDD cycle and reports |
| **Traceability** | A proof matrix (one square per requirement) that leads to each requirement's chain: slice → criterion → evidence, with impact search and a "gaps only" filter |
| **Governance** | Pending decisions, a timeline of every decision with its wait (and the ones recorded before they were requested), architecture choices with the discarded options, and open risks by severity and feature |
| **History** | What guarantees the record (hash chain, Ed25519 signatures, external anchor), when the work happens by day and hour, and the signed log page by page |
| **Engineering** | Every blueprint side by side (components, personal data, threats, migrations) and the selected one in detail: architecture and data diagrams, endpoints, threats and migrations |
| **Agent team** | Who builds, reviews and validates, with each agent's cost, the agents outside the team, and whether each approved lesson actually fixes what it targets |

A broken log puts a red banner on top and hides every approve command. Run it live with `build_panel.py --serve` (it refreshes every 3 s without losing scroll, filters or the open drawer) or as a static page.

## Where AISEF sits among the alternatives

Based on each project's README and official docs as of 2026-11-18. "Instruction" means the process relies on the model obeying; "enforced" means code prevents it.

| | Specs | Enforcement | TDD | Parallelism | Traceability | Audit | Cost by risk |
|---|---|---|---|---|---|---|---|
| **AISEF** | ● spec + slices | ● gateway, per-agent ceiling | ● red→green checked | ● waves + per-wave validation | ● requirement→evidence | ● hash + Ed25519 | ● L0–L6 |
| Spec Kit (150k★) | ● | ◐ extension hooks | – | – | ◐ | – | – |
| Superpowers (321k★) | ◐ | ◐ instruction + bootstrap | ● | ● | – | – | ◐ |
| BMAD (55k★) | ● | – instruction | ◐ | ◐ | ◐ IDs with source | – | – |
| OpenSpec (75k★) | ● | – instruction | – | – | ◐ | – | – |
| Kiro (AWS) | ● | ● hooks | ◐ | ● waves | – | – | – |
| Matt Pocock (327k★) | ● | – instruction | ● | ● | ◐ blocking edges | – | – |
| everything-claude-code (306k★) | ◐ | ● Node hooks | ● | ◐ | – | ◐ scanning | ◐ |
| Plain Claude Code | – | ● permissions and hooks | – | ● | – | – | ◐ manual |

● covers · ◐ partly · – not described

### Limits, stated up front

- The signed log does not protect against someone holding your machine's private key.
- The quick maintenance path has lighter traceability than the lean and full paths.
- A large wave on a single validator should be split.
- Claude Code environment variables can override the model router; the router warns when they do.
- If you approve without reading, no technical layer stops it.

### Adding up instead of competing

AISEF is the **spine** (governance, traceability, decisions and reviewed learning). The **muscle** comes from ready-made skills maintained by their authors:
- **Matt Pocock:** `grilling`, `domain-modeling`, `tdd` (preloaded in the `implementer` agent) and `code-review`.
- **Design:** UI/UX Pro Max, Taste and Impeccable, working inside a design authority you approve.
- **Code graphs:** codebase-memory-mcp (code) and Graphify (docs and decisions).

## Install

Requirements:
- Claude Code;
- Python 3.10+ with `pip install jsonschema cryptography`;
- on Windows, Git Bash (Claude Code already uses it for hooks).

```
/plugin marketplace add NowItMakesSense/aisef
/plugin install aisef@aisef
```

If the Python with `cryptography` is not the first one on your PATH, set `AISEF_PYTHON` to it (this also makes the hooks faster). To update an older install: `/plugin marketplace update aisef`, then `/plugin update aisef@aisef`.

## Start in 5 minutes

1. In a project folder, say **"start AISEF in this project"**. On an existing codebase, AISEF investigates before proposing anything.
2. Approve the agents and the native second-layer rules when asked. On an existing codebase, the **architecture radar** runs and presents your stack, your style and its recommendations. You adopt a style and install the matching **best practices** with one approval each.
3. Describe what you want. AISEF tells you which phase you are in and walks you through Grill → Spec → Slices up to the plan you approve.
4. Watch it live: `aisef-panel` opens the panel with the execution map, who spawned whom, the decisions waiting for you and the parallel lanes.
5. Just a question? `/aisef:ask <question>` answers without changing anything: it reads the project and, when the question calls for it, researches the web with cited sources, choosing the model by the question. `/aisef:modo ask` keeps the whole session read-only until `/aisef:modo exec`. See [how it compares to Cursor's Ask](docs/guide/ask-mode.md) (Portuguese).

To explore without spending tokens, follow the [walkthrough with the demo project](docs/guide/walkthrough.md) (Portuguese).

## Documentation

Start at [docs/README.md](docs/README.md) (Portuguese) for:
- concepts and the workflow;
- the policy, command and hook references;
- the generated list of check rules;
- the [architecture decisions](docs/adr/README.md);
- the [roadmap](docs/roadmap.md).

## Development

```
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Windows
python run_tests.py
claude plugin validate plugins/aisef
claude plugin eval plugins/aisef --tag trigger --no-publish
```


## License

MIT
