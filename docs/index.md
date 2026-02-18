# canvas-ai-cli overview

`canvas-ai` is a Python CLI for Canvas LMS workflows with a strict **human-in-the-loop safety model** and a stable machine-readable interface.

It is designed for two audiences:

- **Students and instructors** who want practical command-line support for Canvas tasks.
- **Agent developers** who need deterministic JSON responses, explicit risk boundaries, and resumable workflows.

## What this CLI is

- A command-line assistant for reading Canvas data and preparing assignment work artifacts.
- A safe submission workflow with explicit user confirmation gates.
- A local run history and artifact store for traceability.

## What this CLI is not

- Not an auto-submit bot.
- Not a bypass for course policies or academic integrity rules.
- Not a hidden background agent; user actions are explicit and auditable.

## Safety model (high level)

The CLI uses layered safeguards:

1. **No implicit submissions**: `do` never submits.
2. **Explicit confirmation required**: `submit` requires `--confirm`.
3. **Fresh review token required**: `submit` also requires `--confirm-token` from `review`.
4. **Idempotency protection**: repeated submit attempts with same key replay previous result.
5. **Deterministic error taxonomy** in JSON mode for predictable agent behavior.

See [Safety & Academic Integrity](safety-policy.md).

## Architecture (high level)

```text
Typer CLI commands
  ├─ CanvasClient (HTTP to Canvas API)
  ├─ Local state/history (SQLite)
  │   ├─ plans
  │   ├─ runs
  │   └─ review + submit idempotency records
  └─ Workflow/artifacts layer
      ├─ do state machine
      ├─ rubric scoring (deterministic MVP)
      └─ artifact files on local disk
```

Core components in `src/canvas_ai/`:

- `cli.py` — command handlers, JSON envelope, error mapping
- `mcp_server.py` — MCP tools that invoke `canvas-ai --json`
- `canvas_client.py` — Canvas API client
- `workflow.py` — autonomous workflow states + artifacts
- `history.py` — local run/plan/review token persistence
- `config.py` — auth and branding config

## Feature delivery policy

Every new feature must update all three integration surfaces together:

1. docs (`docs/`)
2. CLI (`canvas-ai`)
3. MCP (`canvas-ai-mcp`)

## Read next

- [Quickstart](quickstart.md)
- [Command Reference](command-reference.md)
- [Agent Interface](agent-interface.md)
- [Autonomous Workflow](autonomous-workflow.md)
- [Examples](examples.md)
- [MCP Server](mcp-server.md)
- [Troubleshooting](troubleshooting.md)
