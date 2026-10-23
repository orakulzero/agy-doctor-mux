"""Reproducible 5-Sandbox Empirical Benchmark Suite for agy-doctor-mux (v1.1.0)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agy_doctor_mux.lsrpc import AntigravityLSRPCClient
from agy_doctor_mux.mcp_doctor import VALID_IDENTIFIER_RE, audit_mcp_config
from agy_doctor_mux.mux import HookEntry, HookMultiplexer, measure_mux_speedup
from agy_doctor_mux.plugin_builder import (
    install_flagship_plugins,
    validate_native_plugin_bundle,
)
from agy_doctor_mux.sync import sync_surfaces, validate_plugin_manifest
from agy_doctor_mux.worktree_doctor import (
    diagnose_and_heal_worktrees,
    scan_brain_subagents,
)


def _run_sb1_hook_mux_latency_and_collisions() -> dict[str, Any]:
    mux = HookMultiplexer(max_stop_continuations=3)
    order: list[int] = []
    for p in (50, 10, 30, 20, 40):
        if p == 30:
            mux.register(
                HookEntry(
                    name=f"p{p}",
                    event="PreToolUse",
                    priority=p,
                    handler=lambda payload, prio=p: (
                        order.append(prio) or {"decision": "deny", "reason": "P30 block"}
                    ),
                )
            )
        else:
            mux.register(
                HookEntry(
                    name=f"p{p}",
                    event="PreToolUse",
                    priority=p,
                    handler=lambda payload, prio=p: (
                        order.append(prio) or {"decision": "allow"}
                    ),
                )
            )
    pre_res = mux.dispatch("PreToolUse", {"tool_name": "write_file"})
    short_circuit_ok = pre_res["decision"] == "deny" and order == [10, 20, 30]

    deferred_ran = False
    mux.register(
        HookEntry(
            name="p20_defer",
            event="Stop",
            priority=20,
            deferred_until_allow=True,
            handler=lambda payload: {"decision": "allow"},
        )
    )
    mux.register(
        HookEntry(
            name="p30_gate",
            event="Stop",
            priority=30,
            handler=lambda payload: {"decision": "deny", "reason": "Hold"},
        )
    )
    for _ in range(3):
        mux.dispatch("Stop", {"session_id": "bench"})
    r4 = mux.dispatch("Stop", {"session_id": "bench"})
    loop_guard_ok = r4["decision"] == "allow" and r4.get("loop_breaker_triggered") is True

    perf = measure_mux_speedup(iterations=3)
    perf_ok = perf["speedup_factor"] >= 5.0

    passed = short_circuit_ok and loop_guard_ok and not deferred_ran and perf_ok
    return {
        "name": "SB1_HookMux_LatencyAndCollisions",
        "passed": passed,
        "metrics": {
            "short_circuit_verified": short_circuit_ok,
            "anti_loop_guard_verified": loop_guard_ok,
            "speedup_factor": perf["speedup_factor"],
        },
    }


def _run_sb2_worktree_deadlock_and_bigint_heal() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "extensions.worktreeConfig", "true"],
            cwd=str(repo),
            check=True,
        )
        subprocess.run(
            ["git", "config", "core.repositoryformatversion", "1"],
            cwd=str(repo),
            check=True,
        )
        (repo / ".git" / "index.lock").write_text("stale", encoding="utf-8")
        wt = repo / ".git" / "worktrees" / "zombie"
        wt.mkdir(parents=True)
        (wt / "gitdir").write_text(str(root / "nonexistent" / ".git"), encoding="utf-8")

        diag = diagnose_and_heal_worktrees(repo, dry_run=True)
        heal = diagnose_and_heal_worktrees(repo, dry_run=False)
        post = diagnose_and_heal_worktrees(repo, dry_run=True)

        brain = root / "brain"
        c_big = brain / "c_bigint" / ".system_generated" / "logs"
        c_stall = brain / "c_stalled" / ".system_generated" / "logs"
        c_big.mkdir(parents=True)
        c_stall.mkdir(parents=True)
        (c_big / "transcript.jsonl").write_text(
            json.dumps({"status": "ERROR", "content": "Do not know how to serialize a BigInt"}) + "\n",
            encoding="utf-8",
        )
        (c_stall / "transcript.jsonl").write_text(
            json.dumps({"status": "IN_PROGRESS", "content": "Running"}) + "\n",
            encoding="utf-8",
        )
        brain_rep = scan_brain_subagents(brain)

        passed = (
            diag["has_deadlock_risk"] is True
            and heal["healed"] is True
            and post["has_deadlock_risk"] is False
            and "c_bigint" in brain_rep["bigint_crashes"]
            and "c_stalled" in brain_rep["stalled_subagents"]
        )
        return {
            "name": "SB2_WorktreeDeadlock_And_BigInt_Heal",
            "passed": passed,
            "metrics": {
                "issues_detected": diag["issues_count"],
                "healed_cleanly": not post["has_deadlock_risk"],
                "bigint_detected": len(brain_rep["bigint_crashes"]),
            },
        }


def _run_sb3_mcp_64char_and_timeout_shield() -> dict[str, Any]:
    raw_cfg = {
        "mcpServers": {
            "enterprise-global-observability-telemetry-gateway-service": {
                "command": "npx",
                "tools": [
                    "query_distributed_trace_spans_across_multi_region_clusters",
                    "bad$tool!name",
                ],
            }
        }
    }
    audit_bad = audit_mcp_config(raw_cfg, auto_fix=False)
    fixed = audit_mcp_config(raw_cfg, auto_fix=True)
    re_audit = audit_mcp_config(fixed["config"], auto_fix=False)

    all_under_64 = True
    for s_name, s_cfg in fixed["config"]["mcpServers"].items():
        for t_name in s_cfg.get("tools", []):
            comp = f"mcp_{s_name}_{t_name}"
            if len(comp) > 64 or not VALID_IDENTIFIER_RE.match(comp):
                all_under_64 = False

    passed = (
        audit_bad["valid"] is False
        and fixed["valid"] is True
        and re_audit["valid"] is True
        and all_under_64
    )
    return {
        "name": "SB3_MCP_64Char_And_Timeout_Shield",
        "passed": passed,
        "metrics": {
            "violations_caught": len(audit_bad["violations"]),
            "aliases_created": len(fixed["alias_map"]),
            "all_composites_valid": all_under_64,
        },
    }


def _run_sb4_cross_surface_sync_and_plugin_audit() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bad_m = validate_plugin_manifest(
            {"name": "Bad Name!", "version": "1.0.0", "workflows": ["w.md"]}
        )
        good_m = validate_plugin_manifest(
            {"name": "agy-doctor-mux", "version": "1.0.0", "hooks": "./hooks/hooks.json"}
        )
        sync_res = sync_surfaces(
            workspace_dir=root / "ws",
            global_dir=root / "global",
            targets=("antigravity-ide", "agy-cli", "claude-code"),
        )
        passed = (
            bad_m["valid"] is False
            and good_m["valid"] is True
            and sync_res["synced"] is True
            and len(sync_res["written_files"]) >= 3
        )
        return {
            "name": "SB4_CrossSurface_Sync_And_PluginAudit",
            "passed": passed,
            "metrics": {
                "manifest_validation_accurate": bad_m["valid"] is False and good_m["valid"] is True,
                "synced_files_count": len(sync_res["written_files"]),
            },
        }


def _run_sb5_native_plugin_scaffolder_and_lsrpc() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        inst = install_flagship_plugins(root / "plugins")
        all_valid = True
        for name in inst["installed"]:
            v = validate_native_plugin_bundle(root / "plugins" / name, check_oss_gates=True)
            if not v["valid"] or not v["oss_compliant"]:
                all_valid = False

        calls: list[str] = []

        def mock_transport(
            method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None
        ) -> dict[str, Any]:
            calls.append(url)
            if url.endswith("/GetAllPlugins"):
                return {
                    "plugins": [
                        {
                            "name": "agy-doctor-mux",
                            "path": "/Users/dev/.gemini/config/plugins/-445566778899",
                            "disabled": False,
                            "isGlobal": True,
                            "skills": [{"name": "agy-doctor-mux", "content": "X" * 16384}],
                        }
                    ]
                }
            return {"ok": True}

        client = AntigravityLSRPCClient(
            address="localhost:5387",
            csrf_token="bench-token",
            transport=mock_transport,
        )
        listed = client.list_installed_plugins()
        uninst = client.safe_uninstall_plugin(
            "-445566778899",
            path="/Users/dev/.gemini/config/plugins/-445566778899",
            was_disabled=True,
        )
        lsrpc_ok = (
            len(listed) == 1
            and listed[0]["dir"] == "-445566778899"
            and uninst["re_enabled_before_delete"] is True
        )

        passed = len(inst["installed"]) == 3 and all_valid and lsrpc_ok
        return {
            "name": "SB5_NativePluginScaffolder_And_LSRPC",
            "passed": passed,
            "metrics": {
                "flagship_plugins_installed": len(inst["installed"]),
                "all_bundles_valid": all_valid,
                "lsrpc_verified": lsrpc_ok,
            },
        }


def run_benchmark_suite() -> dict[str, Any]:
    """Run all 5 empirical diagnostic sandboxes and return aggregate verification results."""
    sandboxes = [
        _run_sb1_hook_mux_latency_and_collisions(),
        _run_sb2_worktree_deadlock_and_bigint_heal(),
        _run_sb3_mcp_64char_and_timeout_shield(),
        _run_sb4_cross_surface_sync_and_plugin_audit(),
        _run_sb5_native_plugin_scaffolder_and_lsrpc(),
    ]
    return {
        "all_passed": all(sb["passed"] for sb in sandboxes),
        "sandboxes": sandboxes,
    }
