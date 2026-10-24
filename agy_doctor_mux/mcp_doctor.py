"""MCP Schema Linter, <64-Char Composite Identifier Sanitizer, and Timeout Injector."""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

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
