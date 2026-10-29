# Culture-Fit

**Know who can decide. Ask a human when it matters.**

Culture-Fit is an open-source, authority-aware **Human-in-the-Loop (HITL)** coordination layer for developers running multiple AI agents. It connects decision points in a conversation with explicit, scoped authority records, then shows who can proceed or which person needs to answer.

[Try the demo](https://culture-fit-demo-production.up.railway.app/workspace) · [Download and install](https://culture-fit-demo-production.up.railway.app/download) · [Installation guide](docs/install.md)

## What it does

A release agent and a review agent both claim approval authority. Their owners disagree. Culture-Fit surfaces the decision and its source quotes, checks the recorded delegations, and asks for the missing owner approvals. When the operator records an agreed priority, the same decision is re-evaluated without another model call. The agent can query the resulting next action.

- **Evidence-backed decision briefs:** extract agreements, open questions, decision scopes, and exact source quotations.
- **Scoped authority:** evaluate grants, conditions, expiration, revocation, and cross-owner approval records. Authority does not establish factual truth.
- **Human decision dashboard:** review evidence, record approvals and priority, inspect the current decision owner, and browse conversation history with pagination.
- **Agent-readable next actions:** return `wait_for_human`, `follow_authority`, `follow_human_decision`, or a request to refresh stale context.
- **Lightweight ontology:** typed relationships among Person, Agent, Task, Claim, Evidence, Decision, and Commitment. This is a JSON relationship model, not an OWL reasoner or a graph database.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then extract the source ZIP. Python 3.11 or newer is required; the locked development and deployment environment uses Python 3.12.

macOS:

```bash
./start-macos.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-windows.ps1
```

Or run the commands directly from the project directory:

```bash
uv sync --frozen
uv run uvicorn arbiter.app:app --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787/workspace`. The local SQLite database is stored in `.runtime/arbiter.sqlite3`; override it with `ARBITER_DB`. Windows launch instructions are provided, but Windows hardware execution has not yet been verified.

Conversation import and controlled simulations work without a model account. New model briefs require an installed, signed-in Codex CLI and consume that account's usage. Reporting a message through MCP or Slack does not automatically call a model; brief generation is an explicit dashboard or A2A request.

## Connect existing tools

| Integration | What it provides |
|---|---|
| [MCP](docs/mcp-connection.md) | Eight tools to register conversations, report messages, and read coordination state, decisions, authority, and next actions. Supports stdio and local Streamable HTTP. |
| [OpenClaw Skill](docs/openclaw-connection.md) | Instructions and a standard-library Python helper for reporting conversations and checking next actions. Recognition/configuration checked with OpenClaw 2026.3.11. |
| [Slack](docs/slack-connection.md) | Socket Mode receiver for allowlisted channels, thread grouping, deduplication, edits, and deletions. Requires app installation and tokens. A real workspace has not yet been connected. |
| [A2A](docs/a2a-connection.md) | Agent Card discovery and Send/Get/Cancel analysis tasks, verified using the official SDK. Streaming, push notifications, and external authentication are not implemented. |

Start the MCP server with `uv run python -m arbiter.mcp_server`, then add its configuration to an MCP-capable host. The agent must be instructed to report conversations and query results; installing a connection alone does not observe every conversation.

Human decisions and authority changes are entered in the dashboard. MCP exposes no authority-write tools. The local HTTP API does not authenticate remote owner identities; local operator records must not be presented as authenticated external consent. Keep the local integration services on loopback.

## Public demo

The [Railway demo](https://culture-fit-demo-production.up.railway.app) gives each browser a separate, signed-cookie sandbox with its own SQLite data. It uses synthetic conversations and a clearly labelled translated replay of previously recorded model analysis. Live model calls and Slack ingestion are disabled. The public URL is not an external MCP or A2A endpoint.

See [deployment and limits](docs/railway-deployment.md). Users can reset only their own sandbox. Data expires 24 hours after creation. The hosted service uses one worker and one persistent volume.

## Validation and scope

```bash
uv run pytest -q
uv run python experiments/run_comparison.py --help
```

The baseline suite passes 182 tests plus 8 subtests, including actual MCP protocol round trips, authority rules, cancellation, persistence, and visitor isolation. Public HTTPS checks and browser checks cover approvals, reset isolation, pagination, and blocked live model calls.

A separate live Codex-to-MCP smoke made four real tool calls across two model invocations: an initial authority conflict returned `wait_for_human`; a **mock operator approval** then produced `follow_authority` with Review Agent as owner. This verifies tool-mediated authority lookup in a synthetic task, not autonomous external execution, natural-language extraction accuracy, or live Slack/OpenClaw integration.

[Saved comparison results](experiments/results/latest/report.md) contain 24 deterministic runs across eight scenarios:

| Policy | Local checklist passed | Mean turns | Human questions |
|---|---:|---:|---:|
| Turn limit | 2/8 | 14.75 | 0 |
| Periodic check-in | 8/8 | 5.00 | 7 |
| Stall-aware check-in | 8/8 | 5.00 | 6 |

The two check-in policies have the same mean turn count. One question was avoided in these controlled cases. Human responses were simulated; these results do not establish real-world effectiveness, statistical significance, or token savings. See [experiment limitations](experiments/README.md) and the [recorded model briefing smoke](experiments/results/briefing-smoke/README.md).

## Open-source scope

MIT licensed; see [LICENSE](LICENSE). Domain experts can supply their own tasks, evidence, and delegation policies. The library package and CLI modules retain the implementation name `arbiter`.

Submission reports, videos, original uploads, personal contacts, and local credentials are maintained separately and excluded from source downloads and the deployment image. The [earlier design](https://github.com/Ontology0/hanium-arbiter/blob/feat/ontology-hitl/docs/design/v0.3.md) and [decision history](https://github.com/Ontology0/hanium-arbiter/blob/feat/ontology-hitl/docs/decision_log.md) describe prior plans, not the current feature set.
