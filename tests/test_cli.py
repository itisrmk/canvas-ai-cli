from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from canvas_ai import cli, config, history, policy

runner = CliRunner()


class DummyClient:
    def __init__(self) -> None:
        self.submit_calls = 0

    def submit_assignment(self, assignment_id: int, file_path: str):
        self.submit_calls += 1
        return {"assignment_id": assignment_id, "file": file_path, "status": "ok"}

    def get_assignment(self, assignment_id: int):
        return {
            "id": assignment_id,
            "course_id": 456,
            "name": "Essay",
            "description": "Write an essay with evidence and clear argument.",
            "due_at": "2026-03-01T18:00:00Z",
            "rubric": [
                {"description": "Thesis and argument"},
                {"description": "Evidence quality"},
            ],
        }


def _set_temp_state(monkeypatch, tmp_path: Path) -> Path:
    config_dir = tmp_path / "cfg"
    config_file = config_dir / "config.json"
    db_dir = tmp_path / "db"
    db_path = db_dir / "history.db"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_file)
    monkeypatch.setattr(history, "DB_DIR", db_dir)
    monkeypatch.setattr(history, "DB_PATH", db_path)
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "CONFIG_FILE", config_file)
    monkeypatch.setattr(policy, "POLICY_JSON", config_dir / "policy.json")
    monkeypatch.setattr(policy, "POLICY_YAML", config_dir / "policy.yaml")
    return config_file


def test_top_level_help_contains_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    commands = [
        "auth",
        "runs",
        "agent",
        "plan",
        "execute",
        "review",
        "submit",
        "feedback",
        "metrics",
        "init",
    ]
    for cmd in commands:
        assert cmd in result.stdout


def test_json_envelope_contains_schema_version(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    result = runner.invoke(cli.app, ["--json", "agent", "capabilities"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "v5"
    assert payload["ok"] is True


def test_submit_refuses_without_confirm_json(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    test_file = tmp_path / "essay.txt"
    test_file.write_text("hello")

    result = runner.invoke(cli.app, ["--json", "submit", "123", "--file", str(test_file)])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "CONFIRM_REQUIRED"


def test_submit_requires_review_token(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "get_client", lambda: DummyClient())
    test_file = tmp_path / "essay.txt"
    test_file.write_text("hello")

    result = runner.invoke(
        cli.app,
        ["--json", "submit", "123", "--file", str(test_file), "--confirm"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "CONFIRM_REQUIRED"


def test_submit_idempotency_replay(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "get_client", lambda: DummyClient())
    test_file = tmp_path / "essay.txt"
    test_file.write_text("hello")

    review = runner.invoke(cli.app, ["--json", "review", "123"])
    token = json.loads(review.stdout)["result"]["confirm_token"]

    key = "abc-123"
    first = runner.invoke(
        cli.app,
        [
            "--json",
            "submit",
            "123",
            "--file",
            str(test_file),
            "--confirm",
            "--confirm-token",
            token,
            "--idempotency-key",
            key,
            "--dry-run",
        ],
    )
    assert first.exit_code == 0
    first_payload = json.loads(first.stdout)
    assert first_payload["result"]["replayed"] is False

    second = runner.invoke(
        cli.app,
        [
            "--json",
            "submit",
            "123",
            "--file",
            str(test_file),
            "--confirm",
            "--confirm-token",
            token,
            "--idempotency-key",
            key,
            "--dry-run",
        ],
    )
    assert second.exit_code == 0
    second_payload = json.loads(second.stdout)
    assert second_payload["result"]["replayed"] is True


def test_do_goal_feedback_sources_and_artifacts(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "get_client", lambda: DummyClient())

    add_feedback = runner.invoke(
        cli.app,
        [
            "--json",
            "feedback",
            "add",
            "--course-id",
            "456",
            "--text",
            "Use stronger thesis statements and cite at least two sources.",
        ],
    )
    assert add_feedback.exit_code == 0

    result = runner.invoke(
        cli.app,
        ["--json", "do", "123", "--mode", "draft", "--goal", "Earn an A with strong evidence"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    artifacts = payload["result"]["artifacts"]
    assert Path(artifacts["sources_json"]).exists()
    assert Path(artifacts["plan_json"]).exists()

    review_payload = json.loads(Path(artifacts["review_json"]).read_text())
    assert "optimization" in review_payload
    assert review_payload["goal"] == "Earn an A with strong evidence"


def test_metrics_summary_json(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "get_client", lambda: DummyClient())

    _ = runner.invoke(cli.app, ["--json", "do", "123", "--mode", "outline"])
    metrics = runner.invoke(cli.app, ["--json", "metrics", "summary"])
    assert metrics.exit_code == 0
    payload = json.loads(metrics.stdout)
    assert payload["result"]["total_runs"] >= 1


def test_init_writes_templates(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    result = runner.invoke(
        cli.app,
        [
            "--json",
            "init",
            "--base-url",
            "https://example.instructure.com",
            "--token",
            "abc123",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert Path(payload["result"]["config_path"]).exists()


def test_golden_agent_do_review_submit_envelopes(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "get_client", lambda: DummyClient())
    f = tmp_path / "essay.txt"
    f.write_text("hello")

    do_out = json.loads(runner.invoke(cli.app, ["--json", "do", "123", "--mode", "draft"]).stdout)
    review_out = json.loads(runner.invoke(cli.app, ["--json", "review", "123"]).stdout)
    token = review_out["result"]["confirm_token"]
    submit_out = json.loads(
        runner.invoke(
            cli.app,
            [
                "--json",
                "submit",
                "123",
                "--file",
                str(f),
                "--confirm",
                "--confirm-token",
                token,
                "--dry-run",
            ],
        ).stdout
    )

    expected_dir = Path(__file__).parent / "fixtures"
    expected_dir.mkdir(exist_ok=True)
    (expected_dir / "golden_do_keys.json").write_text(
        json.dumps(sorted(do_out.keys()), indent=2)
    )
    (expected_dir / "golden_review_keys.json").write_text(
        json.dumps(sorted(review_out.keys()), indent=2)
    )
    (expected_dir / "golden_submit_keys.json").write_text(
        json.dumps(sorted(submit_out.keys()), indent=2)
    )

    assert sorted(do_out.keys()) == ["command", "lines", "ok", "result", "schema_version"]
    assert sorted(review_out.keys()) == ["command", "lines", "ok", "result", "schema_version"]
    assert sorted(submit_out.keys()) == ["command", "lines", "ok", "result", "schema_version"]


def test_submit_policy_blocks_old_review_token(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "get_client", lambda: DummyClient())
    test_file = tmp_path / "essay.txt"
    test_file.write_text("hello")

    # write policy template file directly
    (config.CONFIG_DIR / "policy.json").parent.mkdir(parents=True, exist_ok=True)
    (config.CONFIG_DIR / "policy.json").write_text(
        json.dumps({"default": {"max_review_token_age_minutes": 0}, "courses": {}})
    )

    review = runner.invoke(cli.app, ["--json", "review", "123"])
    token = json.loads(review.stdout)["result"]["confirm_token"]
    monkeypatch.setattr(
        cli,
        "get_review_token",
        lambda _token: {
            "assignment_id": 123,
            "expires_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2000-01-01T00:00:00+00:00",
        },
    )

    result = runner.invoke(
        cli.app,
        [
            "--json",
            "submit",
            "123",
            "--file",
            str(test_file),
            "--confirm",
            "--confirm-token",
            token,
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "POLICY_VIOLATION"
    assert "POLICY_REVIEW_TOKEN_TOO_OLD" in payload["error"]["message"]


def test_canvas_error_maps_to_deterministic_code() -> None:
    err = cli.CanvasClientError("unauthorized", status_code=401, error_type="http")
    mapped = cli._map_canvas_error(err)
    assert mapped.code == "AUTH_401"
