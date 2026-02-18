# canvas-ai-cli

![python](https://img.shields.io/badge/python-3.10%2B-blue)
![safety](https://img.shields.io/badge/human--in--the--loop-required-green)

`canvas-ai` is a human-in-the-loop CLI for Canvas LMS workflows, with a deterministic JSON interface for agents and MCP clients.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

export CANVAS_BASE_URL="https://<your-school>.instructure.com"
export CANVAS_API_TOKEN="<your-token>"

canvas-ai auth status
canvas-ai assignments due --days 7
canvas-ai plan 12345
canvas-ai do 12345 --mode draft --goal "Score above 90%"
```

## Install

### Local development install

```bash
git clone <your-repo-url>
cd canvas-ai-cli
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### Requirements

- Python 3.10+
- Canvas base URL (for your institution)
- Canvas API token

## Configuration

You can configure credentials through environment variables:

```bash
export CANVAS_BASE_URL="https://<your-school>.instructure.com"
export CANVAS_API_TOKEN="<your-token>"
```

Or use CLI setup helpers:

```bash
canvas-ai auth login
canvas-ai init
canvas-ai auth status
```

## MCP setup

This project includes an MCP server entrypoint that wraps `canvas-ai --json ...` commands.

- Docs: [`docs/mcp-server.md`](docs/mcp-server.md)
- JSON schemas: [`schemas/`](schemas/)

Typical usage pattern for MCP integrations:

1. Install `canvas-ai-cli` in the MCP runtime environment.
2. Configure auth (`CANVAS_BASE_URL`, `CANVAS_API_TOKEN`).
3. Start/invoke MCP tools that proxy CLI commands.
4. Validate against local schemas for strict contract safety.

## Common examples

### Human CLI

```bash
canvas-ai auth status
canvas-ai org info
canvas-ai assignments due --days 14
canvas-ai do 12345 --mode outline
canvas-ai review <run_id>
canvas-ai submit <run_id> --confirm --confirm-token <token>
```

### Agent-safe JSON mode

```bash
canvas-ai --json plan 12345
canvas-ai --json do 12345 --mode draft
canvas-ai --json review <run_id>
```

### Feedback memory + metrics

```bash
canvas-ai feedback add --course-id 77 --text "Use stronger thesis statements"
canvas-ai feedback list --course-id 77
canvas-ai metrics summary --json
```

## Safety model

`canvas-ai` is designed to keep users in control:

- No hidden auto-submit behavior
- Explicit confirmation gates for submission
- Deterministic machine-readable errors/responses
- Local run/artifact history for traceability

Read full policy: [`docs/safety-policy.md`](docs/safety-policy.md)

## Documentation

- Overview: [`docs/index.md`](docs/index.md)
- Quickstart: [`docs/quickstart.md`](docs/quickstart.md)
- Command reference: [`docs/command-reference.md`](docs/command-reference.md)
- Agent interface: [`docs/agent-interface.md`](docs/agent-interface.md)
- MCP server: [`docs/mcp-server.md`](docs/mcp-server.md)
- Autonomous workflow: [`docs/autonomous-workflow.md`](docs/autonomous-workflow.md)
- Examples: [`docs/examples.md`](docs/examples.md)
- Workflow examples: [`docs/workflow-examples.md`](docs/workflow-examples.md)
- Troubleshooting: [`docs/troubleshooting.md`](docs/troubleshooting.md)

### Build docs locally

```bash
pip install mkdocs mkdocs-material
mkdocs serve
# or: mkdocs build
```

## Development contract

Feature work should keep **CLI + MCP + docs** in sync:

```bash
canvas-ai --json agent feature-contract
```

## License

This project is licensed under the [MIT License](LICENSE).
