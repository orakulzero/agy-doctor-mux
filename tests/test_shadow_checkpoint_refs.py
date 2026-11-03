"""
ISO 9001:2015 / Agile V Verification Suite — REQ-DOC-SHADOW-01
Component: Shadow Checkpoint Git Refs Manager (Zero Index/HEAD Pollution)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import agy_doctor_mux
from agy_doctor_mux.shadow_checkpoint_refs import (
    ShadowCheckpointManager,
    create_shadow_checkpoint,
    restore_shadow_checkpoint,
)


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout.strip()


def test_req_doc_shadow_01_create_list_and_restore_without_touching_head_or_index(
    tmp_path: Path,
) -> None:
    """Verify REQ-DOC-SHADOW-01 creates and restores shadow checkpoints without mutating HEAD or .git/index."""
    assert getattr(agy_doctor_mux, "__v3_generation__", None) == "3.0.0"
    assert getattr(agy_doctor_mux, "ShadowCheckpointManager", None) is ShadowCheckpointManager
    assert getattr(agy_doctor_mux, "create_shadow_checkpoint", None) is create_shadow_checkpoint
    assert getattr(agy_doctor_mux, "restore_shadow_checkpoint", None) is restore_shadow_checkpoint

    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "tester")

    app_py = tmp_path / "app.py"
    app_py.write_text("v1\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")
    _git(tmp_path, "commit", "-m", "initial commit")

    app_py.write_text("v2_experimental\n", encoding="utf-8")
    notes_txt = tmp_path / "notes.txt"
    notes_txt.write_text("draft\n", encoding="utf-8")

    head_before = _git(tmp_path, "rev-parse", "HEAD")
    status_before = _git(tmp_path, "status", "--porcelain")

    cp = create_shadow_checkpoint(str(tmp_path), "chk_01", message="before risky edit")
    assert cp["requirement_id"] == "REQ-DOC-SHADOW-01"
    assert cp["status"] == "CREATED"
    assert cp["ref_name"] == "refs/agy-checkpoints/chk_01"
    assert cp["head_unchanged"] is True

    assert _git(tmp_path, "rev-parse", "HEAD") == head_before
    assert _git(tmp_path, "status", "--porcelain") == status_before
    log_lines = [line for line in _git(tmp_path, "log", "--oneline").splitlines() if line.strip()]
    assert len(log_lines) == 1

    app_py.write_text("corrupted\n", encoding="utf-8")
    notes_txt.unlink()

    restored = restore_shadow_checkpoint(str(tmp_path), "chk_01")
    assert restored["requirement_id"] == "REQ-DOC-SHADOW-01"
    assert restored["status"] == "RESTORED"
    assert app_py.read_text(encoding="utf-8") == "v2_experimental\n"
    assert notes_txt.read_text(encoding="utf-8") == "draft\n"

    mgr = ShadowCheckpointManager(str(tmp_path))
    checkpoints = mgr.list_checkpoints()
    checkpoint_ids = [
        item["checkpoint_id"] if isinstance(item, dict) else str(item)
        for item in checkpoints
    ]
    assert "chk_01" in checkpoint_ids or any("chk_01" in str(c) for c in checkpoints)

    missing = restore_shadow_checkpoint(str(tmp_path), "non_existent_chk")
    assert missing["status"] == "NOT_FOUND"
