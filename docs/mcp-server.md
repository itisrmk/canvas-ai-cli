# MCP server

`canvas-ai-cli` includes an MCP server entrypoint that wraps existing `canvas-ai` CLI commands.

## Design rule

The MCP server does **not** call Canvas APIs directly. Every MCP tool shells out to:

```bash
canvas-ai --json ...
```

## Schema validation

All CLI JSON envelopes returned through MCP are validated against local `schemas/*.schema.json` files.

On drift/mismatch, MCP returns deterministic structured errors:

- `ok: false`
- `error.code: SCHEMA_VALIDATION_ERROR`
- `error.details.command`
- `error.details.schema_file`
- `error.details.validation_error`

## Tool surface (v1)

- `mcp_version_info`
- `capabilities`
- `auth_status`, `auth_set_mode`, `auth_login`
- `init`
- `courses_list`, `assignments_due`, `assignment_show`
- `plan`
- `do_workflow`, `review`, `submit`
- `runs_show`, `runs_tail`
- `feedback_add`, `feedback_list`
- `metrics_summary`
- `org_info`, `org_set`, `org_probe`

## Read-only MCP resources

- `canvas-ai://runs/latest` — latest run list envelope.
- `canvas-ai://artifacts/latest` — latest `do` run artifact metadata + previews.

Resources are read-only and derived from CLI outputs/artifact files.

## Version handshake

`mcp_version_info` returns:

- `cli_version`
- `schema_version`
- `feature_contract_version`

Use this at session start for compatibility checks.

## Feature development policy

Every feature update must keep **CLI + MCP + docs** coherent in one change set.
