import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import agy_doctor_mux.benchmarks as benchmarks

# --- Fakes for SB1 ---
class FakeMux:
    def __init__(self, **kwargs):
        self.hooks = []
    def register(self, hook):
        self.hooks.append(hook)
    def dispatch(self, event, payload):
        if event == "PreToolUse":
            hooks = sorted([h for h in self.hooks if h.event == event], key=lambda x: x.priority)
            for h in hooks:
                res = h.handler(payload)
                if res and res.get("decision") == "deny":
                    return res
            return {"decision": "allow"}
        if event == "Stop":
            if not hasattr(self, 'stop_calls'):
                self.stop_calls = 0
            self.stop_calls += 1
            if self.stop_calls == 4:
                return {"decision": "allow", "loop_breaker_triggered": True}
            return {"decision": "deny"}

class FakeHookEntry:
    def __init__(self, name, event, priority, handler, **kwargs):
        self.name = name
        self.event = event
        self.priority = priority
        self.handler = handler

@patch('agy_doctor_mux.benchmarks.HookMultiplexer', FakeMux)
@patch('agy_doctor_mux.benchmarks.HookEntry', FakeHookEntry)
@patch('agy_doctor_mux.benchmarks.measure_mux_speedup')
def test_sb1_pass(mock_speedup):
    mock_speedup.return_value = {"speedup_factor": 5.0}
    res = benchmarks._run_sb1_hook_mux_latency_and_collisions()
    assert res["passed"] is True

@patch('agy_doctor_mux.benchmarks.HookMultiplexer', FakeMux)
@patch('agy_doctor_mux.benchmarks.HookEntry', FakeHookEntry)
@patch('agy_doctor_mux.benchmarks.measure_mux_speedup')
def test_sb1_fail(mock_speedup):
    mock_speedup.return_value = {"speedup_factor": 2.0} # Fail condition
    res = benchmarks._run_sb1_hook_mux_latency_and_collisions()
    assert res["passed"] is False

# --- Fakes for SB2 ---
@patch('agy_doctor_mux.benchmarks.subprocess.run')
@patch('agy_doctor_mux.benchmarks.Path.write_text')
@patch('agy_doctor_mux.benchmarks.diagnose_and_heal_worktrees')
@patch('agy_doctor_mux.benchmarks.scan_brain_subagents')
def test_sb2_pass(mock_scan, mock_diag, mock_write_text, mock_subproc):
    mock_diag.side_effect = [
        {"has_deadlock_risk": True, "issues_count": 1},
        {"healed": True},
        {"has_deadlock_risk": False}
    ]
    mock_scan.return_value = {
        "bigint_crashes": ["c_bigint"],
        "stalled_subagents": ["c_stalled"]
    }
    res = benchmarks._run_sb2_worktree_deadlock_and_bigint_heal()
    assert res["passed"] is True

@patch('agy_doctor_mux.benchmarks.subprocess.run')
@patch('agy_doctor_mux.benchmarks.Path.write_text')
@patch('agy_doctor_mux.benchmarks.diagnose_and_heal_worktrees')
@patch('agy_doctor_mux.benchmarks.scan_brain_subagents')
def test_sb2_fail(mock_scan, mock_diag, mock_write_text, mock_subproc):
    mock_diag.side_effect = [
        {"has_deadlock_risk": True, "issues_count": 1},
        {"healed": False}, # Fail condition
        {"has_deadlock_risk": True}
    ]
    mock_scan.return_value = {
        "bigint_crashes": [],
        "stalled_subagents": []
    }
    res = benchmarks._run_sb2_worktree_deadlock_and_bigint_heal()
    assert res["passed"] is False

# --- Fakes for SB3 ---
@patch('agy_doctor_mux.benchmarks.audit_mcp_config')
def test_sb3_pass(mock_audit):
    mock_audit.side_effect = [
        {"valid": False, "violations": ["err"]},
        {"valid": True, "alias_map": {"x": "y"}, "config": {
            "mcpServers": {
                "s1": {"tools": ["t1"]} # len < 64
            }
        }},
        {"valid": True}
    ]
    res = benchmarks._run_sb3_mcp_64char_and_timeout_shield()
    assert res["passed"] is True

@patch('agy_doctor_mux.benchmarks.audit_mcp_config')
def test_sb3_fail(mock_audit):
    mock_audit.side_effect = [
        {"valid": False, "violations": ["err"]},
        {"valid": True, "alias_map": {"x": "y"}, "config": {
            "mcpServers": {
                "very_long_server_name_that_will_make_the_composite_length_exceed_sixty_four_characters": {"tools": ["t1"]} 
            }
        }},
        {"valid": True}
    ]
    res = benchmarks._run_sb3_mcp_64char_and_timeout_shield()
    assert res["passed"] is False


# --- Fakes for SB4 ---
@patch('agy_doctor_mux.benchmarks.validate_plugin_manifest')
@patch('agy_doctor_mux.benchmarks.sync_surfaces')
def test_sb4_pass(mock_sync, mock_val):
    mock_val.side_effect = [
        {"valid": False},
        {"valid": True}
    ]
    mock_sync.return_value = {"synced": True, "written_files": ["f1", "f2", "f3"]}
    res = benchmarks._run_sb4_cross_surface_sync_and_plugin_audit()
    assert res["passed"] is True

@patch('agy_doctor_mux.benchmarks.validate_plugin_manifest')
@patch('agy_doctor_mux.benchmarks.sync_surfaces')
def test_sb4_fail(mock_sync, mock_val):
    mock_val.side_effect = [
        {"valid": False},
        {"valid": True}
    ]
    mock_sync.return_value = {"synced": True, "written_files": ["f1"]} # Less than 3 files
    res = benchmarks._run_sb4_cross_surface_sync_and_plugin_audit()
    assert res["passed"] is False

# --- Fakes for SB5 ---
class FakeClient:
    def __init__(self, **kwargs):
        pass
    def list_installed_plugins(self):
        return [{"dir": "-445566778899"}]
    def safe_uninstall_plugin(self, *args, **kwargs):
        return {"re_enabled_before_delete": True}

@patch('agy_doctor_mux.benchmarks.install_flagship_plugins')
@patch('agy_doctor_mux.benchmarks.validate_native_plugin_bundle')
@patch('agy_doctor_mux.benchmarks.AntigravityLSRPCClient', FakeClient)
def test_sb5_pass(mock_val, mock_inst):
    mock_inst.return_value = {"installed": ["p1", "p2", "p3"]}
    mock_val.return_value = {"valid": True, "oss_compliant": True}
    res = benchmarks._run_sb5_native_plugin_scaffolder_and_lsrpc()
    assert res["passed"] is True

@patch('agy_doctor_mux.benchmarks.install_flagship_plugins')
@patch('agy_doctor_mux.benchmarks.validate_native_plugin_bundle')
@patch('agy_doctor_mux.benchmarks.AntigravityLSRPCClient', FakeClient)
def test_sb5_fail(mock_val, mock_inst):
    mock_inst.return_value = {"installed": ["p1", "p2"]} # Only 2 plugins
    mock_val.return_value = {"valid": True, "oss_compliant": True}
    res = benchmarks._run_sb5_native_plugin_scaffolder_and_lsrpc()
    assert res["passed"] is False

# --- Fakes for run_benchmark_suite ---
@patch('agy_doctor_mux.benchmarks._run_sb1_hook_mux_latency_and_collisions')
@patch('agy_doctor_mux.benchmarks._run_sb2_worktree_deadlock_and_bigint_heal')
@patch('agy_doctor_mux.benchmarks._run_sb3_mcp_64char_and_timeout_shield')
@patch('agy_doctor_mux.benchmarks._run_sb4_cross_surface_sync_and_plugin_audit')
@patch('agy_doctor_mux.benchmarks._run_sb5_native_plugin_scaffolder_and_lsrpc')
def test_run_benchmark_suite_pass(mock_sb5, mock_sb4, mock_sb3, mock_sb2, mock_sb1):
    mock_sb1.return_value = {"passed": True}
    mock_sb2.return_value = {"passed": True}
    mock_sb3.return_value = {"passed": True}
    mock_sb4.return_value = {"passed": True}
    mock_sb5.return_value = {"passed": True}
    res = benchmarks.run_benchmark_suite()
    assert res["all_passed"] is True
    assert len(res["sandboxes"]) == 5

@patch('agy_doctor_mux.benchmarks._run_sb1_hook_mux_latency_and_collisions')
@patch('agy_doctor_mux.benchmarks._run_sb2_worktree_deadlock_and_bigint_heal')
@patch('agy_doctor_mux.benchmarks._run_sb3_mcp_64char_and_timeout_shield')
@patch('agy_doctor_mux.benchmarks._run_sb4_cross_surface_sync_and_plugin_audit')
@patch('agy_doctor_mux.benchmarks._run_sb5_native_plugin_scaffolder_and_lsrpc')
def test_run_benchmark_suite_fail(mock_sb5, mock_sb4, mock_sb3, mock_sb2, mock_sb1):
    mock_sb1.return_value = {"passed": True}
    mock_sb2.return_value = {"passed": True}
    mock_sb3.return_value = {"passed": False} # Fail
    mock_sb4.return_value = {"passed": True}
    mock_sb5.return_value = {"passed": True}
    res = benchmarks.run_benchmark_suite()
    assert res["all_passed"] is False
