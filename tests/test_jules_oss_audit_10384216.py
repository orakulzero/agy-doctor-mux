import subprocess
from pathlib import Path
from typing import Any

import pytest
from agy_doctor_mux.oss_audit import audit_git_repository


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def test_empty_repo_no_tracked_files(tmp_path: Path) -> None:
    # Initialize an empty git repository
    run_git(tmp_path, "init")

    # Audit the empty repository
    result = audit_git_repository(tmp_path)
    
    assert isinstance(result, dict)
    assert result["repo_path"] == str(tmp_path.resolve())
    assert result["tracked_files_count"] == 0
    assert result["passed"] is False  # Missing LICENSE, README, etc.
    assert isinstance(result["violations"], list)
    
    # Missing required files violations
    assert any("Missing required OSS file: LICENSE" in v for v in result["violations"])
    assert any("Missing required OSS file: README.md" in v for v in result["violations"])
    assert any("Missing required OSS file: .gitignore" in v for v in result["violations"])
    assert any("Missing project manifest file" in v for v in result["violations"])


def test_empty_repo_str_path(tmp_path: Path) -> None:
    run_git(tmp_path, "init")

    # Pass path as a string instead of Path object
    result = audit_git_repository(str(tmp_path))
    
    assert isinstance(result, dict)
    assert result["repo_path"] == str(tmp_path.resolve())
    assert result["tracked_files_count"] == 0


def test_repo_with_untracked_files(tmp_path: Path) -> None:
    run_git(tmp_path, "init")
    
    # Create some untracked files
    (tmp_path / "README.md").write_text("Hello World", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")
    
    result = audit_git_repository(tmp_path)
    
    assert result["tracked_files_count"] == 0
    # Even though files exist, they are untracked, but wait, the audit checks `repo / req_file.is_file()`
    # Let's verify what the code does for `repo / req_file`
    # The code does:
    # for req_file in ("LICENSE", "README.md", ".gitignore"):
    #     if not (repo / req_file).is_file():
    #         violations.append(...)
    # So it doesn't care if they are tracked or not for the existence check!
    # But it does check tracked files count.
    
    assert any("Missing required OSS file: .gitignore" in v for v in result["violations"])
    assert not any("Missing required OSS file: README.md" in v for v in result["violations"])
    assert not any("Missing required OSS file: LICENSE" in v for v in result["violations"])


def test_repo_with_no_tracked_files_but_commit_history(tmp_path: Path) -> None:
    run_git(tmp_path, "init")
    
    # Create a file, track it, commit it, then rm it
    test_file = tmp_path / "test.txt"
    test_file.write_text("Test content", encoding="utf-8")
    
    run_git(tmp_path, "config", "user.name", "Test User")
    run_git(tmp_path, "config", "user.email", "test@example.com")
    run_git(tmp_path, "add", "test.txt")
    run_git(tmp_path, "commit", "-m", "Initial commit")
    
    run_git(tmp_path, "rm", "test.txt")
    run_git(tmp_path, "commit", "-m", "Remove file")
    
    result = audit_git_repository(tmp_path)
    
    assert result["tracked_files_count"] == 0
    assert any("Unexpected commit author email: test@example.com" in v for v in result["violations"])
