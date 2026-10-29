"""Test inject_v8_bigint_shield correctly handles JSONL files with unsafe integers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agy_doctor_mux.freeze_watchdog import FreezeWatchdog, MAX_SAFE_V8_INTEGER


@pytest.fixture
def watchdog(tmp_path: Path) -> FreezeWatchdog:
    """Create a FreezeWatchdog instance with a temporary workspace."""
    return FreezeWatchdog(workspace_root=tmp_path)


def test_inject_v8_bigint_shield_unsafe_integers(watchdog: FreezeWatchdog, tmp_path: Path) -> None:
    """Test that unsafe >53-bit integers are quoted."""
    jsonl_file = tmp_path / "transcript.jsonl"
    unsafe_int = MAX_SAFE_V8_INTEGER + 1000
    content = f'{{"id": {unsafe_int}, "data": "test"}}\n'
    jsonl_file.write_text(content, encoding="utf-8")

    result = watchdog.inject_v8_bigint_shield(jsonl_file)

    assert result["clean"] is True
    assert result["sanitized_count"] == 1
    assert result["path"] == str(jsonl_file)
    
    sanitized = jsonl_file.read_text(encoding="utf-8")
    assert f'"{unsafe_int}"' in sanitized
    assert json.loads(sanitized)["id"] == str(unsafe_int)


def test_inject_v8_bigint_shield_bigint_literals(watchdog: FreezeWatchdog, tmp_path: Path) -> None:
    """Test that BigInt literals (with 'n' suffix) are quoted."""
    jsonl_file = tmp_path / "transcript.jsonl"
    content = '{"count": 123456789n, "safe": 100}\n'
    jsonl_file.write_text(content, encoding="utf-8")

    result = watchdog.inject_v8_bigint_shield(jsonl_file)

    assert result["sanitized_count"] == 1
    sanitized = jsonl_file.read_text(encoding="utf-8")
    assert '"123456789"' in sanitized
    assert ', "safe": 100' in sanitized


def test_inject_v8_bigint_shield_safe_integers(watchdog: FreezeWatchdog, tmp_path: Path) -> None:
    """Test that safe integers within V8 range are unchanged."""
    jsonl_file = tmp_path / "transcript.jsonl"
    safe_int = MAX_SAFE_V8_INTEGER - 1000
    content = f'{{"id": {safe_int}, "count": 42}}\n'
    jsonl_file.write_text(content, encoding="utf-8")

    result = watchdog.inject_v8_bigint_shield(jsonl_file)

    assert result["sanitized_count"] == 0
    assert jsonl_file.read_text(encoding="utf-8") == content


def test_inject_v8_bigint_shield_nonexistent_file(watchdog: FreezeWatchdog, tmp_path: Path) -> None:
    """Test that nonexistent file returns clean=False."""
    missing_file = tmp_path / "nonexistent.jsonl"
    
    result = watchdog.inject_v8_bigint_shield(missing_file)
    
    assert result["clean"] is False
    assert result["sanitized_count"] == 0
