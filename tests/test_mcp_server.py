from __future__ import annotations

import json
import subprocess

from canvas_ai import mcp_server


def test_run_canvas_cli_success_json_parse(monkeypatch) -> None:
    def _fake_run(cmd, capture_output, text, check):
        assert cmd == ["canvas-ai", "--json", "auth", "status"]
        assert capture_output is True
        assert text is True
        assert check is False
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"schema_version":"v5","ok":true,"command":"auth.status","result":{"auth_mode":"token","base_url":"x","token":"configured"}}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    payload = mcp_server._run_canvas_cli(["auth", "status"])
    assert payload["ok"] is True
    assert payload["command"] == "auth.status"


def test_run_canvas_cli_fallback_line_by_line_parse(monkeypatch) -> None:
    def _fake_run(cmd, capture_output, text, check):
        stdout = (
            "debug: preflight\n"
            '{"schema_version":"v5","ok":true,"command":"courses.list","result":{"courses":[]}}\n'
            "extra trailing text"
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    payload = mcp_server._run_canvas_cli(["courses", "list"])
    assert payload == {
        "schema_version": "v5",
        "ok": True,
        "command": "courses.list",
        "result": {"courses": []},
    }


def test_run_canvas_cli_invalid_json_returns_deterministic_error(monkeypatch) -> None:
    def _fake_run(cmd, capture_output, text, check):
        return subprocess.CompletedProcess(
            cmd,
            9,
            stdout="not-json\nstill-not-json",
            stderr="bad things",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    payload = mcp_server._run_canvas_cli(["runs", "tail", "--limit", "1"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "Failed to parse JSON returned from canvas-ai."


def test_run_canvas_cli_binary_missing_returns_error(monkeypatch) -> None:
    monkeypatch.setenv("CANVAS_AI_BIN", "/custom/path/canvas-ai")

    def _fake_run(cmd, capture_output, text, check):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", _fake_run)

    payload = mcp_server._run_canvas_cli(["agent", "capabilities"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "CLI_BINARY_MISSING"


def test_schema_validation_error_on_drift(monkeypatch) -> None:
    def _fake_run(cmd, capture_output, text, check):
        # Missing required result.auth_mode from auth.status schema
        stdout = {
            "schema_version": "v5",
            "ok": True,
            "command": "auth.status",
            "result": {"unexpected": True},
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(stdout), stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    payload = mcp_server._run_canvas_cli(["auth", "status"])
    assert payload["ok"] is False
    assert payload["error"]["code"] == "SCHEMA_VALIDATION_ERROR"


def test_tool_plan_parity(monkeypatch) -> None:
    captured: list[list[str]] = []

    def _fake_run_canvas_cli(args: list[str]):
        captured.append(args)
        return {"ok": True, "command": "plan", "result": {"plan": {"id": "x"}}}

    monkeypatch.setattr(mcp_server, "_run_canvas_cli", _fake_run_canvas_cli)
    out = mcp_server.plan(123)
    assert captured == [["plan", "123"]]
    assert out["ok"] is True


def test_mcp_version_info() -> None:
    payload = mcp_server.mcp_version_info()
    assert payload["ok"] is True
    assert payload["schema_version"] == "v5"
    assert "feature_contract_version" in payload
