from __future__ import annotations

from pathlib import Path

from canvas_ai import cli, mcp_server

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_feature_contract_versions_match() -> None:
    assert cli.FEATURE_CONTRACT_VERSION == mcp_server.FEATURE_CONTRACT_VERSION
    assert cli.SCHEMA_VERSION == mcp_server.SCHEMA_VERSION


def test_mcp_command_schema_mapping_files_exist() -> None:
    for schema_file in mcp_server.CLI_COMMAND_SCHEMAS.values():
        assert (REPO_ROOT / "schemas" / schema_file).exists(), schema_file


def test_docs_cover_mcp_tools_and_policies() -> None:
    mcp_doc = (REPO_ROOT / "docs" / "mcp-server.md").read_text()
    cmd_doc = (REPO_ROOT / "docs" / "command-reference.md").read_text()
    agent_doc = (REPO_ROOT / "docs" / "agent-interface.md").read_text()

    required_mcp_mentions = [
        "plan",
        "mcp_version_info",
        "resources",
        "auth_set_mode",
        "auth_login",
        "org_info",
        "org_set",
        "org_probe",
    ]
    for item in required_mcp_mentions:
        assert item in mcp_doc

    assert "max_review_token_age_minutes" in cmd_doc
    assert "feature_contract_version" in agent_doc
