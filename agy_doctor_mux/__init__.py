"""Antigravity 2.0 Hook Multiplexer, Worktree Deadlock Doctor, MCP Shield, and L2 Native Plugin Builder."""

__version__ = "2.0.0"

from agy_doctor_mux.benchmarks import run_benchmark_suite
from agy_doctor_mux.desktop_doctor import diagnose_desktop_and_sandbox_health
from agy_doctor_mux.lsrpc import AntigravityLSRPCClient
from agy_doctor_mux.mcp_doctor import (
    audit_mcp_config,
    compact_mcp_schema_descriptions,
    diagnose_and_heal_network_env,
    validate_mcp_config_strict,
)
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
    audit_ecosystem_version_matrix,
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
    "audit_ecosystem_version_matrix",
    "audit_git_repository",
    "audit_mcp_config",
    "compact_mcp_schema_descriptions",
    "create_default_golden_stack_mux",
    "detect_plugin_drift",
    "diagnose_and_heal_network_env",
    "diagnose_and_heal_worktrees",
    "diagnose_desktop_and_sandbox_health",
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


def __getattr__(name: str):
    if name == 'main':
        from agy_doctor_mux.cli import main
        return main
    if name == 'run_cli':
        from agy_doctor_mux.cli import run_cli
        return run_cli
    if name == 'handle_mcp_request':
        from agy_doctor_mux.mcp_server import handle_mcp_request
        return handle_mcp_request
    if name == 'run_stdio_server':
        from agy_doctor_mux.mcp_server import run_stdio_server
        return run_stdio_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
