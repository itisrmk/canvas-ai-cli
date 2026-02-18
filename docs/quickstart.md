# Quickstart

## 1) Install

```bash
cd canvas-ai-cli
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Optional docs tooling:

```bash
pip install mkdocs mkdocs-material
```

## 2) Configure Canvas auth

Set base URL and API token:

```bash
export CANVAS_BASE_URL="https://school.instructure.com"
export CANVAS_API_TOKEN="<your_canvas_token>"
```

Or save token interactively:

```bash
canvas-ai auth login
```

Check status:

```bash
canvas-ai auth status
```

## 3) First run

Try safe read-only commands:

```bash
canvas-ai courses list
canvas-ai assignments due --days 14
canvas-ai assignment show 12345
```

## 4) First workflow run (`do`)

```bash
canvas-ai do 12345 --mode outline --goal "produce a rubric-aligned structure"
```

Modes:

- `tutor`
- `outline`
- `draft`
- `polish` (supports `--input-file`)

## 5) Feedback memory + metrics

```bash
canvas-ai feedback add --course-id 77 --text "Use stronger transitions"
canvas-ai feedback list --course-id 77
canvas-ai metrics summary --json
```

## 6) Safe submit flow

```bash
canvas-ai review 12345 --json
canvas-ai submit 12345 --file ./paper.pdf --confirm --confirm-token <token> --json
```

`submit` will fail if either confirmation flag/token is missing or invalid.

## 7) Machine mode (for agents)

```bash
canvas-ai --json plan 12345
canvas-ai --json agent capabilities
```

Global machine flags:

- `--json` stable envelope
- `--quiet` reduced human output

See [Agent Interface](agent-interface.md).
