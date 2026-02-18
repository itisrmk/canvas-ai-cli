# Command reference

This page focuses on the current v5 command set for users and agent integrations.

For MCP usage, see `canvas-ai-mcp` in [MCP Server](mcp-server.md).

## Global flags

```bash
canvas-ai [--json] [--quiet] <command>
```

- `--json`: emits machine envelope with `schema_version: "v5"`
- `--quiet`: suppresses non-essential human output

## auth

### `auth login`

Save Canvas token locally.

```bash
canvas-ai auth login
```

### `auth status`

Show auth mode, base URL, and token status.

```bash
canvas-ai auth status
```

### `auth set-mode`

```bash
canvas-ai auth set-mode token
canvas-ai auth set-mode oauth_placeholder
```

## org

### `org info`

Resolve school name/logo using Canvas endpoints + local overrides.

```bash
canvas-ai org info
```

### `org set`

```bash
canvas-ai org set --school-name "My University"
canvas-ai org set --logo-url "https://example.edu/logo.png"
```

### `org probe`

Debug source fallback behavior.

```bash
canvas-ai org probe --verbose
```

## course & assignment read commands

```bash
canvas-ai --json courses list
canvas-ai --json assignments due --days 14
canvas-ai --json assignment show 12345
canvas-ai --json draft 12345
```

## agent

### `agent capabilities`

Return command metadata including risk and confirmation requirements.

```bash
canvas-ai --json agent capabilities
```

### `agent feature-contract`

Return the enforced feature sync policy for this project.

```bash
canvas-ai --json agent feature-contract
```

## plan

Generate an assignment step plan and persist it locally.

```bash
canvas-ai --json plan 12345
```

## execute

Execute a single plan step in tracked run history.

```bash
canvas-ai --json execute <plan_id> --step 1
```

## review

Generate short-lived confirmation token for guarded submission.

```bash
canvas-ai --json review 12345
```

Output includes:

- `confirm_token`
- `expires_at`
- `run_id`

## submit

Guarded submission command.

```bash
canvas-ai --json submit 12345 \
  --file ./paper.pdf \
  --confirm \
  --confirm-token rvw_xxx \
  --idempotency-key submit-12345-v1
```

Options:

- `--file` (required)
- `--confirm` (required)
- `--confirm-token` (required, from `review`)
- `--idempotency-key` (recommended)
- `--dry-run` (no Canvas submission side effect)

Policy guardrail (optional):

- `policy.default.max_review_token_age_minutes`
- if set, non-dry-run `submit` is blocked when review token age exceeds this value.

## runs

### `runs show`

```bash
canvas-ai --json runs show <run_id>
```

### `runs tail`

```bash
canvas-ai --json runs tail --limit 20
```

## do

Top-level autonomous (but non-submitting) workflow.

```bash
canvas-ai --json do 12345 --mode draft --goal "score above 90%"
canvas-ai --json do 12345 --mode draft --resume <run_id>
```

Options:

- `--mode <tutor|outline|draft|polish>`
- `--goal <text>`
- `--resume <run_id>`
- `--input-file <path>` (primarily for `polish` mode)

Artifacts include: `draft.md`, `review.json`, `evidence.json`, `sources.json`, `plan.json`, and `submit_checklist.md`.

## feedback

```bash
canvas-ai --json feedback add --course-id 77 --text "Use stronger thesis statements"
canvas-ai --json feedback list --course-id 77
```

## metrics

```bash
canvas-ai metrics summary --json
# or global envelope form
canvas-ai --json metrics summary
```

## init

```bash
canvas-ai --json init --non-interactive --base-url https://school.instructure.com --token "$CANVAS_API_TOKEN"
```

See [Autonomous Workflow](autonomous-workflow.md) for state and artifact details.
