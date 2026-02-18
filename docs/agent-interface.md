# Agent interface

The CLI supports a deterministic JSON contract for integrations.

Contract versions:

- `schema_version`: JSON envelope schema generation (`v5`)
- `feature_contract_version`: CLI+MCP+docs coherence contract (`2026-02-v1`)

## Enable machine mode

Use global `--json`:

```bash
canvas-ai --json plan 12345
```

## JSON envelope

Success shape:

```json
{
  "schema_version": "v5",
  "ok": true,
  "command": "plan",
  "result": {
    "plan": {
      "id": "plan_abcd",
      "assignment_id": 12345,
      "steps": []
    }
  }
}
```

Error shape:

```json
{
  "schema_version": "v5",
  "ok": false,
  "error": {
    "code": "CONFIRM_REQUIRED",
    "message": "Missing or invalid --confirm-token. Run review first.",
    "details": {}
  }
}
```

## Error taxonomy

The CLI maps expected failures into stable codes:

- `AUTH_401`
- `PERM_403`
- `NOT_FOUND_404`
- `RATE_LIMIT`
- `NETWORK_TIMEOUT`
- `CONFIRM_REQUIRED`
- `VALIDATION_ERROR`
- `POLICY_VIOLATION`
- `INTERNAL_ERROR`

### Mapping notes

- Canvas HTTP 401/403/404/429 map directly.
- Request timeout and connection errors map to `NETWORK_TIMEOUT`.
- Invalid command inputs map to `VALIDATION_ERROR`.
- Policy failures map to `POLICY_VIOLATION`.
- Confirmation gate failures map to `CONFIRM_REQUIRED`.

## Capability discovery

Use:

```bash
canvas-ai --json agent capabilities
```

The response lists command-level metadata, including:

- `risk` (`low`, `medium`, `high`)
- `confirmation_required` (boolean)
- `permissions` (scopes like `canvas:read`, `canvas:write`, `local:state`)

## MCP wrapper

The `canvas-ai-mcp` server wraps these same CLI contracts by executing `canvas-ai --json ...` per tool call and returning the parsed envelope plus stdout/stderr passthrough.

This ensures MCP and CLI behavior remain aligned.

## Integration guidance

- Treat `schema_version` as required.
- Branch on `ok` before reading `result`.
- Handle `error.code` deterministically.
- For write operations, enforce your own idempotency key strategy.
- Keep docs + CLI + MCP in sync for every new feature.
