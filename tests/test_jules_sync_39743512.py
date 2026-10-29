from __future__ import annotations

import json
from pathlib import Path

from agy_doctor_mux.sync import sync_surfaces


def test_sync_surfaces_unsupported_target_writes_nothing(tmp_path: Path) -> None:
    """An unknown target yields synced=True and an empty written_files list."""
    workspace = tmp_path / "ws"
    global_dir = tmp_path / "glob"
    result = sync_surfaces(workspace, global_dir, targets=["bogus-surface"])
    assert result["synced"] is True
    assert result["targets"] == ["bogus-surface"]
    assert result["written_files"] == []
    assert (workspace).is_dir()
    assert (global_dir).is_dir()
    assert not (workspace / ".agents").exists()
    assert not (workspace / ".claude").exists()
    assert not (global_dir / "plugins").exists()


def test_sync_surfaces_empty_targets(tmp_path: Path) -> None:
    """Empty targets sequence produces no files but still creates base dirs."""
    workspace = tmp_path / "ws"
    global_dir = tmp_path / "glob"
    result = sync_surfaces(workspace, global_dir, targets=())
    assert result["written_files"] == []
    assert result["targets"] == []
    assert workspace.is_dir()
    assert global_dir.is_dir()


def test_sync_surfaces_targets_mixed_case_and_whitespace(tmp_path: Path) -> None:
    """Case/whitespace variants of known targets are normalized before matching."""
    workspace = tmp_path / "ws"
    global_dir = tmp_path / "glob"
    result = sync_surfaces(workspace, global_dir, targets=["  CLAUDE-CODE  "])
    written = result["written_files"]
    assert len(written) == 1
    settings = workspace / ".claude" / "settings.json"
    assert str(settings) in written
    assert settings.is_file()
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert "PreToolUse" in payload["hooks"]
    assert not (workspace / ".agents").exists()
    assert not (global_dir / "plugins").exists()


def test_sync_surfaces_default_targets_write_all(tmp_path: Path) -> None:
    """Default targets write agent hooks, global plugin, and claude settings."""
    result = sync_surfaces(tmp_path / "ws", tmp_path / "glob")
    written = result["written_files"]
    assert len(written) == 4
    for path_str in written:
        assert Path(path_str).is_file()
