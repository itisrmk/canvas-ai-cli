from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich import print

from .ai_helpers import generate_draft, generate_plan
from .canvas_client import CanvasClient, CanvasClientError
from .config import (
    CONFIG_DIR,
    CONFIG_FILE,
    get_auth_mode,
    get_canvas_base_url,
    get_canvas_token,
    load_config,
    save_config,
    save_token,
    set_auth_mode,
    set_branding_overrides,
)
from .history import (
    create_review_token,
    create_run,
    feedback_hints_for_assignment,
    get_plan,
    get_review_token,
    get_run,
    get_submission_by_idempotency_key,
    init_db,
    list_feedback,
    list_runs,
    log_action,
    metrics_summary,
    store_feedback,
    store_plan,
    store_submission_idempotency,
    update_run,
    validate_review_token,
)
from .org import resolve_org_info, resolve_org_info_with_probe
from .policy import PolicyError, enforce_do_policy, enforce_submit_policy
from .workflow import (
    WORKFLOW_STATES,
    build_sources,
    derive_schedule_blocks,
    generate_mode_output,
    inject_inline_citation_suggestions,
    optimize_draft_for_rubric,
    utc_now_iso,
    write_artifacts,
)

SCHEMA_VERSION = "v5"
FEATURE_CONTRACT_VERSION = "2026-02-v1"

ERROR_CODES = {
    "AUTH_401",
    "PERM_403",
    "NOT_FOUND_404",
    "RATE_LIMIT",
    "NETWORK_TIMEOUT",
    "CONFIRM_REQUIRED",
    "VALIDATION_ERROR",
    "POLICY_VIOLATION",
    "INTERNAL_ERROR",
}

app = typer.Typer(help="Canvas AI CLI (human-in-the-loop)")
auth_app = typer.Typer()
courses_app = typer.Typer()
assignments_app = typer.Typer()
assignment_app = typer.Typer()
org_app = typer.Typer()
runs_app = typer.Typer()
agent_app = typer.Typer()
feedback_app = typer.Typer()
metrics_app = typer.Typer()

app.add_typer(auth_app, name="auth")
app.add_typer(courses_app, name="courses")
app.add_typer(assignments_app, name="assignments")
app.add_typer(assignment_app, name="assignment")
app.add_typer(org_app, name="org")
app.add_typer(runs_app, name="runs")
app.add_typer(agent_app, name="agent")
app.add_typer(feedback_app, name="feedback")
app.add_typer(metrics_app, name="metrics")


@dataclass
class AppContext:
    json_mode: bool = False
    quiet: bool = False


class AgentCliError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        if code not in ERROR_CODES:
            code = "INTERNAL_ERROR"
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _ctx_or_default(ctx: typer.Context | None) -> AppContext:
    if ctx is None or not isinstance(ctx.obj, AppContext):
        return AppContext()
    return ctx.obj


def _emit(ctx: typer.Context | None, data: dict[str, Any], quiet_ok: bool = False) -> None:
    app_ctx = _ctx_or_default(ctx)
    if app_ctx.quiet and quiet_ok:
        return
    if app_ctx.json_mode:
        payload = {"schema_version": SCHEMA_VERSION, **data}
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        for line in data.get("lines", []):
            print(line)


def _emit_error(ctx: typer.Context | None, err: AgentCliError) -> None:
    app_ctx = _ctx_or_default(ctx)
    log_action("error", err.code)
    if app_ctx.json_mode:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error": {
                "code": err.code,
                "message": err.message,
                "details": err.details,
            },
        }
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        print(f"[red]{err.code}[/red]: {err.message}")
    raise typer.Exit(code=1)


def _map_canvas_error(exc: CanvasClientError) -> AgentCliError:
    if exc.status_code == 401:
        code = "AUTH_401"
    elif exc.status_code == 403:
        code = "PERM_403"
    elif exc.status_code == 404:
        code = "NOT_FOUND_404"
    elif exc.status_code == 429:
        code = "RATE_LIMIT"
    elif exc.error_type in {"timeout", "network"}:
        code = "NETWORK_TIMEOUT"
    else:
        code = "INTERNAL_ERROR"
    return AgentCliError(code, f"Canvas API error: {exc}")


def _mask_token(token: str | None) -> str:
    if not token:
        return "not configured"
    if len(token) < 6:
        return "configured"
    return f"configured ({token[:2]}***{token[-2:]})"


def _workflow_metadata(run: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(run.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        return {}


def _state_index(state: str) -> int:
    try:
        return WORKFLOW_STATES.index(state)
    except ValueError:
        return 0


def get_client() -> CanvasClient:
    base_url = get_canvas_base_url()
    token = get_canvas_token()
    mode = get_auth_mode()

    if mode == "oauth_placeholder" and not token:
        raise AgentCliError(
            "AUTH_401",
            "Auth mode is oauth_placeholder; switch to token mode and login for now.",
        )

    if not base_url or not token:
        raise AgentCliError(
            "VALIDATION_ERROR",
            "Missing CANVAS_BASE_URL and/or CANVAS_API_TOKEN. Run `canvas-ai auth login`.",
        )
    return CanvasClient(base_url=base_url, api_token=token)


@app.callback()
def main(
    ctx: typer.Context,
    json_mode: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress non-essential output."),
) -> None:
    init_db()
    ctx.obj = AppContext(json_mode=json_mode, quiet=quiet)


@app.command("init")
def init_command(
    ctx: typer.Context,
    base_url: str | None = typer.Option(None, "--base-url"),
    token: str | None = typer.Option(None, "--token"),
    write_templates: bool = typer.Option(True, "--write-templates/--no-write-templates"),
    non_interactive: bool = typer.Option(False, "--non-interactive"),
) -> None:
    config = load_config()
    if base_url:
        config["canvas_base_url"] = base_url
    if token:
        config.setdefault("auth", {})["token"] = token
        config.setdefault("auth", {})["mode"] = "token"

    if not non_interactive:
        if not config.get("canvas_base_url"):
            entered = typer.prompt("Canvas base URL", default="https://canvas.instructure.com")
            config["canvas_base_url"] = entered
        auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
        if not auth.get("token"):
            entered_token = typer.prompt("Canvas API token (optional)", default="", hide_input=True)
            if entered_token:
                auth["token"] = entered_token
                auth["mode"] = "token"
        config["auth"] = auth

    save_config(config)

    templates = []
    if write_templates:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        policy = {
            "default": {
                "allowed_modes": ["tutor", "outline", "draft", "polish"],
                "dry_run_only": True,
                "max_review_token_age_minutes": 10,
            },
            "courses": {},
        }
        policy_path = CONFIG_DIR / "policy.json"
        policy_path.write_text(json.dumps(policy, indent=2))
        templates.append(str(policy_path))

    _emit(
        ctx,
        {
            "ok": True,
            "command": "init",
            "result": {"config_path": str(CONFIG_FILE), "templates": templates},
            "lines": [
                f"Initialized config at {CONFIG_FILE}",
                *[f"Template: {t}" for t in templates],
            ],
        },
    )


@metrics_app.command("summary")
def metrics_summary_cmd(
    ctx: typer.Context,
    json_only: bool = typer.Option(False, "--json", help="Emit JSON for this command."),
) -> None:
    summary = metrics_summary()
    payload = {
        "ok": True,
        "command": "metrics.summary",
        "result": summary,
        "lines": [
            f"Total runs: {summary['total_runs']}",
            f"Success: {summary['success_runs']} Failed: {summary['failed_runs']}",
        ],
    }
    if json_only and not _ctx_or_default(ctx).json_mode:
        typer.echo(json.dumps({"schema_version": SCHEMA_VERSION, **payload}, sort_keys=True))
        return
    _emit(ctx, payload)


@feedback_app.command("add")
def feedback_add(
    ctx: typer.Context,
    text: str = typer.Option(..., "--text"),
    course_id: int | None = typer.Option(None, "--course-id"),
    assignment_id: int | None = typer.Option(None, "--assignment-id"),
    source: str | None = typer.Option(None, "--source"),
) -> None:
    feedback_id = store_feedback(
        feedback_text=text,
        course_id=course_id,
        assignment_id=assignment_id,
        source=source,
    )
    _emit(
        ctx,
        {
            "ok": True,
            "command": "feedback.add",
            "result": {"id": feedback_id},
            "lines": [f"Saved feedback #{feedback_id}"],
        },
    )


@feedback_app.command("list")
def feedback_list(
    ctx: typer.Context,
    course_id: int | None = typer.Option(None, "--course-id"),
    assignment_id: int | None = typer.Option(None, "--assignment-id"),
) -> None:
    rows = list_feedback(course_id=course_id, assignment_id=assignment_id)
    _emit(
        ctx,
        {
            "ok": True,
            "command": "feedback.list",
            "result": {"feedback": rows},
            "lines": (
                [f"#{r['id']} {r['feedback_text']}" for r in rows]
                if rows
                else ["No feedback found."]
            ),
        },
    )


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    token: str = typer.Option(..., prompt=True, hide_input=True),
) -> None:
    path = save_token(token)
    log_action("auth login", "token_saved")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "auth.login",
            "result": {"config_path": str(path)},
            "lines": [f"[green]Canvas token saved to[/green] {path}"],
        },
    )


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    config = load_config()
    mode = get_auth_mode(config)
    base_url = get_canvas_base_url() or "not configured"
    token_status = _mask_token(get_canvas_token())
    _emit(
        ctx,
        {
            "ok": True,
            "command": "auth.status",
            "result": {"auth_mode": mode, "base_url": base_url, "token": token_status},
            "lines": [
                f"Auth mode: [bold]{mode}[/bold]",
                f"Canvas base URL: {base_url}",
                f"Token: {token_status}",
            ],
        },
    )


@auth_app.command("set-mode")
def auth_set_mode(
    ctx: typer.Context,
    mode: str = typer.Argument(..., help="token | oauth_placeholder"),
) -> None:
    if mode not in {"token", "oauth_placeholder"}:
        _emit_error(
            ctx,
            AgentCliError("VALIDATION_ERROR", "Mode must be token or oauth_placeholder"),
        )
    path = set_auth_mode(mode)  # type: ignore[arg-type]
    log_action("auth set-mode", mode)
    _emit(
        ctx,
        {
            "ok": True,
            "command": "auth.set-mode",
            "result": {"mode": mode, "config_path": str(path)},
            "lines": [f"Auth mode set to [bold]{mode}[/bold] ([dim]{path}[/dim])"],
        },
    )


@org_app.command("info")
def org_info(ctx: typer.Context) -> None:
    base_url = get_canvas_base_url()
    if not base_url:
        _emit_error(ctx, AgentCliError("VALIDATION_ERROR", "Missing CANVAS_BASE_URL."))

    token = get_canvas_token()
    client = CanvasClient(base_url=base_url, api_token=token) if token else None
    info = resolve_org_info(base_url=base_url, client=client, config=load_config())
    _emit(
        ctx,
        {
            "ok": True,
            "command": "org.info",
            "result": {
                "school_name": info.school_name,
                "logo_url": info.logo_url,
                "source": info.source,
            },
            "lines": [
                f"School name: {info.school_name or 'Unknown (fallback used)'}",
                f"Logo URL: {info.logo_url or 'Unavailable'}",
                f"Source: {info.source}",
            ],
        },
    )


@org_app.command("set")
def org_set(
    ctx: typer.Context,
    school_name: str | None = typer.Option(None, "--school-name"),
    logo_url: str | None = typer.Option(None, "--logo-url"),
) -> None:
    if school_name is None and logo_url is None:
        _emit_error(
            ctx,
            AgentCliError("VALIDATION_ERROR", "Provide --school-name and/or --logo-url"),
        )

    path = set_branding_overrides(school_name=school_name, logo_url=logo_url)
    log_action("org set", f"school_name={bool(school_name)},logo_url={bool(logo_url)}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "org.set",
            "result": {"config_path": str(path)},
            "lines": [f"Branding overrides saved to {path}"],
        },
    )


@org_app.command("probe")
def org_probe(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", help="Show attempt details."),
) -> None:
    base_url = get_canvas_base_url()
    if not base_url:
        _emit_error(ctx, AgentCliError("VALIDATION_ERROR", "Missing CANVAS_BASE_URL."))

    token = get_canvas_token()
    client = CanvasClient(base_url=base_url, api_token=token) if token else None

    info, report = resolve_org_info_with_probe(
        base_url=base_url,
        client=client,
        config=load_config(),
    )
    lines = [
        f"Source order: {' > '.join(report.source_order)}",
        f"Winner: {report.winner_source}",
        f"Reason: {report.winner_reason}",
        f"School name: {info.school_name or 'Unknown (fallback used)'}",
        f"Logo URL: {info.logo_url or 'Unavailable'}",
    ]
    if verbose:
        lines.append("Attempt details:")
        for attempt in report.attempts:
            needed = "needed" if attempt.needed else "not-needed"
            lines.append(f"- {attempt.endpoint}: {attempt.outcome} ({needed}) - {attempt.detail}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "org.probe",
            "result": {
                "winner": report.winner_source,
                "reason": report.winner_reason,
                "school_name": info.school_name,
                "logo_url": info.logo_url,
            },
            "lines": lines,
        },
    )


@courses_app.command("list")
def courses_list(ctx: typer.Context) -> None:
    try:
        client = get_client()
        courses = client.list_courses()
    except AgentCliError as exc:
        _emit_error(ctx, exc)
    except CanvasClientError as exc:
        _emit_error(ctx, _map_canvas_error(exc))

    log_action("courses list", f"count={len(courses)}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "courses.list",
            "result": {"courses": courses},
            "lines": [f"- {c.get('id')}: {c.get('name', 'Unnamed course')}" for c in courses]
            if courses
            else ["No courses found."],
        },
    )


@assignments_app.command("due")
def assignments_due(ctx: typer.Context, days: int = typer.Option(14, min=1)) -> None:
    try:
        client = get_client()
        items = client.list_assignments_due(days)
    except AgentCliError as exc:
        _emit_error(ctx, exc)
    except CanvasClientError as exc:
        _emit_error(ctx, _map_canvas_error(exc))

    log_action("assignments due", f"days={days},count={len(items)}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "assignments.due",
            "result": {"days": days, "assignments": items},
            "lines": [
                f"- {item.get('id')}: {item.get('name', 'Untitled')} (due: {item.get('due_at')})"
                for item in items
            ]
            if items
            else ["No upcoming assignments found."],
        },
    )


@assignment_app.command("show")
def assignment_show(ctx: typer.Context, assignment_id: int) -> None:
    try:
        client = get_client()
        item = client.get_assignment(assignment_id)
    except AgentCliError as exc:
        _emit_error(ctx, exc)
    except CanvasClientError as exc:
        _emit_error(ctx, _map_canvas_error(exc))

    log_action("assignment show", f"id={assignment_id}")
    if not item:
        _emit_error(ctx, AgentCliError("NOT_FOUND_404", "Assignment not found."))

    _emit(
        ctx,
        {
            "ok": True,
            "command": "assignment.show",
            "result": {"assignment": item},
            "lines": [
                f"[bold]{item.get('name', 'Untitled')}[/bold]",
                f"ID: {item.get('id')}",
                f"Due: {item.get('due_at')}",
                f"Description: {item.get('description', '(none)')}",
            ],
        },
    )


@app.command("draft")
def draft_assignment(ctx: typer.Context, assignment_id: int) -> None:
    try:
        client = get_client()
        item = client.get_assignment(assignment_id)
    except AgentCliError as exc:
        _emit_error(ctx, exc)
    except CanvasClientError as exc:
        _emit_error(ctx, _map_canvas_error(exc))

    text = generate_draft(item)
    log_action("draft", f"id={assignment_id}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "draft",
            "result": {"assignment_id": assignment_id, "draft": text},
            "lines": [text],
        },
    )


@app.command("do")
def do_assignment(
    ctx: typer.Context,
    assignment_id: int,
    mode: str = typer.Option(..., "--mode", help="tutor|outline|draft|polish"),
    goal: str | None = typer.Option(None, "--goal", help="Optional intent goal for this run."),
    resume: str | None = typer.Option(None, "--resume", help="Resume an existing do run_id."),
    input_file: Path | None = typer.Option(
        None,
        "--input-file",
        exists=True,
        readable=True,
        help="Optional draft input for --mode polish.",
    ),
) -> None:
    if mode not in {"tutor", "outline", "draft", "polish"}:
        _emit_error(
            ctx,
            AgentCliError(
                "VALIDATION_ERROR",
                "Mode must be one of: tutor, outline, draft, polish.",
            ),
        )

    if resume:
        existing = get_run(resume)
        if not existing or existing.get("command") != "do":
            _emit_error(ctx, AgentCliError("NOT_FOUND_404", f"Workflow run not found: {resume}"))
        metadata = _workflow_metadata(existing)
        if metadata.get("assignment_id") != assignment_id:
            _emit_error(
                ctx,
                AgentCliError(
                    "VALIDATION_ERROR",
                    "--resume run assignment_id does not match the provided assignment_id.",
                ),
            )
        if metadata.get("mode") and metadata.get("mode") != mode:
            _emit_error(
                ctx,
                AgentCliError("VALIDATION_ERROR", "--resume run mode does not match --mode."),
            )
        run_id = resume
        state_history = metadata.get("state_history", [])
        existing_state = metadata.get("state", existing.get("status", "queued"))
    else:
        metadata = {
            "assignment_id": assignment_id,
            "mode": mode,
            "goal": goal,
            "state": "queued",
            "state_history": [{"state": "queued", "ts": utc_now_iso()}],
        }
        run_id = create_run("do", "queued", json.dumps(metadata))
        state_history = metadata["state_history"]
        existing_state = "queued"

    if existing_state == "ready":
        artifact_paths = metadata.get("artifacts", {})
        _emit(
            ctx,
            {
                "ok": True,
                "command": "do",
                "result": {
                    "run_id": run_id,
                    "state": "ready",
                    "mode": mode,
                    "goal": metadata.get("goal"),
                    "artifacts": artifact_paths,
                    "summary": metadata.get("summary", "Workflow already completed."),
                },
                "lines": [f"Workflow already ready. run_id={run_id}"],
            },
        )
        return

    try:
        client = get_client()
        assignment = client.get_assignment(assignment_id)
        enforce_do_policy(assignment.get("course_id"), mode)
    except AgentCliError as exc:
        _emit_error(ctx, exc)
    except CanvasClientError as exc:
        _emit_error(ctx, _map_canvas_error(exc))
    except PolicyError as exc:
        _emit_error(ctx, AgentCliError("POLICY_VIOLATION", str(exc)))

    polish_input = input_file.read_text() if input_file else None

    start_at = _state_index(existing_state) + 1 if resume else 1
    for state in WORKFLOW_STATES[start_at:]:
        metadata["state"] = state
        state_history.append({"state": state, "ts": utc_now_iso()})
        metadata["state_history"] = state_history

        if state == "planning":
            feedback_hints = feedback_hints_for_assignment(assignment)
            output = generate_mode_output(
                mode=mode,
                assignment=assignment,
                polish_input=polish_input,
                goal=goal,
                feedback_hints=feedback_hints,
            )
            metadata["draft"] = output["draft"]
            metadata["summary"] = output["summary"]
            metadata["feedback_hints_used"] = feedback_hints
            metadata["plan"] = {"schedule_blocks": derive_schedule_blocks(assignment)}

        if state == "drafting":
            sources = build_sources(assignment, metadata.get("draft", ""))
            metadata["sources"] = sources
            metadata["draft"] = inject_inline_citation_suggestions(
                metadata.get("draft", ""), sources
            )

        if state == "reviewing":
            improved_draft, optimization, review_rows = optimize_draft_for_rubric(
                assignment,
                metadata.get("draft", ""),
            )
            metadata["draft"] = improved_draft
            metadata["review"] = {
                "rubric_scores": review_rows,
                "optimization": optimization,
                "notes": (
                    "Deterministic MVP scorer; verify against official rubric "
                    "before submission."
                ),
                "goal": goal,
            }
            metadata["evidence"] = {
                "assignment_id": assignment_id,
                "assignment_name": assignment.get("name"),
                "mode": mode,
                "goal": goal,
                "generated_at": utc_now_iso(),
            }

        if state == "ready":
            artifacts = write_artifacts(
                run_id,
                metadata.get("draft", ""),
                metadata.get("evidence", {}),
                metadata.get("review", {}),
                metadata.get("sources", {}),
                metadata.get("plan", {}),
            )
            metadata["artifacts"] = artifacts

        update_run(run_id, state, json.dumps(metadata))

    log_action("do", f"id={assignment_id},mode={mode},run_id={run_id},resume={bool(resume)}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "do",
            "result": {
                "run_id": run_id,
                "state": metadata.get("state", "ready"),
                "mode": mode,
                "goal": goal,
                "artifacts": metadata.get("artifacts", {}),
                "summary": metadata.get("summary", "Workflow complete."),
            },
            "lines": [
                f"Workflow complete: run_id={run_id}",
                "Artifacts written for human review. No auto-submit performed.",
            ],
        },
    )


@app.command("plan")
def plan_assignment(ctx: typer.Context, assignment_id: int) -> None:
    try:
        client = get_client()
        item = client.get_assignment(assignment_id)
    except AgentCliError as exc:
        _emit_error(ctx, exc)
    except CanvasClientError as exc:
        _emit_error(ctx, _map_canvas_error(exc))

    steps = generate_plan(item)
    plan_id = store_plan(assignment_id, json.dumps(steps))
    log_action("plan", f"id={assignment_id},plan_id={plan_id}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "plan",
            "result": {
                "plan": {
                    "id": plan_id,
                    "assignment_id": assignment_id,
                    "steps": [
                        {"step": idx, "instruction": step}
                        for idx, step in enumerate(steps, 1)
                    ],
                }
            },
            "lines": [f"{idx}. {step}" for idx, step in enumerate(steps, start=1)],
        },
    )


@app.command("execute")
def execute_plan(ctx: typer.Context, plan_id: str, step: int = typer.Option(..., min=1)) -> None:
    plan = get_plan(plan_id)
    if not plan:
        _emit_error(ctx, AgentCliError("NOT_FOUND_404", f"Plan not found: {plan_id}"))
    steps = json.loads(plan["steps_json"])
    if step > len(steps):
        _emit_error(
            ctx,
            AgentCliError("VALIDATION_ERROR", f"Step {step} is out of range for plan {plan_id}"),
        )

    run_id = create_run(
        "execute",
        "running",
        json.dumps({"plan_id": plan_id, "step": step}),
    )
    selected = steps[step - 1]
    update_run(
        run_id,
        "succeeded",
        json.dumps({"plan_id": plan_id, "step": step, "action": selected}),
    )
    _emit(
        ctx,
        {
            "ok": True,
            "command": "execute",
            "result": {
                "run_id": run_id,
                "plan_id": plan_id,
                "assignment_id": plan["assignment_id"],
                "step": step,
                "action": selected,
                "status": "succeeded",
            },
            "lines": [f"Executed step {step}: {selected}"],
        },
    )


@app.command("review")
def review_assignment(ctx: typer.Context, assignment_id: int) -> None:
    try:
        client = get_client()
        _ = client.get_assignment(assignment_id)
    except AgentCliError as exc:
        _emit_error(ctx, exc)
    except CanvasClientError as exc:
        _emit_error(ctx, _map_canvas_error(exc))

    token_data = create_review_token(assignment_id)
    run_id = create_run(
        "review",
        "succeeded",
        json.dumps({"assignment_id": assignment_id, "expires_at": token_data["expires_at"]}),
    )
    _emit(
        ctx,
        {
            "ok": True,
            "command": "review",
            "result": {
                "run_id": run_id,
                "assignment_id": assignment_id,
                "confirm_token": token_data["token"],
                "expires_at": token_data["expires_at"],
            },
            "lines": [
                f"Review complete for assignment {assignment_id}.",
                f"Confirm token (short-lived): {token_data['token']}",
            ],
        },
    )


@app.command("submit")
def submit_assignment(
    ctx: typer.Context,
    assignment_id: int,
    file: Path = typer.Option(..., exists=True, readable=True),
    confirm: bool = typer.Option(False, "--confirm", help="Required to execute submission."),
    confirm_token: str | None = typer.Option(None, "--confirm-token"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    if not confirm:
        _emit_error(
            ctx,
            AgentCliError("CONFIRM_REQUIRED", "Refusing to submit without explicit --confirm."),
        )
    if not confirm_token or not validate_review_token(assignment_id, confirm_token):
        _emit_error(
            ctx,
            AgentCliError(
                "CONFIRM_REQUIRED",
                "Missing or invalid --confirm-token. Run review first.",
            ),
        )
    review_token = get_review_token(confirm_token)

    try:
        assignment = get_client().get_assignment(assignment_id)
        enforce_submit_policy(
            assignment.get("course_id"),
            dry_run,
            review_token_created_at=(review_token or {}).get("created_at"),
        )
    except (AgentCliError, CanvasClientError):
        assignment = {}
    except PolicyError as exc:
        _emit_error(ctx, AgentCliError("POLICY_VIOLATION", str(exc)))

    key = idempotency_key or f"submit:{assignment_id}:{file.resolve()}"
    prior = get_submission_by_idempotency_key(key)
    if prior:
        prior_result = json.loads(prior["result_json"])
        _emit(
            ctx,
            {
                "ok": True,
                "command": "submit",
                "result": {"replayed": True, **prior_result},
                "lines": ["Idempotency replay: returning previous submission result."],
            },
        )
        return

    run_id = create_run(
        "submit",
        "running",
        json.dumps({"assignment_id": assignment_id, "file": str(file), "dry_run": dry_run}),
    )

    if dry_run:
        result = {
            "assignment_id": assignment_id,
            "file": str(file),
            "status": "dry_run",
            "message": "Dry run only. No submission sent.",
            "run_id": run_id,
        }
    else:
        try:
            client = get_client()
            submit_result = client.submit_assignment(assignment_id, str(file))
            result = {
                "assignment_id": assignment_id,
                "file": str(file),
                "run_id": run_id,
                **submit_result,
            }
        except AgentCliError as exc:
            update_run(run_id, "failed")
            _emit_error(ctx, exc)
        except CanvasClientError as exc:
            update_run(run_id, "failed")
            _emit_error(ctx, _map_canvas_error(exc))

    update_run(run_id, "succeeded", json.dumps(result))
    store_submission_idempotency(
        idempotency_key=key,
        assignment_id=assignment_id,
        file_path=str(file),
        dry_run=dry_run,
        result_json=json.dumps(result),
    )

    log_action("submit", f"id={assignment_id},file={file},idempotency_key={key},dry_run={dry_run}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "submit",
            "result": {"replayed": False, **result},
            "lines": [f"Submission result: {result}"],
        },
    )


@runs_app.command("show")
def runs_show(ctx: typer.Context, run_id: str) -> None:
    run = get_run(run_id)
    if not run:
        _emit_error(ctx, AgentCliError("NOT_FOUND_404", f"Run not found: {run_id}"))
    metadata = json.loads(run["metadata_json"] or "{}")
    _emit(
        ctx,
        {
            "ok": True,
            "command": "runs.show",
            "result": {"run": {**run, "metadata": metadata}},
            "lines": [f"Run {run_id}: {run['status']} ({run['command']})"],
        },
    )


@runs_app.command("tail")
def runs_tail(ctx: typer.Context, limit: int = typer.Option(10, min=1, max=200)) -> None:
    runs = list_runs(limit=limit)
    formatted = [{**run, "metadata": json.loads(run["metadata_json"] or "{}")} for run in runs]
    _emit(
        ctx,
        {
            "ok": True,
            "command": "runs.tail",
            "result": {"runs": formatted},
            "lines": [f"{r['id']} {r['status']} {r['command']}" for r in formatted]
            if formatted
            else ["No runs found."],
        },
    )


@agent_app.command("feature-contract")
def agent_feature_contract(ctx: typer.Context) -> None:
    contract = {
        "policy": "feature_sync_required",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "requirements": [
            "Every feature change must update CLI behavior and/or command surface.",
            "Every feature change must update MCP server tool surface or mapping.",
            "Every feature change must update docs (command reference + relevant guides).",
            "Feature PRs should include verification evidence for CLI + MCP + docs coherence.",
        ],
    }
    _emit(
        ctx,
        {
            "ok": True,
            "command": "agent.feature-contract",
            "result": contract,
            "lines": [
                "Feature contract:",
                "- Update CLI",
                "- Update MCP",
                "- Update docs",
                "- Include verification evidence",
            ],
        },
    )


@agent_app.command("capabilities")
def agent_capabilities(ctx: typer.Context) -> None:
    capabilities = {
        "commands": [
            {
                "name": "plan",
                "risk": "low",
                "confirmation_required": False,
                "permissions": ["canvas:read"],
            },
            {
                "name": "execute",
                "risk": "medium",
                "confirmation_required": False,
                "permissions": ["local:state"],
            },
            {
                "name": "review",
                "risk": "medium",
                "confirmation_required": False,
                "permissions": ["canvas:read", "local:state"],
            },
            {
                "name": "do",
                "risk": "medium",
                "confirmation_required": False,
                "permissions": ["canvas:read", "local:state", "local:artifacts"],
            },
            {
                "name": "submit",
                "risk": "high",
                "confirmation_required": True,
                "permissions": ["canvas:write", "local:state"],
            },
            {
                "name": "runs.show",
                "risk": "low",
                "confirmation_required": False,
                "permissions": ["local:state"],
            },
            {
                "name": "runs.tail",
                "risk": "low",
                "confirmation_required": False,
                "permissions": ["local:state"],
            },
        ]
    }
    _emit(
        ctx,
        {
            "ok": True,
            "command": "agent.capabilities",
            "result": capabilities,
            "lines": ["Use --json for machine-readable capabilities."],
        },
    )


if __name__ == "__main__":
    app()
