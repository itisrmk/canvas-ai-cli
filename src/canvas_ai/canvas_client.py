from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests

RETRY_DELAYS_SECONDS = (0.0, 0.4, 1.0)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class CanvasClientError(RuntimeError):
    """Raised for Canvas API client errors."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        status_code: int | None = None,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code
        self.error_type = error_type


@dataclass
class CanvasClient:
    base_url: str
    api_token: str

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    def _request_with_retry(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self.base_url}/api/v1/{path.lstrip('/')}"

        for attempt, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
            if delay:
                time.sleep(delay)
            try:
                resp = requests.get(url, headers=self._headers, params=params, timeout=15)
                if (
                    resp.status_code in RETRYABLE_STATUS_CODES
                    and attempt < len(RETRY_DELAYS_SECONDS)
                ):
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        time.sleep(float(retry_after))
                    continue
                resp.raise_for_status()
                return resp
            except requests.Timeout as exc:
                if attempt < len(RETRY_DELAYS_SECONDS):
                    continue
                raise CanvasClientError(
                    f"timeout calling {url}",
                    endpoint=path,
                    error_type="timeout",
                ) from exc
            except requests.ConnectionError as exc:
                if attempt < len(RETRY_DELAYS_SECONDS):
                    continue
                raise CanvasClientError(
                    f"network error calling {url}",
                    endpoint=path,
                    error_type="network",
                ) from exc
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in {401, 403}:
                    raise CanvasClientError(
                        f"http error {status_code} calling {url}",
                        endpoint=path,
                        status_code=status_code,
                        error_type="http_auth",
                    ) from exc
                if status_code in RETRYABLE_STATUS_CODES and attempt < len(RETRY_DELAYS_SECONDS):
                    continue
                raise CanvasClientError(
                    f"http error {status_code} calling {url}",
                    endpoint=path,
                    status_code=status_code,
                    error_type="http",
                ) from exc
            except requests.RequestException as exc:
                if attempt < len(RETRY_DELAYS_SECONDS):
                    continue
                raise CanvasClientError(
                    f"request error calling {url}: {exc}",
                    endpoint=path,
                    error_type="request",
                ) from exc

        raise CanvasClientError(f"request error calling {url}", endpoint=path, error_type="request")

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        resp = self._request_with_retry(path, params=params)
        return resp.json()

    def list_courses(self) -> list[dict]:
        data = self._get("courses", params={"enrollment_state": "active"})
        return data if isinstance(data, list) else []

    def list_assignments_due(self, days: int) -> list[dict]:
        end_date = (datetime.now(UTC) + timedelta(days=days)).isoformat()
        all_items: list[dict] = []
        courses = self.list_courses()
        for course in courses:
            cid = course.get("id")
            if not cid:
                continue
            items = self._get(
                f"courses/{cid}/assignments",
                params={"bucket": "upcoming", "end_date": end_date},
            )
            if isinstance(items, list):
                all_items.extend(items)
        return all_items

    def get_assignment(self, assignment_id: int) -> dict:
        data = self._get(f"assignments/{assignment_id}")
        return data if isinstance(data, dict) else {}

    def get_user_profile(self) -> dict:
        data = self._get("users/self/profile")
        return data if isinstance(data, dict) else {}

    def list_accounts(self) -> list[dict]:
        data = self._get("accounts")
        return data if isinstance(data, list) else []

    def get_branding_theme(self) -> dict:
        data = self._get("accounts/self/theme")
        return data if isinstance(data, dict) else {}

    def submit_assignment(self, assignment_id: int, file_path: str) -> dict:
        # Stub placeholder for v1.
        # Real Canvas submission flow needs file upload + submission endpoint.
        return {
            "status": "stubbed",
            "assignment_id": assignment_id,
            "file": file_path,
            "message": "Submission flow placeholder. Human-confirmed execution only.",
        }
