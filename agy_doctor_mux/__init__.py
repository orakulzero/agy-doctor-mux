"""Antigravity 2.0 Hook Multiplexer, Worktree Deadlock Doctor, MCP Shield, and L2 Native Plugin Builder."""

from __future__ import annotations

__version__ = "1.1.1"

from agy_doctor_mux.benchmarks import run_benchmark_suite
from agy_doctor_mux.cli import main, run_cli
from agy_doctor_mux.lsrpc import AntigravityLSRPCClient
from agy_doctor_mux.mcp_doctor import audit_mcp_config, validate_mcp_config_strict
from agy_doctor_mux.mcp_server import handle_mcp_request, run_stdio_server
from agy_doctor_mux.mux import (
    HookEntry,
    HookMultiplexer,
    create_default_golden_stack_mux,
    measure_mux_speedup,
)
from agy_doctor_mux.oss_audit import audit_git_repository
from agy_doctor_mux.plugin_builder import (
    heal_all_plugins,
    heal_plugin_bundle,
    install_flagship_plugins,
    scaffold_native_plugin,
    validate_native_plugin_bundle,
)
from agy_doctor_mux.sync import (
    detect_plugin_drift,
    reconcile_plugin_drift,
    sync_surfaces,
    validate_plugin_manifest,
)
from agy_doctor_mux.worktree_doctor import (
    diagnose_and_heal_worktrees,
    scan_brain_subagents,
)

__all__ = [
    "__version__",
    "AntigravityLSRPCClient",
    "HookEntry",
    "HookMultiplexer",
    "audit_git_repository",
    "audit_mcp_config",
    "create_default_golden_stack_mux",
    "detect_plugin_drift",
    "diagnose_and_heal_worktrees",
    "handle_mcp_request",
    "heal_all_plugins",
    "heal_plugin_bundle",
    "install_flagship_plugins",
    "main",
    "measure_mux_speedup",
    "reconcile_plugin_drift",
    "run_benchmark_suite",
    "run_cli",
    "run_stdio_server",
    "scaffold_native_plugin",
    "scan_brain_subagents",
    "sync_surfaces",
    "validate_mcp_config_strict",
    "validate_native_plugin_bundle",
    "validate_plugin_manifest",
]
