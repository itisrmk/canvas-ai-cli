# Autonomous workflow (`do`)

`do` is a resumable workflow command that creates draft/review artifacts without auto-submission.

## Command

```bash
canvas-ai do <assignment_id> --mode <tutor|outline|draft|polish> [--goal <text>] [--resume <run_id>] [--input-file <path>] [--json]
```

## Modes

- `tutor`: guided steps and reflective questions
- `outline`: structured outline with section goals
- `draft`: first-pass draft text
- `polish`: improves provided text and includes revision rationale

## State machine

Workflow states:

```text
queued -> planning -> drafting -> reviewing -> ready
```

Behavior:

- New run starts in `queued`.
- Resume (`--resume`) continues from stored state.
- If already `ready`, CLI returns existing artifacts without re-running side effects.

## Artifacts

On `ready`, files are written to:

```text
~/.local/share/canvas-ai/artifacts/<run_id>/
```

Files:

- `draft.md`
- `evidence.json`
- `review.json`
- `sources.json`
- `plan.json`
- `submit_checklist.md`

## Review stage output

Current deterministic MVP rubric scorer returns per criterion:

- `criterion`
- `estimated_score_band`
- `gaps`
- `suggested_fixes`

This is guidance, not final grading.

## Resume and observability

Inspect runs:

```bash
canvas-ai runs show <run_id> --json
canvas-ai runs tail --json
```

Resume example:

```bash
canvas-ai do 12345 --mode draft --resume run_abc123 --json
```

## Safety invariant

`do` **never** submits to Canvas. Submission always requires explicit `review` + `submit --confirm --confirm-token`.
