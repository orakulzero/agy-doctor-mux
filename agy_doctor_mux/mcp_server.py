"""Stdio JSON-RPC 2.0 MCP Server for agy-doctor-mux."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agy_doctor_mux.mcp_doctor import audit_mcp_config
from agy_doctor_mux.mux import measure_mux_speedup
from agy_doctor_mux.sync import sync_surfaces
from agy_doctor_mux.worktree_doctor import (
    diagnose_and_heal_worktrees,
    scan_brain_subagents,
)

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "agy_diagnose_workspace",
        "description": "Diagnose Antigravity 2.0 Git worktree deadlock risks and scan brain subagent transcripts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "brain_dir": {"type": "string"},
            },
        },
    },
    {
        "name": "agy_heal_worktree_deadlock",
        "description": "Heal Git worktree deadlocks, unset extensions.worktreeConfig, and remove stale locks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "agy_audit_mcp_config",
        "description": "Lint MCP server config for <64-char composite tool identifiers, regex compliance, and timeouts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config": {"type": "object"},
                "auto_fix": {"type": "boolean", "default": False},
            },
            "required": ["config"],
        },
    },
    {
        "name": "agy_benchmark_hook_mux",
        "description": "Benchmark single-process hook multiplexer latency against sequential subprocess spawning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "iterations": {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "agy_sync_surfaces",
        "description": "Synchronize multiplexer hooks across Antigravity IDE, agy CLI, and Claude Code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "global_dir": {"type": "string"},
            },
        },
    },
]


def handle_mcp_request(
    req: dict[str, Any], workspace: Path | str = "."
) -> dict[str, Any]:
    """Process a single JSON-RPC 2.0 MCP request."""
    ws = Path(workspace).resolve()
    req_id = req.get("id")
    method = str(req.get("method") or "")
    params = req.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "agy-doctor-mux-mcp",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }

    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        try:
            if name == "agy_diagnose_workspace":
                wt_rep = diagnose_and_heal_worktrees(ws, dry_run=True)
                brain_path = args.get("brain_dir")
                brain_rep = (
                    scan_brain_subagents(Path(brain_path))
                    if brain_path
                    else {"total_conversations": 0, "bigint_crashes": [], "stalled_subagents": []}
                )
                out: dict[str, Any] = {"worktree": wt_rep, "brain": brain_rep}
            elif name == "agy_heal_worktree_deadlock":
                dry = bool(args.get("dry_run", False))
                out = diagnose_and_heal_worktrees(ws, dry_run=dry)
            elif name == "agy_audit_mcp_config":
                cfg = args.get("config") or {"mcpServers": {}}
                auto_fix = bool(args.get("auto_fix", False))
                out = audit_mcp_config(cfg, auto_fix=auto_fix)
            elif name == "agy_benchmark_hook_mux":
                iters = int(args.get("iterations", 5))
                out = measure_mux_speedup(iterations=iters)
            elif name == "agy_sync_surfaces":
                glob_dir = Path(args.get("global_dir") or (ws / ".global_agy"))
                out = sync_surfaces(workspace_dir=ws, global_dir=glob_dir)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                        "isError": True,
                    },
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(out)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_stdio_server(workspace: Path | str = ".") -> None:
    """Run the JSON-RPC 2.0 MCP server over stdin/stdout."""
    for line in sys.stdin:
        s = line.strip()
        if not s:
            continue
        try:
            req = json.loads(s)
            resp = handle_mcp_request(req, workspace=workspace)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


def main() -> None:
    run_stdio_server()


if __name__ == "__main__":
    main()
