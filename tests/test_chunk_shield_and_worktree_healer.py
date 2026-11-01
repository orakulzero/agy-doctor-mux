"""Agile V Verification Tests for Chunking Shield & Worktree Healer.

Traceability:
- REQ-DM-CHUNK-01: Pre-tool SSE stream EOF chunking shield rejecting write/edit >180 lines.
- REQ-DM-LOCK-01: Automated git worktree/index lock healer hook.

Quality Framework: ISO 9001:2015, ISO/IEC 42001:2023, Agile V Role Separation.
Hygiene: 100% English-only (0 Cyrillic characters).
"""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any, Dict
import pytest

from agy_doctor_mux.mux import HookEntry, HookMultiplexer
from agy_doctor_mux.worktree_doctor import diagnose_and_heal_worktrees

try:
    from agy_doctor_mux.chunk_guard import (
        validate_write_chunk_limit,
        create_chunk_shield_hook,
    )
except ImportError:
    validate_write_chunk_limit = None
    create_chunk_shield_hook = None


def _init_test_git_repo(repo_dir: Path) -> Path:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@antigravity.org"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Designer"], cwd=str(repo_dir), check=True, capture_output=True)
    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit", "-q"], cwd=str(repo_dir), check=True, capture_output=True)
    return repo_dir


# ============================================================================
# REQ-DM-CHUNK-01: Pre-tool SSE Stream EOF Chunking Shield
# ============================================================================


def test_req_dm_chunk_01_module_contract_and_presence():
    """Verify agy_doctor_mux.chunk_guard module is importable and implements contract (REQ-DM-CHUNK-01)."""
    assert validate_write_chunk_limit is not None, (
        "Contract violation: agy_doctor_mux.chunk_guard.validate_write_chunk_limit must be implemented"
    )
    assert create_chunk_shield_hook is not None, (
        "Contract violation: agy_doctor_mux.chunk_guard.create_chunk_shield_hook must be implemented"
    )


def test_req_dm_chunk_01_rejects_payload_exceeding_180_lines():
    """Verify write payload exceeding 180 lines is rejected with informative reason (REQ-DM-CHUNK-01)."""
    assert validate_write_chunk_limit is not None
    large_payload = "\n".join(f"# Line {i}" for i in range(1, 220)) + "\n"
    res = validate_write_chunk_limit(large_payload, max_lines=180)
    assert isinstance(res, dict)
    assert res.get("is_valid") is False
    assert res.get("line_count") == 219
    assert res.get("max_lines") == 180
    assert "180" in str(res.get("error"))


def test_req_dm_chunk_01_accepts_payload_within_180_lines():
    """Verify write payload with <= 180 lines passes validation (REQ-DM-CHUNK-01)."""
    assert validate_write_chunk_limit is not None
    valid_payload = "\n".join(f"var_{i} = {i}" for i in range(1, 150)) + "\n"
    res = validate_write_chunk_limit(valid_payload, max_lines=180)
    assert res.get("is_valid") is True
    assert res.get("error") is None


def test_req_dm_chunk_01_hook_multiplexer_integration():
    """Verify chunk shield hook integrates with HookMultiplexer PreToolUse event (REQ-DM-CHUNK-01)."""
    assert create_chunk_shield_hook is not None
    mux = HookMultiplexer()
    hook_entry = create_chunk_shield_hook(max_lines=180, priority=10)
    assert isinstance(hook_entry, HookEntry)
    assert hook_entry.event == "PreToolUse"
    mux.register(hook_entry)

    # Deny large write_to_file call
    large_text = "\n".join(f"line_{i}" for i in range(195))
    deny_payload = {
        "tool_name": "write_to_file",
        "tool_args": {"TargetFile": "src/sample.py", "CodeContent": large_text},
    }
    res_deny = mux.dispatch("PreToolUse", deny_payload)
    assert res_deny.get("decision") == "deny"
    assert "180" in res_deny.get("reason", "")

    # Allow compliant write_to_file call
    small_text = "print('hello world')\n"
    allow_payload = {
        "tool_name": "write_to_file",
        "tool_args": {"TargetFile": "src/sample.py", "CodeContent": small_text},
    }
    res_allow = mux.dispatch("PreToolUse", allow_payload)
    assert res_allow.get("decision") == "allow"

    # Allow read-only tools regardless of line references
    read_payload = {"tool_name": "read_file", "tool_args": {"AbsolutePath": "src/large.py"}}
    assert mux.dispatch("PreToolUse", read_payload).get("decision") == "allow"


# ============================================================================
# REQ-DM-LOCK-01: Automated Git Worktree / Index Lock Healer Hook
# ============================================================================


def test_req_dm_lock_01_diagnose_and_heal_stale_index_lock(tmp_path: Path):
    """Verify diagnose_and_heal_worktrees removes stale index.lock (REQ-DM-LOCK-01)."""
    repo = _init_test_git_repo(tmp_path / "repo_stale_index")
    index_lock = repo / ".git" / "index.lock"
    index_lock.write_text("lock pid 12345\n", encoding="utf-8")

    # Dry-run detects risk without deletion
    dry_rep = diagnose_and_heal_worktrees(repo, dry_run=True)
    assert dry_rep.get("has_deadlock_risk") is True
    assert "stale_index_lock" in dry_rep.get("issues", [])
    assert index_lock.exists()

    # Active heal removes lock
    heal_rep = diagnose_and_heal_worktrees(repo, dry_run=False)
    assert heal_rep.get("healed") is True
    assert not index_lock.exists()


def test_req_dm_lock_01_diagnose_and_heal_dangling_worktree(tmp_path: Path):
    """Verify diagnose_and_heal_worktrees removes orphaned worktree records (REQ-DM-LOCK-01)."""
    repo = _init_test_git_repo(tmp_path / "repo_dangling_wt")
    wt_dir = repo / ".git" / "worktrees" / "orphaned_wt"
    wt_dir.mkdir(parents=True, exist_ok=True)
    (wt_dir / "gitdir").write_text(str(tmp_path / "deleted_worktree_path"), encoding="utf-8")

    heal_rep = diagnose_and_heal_worktrees(repo, dry_run=False)
    assert heal_rep.get("healed") is True
    assert any("dangling_worktree:orphaned_wt" in iss for iss in heal_rep.get("issues", []))
    assert not wt_dir.exists()


def test_req_dm_lock_01_hook_dispatch_healing(tmp_path: Path):
    """Verify worktree healer hook dispatches and cleans repo locks automatically (REQ-DM-LOCK-01)."""
    repo = _init_test_git_repo(tmp_path / "repo_hook_test")
    index_lock = repo / ".git" / "index.lock"
    index_lock.write_text("stale lock\n", encoding="utf-8")

    mux = HookMultiplexer()

    def _healer_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        target_dir = payload.get("repo_path") or str(repo)
        report = diagnose_and_heal_worktrees(target_dir, dry_run=False)
        return {"decision": "allow", "healer_report": report}

    mux.register(
        HookEntry(
            name="git_worktree_healer_shield",
            event="PreToolUse",
            priority=15,
            handler=_healer_handler,
        )
    )

    res = mux.dispatch("PreToolUse", {"tool_name": "run_command", "repo_path": str(repo)})
    assert res.get("decision") == "allow"
    assert not index_lock.exists()
