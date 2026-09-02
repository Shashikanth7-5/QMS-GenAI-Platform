"""MCP server registry for future agent tool integrations.

The registry is intentionally config-only today. It gives LangGraph/MCP
branches a stable place to declare external tool servers without making
test or production startup depend on network connections.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from services.logging_config import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str
    endpoint: str
    enabled: bool = True
    auth_env: str | None = None
    scopes: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "transport": self.transport,
            "endpoint": self.endpoint,
            "enabled": self.enabled,
            "authEnv": self.auth_env,
            "scopes": list(self.scopes),
            "metadata": dict(self.metadata or {}),
        }


def load_mcp_servers(raw_config: str | None = None) -> list[MCPServerConfig]:
    """Load MCP server declarations from JSON.

    Expected shape:
      [{"name": "salesforce", "transport": "http", "endpoint": "..."}]

    Set ``MCP_SERVER_CONFIG`` in production when the MCP layer is ready.
    Invalid entries are ignored so a bad optional tool declaration does not
    break the core QMS workflow.
    """

    raw = raw_config if raw_config is not None else os.getenv("MCP_SERVER_CONFIG", "")
    if not raw.strip():
        return []

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("mcp.registry.invalid_json", extra={"error": str(exc)})
        return []

    if not isinstance(decoded, list):
        log.warning("mcp.registry.invalid_shape", extra={"type": type(decoded).__name__})
        return []

    servers: list[MCPServerConfig] = []
    for item in decoded:
        config = _coerce_server(item)
        if config:
            servers.append(config)
    return servers


def enabled_mcp_tools(raw_config: str | None = None) -> list[dict[str, Any]]:
    return [server.to_dict() for server in load_mcp_servers(raw_config) if server.enabled]


def _coerce_server(item: Any) -> MCPServerConfig | None:
    if not isinstance(item, dict):
        return None

    name = str(item.get("name", "")).strip()
    transport = str(item.get("transport", "http")).strip().lower()
    endpoint = str(item.get("endpoint", "")).strip()
    if not name or not endpoint:
        return None

    scopes = item.get("scopes") or ()
    if isinstance(scopes, str):
        scopes = (scopes,)
    elif isinstance(scopes, list):
        scopes = tuple(str(scope) for scope in scopes if str(scope).strip())
    else:
        scopes = ()

    return MCPServerConfig(
        name=name,
        transport=transport,
        endpoint=endpoint,
        enabled=bool(item.get("enabled", True)),
        auth_env=item.get("authEnv") or item.get("auth_env"),
        scopes=tuple(scopes),
        metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    )
