from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from canvas_ai import cli, config, history


class DummyClient:
    def submit_assignment(self, assignment_id: int, file_path: str):
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

runner = CliRunner()


def _set_temp_state(monkeypatch, tmp_path: Path) -> None:
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


def _normalize(payload: dict) -> dict:
    out = json.loads(json.dumps(payload))
    if out.get("command") == "do":
        out["result"]["run_id"] = "run_<id>"
        out["result"]["summary"] = "<summary>"
        out["lines"] = ["Workflow complete: run_id=run_<id>", out["lines"][1]]
        for key in list(out["result"].get("artifacts", {}).keys()):
            out["result"]["artifacts"][key] = f"<artifact:{key}>"
    if out.get("command") == "submit":
        out["result"]["run_id"] = "run_<id>"
        out["result"]["file"] = "<file>"
        out["lines"] = ["Submission result: <redacted>"]
    if out.get("command") == "feedback.add":
        out["result"]["id"] = 1
    if out.get("command") == "metrics.summary":
        out["result"]["total_runs"] = "<n>"
        out["result"]["success_runs"] = "<n>"
        out["result"]["failed_runs"] = "<n>"
        out["result"]["by_command"] = "<map>"
        out["result"]["common_error_codes"] = "<list>"
        out["lines"] = ["Total runs: <n>", "Success: <n> Failed: <n>"]
    return out


def _assert_snapshot(name: str, payload: dict) -> None:
    path = Path(__file__).parent / "fixtures" / name
    expected = json.loads(path.read_text())
    assert _normalize(payload) == expected


def test_golden_envelopes_do_submit_feedback_metrics(monkeypatch, tmp_path: Path) -> None:
    _set_temp_state(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "get_client", lambda: DummyClient())

    out_do = runner.invoke(cli.app, ["--json", "do", "123", "--mode", "draft"])
    assert out_do.exit_code == 0
    payload_do = json.loads(out_do.stdout)

    out_review = runner.invoke(cli.app, ["--json", "review", "123"])
    token = json.loads(out_review.stdout)["result"]["confirm_token"]

    file_path = tmp_path / "essay.txt"
    file_path.write_text("content")
    out_submit = runner.invoke(
        cli.app,
        [
            "--json",
            "submit",
            "123",
            "--file",
            str(file_path),
            "--confirm",
            "--confirm-token",
            token,
            "--dry-run",
        ],
    )
    assert out_submit.exit_code == 0
    payload_submit = json.loads(out_submit.stdout)

    out_feedback = runner.invoke(
        cli.app,
        ["--json", "feedback", "add", "--course-id", "456", "--text", "Use evidence"],
    )
    assert out_feedback.exit_code == 0
    payload_feedback = json.loads(out_feedback.stdout)

    out_metrics = runner.invoke(cli.app, ["--json", "metrics", "summary"])
    assert out_metrics.exit_code == 0
    payload_metrics = json.loads(out_metrics.stdout)

    _assert_snapshot("snapshot_do.json", payload_do)
    _assert_snapshot("snapshot_submit.json", payload_submit)
    _assert_snapshot("snapshot_feedback_add.json", payload_feedback)
    _assert_snapshot("snapshot_metrics_summary.json", payload_metrics)
