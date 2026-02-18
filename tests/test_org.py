from __future__ import annotations

from canvas_ai.canvas_client import CanvasClientError
from canvas_ai.org import resolve_org_info, resolve_org_info_with_probe


class APIClient:
    def list_accounts(self):
        return [{"name": "State University"}]

    def get_branding_theme(self):
        return {"logo_url": "https://cdn/logo.png"}


class PartialAPIClient:
    def list_accounts(self):
        return [{"display_name": "Only Name College"}]

    def get_branding_theme(self):
        raise CanvasClientError("theme forbidden", status_code=403, error_type="http")


class ErrorClient:
    def __init__(self, accounts_error: CanvasClientError, theme_error: CanvasClientError):
        self.accounts_error = accounts_error
        self.theme_error = theme_error

    def list_accounts(self):
        raise self.accounts_error

    def get_branding_theme(self):
        raise self.theme_error


def test_org_resolver_precedence_user_override_over_api() -> None:
    config = {"branding": {"school_name": "Override U", "logo_url": "https://override/logo.png"}}
    info, report = resolve_org_info_with_probe(
        "https://school.instructure.com", client=APIClient(), config=config
    )

    assert info.school_name == "Override U"
    assert info.logo_url == "https://override/logo.png"
    assert info.source == "user_override"
    assert report.winner_source == "user_override"
    assert any(a.outcome == "skipped" for a in report.attempts)


def test_org_resolver_uses_api_when_no_override() -> None:
    info, report = resolve_org_info_with_probe(
        "https://school.instructure.com", client=APIClient(), config={}
    )

    assert info.school_name == "State University"
    assert info.logo_url == "https://cdn/logo.png"
    assert info.source == "api_theme"
    assert report.winner_reason.startswith("API/theme")


def test_org_resolver_deterministic_partial_api_data() -> None:
    info, report = resolve_org_info_with_probe(
        "https://north-ridge.instructure.com",
        client=PartialAPIClient(),
        config={},
    )

    assert info.school_name == "Only Name College"
    assert info.logo_url is None
    assert info.source == "api_theme"
    assert any(
        a.endpoint == "GET /api/v1/accounts/self/theme" and a.outcome == "forbidden"
        for a in report.attempts
    )


def test_org_resolver_handles_401_403_404_and_falls_back() -> None:
    client = ErrorClient(
        accounts_error=CanvasClientError("unauthorized", status_code=401, error_type="http"),
        theme_error=CanvasClientError("missing", status_code=404, error_type="http"),
    )
    info, report = resolve_org_info_with_probe(
        "https://north-ridge.instructure.com",
        client=client,
        config={},
    )

    assert info.source == "domain_guess"
    assert any(a.outcome == "unauthorized" for a in report.attempts)
    assert any(a.outcome == "not_found" for a in report.attempts)


def test_org_resolver_handles_timeout_network_and_falls_back() -> None:
    client = ErrorClient(
        accounts_error=CanvasClientError("timeout", error_type="timeout"),
        theme_error=CanvasClientError("network", error_type="network"),
    )
    info = resolve_org_info("https://north-ridge.instructure.com", client=client, config={})

    assert info.school_name == "North Ridge"
    assert info.logo_url is None
    assert info.source == "domain_guess"
