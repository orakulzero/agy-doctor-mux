import os
import pytest
from agy_doctor_mux.lsrpc import AntigravityLSRPCClient

def test_list_installed_plugins_edge_case():
    client = AntigravityLSRPCClient()
    
    # Mock call_rpc
    def mock_call_rpc(method, payload):
        if method == "GetAllPlugins":
            return {
                "plugins": [
                    {
                        "path": "",
                        "name": "fallback-name",
                        "agents": [
                            {"agent": {"name": "nested-agent"}}
                        ]
                    }
                ]
            }
        return {}
    
    client.call_rpc = mock_call_rpc
    
    summary = client.list_installed_plugins()
    assert len(summary) == 1
    plugin_summary = summary[0]
    
    assert plugin_summary["dir"] == "fallback-name"
    assert plugin_summary["agents"] == ["nested-agent"]
    assert plugin_summary["name"] == "fallback-name"
    assert plugin_summary["skills"] == []
    assert plugin_summary["rules"] == []
    assert plugin_summary["mcp"] == []
    assert plugin_summary["disabled"] is False
    assert plugin_summary["isGlobal"] is False
    assert plugin_summary["hooks"] is False

def test_list_installed_plugins_all_fields():
    client = AntigravityLSRPCClient()
    
    # Mock call_rpc
    def mock_call_rpc(method, payload):
        if method == "GetAllPlugins":
            return {
                "plugins": [
                    {
                        "path": "some\\windows\\path\\plugin_id\\",
                        "name": "full-plugin",
                        "disabled": True,
                        "isGlobal": True,
                        "skills": [
                            {"name": "skill1"},
                            "invalid_skill",
                            {"name": ""}
                        ],
                        "agents": [
                            {"name": "agent1"},
                            {"agent": {"name": "agent2"}},
                            "invalid_agent",
                            {"agent": "invalid_nested"}
                        ],
                        "rules": [
                            {"absolutePath": "/tmp/rule1"},
                            {"relative": "rule2"}
                        ],
                        "mcpServers": [
                            {"name": "mcp1"}
                        ],
                        "hooks": True
                    }
                ]
            }
        return {}
    
    client.call_rpc = mock_call_rpc
    
    summary = client.list_installed_plugins()
    assert len(summary) == 1
    plugin_summary = summary[0]
    
    assert plugin_summary["dir"] == "plugin_id"
    assert plugin_summary["name"] == "full-plugin"
    assert plugin_summary["disabled"] is True
    assert plugin_summary["isGlobal"] is True
    assert plugin_summary["skills"] == ["skill1"]
    assert plugin_summary["agents"] == ["agent1", "agent2"]
    assert plugin_summary["rules"] == ["/tmp/rule1"]
    assert plugin_summary["mcp"] == ["mcp1"]
    assert plugin_summary["hooks"] is True

def test_list_installed_plugins_invalid_plugin_type():
    client = AntigravityLSRPCClient()
    
    # Mock call_rpc
    def mock_call_rpc(method, payload):
        if method == "GetAllPlugins":
            return {
                "plugins": [
                    "this is a string, not a dict",
                    None,
                    123
                ]
            }
        return {}
    
    client.call_rpc = mock_call_rpc
    
    summary = client.list_installed_plugins()
    assert len(summary) == 0

def test_safe_uninstall_plugin_builtin():
    client = AntigravityLSRPCClient()
    with pytest.raises(ValueError, match="Built-in plugins cannot be uninstalled"):
        client.safe_uninstall_plugin("my_plugin", path="/foo/builtin/plugins/my_plugin")

def test_safe_uninstall_plugin_was_disabled():
    client = AntigravityLSRPCClient()
    
    calls = []
    def mock_call_rpc(method, payload):
        calls.append((method, payload))
        return {}
    client.call_rpc = mock_call_rpc
    
    res = client.safe_uninstall_plugin("my_plugin", path="/foo/my_plugin", was_disabled=True)
    
    assert res["uninstalled"] is True
    assert res["pluginId"] == "my_plugin"
    assert res["re_enabled_before_delete"] is True
    
    assert len(calls) == 2
    assert calls[0][0] == "JetboxWriteState"
    assert calls[0][1] == {"userConfig": {"plugins": {"my_plugin": {"enabled": True}}}}
    assert calls[1][0] == "DeletePlugin"
    assert calls[1][1] == {"pluginId": "my_plugin"}

def test_safe_uninstall_plugin_normal():
    client = AntigravityLSRPCClient()
    
    calls = []
    def mock_call_rpc(method, payload):
        calls.append((method, payload))
        return {}
    client.call_rpc = mock_call_rpc
    
    res = client.safe_uninstall_plugin("my_plugin", path="/foo/my_plugin", was_disabled=False)
    
    assert res["uninstalled"] is True
    assert res["pluginId"] == "my_plugin"
    assert res["re_enabled_before_delete"] is False
    
    assert len(calls) == 1
    assert calls[0][0] == "DeletePlugin"
    assert calls[0][1] == {"pluginId": "my_plugin"}

def test_set_plugin_enabled():
    client = AntigravityLSRPCClient()
    
    calls = []
    def mock_call_rpc(method, payload):
        calls.append((method, payload))
        return {}
    client.call_rpc = mock_call_rpc
    
    client.set_plugin_enabled("my_plugin", False)
    
    assert len(calls) == 1
    assert calls[0][0] == "JetboxWriteState"
    assert calls[0][1] == {"userConfig": {"plugins": {"my_plugin": {"enabled": False}}}}

def test_client_init():
    os.environ["ANTIGRAVITY_LS_ADDRESS"] = "custom:1234"
    os.environ["ANTIGRAVITY_CSRF_TOKEN"] = "my_token"
    
    client = AntigravityLSRPCClient()
    assert client.address == "custom:1234"
    assert client.csrf_token == "my_token"
    
    if "ANTIGRAVITY_LS_ADDRESS" in os.environ:
        del os.environ["ANTIGRAVITY_LS_ADDRESS"]
    if "ANTIGRAVITY_CSRF_TOKEN" in os.environ:
        del os.environ["ANTIGRAVITY_CSRF_TOKEN"]
    
    client = AntigravityLSRPCClient(address=" passed_address ", csrf_token="passed_token")
    assert client.address == "passed_address"
    assert client.csrf_token == "passed_token"

def test_call_rpc():
    def mock_transport(method, url, headers, body):
        return {"method": method, "url": url, "headers": headers, "body": body}
    
    client = AntigravityLSRPCClient(address="localhost:1111", csrf_token="tok", transport=mock_transport)
    res = client.call_rpc("MyMethod", {"foo": "bar"})
    
    assert res["method"] == "POST"
    assert res["url"] == "http://localhost:1111/exa.language_server_pb.LanguageServerService/MyMethod"
    assert res["headers"] == {
        "Content-Type": "application/json",
        "x-codeium-csrf-token": "tok"
    }
    assert res["body"] == {"foo": "bar"}
