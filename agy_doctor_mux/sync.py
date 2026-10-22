"""Cross-Surface Config Synchronizer & Agent Plugins 1.0 Manifest Validator."""

from __future__ import annotations

from collections.abc import Sequence
import json
import re
from pathlib import Path
from typing import Any

PLUGIN_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UNSUPPORTED_MANIFEST_KEYS = {"workflows", "sidecars"}


def validate_plugin_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate an Antigravity Agent Plugins 1.0 manifest dictionary."""
    errors: list[str] = []

    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("Field 'name' must be a non-empty string.")
    elif not PLUGIN_KEBAB_RE.match(name):
        errors.append(
            f"Field 'name' ({name!r}) must be lowercase kebab-case matching {PLUGIN_KEBAB_RE.pattern}."
        )

    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("Field 'version' must be a non-empty semantic version string.")

    for bad_key in sorted(UNSUPPORTED_MANIFEST_KEYS):
        if bad_key in manifest:
            errors.append(
                f"Unsupported key {bad_key!r}: Agent Plugins 1.0 does not bundle workflows or sidecars."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def sync_surfaces(
    workspace_dir: Path | str,
    global_dir: Path | str,
    targets: Sequence[str] = ("antigravity-ide", "agy-cli", "claude-code"),
) -> dict[str, Any]:
    """Synchronize single-process multiplexer hooks across Antigravity IDE, agy CLI, and Claude Code."""
    ws = Path(workspace_dir).resolve()
    glob = Path(global_dir).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    glob.mkdir(parents=True, exist_ok=True)

    target_set = {t.lower().strip() for t in targets}
    written_files: list[str] = []

    mux_hook_spec = {
        "multiplexer": "agy-doctor-mux",
        "version": "1.0.0",
        "priority_order": [
            "P10_context_guard",
            "P20_memory_consolidator",
            "P30_supergraph_dag_gate",
            "P40_code_review_advisor",
            "P50_audit_logger",
        ],
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": ".*",
                    "command": "agy-doctor-mux mux-dispatch --event PreToolUse",
                }
            ],
            "PostToolUse": [
                {
                    "matcher": ".*",
                    "command": "agy-doctor-mux mux-dispatch --event PostToolUse",
                }
            ],
            "Stop": [
                {
                    "matcher": ".*",
                    "command": "agy-doctor-mux mux-dispatch --event Stop",
                }
            ],
        },
    }

    if "antigravity-ide" in target_set or "agy-cli" in target_set:
        agents_dir = ws / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        ws_mux_file = agents_dir / "mux_hooks.json"
        ws_mux_file.write_text(json.dumps(mux_hook_spec, indent=2), encoding="utf-8")
        written_files.append(str(ws_mux_file))

        plugin_root = glob / "plugins" / "agy-doctor-mux"
        hooks_dir = plugin_root / "hooks"
        manifest_dir = plugin_root / ".antigravity-plugin"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        manifest_dir.mkdir(parents=True, exist_ok=True)

        glob_hooks_file = hooks_dir / "hooks.json"
        glob_hooks_file.write_text(json.dumps(mux_hook_spec, indent=2), encoding="utf-8")
        written_files.append(str(glob_hooks_file))

        manifest_file = manifest_dir / "plugin.json"
        manifest_payload = {
            "name": "agy-doctor-mux",
            "version": "1.0.0",
            "description": "Single-process hook multiplexer and worktree/MCP doctor for Antigravity 2.0",
            "hooks": "./hooks/hooks.json",
        }
        manifest_file.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
        written_files.append(str(manifest_file))

    if "claude-code" in target_set:
        claude_dir = ws / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        claude_settings = claude_dir / "settings.json"
        claude_payload = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "agy-doctor-mux mux-dispatch --event PreToolUse",
                            }
                        ],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "agy-doctor-mux mux-dispatch --event PostToolUse",
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "agy-doctor-mux mux-dispatch --event Stop",
                            }
                        ],
                    }
                ],
            }
        }
        claude_settings.write_text(json.dumps(claude_payload, indent=2), encoding="utf-8")
        written_files.append(str(claude_settings))

    return {
        "synced": True,
        "targets": list(targets),
        "written_files": written_files,
    }
