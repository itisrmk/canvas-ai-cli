from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .config import CONFIG_DIR

POLICY_JSON = CONFIG_DIR / "policy.json"
POLICY_YAML = CONFIG_DIR / "policy.yaml"


class PolicyError(RuntimeError):
    pass


def _parse_yaml_minimal(text: str) -> dict[str, Any]:
    # Minimal fallback parser for simple key/value + one-level mapping/list data.
    data: dict[str, Any] = {}
    current_key: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line and not line.startswith("-"):
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                data[key] = {}
                current_key = key
            elif value.startswith("[") and value.endswith("]"):
                parts = [
                    x.strip().strip('"').strip("'")
                    for x in value[1:-1].split(",")
                    if x.strip()
                ]
                data[key] = parts
                current_key = None
            elif value.lower() in {"true", "false"}:
                data[key] = value.lower() == "true"
                current_key = None
            else:
                data[key] = value.strip('"').strip("'")
                current_key = None
        elif line.startswith("-") and current_key:
            arr = data.get(current_key)
            if not isinstance(arr, list):
                arr = []
                data[current_key] = arr
            arr.append(line.lstrip("-").strip().strip('"').strip("'"))
    return data


def load_policy() -> dict[str, Any]:
    if POLICY_JSON.exists():
        return json.loads(POLICY_JSON.read_text())
    if POLICY_YAML.exists():
        text = POLICY_YAML.read_text()
        try:
            import yaml  # type: ignore

            loaded = yaml.safe_load(text)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return _parse_yaml_minimal(text)
    return {}


def policy_for_course(course_id: int | None) -> dict[str, Any]:
    policy = load_policy()
    if course_id is None:
        return policy.get("default", {}) if isinstance(policy.get("default"), dict) else {}

    courses = policy.get("courses", {})
    if isinstance(courses, dict):
        item = courses.get(str(course_id)) or courses.get(course_id)
        if isinstance(item, dict):
            return item
    return policy.get("default", {}) if isinstance(policy.get("default"), dict) else {}


def enforce_do_policy(course_id: int | None, mode: str) -> None:
    rule = policy_for_course(course_id)
    allowed_modes = rule.get("allowed_modes")
    if isinstance(allowed_modes, list) and allowed_modes and mode not in allowed_modes:
        raise PolicyError(f"POLICY_BLOCKED_MODE: mode '{mode}' is not allowed for this course")


def enforce_submit_policy(
    course_id: int | None,
    dry_run: bool,
    *,
    review_token_created_at: str | None = None,
) -> None:
    rule = policy_for_course(course_id)
    if rule.get("disable_submit") is True:
        raise PolicyError("POLICY_SUBMIT_DISABLED: submissions are disabled by course policy")
    if rule.get("dry_run_only") is True and not dry_run:
        raise PolicyError("POLICY_DRY_RUN_ONLY: policy requires --dry-run for this course")

    max_review_token_age_minutes = rule.get("max_review_token_age_minutes")
    if dry_run or max_review_token_age_minutes is None:
        return
    if review_token_created_at is None:
        raise PolicyError(
            "POLICY_REVIEW_TOKEN_REQUIRED: policy requires a recent review token for submit"
        )
    created_at = datetime.fromisoformat(review_token_created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    age_minutes = (datetime.now(UTC) - created_at).total_seconds() / 60.0
    if age_minutes > float(max_review_token_age_minutes):
        raise PolicyError(
            "POLICY_REVIEW_TOKEN_TOO_OLD: review token is older than policy allows"
        )
