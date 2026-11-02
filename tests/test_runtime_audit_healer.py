"""Locked verification test suite for agy-doctor-mux runtime audit remediation.

Requirements traced:
- REQ-DM-URI-01: Sanitize file:/// URIs and percent-encoded UTF-8/Cyrillic paths into normalized OS paths.
- REQ-DM-PWLOCK-01: Heal stale Playwright/Chrome profile SingletonLock/SingletonCookie/SingletonSocket artifacts.
- REQ-DM-PSGUARD-01: Rewrite fragile PowerShell inline python -c commands to Here-String pipelines and repair stripped $_ variables.
"""

from __future__ import annotations

from pathlib import Path
import re

from agy_doctor_mux.runtime_audit_healer import (
    heal_playwright_profile_lock,
    rewrite_powershell_inline_python,
    sanitize_file_uri_and_cyrillic_path,
)

CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")


def test_sanitize_file_uri_unquotes_percent_encoded_cyrillic_and_strips_scheme() -> None:
    """Verify REQ-DM-URI-01 unquotes percent-encoded UTF-8 paths and strips file:/// scheme."""
    raw_uri = "file:///e:/STUDY_NEW_GEN/%D0%9C%D0%9E%D0%B8%D0%90%D0%94/progress.md"
    result = sanitize_file_uri_and_cyrillic_path(raw_uri)
    assert isinstance(result, str)
    assert not result.lower().startswith("file:")
    assert "%D0%" not in result.upper()
    expected_segment = "\u041c\u041e\u0438\u0410\u0414"
    assert expected_segment in result
    normalized = result.replace("\\", "/")
    assert normalized == f"e:/STUDY_NEW_GEN/{expected_segment}/progress.md"


def test_sanitize_file_uri_preserves_plain_windows_and_posix_paths() -> None:
    """Verify REQ-DM-URI-01 preserves plain Windows and POSIX paths without corruption."""
    win_path = str(Path(__file__).resolve().parents[1] / "README.md")
    result_win = sanitize_file_uri_and_cyrillic_path(win_path)
    assert isinstance(result_win, str)
    assert "file://" not in result_win.lower()
    assert result_win.replace("/", "\\") == win_path.replace("/", "\\")

    posix_path = "/opt/workspace/agy-doctor-mux/PROGRESS.md"
    result_posix = sanitize_file_uri_and_cyrillic_path(posix_path)
    assert isinstance(result_posix, str)
    assert "file://" not in result_posix.lower()
    assert result_posix.replace("\\", "/") == posix_path


def test_heal_playwright_profile_lock_removes_stale_singleton_files(tmp_path: Path) -> None:
    """Verify REQ-DM-PWLOCK-01 removes SingletonLock, SingletonCookie, and SingletonSocket."""
    lock_names = ("SingletonLock", "SingletonCookie", "SingletonSocket")
    for name in lock_names:
        (tmp_path / name).write_text("stale-lock", encoding="utf-8")
    keep_file = tmp_path / "Preferences"
    keep_file.write_text("{}", encoding="utf-8")

    res = heal_playwright_profile_lock(tmp_path, kill_orphan_processes=False)
    assert isinstance(res, dict)
    assert "removed_locks" in res
    assert "SingletonLock" in res["removed_locks"]
    assert "SingletonCookie" in res["removed_locks"]
    assert "SingletonSocket" in res["removed_locks"]

    for name in lock_names:
        assert not (tmp_path / name).exists()
    assert keep_file.exists()


def test_rewrite_powershell_inline_python_converts_fragile_python_c_to_herestring() -> None:
    """Verify REQ-DM-PSGUARD-01 converts fragile python -c inline commands to Here-String pipelines."""
    cmd = 'python -u -c "import re; print(1 < 2)"'
    rewritten = rewrite_powershell_inline_python(cmd)
    assert isinstance(rewritten, str)
    assert "@'\n" in rewritten
    assert "\n'@" in rewritten
    assert "import re; print(1 < 2)" in rewritten
    assert "| python -u -" in rewritten


def test_detect_fragile_powershell_dollar_underscore_in_double_quotes() -> None:
    """Verify REQ-DM-PSGUARD-01 repairs missing $_ before .LastWriteTime in PowerShell double-quoted command."""
    fragile_cmd = (
        'powershell -Command "Get-Item foo | '
        "Select @{N='m';E={(Get-Date) - .LastWriteTime}}\""
    )
    repaired = rewrite_powershell_inline_python(fragile_cmd)
    assert isinstance(repaired, str)
    assert "$_.LastWriteTime" in repaired or "`$_.LastWriteTime" in repaired


def test_req_dm_runtime_audit_healer_traceability_and_english_hygiene() -> None:
    """Verify REQ-DM-URI-01, REQ-DM-PWLOCK-01, and REQ-DM-PSGUARD-01 tags and 0 Cyrillic characters."""
    repo_root = Path(__file__).resolve().parents[1]
    target_module = repo_root / "agy_doctor_mux" / "runtime_audit_healer.py"
    assert target_module.exists(), f"Missing target module: {target_module}"

    source = target_module.read_text(encoding="utf-8")
    for req_id in ("REQ-DM-URI-01", "REQ-DM-PWLOCK-01", "REQ-DM-PSGUARD-01"):
        assert req_id in source, f"Missing requirement tag {req_id} in {target_module.name}"

    assert not CYRILLIC_RE.search(source), "Cyrillic characters found in runtime_audit_healer.py"
    this_source = Path(__file__).read_text(encoding="utf-8")
    assert not CYRILLIC_RE.search(this_source), "Cyrillic characters found in test file"
