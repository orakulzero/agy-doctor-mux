"""MCP Schema Linter, <64-Char Composite Identifier Sanitizer, and Timeout Injector."""

from __future__ import annotations

import copy
import hashlib
import os
import re
import socket
from typing import Any
from urllib.parse import urlsplit

VALID_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_.\-:]+$")
INVALID_CHAR_RE = re.compile(r"[^a-zA-Z0-9_.\-:]")
MAX_COMPOSITE_LEN = 64
MAX_SERVER_NAME_LEN = 22
DEFAULT_TIMEOUT_MS = 15000


def _short_hash(text: str, length: int = 6) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _sanitize_chars(text: str) -> str:
    return INVALID_CHAR_RE.sub("_", text)


def _process_single_tool_name(
    orig_srv: str,
    target_srv: str,
    tool_str: str,
    auto_fix: bool,
    violations: list[dict[str, Any]],
    alias_map: dict[str, str],
) -> str:
    orig_composite = f"mcp_{orig_srv}_{tool_str}"
    if not VALID_IDENTIFIER_RE.match(orig_composite):
        violations.append(
            {
                "type": "invalid_characters",
                "server": orig_srv,
                "tool": tool_str,
                "composite": orig_composite,
            }
        )
    if len(orig_composite) > MAX_COMPOSITE_LEN:
        violations.append(
            {
                "type": "overlong_identifier",
                "server": orig_srv,
                "tool": tool_str,
                "composite": orig_composite,
                "length": len(orig_composite),
            }
        )

    if not auto_fix:
        return tool_str

    clean_tool = _sanitize_chars(tool_str)
    prefix_len = len(f"mcp_{target_srv}_")
    max_tool_len = MAX_COMPOSITE_LEN - prefix_len
    if len(clean_tool) > max_tool_len:
        th6 = _short_hash(tool_str, 6)
        keep = max(1, max_tool_len - 7)
        fixed_tool = f"{clean_tool[:keep]}_{th6}"
    else:
        fixed_tool = clean_tool
    new_composite = f"mcp_{target_srv}_{fixed_tool}"
    if new_composite != orig_composite:
        alias_map[orig_composite] = new_composite
    return fixed_tool


def audit_mcp_config(
    config: dict[str, Any],
    auto_fix: bool = False,
    default_timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    """Audit and optionally auto-fix MCP server configurations against Antigravity 2.0 limits."""
    working_cfg = copy.deepcopy(config)
    servers = working_cfg.get("mcpServers")
    if not isinstance(servers, dict):
        return {
            "valid": True,
            "violations": [],
            "alias_map": {},
            "config": working_cfg,
        }

    violations: list[dict[str, Any]] = []
    alias_map: dict[str, str] = {}
    new_servers: dict[str, Any] = {}

    for orig_srv, srv_cfg in servers.items():
        if not isinstance(srv_cfg, dict):
            new_servers[orig_srv] = srv_cfg
            continue

        # 1. Check timeout_ms
        timeout_val = srv_cfg.get("timeout_ms")
        if not isinstance(timeout_val, int) or timeout_val <= 0:
            violations.append(
                {
                    "type": "missing_timeout",
                    "server": orig_srv,
                }
            )
            if auto_fix:
                srv_cfg["timeout_ms"] = default_timeout_ms

        # 2. Check server name and tool names
        clean_srv = _sanitize_chars(orig_srv)
        if len(clean_srv) > MAX_SERVER_NAME_LEN:
            h6 = _short_hash(orig_srv, 6)
            short_srv = f"{clean_srv[:MAX_SERVER_NAME_LEN - 7]}_{h6}"
        else:
            short_srv = clean_srv

        target_srv = short_srv if auto_fix else orig_srv
        if auto_fix and target_srv != orig_srv:
            alias_map[f"server:{orig_srv}"] = target_srv

        tools = srv_cfg.get("tools")
        if isinstance(tools, list):
            new_tools_list: list[str] = []
            for orig_tool in tools:
                fixed_tool = _process_single_tool_name(
                    orig_srv=orig_srv,
                    target_srv=target_srv,
                    tool_str=str(orig_tool),
                    auto_fix=auto_fix,
                    violations=violations,
                    alias_map=alias_map,
                )
                new_tools_list.append(fixed_tool)
            srv_cfg["tools"] = new_tools_list
        elif isinstance(tools, dict):
            new_tools_dict: dict[str, Any] = {}
            for orig_tool, tool_meta in tools.items():
                fixed_tool = _process_single_tool_name(
                    orig_srv=orig_srv,
                    target_srv=target_srv,
                    tool_str=str(orig_tool),
                    auto_fix=auto_fix,
                    violations=violations,
                    alias_map=alias_map,
                )
                new_tools_dict[fixed_tool] = copy.deepcopy(tool_meta)
            srv_cfg["tools"] = new_tools_dict

        new_servers[target_srv] = srv_cfg

    working_cfg["mcpServers"] = new_servers
    return {
        "valid": True if auto_fix else (len(violations) == 0),
        "violations": violations,
        "alias_map": alias_map,
        "config": working_cfg,
    }


def validate_mcp_config_strict(config: dict[str, Any]) -> tuple[bool, list[str]]:
    """Strictly validate MCP configuration enforcing <=64-char names and timeout_ms > 0."""
    res = audit_mcp_config(config, auto_fix=False)
    violations = res.get("violations") or []
    errors: list[str] = []
    for v in violations:
        v_type = v.get("type")
        srv = v.get("server")
        if v_type == "missing_timeout":
            errors.append(f"Server '{srv}' is missing a positive integer 'timeout_ms'.")
        elif v_type == "overlong_identifier":
            errors.append(f"Identifier '{v.get('composite')}' exceeds 64 characters (length: {v.get('length')}).")
        elif v_type == "invalid_characters":
            errors.append(f"Identifier '{v.get('composite')}' contains invalid characters.")
    return len(errors) == 0, errors


def diagnose_and_heal_network_env(
    env: dict[str, str] | None = None,
    heal: bool = True,
    probe_timeout_s: float = 0.2,
) -> dict[str, Any]:
    """Diagnose and heal unreachable loopback proxy environment variables.

    Inspects HTTP_PROXY, HTTPS_PROXY, ALL_PROXY and lowercase equivalents.
    If a variable points to a loopback address (127.0.0.1, localhost, ::1, 127.*)
    and TCP connection fails or times out, marks it as dead. If heal=True,
    removes the variable from the environment.

    Non-loopback proxies are preserved regardless of connectivity.
    """
    if env is None:
        target_env = os.environ
    else:
        target_env = env

    stale_proxy_vars: list[str] = []
    healed_vars: list[str] = []
    probed_proxies: list[dict[str, Any]] = []

    # Target proxy variables to inspect (both upper and lower variants)
    target_keys: list[str] = []
    for k in list(target_env.keys()):
        if k.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}:
            target_keys.append(k)

    for var_name in target_keys:
        raw_val = target_env.get(var_name)
        if not raw_val or not isinstance(raw_val, str) or not raw_val.strip():
            continue
        val_str = raw_val.strip()

        # Parse host and port
        try:
            if "://" not in val_str:
                parsed = urlsplit(f"http://{val_str}")
            else:
                parsed = urlsplit(val_str)
            raw_host = (parsed.hostname or "").strip()
            host_clean = raw_host.strip("[]").lower()
            port = parsed.port
            if port is None:
                scheme = (parsed.scheme or "http").lower()
                if scheme == "https":
                    port = 443
                elif scheme in ("socks5", "socks4"):
                    port = 1080
                else:
                    port = 80
        except Exception:
            raw_host = ""
            host_clean = ""
            port = 80

        is_loopback = False
        if host_clean in ("127.0.0.1", "localhost", "::1") or host_clean.startswith("127."):
            is_loopback = True

        reachable: bool | None = None
        error_msg: str | None = None
        is_dead = False

        if is_loopback:
            try:
                with socket.create_connection((host_clean, port), timeout=probe_timeout_s):
                    reachable = True
            except (OSError, TimeoutError) as exc:
                reachable = False
                error_msg = str(exc)
                is_dead = True
        else:
            # Non-loopback proxies must NOT be removed even if connection test times out
            is_dead = False
            reachable = None

        probe_info: dict[str, Any] = {
            "variable": var_name,
            "url": val_str,
            "host": host_clean,
            "port": port,
            "is_loopback": is_loopback,
            "reachable": reachable,
            "dead": is_dead,
        }
        if error_msg:
            probe_info["error"] = error_msg
        probed_proxies.append(probe_info)

        if is_dead:
            stale_proxy_vars.append(var_name)
            if heal:
                target_env.pop(var_name, None)
                healed_vars.append(var_name)

    return {
        "clean": len(stale_proxy_vars) == 0,
        "stale_proxy_vars": stale_proxy_vars,
        "healed_vars": healed_vars,
        "probed_proxies": probed_proxies,
        "sanitized_env": dict(target_env),
        "healed": len(healed_vars) > 0,
        "env_healed": len(healed_vars) > 0,
    }
