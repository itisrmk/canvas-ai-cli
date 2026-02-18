from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate
from mcp.server.fastmcp import FastMCP

from . import __version__ as CLI_VERSION

FEATURE_CONTRACT_VERSION = "2026-02-v1"
SCHEMA_VERSION = "v5"
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"

mcp = FastMCP("canvas-ai-cli")

CLI_COMMAND_SCHEMAS: dict[str, str] = {
    "agent.capabilities": "agent.capabilities.schema.json",
    "auth.status": "auth.status.schema.json",
    "auth.login": "auth.login.schema.json",
    "auth.set-mode": "auth.set-mode.schema.json",
    "courses.list": "courses.list.schema.json",
    "assignments.due": "assignments.due.schema.json",
    "assignment.show": "assignment.show.schema.json",
    "do": "do.result.schema.json",
    "plan": "plan.result.schema.json",
    "review": "review.result.schema.json",
    "submit": "submit.result.schema.json",
    "runs.show": "runs.show.schema.json",
    "runs.tail": "runs.tail.schema.json",
    "feedback.add": "feedback.add.schema.json",
    "feedback.list": "feedback.list.schema.json",
    "metrics.summary": "metrics.summary.schema.json",
    "init": "init.schema.json",
    "org.info": "org.info.schema.json",
    "org.set": "org.set.schema.json",
    "org.probe": "org.probe.schema.json",
}


def _error_payload(
    code: str,
    message: str,
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = None,
    command: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_details: dict[str, Any] = {"stdout": stdout, "stderr": stderr}
    if exit_code is not None:
        out_details["exit_code"] = exit_code
    if command is not None:
        out_details["command"] = command
    if details:
        out_details.update(details)
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": out_details,
        },
    }


def _load_schema(schema_name: str) -> dict[str, Any]:
    schema_path = SCHEMAS_DIR / schema_name
    return json.loads(schema_path.read_text())


def _validate_cli_envelope(payload: dict[str, Any]) -> dict[str, Any] | None:
    command = payload.get("command")
    if not isinstance(command, str):
        return _error_payload(
            "SCHEMA_VALIDATION_ERROR",
            "CLI JSON envelope missing required 'command' field.",
            details={"schema_dir": str(SCHEMAS_DIR), "payload": payload},
        )

    schema_name = CLI_COMMAND_SCHEMAS.get(command)
    if not schema_name:
        return _error_payload(
            "SCHEMA_VALIDATION_ERROR",
            f"No local schema registered for command '{command}'.",
            details={"command": command, "schema_dir": str(SCHEMAS_DIR)},
        )

    schema_path = SCHEMAS_DIR / schema_name
    if not schema_path.exists():
        return _error_payload(
            "SCHEMA_VALIDATION_ERROR",
            "Registered schema file is missing.",
            details={"command": command, "schema_file": str(schema_path)},
        )

    try:
        validate(instance=payload, schema=_load_schema(schema_name))
    except ValidationError as exc:
        return _error_payload(
            "SCHEMA_VALIDATION_ERROR",
            "CLI JSON envelope failed schema validation.",
            details={
                "command": command,
                "schema_file": str(schema_path),
                "validation_error": exc.message,
                "validator": exc.validator,
                "path": list(exc.absolute_path),
            },
        )
    return None


def _run_canvas_cli(args: list[str]) -> dict[str, Any]:
    canvas_ai_bin = os.getenv("CANVAS_AI_BIN", "canvas-ai")
    cmd = [canvas_ai_bin, "--json", *args]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return _error_payload(
            "CLI_BINARY_MISSING",
            f"`{canvas_ai_bin}` is not installed or not on PATH. Install this package first.",
            command=cmd,
        )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if not stdout:
        return _error_payload(
            "INTERNAL_ERROR",
            "No JSON returned from canvas-ai.",
            stderr=stderr,
            exit_code=completed.returncode,
            command=cmd,
        )

    parsed: dict[str, Any] | None = None
    try:
        maybe = json.loads(stdout)
        if isinstance(maybe, dict):
            parsed = maybe
    except json.JSONDecodeError:
        pass

    if parsed is None:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                maybe = json.loads(line)
                if isinstance(maybe, dict):
                    parsed = maybe
                    break
            except json.JSONDecodeError:
                continue

    if parsed is None:
        return _error_payload(
            "INTERNAL_ERROR",
            "Failed to parse JSON returned from canvas-ai.",
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
            command=cmd,
        )

    schema_error = _validate_cli_envelope(parsed)
    if schema_error:
        return schema_error

    return parsed


@mcp.tool()
def mcp_version_info() -> dict[str, Any]:
    """Return handshake metadata for CLI/MCP/schema compatibility."""
    return {
        "ok": True,
        "mcp_server": "canvas-ai-cli",
        "cli_version": CLI_VERSION,
        "schema_version": SCHEMA_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
    }


@mcp.tool()
def capabilities() -> dict[str, Any]:
    """Return command metadata and risk/confirmation information from canvas-ai."""
    return _run_canvas_cli(["agent", "capabilities"])


@mcp.tool()
def auth_status() -> dict[str, Any]:
    """Read auth mode and token/base-url status."""
    return _run_canvas_cli(["auth", "status"])


@mcp.tool()
def auth_set_mode(mode: str) -> dict[str, Any]:
    """Set auth mode using explicit allowlisted values."""
    if mode not in {"token", "oauth_placeholder"}:
        return _error_payload(
            "VALIDATION_ERROR",
            "mode must be one of: token, oauth_placeholder",
            details={"mode": mode},
        )
    return _run_canvas_cli(["auth", "set-mode", mode])


@mcp.tool()
def auth_login(token: str) -> dict[str, Any]:
    """Set API token (safe argv wrapper; no shell interpolation)."""
    return _run_canvas_cli(["auth", "login", "--token", token])


@mcp.tool()
def init(
    base_url: str | None = None,
    token: str | None = None,
    write_templates: bool = True,
    non_interactive: bool = True,
) -> dict[str, Any]:
    """Initialize local config safely for CLI and MCP use."""
    args = ["init"]
    if base_url:
        args.extend(["--base-url", base_url])
    if token:
        args.extend(["--token", token])
    args.append("--write-templates" if write_templates else "--no-write-templates")
    if non_interactive:
        args.append("--non-interactive")
    return _run_canvas_cli(args)


@mcp.tool()
def courses_list() -> dict[str, Any]:
    """List Canvas courses available to the current token."""
    return _run_canvas_cli(["courses", "list"])


@mcp.tool()
def assignments_due(days: int = 14) -> dict[str, Any]:
    """List upcoming assignments due within N days."""
    return _run_canvas_cli(["assignments", "due", "--days", str(days)])


@mcp.tool()
def assignment_show(assignment_id: int) -> dict[str, Any]:
    """Get assignment details by id."""
    return _run_canvas_cli(["assignment", "show", str(assignment_id)])


@mcp.tool()
def plan(assignment_id: int) -> dict[str, Any]:
    """Generate assignment plan with persisted plan_id."""
    return _run_canvas_cli(["plan", str(assignment_id)])


@mcp.tool()
def do_workflow(
    assignment_id: int,
    mode: str,
    goal: str | None = None,
    resume: str | None = None,
    input_file: str | None = None,
) -> dict[str, Any]:
    """Run the non-submitting do workflow and return artifacts metadata."""
    args = ["do", str(assignment_id), "--mode", mode]
    if goal:
        args.extend(["--goal", goal])
    if resume:
        args.extend(["--resume", resume])
    if input_file:
        args.extend(["--input-file", input_file])
    return _run_canvas_cli(args)


@mcp.tool()
def review(assignment_id: int) -> dict[str, Any]:
    """Create a short-lived confirmation token for guarded submit."""
    return _run_canvas_cli(["review", str(assignment_id)])


@mcp.tool()
def submit(
    assignment_id: int,
    file_path: str,
    confirm_token: str,
    idempotency_key: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Guarded submit command. Requires explicit token and sets --confirm always."""
    args = [
        "submit",
        str(assignment_id),
        "--file",
        file_path,
        "--confirm",
        "--confirm-token",
        confirm_token,
    ]
    if idempotency_key:
        args.extend(["--idempotency-key", idempotency_key])
    if dry_run:
        args.append("--dry-run")
    return _run_canvas_cli(args)


@mcp.tool()
def runs_show(run_id: str) -> dict[str, Any]:
    """Fetch full metadata for a stored run id."""
    return _run_canvas_cli(["runs", "show", run_id])


@mcp.tool()
def runs_tail(limit: int = 10) -> dict[str, Any]:
    """List recent run history."""
    return _run_canvas_cli(["runs", "tail", "--limit", str(limit)])


@mcp.resource("canvas-ai://runs/latest", mime_type="application/json")
def resource_runs_latest() -> str:
    """Read-only resource: recent run records for IDE/agent browsing."""
    return json.dumps(_run_canvas_cli(["runs", "tail", "--limit", "10"]), sort_keys=True)


@mcp.resource("canvas-ai://artifacts/latest", mime_type="application/json")
def resource_latest_artifacts() -> str:
    """Read-only resource: artifact paths/content metadata for the newest do run."""
    tail = _run_canvas_cli(["runs", "tail", "--limit", "20"])
    if not tail.get("ok"):
        return json.dumps(tail, sort_keys=True)
    runs = tail.get("result", {}).get("runs", [])
    do_run = next((r for r in runs if r.get("command") == "do"), None)
    if not isinstance(do_run, dict):
        return json.dumps({"ok": True, "result": {"artifacts": {}, "run_id": None}}, sort_keys=True)

    metadata = do_run.get("metadata") or {}
    artifacts = metadata.get("artifacts") if isinstance(metadata, dict) else {}
    out: dict[str, Any] = {"ok": True, "result": {"run_id": do_run.get("id"), "artifacts": {}}}
    if isinstance(artifacts, dict):
        for name, file_path in artifacts.items():
            if isinstance(file_path, str):
                p = Path(file_path)
                out["result"]["artifacts"][name] = {
                    "path": file_path,
                    "exists": p.exists(),
                    "preview": p.read_text()[:5000] if p.exists() else "",
                }
    return json.dumps(out, sort_keys=True)


@mcp.tool()
def feedback_add(
    text: str,
    course_id: int | None = None,
    assignment_id: int | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Persist feedback hints for future do workflow optimization."""
    args = ["feedback", "add", "--text", text]
    if course_id is not None:
        args.extend(["--course-id", str(course_id)])
    if assignment_id is not None:
        args.extend(["--assignment-id", str(assignment_id)])
    if source:
        args.extend(["--source", source])
    return _run_canvas_cli(args)


@mcp.tool()
def feedback_list(
    course_id: int | None = None,
    assignment_id: int | None = None,
) -> dict[str, Any]:
    """List stored feedback hints."""
    args = ["feedback", "list"]
    if course_id is not None:
        args.extend(["--course-id", str(course_id)])
    if assignment_id is not None:
        args.extend(["--assignment-id", str(assignment_id)])
    return _run_canvas_cli(args)


@mcp.tool()
def metrics_summary() -> dict[str, Any]:
    """Summarize local run metrics and success/failure counts."""
    return _run_canvas_cli(["metrics", "summary"])


@mcp.tool()
def org_info() -> dict[str, Any]:
    """Read resolved org/school branding info."""
    return _run_canvas_cli(["org", "info"])


@mcp.tool()
def org_set(
    school_name: str | None = None,
    logo_url: str | None = None,
) -> dict[str, Any]:
    """Set org branding overrides safely via argv construction."""
    if school_name is None and logo_url is None:
        return _error_payload(
            "VALIDATION_ERROR",
            "Provide school_name and/or logo_url",
        )
    args = ["org", "set"]
    if school_name is not None:
        args.extend(["--school-name", school_name])
    if logo_url is not None:
        args.extend(["--logo-url", logo_url])
    return _run_canvas_cli(args)


@mcp.tool()
def org_probe(verbose: bool = False) -> dict[str, Any]:
    """Inspect org metadata source fallback path."""
    args = ["org", "probe"]
    if verbose:
        args.append("--verbose")
    return _run_canvas_cli(args)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
