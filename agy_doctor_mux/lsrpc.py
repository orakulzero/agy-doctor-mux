"""Antigravity Language Server Connect RPC Client for Programmatic Plugin Lifecycle Management."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import json
import os
from urllib import request as urllib_request
from typing import Any

TransportFn = Callable[[str, str, dict[str, str], dict[str, Any] | None], dict[str, Any]]


def _default_http_transport(
    method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None
) -> dict[str, Any]:
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib_request.Request(url, data=data, headers=headers, method=method)
    with urllib_request.urlopen(req, timeout=10.0) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}


class AntigravityLSRPCClient:
    """Connect RPC client for Antigravity Language Server (GetAllPlugins, JetboxWriteState, DeletePlugin)."""

    def __init__(
        self,
        address: str | None = None,
        csrf_token: str | None = None,
        transport: TransportFn | None = None,
    ) -> None:
        self.address = (
            address or os.environ.get("ANTIGRAVITY_LS_ADDRESS") or "localhost:5387"
        ).strip()
        self.csrf_token = (
            csrf_token
            if csrf_token is not None
            else os.environ.get("ANTIGRAVITY_CSRF_TOKEN", "")
        )
        self._transport: TransportFn = transport or _default_http_transport

    def call_rpc(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke an exa.language_server_pb.LanguageServerService Connect RPC endpoint."""
        url = f"http://{self.address}/exa.language_server_pb.LanguageServerService/{method}"
        headers = {
            "Content-Type": "application/json",
            "x-codeium-csrf-token": self.csrf_token,
        }
        return self._transport("POST", url, headers, payload)

    def list_installed_plugins(
        self, workspace_uris: Sequence[str] = ()
    ) -> list[dict[str, Any]]:
        """List installed plugins with extracted hash dir IDs and stripped SKILL.md bodies."""
        resp = self.call_rpc("GetAllPlugins", {"workspaceUris": list(workspace_uris)})
        raw_plugins = resp.get("plugins") or []
        summary: list[dict[str, Any]] = []

        for p in raw_plugins:
            if not isinstance(p, dict):
                continue
            raw_path = str(p.get("path", "")).replace("\\", "/").rstrip("/")
            dir_id = raw_path.split("/")[-1] if raw_path else str(p.get("name", ""))
            skills = [
                str(s.get("name", ""))
                for s in (p.get("skills") or [])
                if isinstance(s, dict) and s.get("name")
            ]
            agents = [
                str(a.get("name", ""))
                for a in (p.get("agents") or [])
                if isinstance(a, dict) and a.get("name")
            ]
            rules = [
                str(r.get("absolutePath", ""))
                for r in (p.get("rules") or [])
                if isinstance(r, dict) and r.get("absolutePath")
            ]
            mcp_list = p.get("mcpServers") or p.get("mcp") or []
            mcp_names = [
                str(m.get("name", ""))
                for m in mcp_list
                if isinstance(m, dict) and m.get("name")
            ]
            summary.append(
                {
                    "name": str(p.get("name", "")),
                    "dir": dir_id,
                    "disabled": bool(p.get("disabled", False)),
                    "isGlobal": bool(p.get("isGlobal", False)),
                    "skills": skills,
                    "agents": agents,
                    "rules": rules,
                    "hooks": bool(p.get("hooksJson") or p.get("hooks")),
                    "mcp": mcp_names,
                }
            )
        return summary

    def set_plugin_enabled(self, plugin_dir: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable a plugin by its folder name via JetboxWriteState."""
        return self.call_rpc(
            "JetboxWriteState",
            {
                "userConfig": {
                    "plugins": {
                        plugin_dir: {"enabled": bool(enabled)},
                    }
                }
            },
        )

    def safe_uninstall_plugin(
        self,
        plugin_dir: str,
        path: str = "",
        was_disabled: bool = False,
    ) -> dict[str, Any]:
        """Safely uninstall a plugin, guarding built-in plugins and re-enabling disabled plugins before DeletePlugin."""
        norm_path = path.replace("\\", "/")
        if "/builtin/plugins/" in norm_path:
            raise ValueError(
                "Built-in plugins cannot be uninstalled; disable the plugin instead."
            )

        re_enabled = False
        if was_disabled:
            self.set_plugin_enabled(plugin_dir, True)
            re_enabled = True

        self.call_rpc("DeletePlugin", {"pluginId": plugin_dir})
        return {
            "uninstalled": True,
            "pluginId": plugin_dir,
            "re_enabled_before_delete": re_enabled,
        }
