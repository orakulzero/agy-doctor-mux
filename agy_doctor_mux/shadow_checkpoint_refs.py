"""Shadow Checkpoint Git Refs Manager (REQ-DOC-SHADOW-01).

Creates, lists, and restores full working-tree snapshots (including modified
and untracked files) under `refs/agy-checkpoints/<id>` using an isolated
temporary `GIT_INDEX_FILE` so `HEAD`, `.git/index`, and commit history remain
100% untouched.

Requirement Traceability:
- REQ-DOC-SHADOW-01: Shadow Checkpoint Git Refs Manager
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

REF_PREFIX = "refs/agy-checkpoints"


class ShadowCheckpointManager:
    """Manages zero-pollution shadow checkpoints under `refs/agy-checkpoints/*` (REQ-DOC-SHADOW-01)."""

    def __init__(self, repo_path: str | Path) -> None:
        """Initialize manager bound to repo_path (REQ-DOC-SHADOW-01)."""
        self.repo_path = Path(repo_path).resolve()

    def _run_git(
        self,
        *args: str,
        env_overrides: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git plumbing command with an explicit timeout and optional environment overrides."""
        env = dict(os.environ)
        env.setdefault("GIT_AUTHOR_NAME", "shadow-checkpoint")
        env.setdefault("GIT_AUTHOR_EMAIL", "shadow@local.invalid")
        env.setdefault("GIT_COMMITTER_NAME", "shadow-checkpoint")
        env.setdefault("GIT_COMMITTER_EMAIL", "shadow@local.invalid")
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            ["git", *args],
            cwd=str(self.repo_path),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=check,
        )

    def _get_head_sha(self) -> str | None:
        """Return current HEAD commit SHA or None if repository has no commits yet."""
        proc = self._run_git("rev-parse", "--verify", "--quiet", "HEAD", check=False)
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    def create_checkpoint(
        self,
        checkpoint_id: str,
        message: str = "shadow checkpoint",
    ) -> dict[str, Any]:
        """Snapshot tracked and untracked files into `refs/agy-checkpoints/<checkpoint_id>` (REQ-DOC-SHADOW-01)."""
        ref_name = f"{REF_PREFIX}/{checkpoint_id}"
        head_before = self._get_head_sha()
        real_index = self.repo_path / ".git" / "index"

        with tempfile.TemporaryDirectory(prefix="agy_shadow_idx_") as tmp_dir:
            tmp_index = Path(tmp_dir) / "index"
            if real_index.is_file():
                shutil.copy2(real_index, tmp_index)
            env_idx = {"GIT_INDEX_FILE": str(tmp_index)}
            self._run_git("add", "-A", env_overrides=env_idx)
            tree_sha = self._run_git("write-tree", env_overrides=env_idx).stdout.strip()

        commit_args = ["commit-tree", tree_sha]
        if head_before:
            commit_args.extend(["-p", head_before])
        commit_args.extend(["-m", message])
        commit_sha = self._run_git(*commit_args).stdout.strip()
        self._run_git("update-ref", ref_name, commit_sha)

        head_after = self._get_head_sha()
        return {
            "requirement_id": "REQ-DOC-SHADOW-01",
            "status": "CREATED",
            "checkpoint_id": checkpoint_id,
            "ref_name": ref_name,
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "message": message,
            "head_unchanged": head_after == head_before,
        }

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        """Restore working tree files from `refs/agy-checkpoints/<checkpoint_id>` without mutating HEAD or .git/index (REQ-DOC-SHADOW-01)."""
        ref_name = f"{REF_PREFIX}/{checkpoint_id}"
        verify = self._run_git("rev-parse", "--verify", "--quiet", ref_name, check=False)
        if verify.returncode != 0:
            return {
                "requirement_id": "REQ-DOC-SHADOW-01",
                "status": "NOT_FOUND",
                "checkpoint_id": checkpoint_id,
                "ref_name": ref_name,
            }

        commit_sha = verify.stdout.strip()
        head_before = self._get_head_sha()
        with tempfile.TemporaryDirectory(prefix="agy_shadow_restore_") as tmp_dir:
            tmp_index = Path(tmp_dir) / "index"
            env_idx = {"GIT_INDEX_FILE": str(tmp_index)}
            self._run_git("read-tree", ref_name, env_overrides=env_idx)
            self._run_git("checkout-index", "-a", "-f", env_overrides=env_idx)

        head_after = self._get_head_sha()
        return {
            "requirement_id": "REQ-DOC-SHADOW-01",
            "status": "RESTORED",
            "checkpoint_id": checkpoint_id,
            "ref_name": ref_name,
            "commit_sha": commit_sha,
            "head_unchanged": head_after == head_before,
        }

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """List all shadow checkpoints stored under `refs/agy-checkpoints/` (REQ-DOC-SHADOW-01)."""
        proc = self._run_git(
            "for-each-ref",
            "--format=%(refname)|%(objectname)|%(contents:subject)",
            REF_PREFIX,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []

        items: list[dict[str, Any]] = []
        prefix_with_slash = f"{REF_PREFIX}/"
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 2)
            ref_name = parts[0].strip()
            commit_sha = parts[1].strip() if len(parts) > 1 else ""
            subject = parts[2].strip() if len(parts) > 2 else ""
            chk_id = (
                ref_name[len(prefix_with_slash) :]
                if ref_name.startswith(prefix_with_slash)
                else ref_name
            )
            items.append(
                {
                    "checkpoint_id": chk_id,
                    "ref_name": ref_name,
                    "commit_sha": commit_sha,
                    "message": subject,
                }
            )
        return items


def create_shadow_checkpoint(
    repo_path: str | Path,
    checkpoint_id: str,
    message: str = "shadow checkpoint",
) -> dict[str, Any]:
    """Convenience function to create a shadow checkpoint (REQ-DOC-SHADOW-01)."""
    return ShadowCheckpointManager(repo_path).create_checkpoint(
        checkpoint_id=checkpoint_id,
        message=message,
    )


def restore_shadow_checkpoint(
    repo_path: str | Path,
    checkpoint_id: str,
) -> dict[str, Any]:
    """Convenience function to restore a shadow checkpoint (REQ-DOC-SHADOW-01)."""
    return ShadowCheckpointManager(repo_path).restore_checkpoint(
        checkpoint_id=checkpoint_id,
    )
