# Troubleshooting

## Auth setup issues

### Missing base URL or token

Symptom:

- `VALIDATION_ERROR` with message about `CANVAS_BASE_URL` / `CANVAS_API_TOKEN`

Fix:

```bash
export CANVAS_BASE_URL="https://school.instructure.com"
export CANVAS_API_TOKEN="<token>"
canvas-ai auth status
```

Or save token:

```bash
canvas-ai auth login
```

## HTTP errors

### `AUTH_401`

Likely causes:

- invalid/expired token
- wrong Canvas host

Actions:

1. reissue Canvas API token
2. verify base URL is your institution Canvas domain
3. run `canvas-ai auth status`

### `PERM_403`

Likely causes:

- token lacks required role permissions
- endpoint exists but user access denied

Actions:

- confirm account role for the target course/assignment
- retry with token from correct user context

### `NOT_FOUND_404`

Likely causes:

- wrong assignment/run/plan id
- resource inaccessible in current org

Actions:

- verify IDs
- use `runs tail --json` to inspect local run ids

## Network and rate limit

### `NETWORK_TIMEOUT`

Likely causes:

- transient network issue
- Canvas response timeout

Actions:

- retry
- check VPN/firewall settings
- verify Canvas host resolves from your shell

### `RATE_LIMIT`

Likely cause:

- too many requests in a short period

Actions:

- add backoff and retry jitter in automation
- reduce parallel calls

## Submit confirmation problems

### `CONFIRM_REQUIRED`

Symptom examples:

- missing `--confirm`
- missing/expired/invalid `--confirm-token`

Correct flow:

```bash
canvas-ai review 12345 --json
canvas-ai submit 12345 --file ./paper.pdf --confirm --confirm-token <fresh_token> --json
```

## Confirm token timing

Review tokens are short-lived by design.

If a token expires, rerun `review` to mint a fresh token.

## Command help

For exact CLI syntax:

```bash
canvas-ai --help
canvas-ai submit --help
canvas-ai do --help
```
