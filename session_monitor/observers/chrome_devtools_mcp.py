"""Chrome DevTools MCP observer profile for Watcher.

This module does not vendor or reimplement Chrome DevTools MCP. It describes the
official ChromeDevTools/chrome-devtools-mcp server as an optional browser-side
observer and generates a privacy-hardened launch command.

Watcher should ingest only metadata/evidence needed for observability. Full
browser content, cookies, storage values, auth headers, prompts, and page bodies
must not be persisted by default.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import ObserverCapabilities, ObserverDescriptor


OFFICIAL_REPOSITORY = "ChromeDevTools/chrome-devtools-mcp"
NPM_PACKAGE = "chrome-devtools-mcp@latest"

DESCRIPTOR = ObserverDescriptor(
    observer_id="chrome-devtools-mcp",
    display_name="Chrome DevTools MCP",
    transport="mcp",
    capabilities=ObserverCapabilities(
        network=True,
        console=True,
        performance=True,
        browser_pages=True,
        screenshots=True,
    ),
    unavailable=(
        "provider_internal_accounting",
        "authoritative_llm_context_state",
        "authoritative_editor_focus_time",
    ),
    notes=(
        "Official Chrome DevTools MCP server; browser observation is independent of the LLM provider adapter.",
        "Watcher defaults disable Chrome DevTools MCP usage statistics and CrUX performance lookups.",
        "Sensitive network headers should be redacted before MCP results enter Watcher.",
    ),
)


@dataclass(frozen=True)
class ChromeDevToolsMcpConfig:
    browser_url: str | None = None
    headless: bool = False
    redact_network_headers: bool = True
    disable_usage_statistics: bool = True
    disable_performance_crux: bool = True
    slim: bool = False


def launch_args(config: ChromeDevToolsMcpConfig | None = None) -> list[str]:
    """Return the privacy-hardened argv for the official MCP server.

    The caller owns process lifecycle and MCP transport. This function merely
    provides an auditable configuration; it does not launch Chrome or the MCP
    server itself.
    """
    config = config or ChromeDevToolsMcpConfig()
    args = ["npx", "-y", NPM_PACKAGE]

    if config.disable_usage_statistics:
        args.append("--no-usage-statistics")
    if config.disable_performance_crux:
        args.append("--no-performance-crux")
    if config.redact_network_headers:
        args.append("--redact-network-headers")
    if config.browser_url:
        args.append(f"--browser-url={config.browser_url}")
    if config.headless:
        args.append("--headless")
    if config.slim:
        args.append("--slim")

    return args


def evidence_policy() -> dict:
    """Describe what Watcher may persist from this observer by default."""
    return {
        "persist": [
            "request_timestamps",
            "request_method",
            "request_url_redacted_or_scoped",
            "response_status",
            "request_duration",
            "console_event_metadata",
            "performance_timing_metadata",
            "page_or_target_identifier",
            "observer_tool_name",
            "observer_result_status",
        ],
        "do_not_persist_by_default": [
            "cookies",
            "local_storage_values",
            "session_storage_values",
            "authorization_headers",
            "raw_request_bodies",
            "raw_response_bodies",
            "page_text_content",
            "screenshots",
        ],
        "classification": "observed",
    }
