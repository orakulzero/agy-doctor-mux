"""MCP Schema Linter, <64-Char Composite Identifier Sanitizer, and Timeout Injector."""

from __future__ import annotations

import copy
import hashlib
import json
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
    target_env = os.environ if env is None else env

    stale_proxy_vars: list[str] = []
    healed_vars: list[str] = []
    probed_proxies: list[dict[str, Any]] = []

    # Target proxy variables to inspect (both upper and lower variants)
    target_keys = [k for k in list(target_env.keys()) if k.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}]

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


# Boilerplate prefix patterns to strip deterministically
_BOILERPLATE_PREFIXES = [
    # Tool-level introductions
    re.compile(
        r"^(?:this\s+)?(?:tool|function|method|endpoint|service|routine|api)\s+"
        r"(?:allows\s+(?:you|the\s+user)\s+to|is\s+used\s+to|allows\s+to|is\s+designed\s+to|serves\s+to|will|can)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:used\s+to|allows\s+(?:you|the\s+user)\s+to|provides\s+(?:the\s+ability\s+to|a\s+way\s+to))\s*",
        re.IGNORECASE,
    ),
    # Parameter-level intros
    re.compile(
        r"^(?:an?|the)\s+(?:optional|required)?\s*"
        r"(?:string|boolean|integer|number|array|object|float|dict|list|mapping)\s+"
        r"(?:representing|specifying|indicating|denoting|holding|defining|containing|providing|which\s+is|that\s+is)\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:a|an|the)\s+(?:parameter|argument|field|property|flag|value)\s+"
        r"(?:that|which)?\s*(?:specifies|indicates|represents|defines|holds|determines|denotes)?\s*",
        re.IGNORECASE,
    ),
    # Disclaimers / notes
    re.compile(
        r"^(?:please\s+note\s+that|note:|notice:|important:)\s*",
        re.IGNORECASE,
    ),
]


def _compact_text(text: str, is_property: bool = False) -> str:
    """Compact a single description string cleanly and deterministically.

    Strips boilerplate prefixes, cleans whitespace and markdown artifacts,
    retains the primary informative sentence, and enforces concise length bounds.
    """
    if not text or not isinstance(text, str):
        return text

    cleaned = text.strip()

    # Flatten redundant whitespace, line breaks, HTML tags, and markdown bold/italic
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"[*_]{1,3}", "", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

    # Iteratively strip matched boilerplate prefixes
    changed = True
    while changed:
        changed = False
        for pattern in _BOILERPLATE_PREFIXES:
            new_text = pattern.sub("", cleaned).strip()
            if new_text != cleaned:
                cleaned = new_text
                changed = True

    # Strip redundant leading articles if followed by noun
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.IGNORECASE).strip()

    # Extract first sentence
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    first_sentence = sentences[0].strip() if sentences else cleaned

    # Sentence length bounds: tools <= 110 chars, properties <= 65 chars
    max_len = 65 if is_property else 110

    if len(first_sentence) > max_len:
        # Truncate at word boundary with ellipsis
        truncated = first_sentence[: max_len - 3]
        last_space = truncated.rfind(" ")
        if last_space > 20:
            truncated = truncated[:last_space]
        first_sentence = truncated.rstrip(",;:- ") + "..."

    # Ensure capitalized start and trailing punctuation
    if first_sentence:
        first_sentence = first_sentence[0].upper() + first_sentence[1:]
        if not first_sentence.endswith((".", "!", "?", "...")):
            first_sentence += "."

    return first_sentence


def _compact_schema_node(node: Any, is_property: bool = False) -> Any:
    """Recursively traverse schema dictionary and compact description values."""
    if isinstance(node, dict):
        compacted_dict: dict[str, Any] = {}
        for key, val in node.items():
            if key == "description" and isinstance(val, str):
                compacted_dict[key] = _compact_text(val, is_property=is_property)
            elif key == "properties" and isinstance(val, dict):
                compacted_props = {
                    p_name: _compact_schema_node(p_val, is_property=True)
                    for p_name, p_val in val.items()
                }
                compacted_dict[key] = compacted_props
            elif key == "tools" and isinstance(val, list):
                compacted_dict[key] = [
                    _compact_schema_node(t, is_property=False) for t in val
                ]
            else:
                compacted_dict[key] = _compact_schema_node(val, is_property=is_property)
        return compacted_dict

    if isinstance(node, list):
        return [_compact_schema_node(item, is_property=is_property) for item in node]

    return node


def compact_mcp_schema_descriptions(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recursively compact verbose descriptions in an MCP schema.

    Preserves 100% of JSON Schema constraints (type, properties, required,
    enum, items, default, minimum, maximum, etc.) while stripping boilerplate
    prefixes and sentence clutter.

    Args:
        schema: Original MCP or JSON Schema dictionary.

    Returns:
        Tuple of:
            - Compacted schema dictionary.
            - Telemetry dictionary containing:
                * original_chars
                * compacted_chars
                * reduction_pct
                * original_tokens
                * compacted_tokens
                * tokens_saved
    """
    if not isinstance(schema, dict) or not schema:
        return schema if isinstance(schema, dict) else {}, {
            "original_chars": 0,
            "compacted_chars": 0,
            "reduction_pct": 0.0,
            "original_tokens": 0,
            "compacted_tokens": 0,
            "tokens_saved": 0,
        }

    original_copy = copy.deepcopy(schema)
    compacted = _compact_schema_node(original_copy, is_property=False)

    orig_json = json.dumps(original_copy, sort_keys=True)
    comp_json = json.dumps(compacted, sort_keys=True)

    original_chars = len(orig_json)
    compacted_chars = len(comp_json)

    if original_chars > 0 and original_chars > compacted_chars:
        reduction_pct = round(
            ((original_chars - compacted_chars) / original_chars) * 100.0, 2
        )
    else:
        reduction_pct = 0.0

    original_tokens = (original_chars + 3) // 4
    compacted_tokens = (compacted_chars + 3) // 4
    tokens_saved = max(0, original_tokens - compacted_tokens)

    telemetry: dict[str, Any] = {
        "original_chars": original_chars,
        "compacted_chars": compacted_chars,
        "reduction_pct": reduction_pct,
        "original_tokens": original_tokens,
        "compacted_tokens": compacted_tokens,
        "tokens_saved": tokens_saved,
    }

    return compacted, telemetry
