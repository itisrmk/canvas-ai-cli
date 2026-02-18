from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

CONFIG_DIR = Path.home() / ".config" / "canvas-ai"
CONFIG_FILE = CONFIG_DIR / "config.json"

AuthMode = Literal["token", "oauth_placeholder"]


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    return CONFIG_FILE


def get_auth_mode(config: dict | None = None) -> AuthMode:
    data = config if config is not None else load_config()
    auth = data.get("auth", {}) if isinstance(data.get("auth", {}), dict) else {}
    mode = auth.get("mode")
    if mode in {"token", "oauth_placeholder"}:
        return mode
    return "token"


def set_auth_mode(mode: AuthMode) -> Path:
    config = load_config()
    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    auth["mode"] = mode
    config["auth"] = auth
    return save_config(config)


def save_token(token: str) -> Path:
    config = load_config()
    clean = token.strip()

    # Legacy key kept for backward compatibility with older versions.
    config["canvas_api_token"] = clean

    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    auth["mode"] = "token"
    auth["token"] = clean
    config["auth"] = auth

    if os.getenv("CANVAS_BASE_URL"):
        config["canvas_base_url"] = os.getenv("CANVAS_BASE_URL")

    return save_config(config)


def set_branding_overrides(*, school_name: str | None, logo_url: str | None) -> Path:
    config = load_config()
    branding = config.get("branding") if isinstance(config.get("branding"), dict) else {}

    if school_name is not None:
        branding["school_name"] = school_name
    if logo_url is not None:
        branding["logo_url"] = logo_url

    config["branding"] = branding
    return save_config(config)


def get_branding_overrides(config: dict | None = None) -> dict[str, str | None]:
    data = config if config is not None else load_config()
    branding = data.get("branding") if isinstance(data.get("branding"), dict) else {}
    return {
        "school_name": branding.get("school_name"),
        "logo_url": branding.get("logo_url"),
    }


def get_canvas_token() -> str | None:
    env_token = os.getenv("CANVAS_API_TOKEN")
    if env_token:
        return env_token

    config = load_config()
    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    token = auth.get("token")
    if token:
        return token

    # Backward compatibility with v1 config.
    return config.get("canvas_api_token")


def get_canvas_base_url() -> str | None:
    env_base = os.getenv("CANVAS_BASE_URL")
    if env_base:
        return env_base

    config = load_config()
    return config.get("canvas_base_url")
