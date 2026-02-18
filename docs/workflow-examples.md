# Workflow examples

## Goal-oriented do flow

```bash
canvas-ai do 12345 --mode draft --goal "Earn an A with evidence-backed claims"
```

Artifacts now include:
- `draft.md`
- `review.json` (with rubric optimization metadata)
- `sources.json`
- `plan.json` (calendar-aware schedule blocks when due date is known)

## Feedback memory

```bash
canvas-ai feedback add --course-id 77 --text "Use stronger transitions and cite two sources"
canvas-ai feedback list --course-id 77
```

## Safe submit flow

```bash
canvas-ai review 12345 --json
canvas-ai submit 12345 --file ./essay.md --confirm --confirm-token <token> --dry-run
```

## Metrics

```bash
canvas-ai metrics summary --json
```

## Init wizard

```bash
canvas-ai init --non-interactive --base-url https://school.instructure.com --token "$CANVAS_API_TOKEN"
```
