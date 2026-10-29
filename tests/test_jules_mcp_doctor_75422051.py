import os
import pytest
from unittest import mock

from agy_doctor_mux.mcp_doctor import (
    _short_hash,
    _sanitize_chars,
    _process_single_tool_name,
    audit_mcp_config,
    validate_mcp_config_strict,
    diagnose_and_heal_network_env,
    _compact_text,
    _compact_schema_node,
    compact_mcp_schema_descriptions,
)

def test_short_hash():
    h1 = _short_hash("test")
    assert len(h1) == 6
    h2 = _short_hash("test", 10)
    assert len(h2) == 10
    assert h1 == h2[:6]

def test_sanitize_chars():
    assert _sanitize_chars("valid-name_123:") == "valid-name_123:"
    assert _sanitize_chars("invalid/name@123") == "invalid_name_123"

def test_process_single_tool_name_exact_54():
    # orig_srv="valid" (5), mcp_valid_ is 10 chars. 10 + 54 = 64 chars max composite.
    tool_str = "a" * 54
    violations = []
    alias_map = {}
    res = _process_single_tool_name(
        orig_srv="valid",
        target_srv="valid",
        tool_str=tool_str,
        auto_fix=True,
        violations=violations,
        alias_map=alias_map,
    )
    assert res == tool_str
    assert len(violations) == 0
    assert len(alias_map) == 0

def test_process_single_tool_name_overlong():
    tool_str = "a" * 55
    violations = []
    alias_map = {}
    res = _process_single_tool_name(
        orig_srv="valid",
        target_srv="valid",
        tool_str=tool_str,
        auto_fix=True,
        violations=violations,
        alias_map=alias_map,
    )
    assert len(res) == 54
    assert "_" in res
    assert len(violations) == 1
    assert violations[0]["type"] == "overlong_identifier"
    assert len(alias_map) == 1

def test_process_single_tool_name_invalid_chars():
    tool_str = "invalid@tool"
    violations = []
    alias_map = {}
    res = _process_single_tool_name(
        orig_srv="valid",
        target_srv="valid",
        tool_str=tool_str,
        auto_fix=True,
        violations=violations,
        alias_map=alias_map,
    )
    assert res == "invalid_tool"
    assert len(violations) == 1
    assert violations[0]["type"] == "invalid_characters"
    assert len(alias_map) == 1

def test_audit_mcp_config_empty_or_invalid():
    res = audit_mcp_config({})
    assert res["valid"] is True

    res2 = audit_mcp_config({"mcpServers": []})
    assert res2["valid"] is True

def test_audit_mcp_config_valid_and_invalid():
    cfg = {
        "mcpServers": {
            "srv1": {
                "timeout_ms": 1000,
                "tools": ["tool1"]
            },
            "srv2": {
                # missing timeout
                "tools": {"tool@2": {}}
            }
        }
    }
    # auto_fix=False
    res = audit_mcp_config(cfg)
    assert res["valid"] is False
    assert len(res["violations"]) == 2  # missing timeout, invalid chars
    
    # auto_fix=True
    res_fixed = audit_mcp_config(cfg, auto_fix=True)
    assert res_fixed["valid"] is True
    assert "timeout_ms" in res_fixed["config"]["mcpServers"]["srv2"]
    assert "tool_2" in res_fixed["config"]["mcpServers"]["srv2"]["tools"]

def test_audit_mcp_config_non_dict_server():
    cfg = {
        "mcpServers": {
            "srv1": "not a dict"
        }
    }
    res = audit_mcp_config(cfg)
    assert res["config"]["mcpServers"]["srv1"] == "not a dict"

def test_validate_mcp_config_strict():
    valid, errors = validate_mcp_config_strict({"mcpServers": {"srv": {"timeout_ms": 100, "tools": ["a" * 60]}}})
    assert not valid
    assert len(errors) == 1
    assert "exceeds 64 characters" in errors[0]

    valid, errors = validate_mcp_config_strict({"mcpServers": {"srv": {"tools": ["valid"]}}})
    assert not valid
    assert len(errors) == 1
    assert "missing a positive integer" in errors[0]

    valid, errors = validate_mcp_config_strict({"mcpServers": {"srv": {"timeout_ms": 100, "tools": ["val@id"]}}})
    assert not valid
    assert len(errors) == 1
    assert "invalid characters" in errors[0]

@mock.patch("socket.create_connection")
def test_diagnose_and_heal_network_env(mock_conn):
    env = {
        "HTTP_PROXY": "http://127.0.0.1:8080",
        "HTTPS_PROXY": "https://localhost:8443",
        "ALL_PROXY": "socks5://::1:1080",
        "OTHER_VAR": "value",
        "NON_LOOPBACK": "http://example.com"
    }

    # Simulate timeout on 127.0.0.1 and connection refused on localhost, success on ::1
    def side_effect(address, timeout):
        host, port = address
        if host == "127.0.0.1":
            raise TimeoutError("timeout")
        elif host == "localhost":
            raise OSError("refused")
        # else success
        return mock.MagicMock()

    mock_conn.side_effect = side_effect

    res = diagnose_and_heal_network_env(env, heal=True)
    assert not res["clean"]
    assert "HTTP_PROXY" in res["stale_proxy_vars"]
    assert "HTTPS_PROXY" in res["stale_proxy_vars"]
    assert "ALL_PROXY" not in res["stale_proxy_vars"]
    assert "NON_LOOPBACK" not in res["stale_proxy_vars"]

    assert "HTTP_PROXY" not in res["sanitized_env"]
    assert "HTTPS_PROXY" not in res["sanitized_env"]
    assert "ALL_PROXY" in res["sanitized_env"]

def test_diagnose_and_heal_network_env_none_env():
    with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:8080"}):
        with mock.patch("socket.create_connection", side_effect=TimeoutError):
            res = diagnose_and_heal_network_env(heal=False)
            assert not res["clean"]
            assert "HTTP_PROXY" in res["stale_proxy_vars"]
            assert "HTTP_PROXY" in res["sanitized_env"] # no heal

def test_diagnose_and_heal_network_env_various_parsing():
    env = {
        "HTTP_PROXY": "127.0.0.1:8080", # no scheme
        "HTTPS_PROXY": "127.0.0.1", # no scheme, no port
    }
    with mock.patch("socket.create_connection", side_effect=TimeoutError):
        res = diagnose_and_heal_network_env(env, heal=True)
        assert len(res["stale_proxy_vars"]) == 2

def test_compact_text():
    # Long text with boilerplate
    text = "This tool allows you to do something amazing. It does it well."
    assert _compact_text(text) == "Do something amazing."

    prop_text = "An optional string representing the name of the user."
    assert _compact_text(prop_text, is_property=True) == "Name of the user."

    long_text = "This is a very long text that goes on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on."
    compacted = _compact_text(long_text)
    assert len(compacted) <= 110

def test_compact_schema_node():
    schema = {
        "description": "This tool allows you to do X.",
        "properties": {
            "prop1": {
                "description": "An optional string representing Y."
            }
        },
        "tools": [
            {
                "description": "This tool is used to Z."
            }
        ],
        "items": [
            {
                "description": "Some item."
            }
        ]
    }
    compacted = _compact_schema_node(schema)
    assert compacted["description"] == "Do X."
    assert compacted["properties"]["prop1"]["description"] == "Y."
    assert compacted["tools"][0]["description"] == "Z."
    assert compacted["items"][0]["description"] == "Some item."

def test_compact_mcp_schema_descriptions():
    schema = {
        "description": "This tool allows you to do X.",
        "properties": {
            "prop1": {
                "description": "An optional string representing Y."
            }
        }
    }
    compacted, telemetry = compact_mcp_schema_descriptions(schema)
    assert telemetry["reduction_pct"] > 0
    assert compacted["description"] == "Do X."

    compacted_empty, tel_empty = compact_mcp_schema_descriptions({})
    assert tel_empty["original_chars"] == 0
