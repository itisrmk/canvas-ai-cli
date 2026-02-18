# Examples

## Human CLI examples

### Check auth and org

```bash
canvas-ai auth status
canvas-ai org info
canvas-ai org probe --verbose
```

### Plan + execute one step

```bash
canvas-ai plan 12345
canvas-ai execute plan_abcd --step 1
```

### Run autonomous draft workflow

```bash
canvas-ai do 12345 --mode draft
canvas-ai runs tail --limit 5
```

### Safe submit flow with idempotency

```bash
canvas-ai review 12345
canvas-ai submit 12345 --file ./paper.pdf --confirm --confirm-token rvw_xxx --idempotency-key sub-12345-v1
```

## Machine JSON examples

### `agent capabilities`

```bash
canvas-ai --json agent capabilities
```

Example response:

```json
{
  "schema_version": "v3",
  "ok": true,
  "command": "agent.capabilities",
  "result": {
    "commands": [
      {
        "name": "submit",
        "risk": "high",
        "confirmation_required": true,
        "permissions": ["canvas:write", "local:state"]
      }
    ]
  }
}
```

### `review`

```bash
canvas-ai --json review 12345
```

Example response:

```json
{
  "schema_version": "v3",
  "ok": true,
  "command": "review",
  "result": {
    "run_id": "run_123",
    "assignment_id": 12345,
    "confirm_token": "rvw_abc",
    "expires_at": "2026-02-17T10:00:00+00:00"
  }
}
```

### `submit` confirmation failure

```bash
canvas-ai --json submit 12345 --file ./paper.pdf
```

Example error:

```json
{
  "schema_version": "v3",
  "ok": false,
  "error": {
    "code": "CONFIRM_REQUIRED",
    "message": "Refusing to submit without explicit --confirm.",
    "details": {}
  }
}
```
