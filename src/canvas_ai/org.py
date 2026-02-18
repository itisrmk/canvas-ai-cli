from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from .canvas_client import CanvasClient, CanvasClientError
from .config import get_branding_overrides


@dataclass
class OrgInfo:
    school_name: str | None
    logo_url: str | None
    source: str


@dataclass
class ProbeAttempt:
    endpoint: str
    needed: bool
    outcome: str
    detail: str
    school_name: str | None = None
    logo_url: str | None = None


@dataclass
class OrgProbeReport:
    source_order: list[str]
    attempts: list[ProbeAttempt] = field(default_factory=list)
    winner_source: str = ""
    winner_reason: str = ""


def _guess_school_from_domain(base_url: str) -> str | None:
    host = urlparse(base_url).hostname or ""
    if not host:
        return None

    parts = [p for p in host.split(".") if p and p not in {"www", "instructure", "com", "edu"}]
    if not parts:
        return None

    candidate = parts[0].replace("-", " ").replace("_", " ").strip()
    return candidate.title() if candidate else None


def _error_outcome(exc: CanvasClientError) -> tuple[str, str]:
    status = getattr(exc, "status_code", None)
    kind = getattr(exc, "error_type", None)

    if status == 401:
        return "unauthorized", "401 unauthorized"
    if status == 403:
        return "forbidden", "403 forbidden"
    if status == 404:
        return "not_found", "404 not found"
    if kind == "timeout":
        return "timeout", "request timed out"
    if kind == "network":
        return "network_error", "network error"
    return "error", str(exc)


def _resolve_api_theme(client: CanvasClient) -> tuple[str | None, str | None, list[ProbeAttempt]]:
    attempts: list[ProbeAttempt] = []
    school_name: str | None = None
    logo_url: str | None = None

    try:
        accounts = client.list_accounts()
        first = (
            accounts[0]
            if isinstance(accounts, list) and accounts and isinstance(accounts[0], dict)
            else {}
        )
        school_name = first.get("name") or first.get("display_name")
        attempts.append(
            ProbeAttempt(
                endpoint="GET /api/v1/accounts",
                needed=True,
                outcome="success",
                detail="account list returned",
                school_name=school_name,
            )
        )
    except CanvasClientError as exc:
        outcome, detail = _error_outcome(exc)
        attempts.append(
            ProbeAttempt(
                endpoint="GET /api/v1/accounts",
                needed=True,
                outcome=outcome,
                detail=detail,
            )
        )

    try:
        theme = client.get_branding_theme()
        if isinstance(theme, dict):
            logo_url = theme.get("logo") or theme.get("logo_url") or theme.get("brand_logo")
        attempts.append(
            ProbeAttempt(
                endpoint="GET /api/v1/accounts/self/theme",
                needed=True,
                outcome="success",
                detail="theme returned",
                logo_url=logo_url,
            )
        )
    except CanvasClientError as exc:
        outcome, detail = _error_outcome(exc)
        attempts.append(
            ProbeAttempt(
                endpoint="GET /api/v1/accounts/self/theme",
                needed=True,
                outcome=outcome,
                detail=detail,
            )
        )

    return school_name, logo_url, attempts


def resolve_org_info_with_probe(
    base_url: str,
    client: CanvasClient | None = None,
    config: dict | None = None,
) -> tuple[OrgInfo, OrgProbeReport]:
    report = OrgProbeReport(source_order=["override", "api/theme", "domain_guess"])
    overrides = get_branding_overrides(config)

    override_name = overrides.get("school_name")
    override_logo = overrides.get("logo_url")
    if override_name or override_logo:
        report.attempts.append(
            ProbeAttempt(
                endpoint="override",
                needed=True,
                outcome="selected",
                detail="user override present; API/theme not needed",
                school_name=override_name,
                logo_url=override_logo,
            )
        )
        report.attempts.append(
            ProbeAttempt(
                endpoint="GET /api/v1/accounts",
                needed=False,
                outcome="skipped",
                detail="skipped due to user override",
            )
        )
        report.attempts.append(
            ProbeAttempt(
                endpoint="GET /api/v1/accounts/self/theme",
                needed=False,
                outcome="skipped",
                detail="skipped due to user override",
            )
        )
        info = OrgInfo(school_name=override_name, logo_url=override_logo, source="user_override")
        report.winner_source = info.source
        report.winner_reason = "override has highest precedence"
        return info, report

    api_school: str | None = None
    api_logo: str | None = None
    if client is not None:
        api_school, api_logo, attempts = _resolve_api_theme(client)
        report.attempts.extend(attempts)

    if api_school or api_logo:
        info = OrgInfo(
            school_name=api_school,
            logo_url=api_logo,
            source="api_theme",
        )
        report.winner_source = info.source
        report.winner_reason = "API/theme provided at least one branding field"
        return info, report

    guessed = _guess_school_from_domain(base_url)
    info = OrgInfo(
        school_name=guessed,
        logo_url=None,
        source="domain_guess",
    )
    report.winner_source = info.source
    if client is None:
        report.winner_reason = "no API client/token available; used domain fallback"
    else:
        report.winner_reason = "API/theme unavailable or empty; used domain fallback"
    return info, report


def resolve_org_info(
    base_url: str,
    client: CanvasClient | None = None,
    config: dict | None = None,
) -> OrgInfo:
    info, _ = resolve_org_info_with_probe(base_url=base_url, client=client, config=config)
    return info
