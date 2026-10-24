"""Tests for worktree lock healing, plugin drift detection, and strict MCP validation."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from agy_doctor_mux.mcp_doctor import validate_mcp_config_strict
from agy_doctor_mux.sync import detect_plugin_drift, reconcile_plugin_drift
from agy_doctor_mux.worktree_doctor import diagnose_and_heal_worktrees


def test_worktree_stale_lock_detection_and_healing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git_dir = repo / ".git"
    git_dir.mkdir()
    wt_dir = git_dir / "worktrees" / "subagent_branch_1"
    wt_dir.mkdir(parents=True)

    # Valid gitdir so it is not treated as dangling
    work_tree = tmp_path / "wt_work"
    work_tree.mkdir()
    (work_tree / ".git").mkdir()
    (wt_dir / "gitdir").write_text(str(work_tree / ".git"), encoding="utf-8")

    # Add stale 'locked' marker and 'index.lock'
    locked_marker = wt_dir / "locked"
    locked_marker.write_text("Locked by crashed agent", encoding="utf-8")
    idx_lock = wt_dir / "index.lock"
    idx_lock.write_text("lock data", encoding="utf-8")

    # 1. Diagnose in dry_run mode
    diag = diagnose_and_heal_worktrees(repo, dry_run=True)
    assert diag["has_deadlock_risk"] is True
    assert "stale_worktree_locked:subagent_branch_1" in diag["issues"]
    assert "stale_worktree_lock:subagent_branch_1/index.lock" in diag["issues"]
    assert locked_marker.exists()
    assert idx_lock.exists()

    # 2. Heal
    heal_res = diagnose_and_heal_worktrees(repo, dry_run=False)
    assert heal_res["healed"] is True
    assert not locked_marker.exists()
    assert not idx_lock.exists()

    # 3. Re-diagnose
    clean_diag = diagnose_and_heal_worktrees(repo, dry_run=True)
    assert clean_diag["has_deadlock_risk"] is False


def test_plugin_drift_detection_and_reconciliation(tmp_path: Path) -> None:
    src_root = tmp_path / "source_repos"
    src_root.mkdir()
    plugin_repo = src_root / "my-test-plugin"
    plugin_repo.mkdir()

    # Source manifest at v1.1.0
    (plugin_repo / "plugin.json").write_text(json.dumps({
        "name": "my-test-plugin",
        "displayName": "My Test Plugin",
        "description": "Upgraded v1.1.0 description",
        "version": "1.1.0",
        "suggestedPrompts": ["Prompt A", "Prompt B"],
    }), encoding="utf-8")

    # Installed plugin at v1.0.0 (behind)
    installed_root = tmp_path / "installed_plugins"
    installed_plugin = installed_root / "my-test-plugin"
    installed_plugin.mkdir(parents=True)
    (installed_plugin / "plugin.json").write_text(json.dumps({
        "name": "my-test-plugin",
        "displayName": "My Test Plugin",
        "description": "Old v1.0.0 description",
        "version": "1.0.0",
        "suggestedPrompts": ["Old Prompt"],
    }), encoding="utf-8")

    # Also add an untracked installed plugin
    untracked_plugin = installed_root / "orphan-plugin"
    untracked_plugin.mkdir()
    (untracked_plugin / "plugin.json").write_text(json.dumps({"name": "orphan-plugin", "version": "1.0.0"}), encoding="utf-8")

    # 1. Detect drift
    report = detect_plugin_drift([plugin_repo], installed_root)
    assert report["drift_detected"] is True
    assert len(report["drifted_plugins"]) == 1
    drift = report["drifted_plugins"][0]
    assert drift["name"] == "my-test-plugin"
    assert drift["source_version"] == "1.1.0"
    assert drift["installed_version"] == "1.0.0"
    assert "version" in drift["field_diffs"]
    assert "description" in drift["field_diffs"]
    assert "orphan-plugin" in report["untracked_in_source"]

    # 2. Reconcile drift
    rec = reconcile_plugin_drift(report, installed_root, [plugin_repo], auto_sync=True)
    assert rec["reconciled"] is True
    assert "my-test-plugin" in rec["updated_plugins"]

    # 3. Verify installed manifest is updated
    updated_data = json.loads((installed_plugin / "plugin.json").read_text(encoding="utf-8"))
    assert updated_data["version"] == "1.1.0"
    assert updated_data["description"] == "Upgraded v1.1.0 description"

    # Re-detect -> no drift for my-test-plugin
    clean_report = detect_plugin_drift([plugin_repo], installed_root)
    assert len(clean_report["drifted_plugins"]) == 0


def test_validate_mcp_config_strict() -> None:
    # 1. Valid config
    valid_cfg = {
        "mcpServers": {
            "agy_doctor": {
                "command": "python",
                "args": ["-m", "doctor"],
                "timeout_ms": 15000,
                "tools": ["heal_locks", "check_health"],
            }
        }
    }
    is_valid, errors = validate_mcp_config_strict(valid_cfg)
    assert is_valid is True
    assert len(errors) == 0

    # 2. Missing timeout
    missing_timeout_cfg = {
        "mcpServers": {
            "bad_srv": {
                "command": "python",
                "args": [],
            }
        }
    }
    is_val, errs = validate_mcp_config_strict(missing_timeout_cfg)
    assert is_val is False
    assert any("missing a positive integer 'timeout_ms'" in e for e in errs)

    # 3. Overlong tool identifier > 64 chars
    overlong_tool = "a" * 60
    overlong_cfg = {
        "mcpServers": {
            "my_server": {
                "command": "python",
                "timeout_ms": 5000,
                "tools": [overlong_tool],
            }
        }
    }
    is_val_tool, errs_tool = validate_mcp_config_strict(overlong_cfg)
    assert is_val_tool is False
    assert any("exceeds 64 characters" in e for e in errs_tool)
