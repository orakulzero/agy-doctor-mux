"""Antigravity 2.0 Hook Multiplexer, Worktree Deadlock Doctor, and MCP Schema Shield."""

from __future__ import annotations

__version__ = "1.0.0"

from agy_doctor_mux.benchmarks import run_benchmark_suite
from agy_doctor_mux.cli import main, run_cli
from agy_doctor_mux.mcp_doctor import audit_mcp_config
from agy_doctor_mux.mcp_server import handle_mcp_request, run_stdio_server
from agy_doctor_mux.mux import (
    HookEntry,
    HookMultiplexer,
    create_default_golden_stack_mux,
    measure_mux_speedup,
)
from agy_doctor_mux.oss_audit import audit_git_repository
from agy_doctor_mux.sync import sync_surfaces, validate_plugin_manifest
from agy_doctor_mux.worktree_doctor import (
    diagnose_and_heal_worktrees,
    scan_brain_subagents,
)

__all__ = [
    "__version__",
    "HookEntry",
    "HookMultiplexer",
    "audit_git_repository",
    "audit_mcp_config",
    "create_default_golden_stack_mux",
    "diagnose_and_heal_worktrees",
    "handle_mcp_request",
    "main",
    "measure_mux_speedup",
    "run_benchmark_suite",
    "run_cli",
    "run_stdio_server",
    "scan_brain_subagents",
    "sync_surfaces",
    "validate_plugin_manifest",
]
