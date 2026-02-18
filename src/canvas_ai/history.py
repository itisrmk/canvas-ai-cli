from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DB_DIR = Path.home() / ".local" / "share" / "canvas-ai"
DB_PATH = DB_DIR / "history.db"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(ts: datetime | None = None) -> str:
    value = ts or _utc_now()
    return value.isoformat()


def init_db() -> Path:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                command TEXT NOT NULL,
                payload TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY,
                assignment_id INTEGER NOT NULL,
                steps_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_tokens (
                token_hash TEXT PRIMARY KEY,
                assignment_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submission_idempotency (
                idempotency_key TEXT PRIMARY KEY,
                assignment_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER,
                assignment_id INTEGER,
                feedback_text TEXT NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
    return DB_PATH


def _connect() -> sqlite3.Connection:
    init_db()
    return sqlite3.connect(DB_PATH)


def log_action(command: str, payload: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO history (ts, command, payload) VALUES (?, ?, ?)",
            (_iso(), command, payload),
        )
        conn.commit()


def store_feedback(
    *,
    feedback_text: str,
    course_id: int | None = None,
    assignment_id: int | None = None,
    source: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO feedback_memory (
                course_id,
                assignment_id,
                feedback_text,
                source,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (course_id, assignment_id, feedback_text, source, _iso()),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_feedback(
    course_id: int | None = None,
    assignment_id: int | None = None,
) -> list[dict[str, Any]]:
    query = (
        "SELECT id, course_id, assignment_id, feedback_text, source, created_at "
        "FROM feedback_memory"
    )
    clauses: list[str] = []
    values: list[Any] = []
    if course_id is not None:
        clauses.append("course_id = ?")
        values.append(course_id)
    if assignment_id is not None:
        clauses.append("assignment_id = ?")
        values.append(assignment_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY datetime(created_at) DESC LIMIT 50"

    with _connect() as conn:
        rows = conn.execute(query, tuple(values)).fetchall()

    return [
        {
            "id": row[0],
            "course_id": row[1],
            "assignment_id": row[2],
            "feedback_text": row[3],
            "source": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]


def feedback_hints_for_assignment(assignment: dict[str, Any]) -> list[str]:
    assignment_id = assignment.get("id")
    course_id = assignment.get("course_id")
    rows = list_feedback(course_id=course_id, assignment_id=assignment_id)
    if not rows and course_id is not None:
        rows = list_feedback(course_id=course_id)
    return [r["feedback_text"] for r in rows[:3]]


def metrics_summary() -> dict[str, Any]:
    with _connect() as conn:
        run_rows = conn.execute(
            "SELECT command, status, COUNT(*) FROM runs GROUP BY command, status"
        ).fetchall()
        total_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        errors = conn.execute(
            """
            SELECT payload, COUNT(*) as c
            FROM history
            WHERE command = 'error'
            GROUP BY payload
            ORDER BY c DESC
            LIMIT 10
            """
        ).fetchall()

    by_command: dict[str, dict[str, int]] = {}
    success = 0
    failed = 0
    for command, status, count in run_rows:
        item = by_command.setdefault(command, {"succeeded": 0, "failed": 0, "other": 0})
        if status == "succeeded" or status == "ready":
            item["succeeded"] += count
            success += count
        elif status == "failed":
            item["failed"] += count
            failed += count
        else:
            item["other"] += count

    return {
        "total_runs": int(total_runs),
        "success_runs": int(success),
        "failed_runs": int(failed),
        "by_command": by_command,
        "common_error_codes": [
            {"code": row[0], "count": int(row[1])}
            for row in errors
            if row[0]
        ],
    }


def store_plan(assignment_id: int, steps_json: str) -> str:
    plan_id = f"plan_{secrets.token_hex(8)}"
    with _connect() as conn:
        conn.execute(
            "INSERT INTO plans (id, assignment_id, steps_json, created_at) VALUES (?, ?, ?, ?)",
            (plan_id, assignment_id, steps_json, _iso()),
        )
        conn.commit()
    return plan_id


def get_plan(plan_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, assignment_id, steps_json, created_at FROM plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "assignment_id": row[1],
        "steps_json": row[2],
        "created_at": row[3],
    }


def create_review_token(assignment_id: int, ttl_minutes: int = 10) -> dict[str, Any]:
    token = f"rvw_{secrets.token_urlsafe(18)}"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    created_at = _utc_now()
    expires_at = created_at + timedelta(minutes=ttl_minutes)
    with _connect() as conn:
        conn.execute(
            (
                "INSERT INTO review_tokens "
                "(token_hash, assignment_id, expires_at, created_at) "
                "VALUES (?, ?, ?, ?)"
            ),
            (token_hash, assignment_id, _iso(expires_at), _iso(created_at)),
        )
        conn.commit()
    return {
        "token": token,
        "assignment_id": assignment_id,
        "created_at": _iso(created_at),
        "expires_at": _iso(expires_at),
    }


def get_review_token(token: str) -> dict[str, Any] | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _connect() as conn:
        row = conn.execute(
            "SELECT assignment_id, expires_at, created_at FROM review_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
    if not row:
        return None
    return {
        "assignment_id": int(row[0]),
        "expires_at": str(row[1]),
        "created_at": str(row[2]),
    }


def validate_review_token(assignment_id: int, token: str) -> bool:
    row = get_review_token(token)
    if not row:
        return False
    if int(row["assignment_id"]) != assignment_id:
        return False
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at >= _utc_now()


def get_submission_by_idempotency_key(idempotency_key: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT idempotency_key, assignment_id, file_path, dry_run, result_json, created_at
            FROM submission_idempotency WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
    if not row:
        return None
    return {
        "idempotency_key": row[0],
        "assignment_id": row[1],
        "file_path": row[2],
        "dry_run": bool(row[3]),
        "result_json": row[4],
        "created_at": row[5],
    }


def store_submission_idempotency(
    *,
    idempotency_key: str,
    assignment_id: int,
    file_path: str,
    dry_run: bool,
    result_json: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO submission_idempotency
            (idempotency_key, assignment_id, file_path, dry_run, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (idempotency_key, assignment_id, file_path, 1 if dry_run else 0, result_json, _iso()),
        )
        conn.commit()


def create_run(command: str, status: str, metadata_json: str = "{}") -> str:
    run_id = f"run_{secrets.token_hex(8)}"
    now = _iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO runs (id, command, status, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, command, status, metadata_json, now, now),
        )
        conn.commit()
    return run_id


def update_run(run_id: str, status: str, metadata_json: str | None = None) -> None:
    with _connect() as conn:
        if metadata_json is None:
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
                (status, _iso(), run_id),
            )
        else:
            conn.execute(
                "UPDATE runs SET status = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                (status, metadata_json, _iso(), run_id),
            )
        conn.commit()


def get_run(run_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            (
                "SELECT id, command, status, metadata_json, created_at, updated_at "
                "FROM runs WHERE id = ?"
            ),
            (run_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "command": row[1],
        "status": row[2],
        "metadata_json": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, command, status, metadata_json, created_at, updated_at
            FROM runs
            ORDER BY datetime(updated_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "command": r[1],
            "status": r[2],
            "metadata_json": r[3],
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]
