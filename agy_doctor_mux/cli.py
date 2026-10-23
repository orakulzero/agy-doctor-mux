"""Unified CLI Entrypoint for agy-doctor-mux (v1.1.0)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import sys
from pathlib import Path
from typing import Any

from agy_doctor_mux.benchmarks import run_benchmark_suite
from agy_doctor_mux.mcp_doctor import audit_mcp_config
from agy_doctor_mux.mcp_server import run_stdio_server
from agy_doctor_mux.mux import create_default_golden_stack_mux
from agy_doctor_mux.oss_audit import audit_git_repository
from agy_doctor_mux.plugin_builder import (
    heal_all_plugins,
    install_flagship_plugins,
    scaffold_native_plugin,
    validate_native_plugin_bundle,
)
from agy_doctor_mux.sync import sync_surfaces
from agy_doctor_mux.worktree_doctor import (
    diagnose_and_heal_worktrees,
    scan_brain_subagents,
)


def _extract_workspace(argv: list[str]) -> tuple[Path, list[str]]:
    ws = Path.cwd()
    cleaned: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--workspace" and i + 1 < len(argv):
            ws = Path(argv[i + 1]).resolve()
            i += 2
        elif tok.startswith("--workspace="):
            ws = Path(tok.split("=", 1)[1]).resolve()
            i += 1
        else:
            cleaned.append(tok)
            i += 1
    return ws, cleaned


def run_cli(argv: Sequence[str] | None = None) -> dict[str, Any]:
    """Run an agy-doctor-mux CLI command and return a structured result dictionary."""
    raw = list(sys.argv[1:] if argv is None else argv)
    ws, remaining = _extract_workspace(raw)

    parser = argparse.ArgumentParser(prog="agy-doctor-mux", add_help=False)
    sub = parser.add_subparsers(dest="subcommand")

    # 1. diagnose
    p_diag = sub.add_parser("diagnose")
    p_diag.add_argument("--brain-dir", default=None)

    # 2. heal
    sub.add_parser("heal")

    # 3. mux-dispatch
    p_mux = sub.add_parser("mux-dispatch")
    p_mux.add_argument("--event", default="PreToolUse")
    p_mux.add_argument("--payload", default=None)

    # 4. audit-mcp
    p_mcp = sub.add_parser("audit-mcp")
    p_mcp.add_argument("--config-file", required=True)
    p_mcp.add_argument("--auto-fix", action="store_true")

    # 5. sync
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--global-dir", default=None)

    # 6. benchmark
    sub.add_parser("benchmark")

    # 7. oss-audit
    sub.add_parser("oss-audit")

    # 8. mcp-serve
    sub.add_parser("mcp-serve")

    # 9. init-plugin
    p_init_plug = sub.add_parser("init-plugin")
    p_init_plug.add_argument("--target-dir", required=True)
    p_init_plug.add_argument("--name", required=True)
    p_init_plug.add_argument("--display-name", default="")
    p_init_plug.add_argument("--description", default="")

    # 10. validate-plugin
    p_val_plug = sub.add_parser("validate-plugin")
    p_val_plug.add_argument("--plugin-dir", required=True)

    # 11. install-plugins
    p_inst_plug = sub.add_parser("install-plugins")
    p_inst_plug.add_argument("--plugins-root", required=True)

    # 12. heal-plugins
    p_heal_plug = sub.add_parser("heal-plugins")
    p_heal_plug.add_argument("--plugins-root", required=True)

    ns, _ = parser.parse_known_args(remaining)
    cmd = ns.subcommand

    if cmd == "diagnose":
        wt_rep = diagnose_and_heal_worktrees(ws, dry_run=True)
        brain_rep = (
            scan_brain_subagents(Path(ns.brain_dir))
            if ns.brain_dir
            else {"total_conversations": 0, "bigint_crashes": [], "stalled_subagents": []}
        )
        return {"worktree": wt_rep, "brain": brain_rep}

    if cmd == "heal":
        wt_rep = diagnose_and_heal_worktrees(ws, dry_run=False)
        return {"worktree": wt_rep}

    if cmd == "mux-dispatch":
        raw_payload = ns.payload
        if not raw_payload and not sys.stdin.isatty():
            raw_payload = sys.stdin.read().strip()
        payload_obj = json.loads(raw_payload) if raw_payload else {}
        mux = create_default_golden_stack_mux()
        return mux.dispatch(str(ns.event), payload_obj)

    if cmd == "audit-mcp":
        cfg_path = Path(ns.config_file)
        cfg_obj = json.loads(cfg_path.read_text(encoding="utf-8"))
        res = audit_mcp_config(cfg_obj, auto_fix=bool(ns.auto_fix))
        if ns.auto_fix:
            cfg_path.write_text(json.dumps(res["config"], indent=2), encoding="utf-8")
        return res

    if cmd == "sync":
        glob_dir = Path(ns.global_dir) if ns.global_dir else (ws / ".global_agy")
        return sync_surfaces(workspace_dir=ws, global_dir=glob_dir)

    if cmd == "benchmark":
        return run_benchmark_suite()

    if cmd == "oss-audit":
        return audit_git_repository(ws)

    if cmd == "mcp-serve":
        run_stdio_server(workspace=ws)
        return {"status": "stopped"}

    if cmd == "init-plugin":
        return scaffold_native_plugin(
            target_dir=Path(ns.target_dir),
            name=str(ns.name),
            display_name=str(ns.display_name),
            description=str(ns.description),
        )

    if cmd == "validate-plugin":
        return validate_native_plugin_bundle(Path(ns.plugin_dir), check_oss_gates=True)

    if cmd == "install-plugins":
        return install_flagship_plugins(Path(ns.plugins_root))

    if cmd == "heal-plugins":
        return heal_all_plugins(Path(ns.plugins_root))

    raise ValueError(f"Unknown or missing subcommand: {cmd!r}")


def main() -> int:
    res = run_cli()
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
