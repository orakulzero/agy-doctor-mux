"""Git Worktree Deadlock Healer & Subagent Brain Transcript Scanner."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _git_cmd(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def diagnose_and_heal_worktrees(
    repo_path: Path | str, dry_run: bool = True
) -> dict[str, Any]:
    """Diagnose and optionally heal Antigravity 2.0 Git worktree deadlocks and stale locks."""
    repo = Path(repo_path).resolve()
    git_dir = repo / ".git"
    issues: list[str] = []
    actions_taken: list[str] = []

    if not git_dir.is_dir():
        return {
            "repo_path": str(repo),
            "dry_run": dry_run,
            "has_deadlock_risk": False,
            "issues_count": 0,
            "issues": [],
            "healed": False,
            "actions_taken": [],
        }

    # 1. Check extensions.worktreeConfig
    wt_cfg = _git_cmd(repo, "config", "--get", "extensions.worktreeConfig").stdout.strip().lower()
    if wt_cfg == "true":
        issues.append("extensions_worktree_config_enabled")
        if not dry_run:
            _git_cmd(repo, "config", "--unset", "extensions.worktreeConfig")
            actions_taken.append("unset extensions.worktreeConfig")

    # 2. Check core.repositoryformatversion
    fmt_ver = _git_cmd(repo, "config", "--get", "core.repositoryformatversion").stdout.strip()
    if fmt_ver == "1":
        issues.append("repository_format_version_1")
        if not dry_run:
            _git_cmd(repo, "config", "core.repositoryformatversion", "0")
            actions_taken.append("reset core.repositoryformatversion to 0")

    # 3. Check stale .git/index.lock
    index_lock = git_dir / "index.lock"
    if index_lock.exists():
        issues.append("stale_index_lock")
        if not dry_run:
            index_lock.unlink(missing_ok=True)
            actions_taken.append("removed stale .git/index.lock")

    # 4. Check dangling .git/worktrees/* entries
    worktrees_root = git_dir / "worktrees"
    if worktrees_root.is_dir():
        for wt_entry in sorted(worktrees_root.iterdir()):
            if not wt_entry.is_dir():
                continue
            gitdir_file = wt_entry / "gitdir"
            is_dangling = False
            if not gitdir_file.is_file():
                is_dangling = True
            else:
                target_str = gitdir_file.read_text(encoding="utf-8", errors="replace").strip()
                if not target_str or not Path(target_str).exists():
                    is_dangling = True
            if is_dangling:
                issues.append(f"dangling_worktree:{wt_entry.name}")
                if not dry_run:
                    shutil.rmtree(wt_entry, ignore_errors=True)
                    actions_taken.append(f"pruned dangling worktree {wt_entry.name}")

    if not dry_run and actions_taken:
        _git_cmd(repo, "worktree", "prune")

    return {
        "repo_path": str(repo),
        "dry_run": dry_run,
        "has_deadlock_risk": len(issues) > 0,
        "issues_count": len(issues),
        "issues": issues,
        "healed": (not dry_run and len(issues) > 0),
        "actions_taken": actions_taken,
    }


def scan_brain_subagents(brain_dir: Path | str) -> dict[str, Any]:
    """Scan Antigravity brain transcripts for BigInt serialization crashes and stalled subagents."""
    root = Path(brain_dir).resolve()
    bigint_crashes: list[str] = []
    stalled_subagents: list[str] = []
    healthy_conversations: list[str] = []
    total_conversations = 0

    if not root.is_dir():
        return {
            "brain_dir": str(root),
            "total_conversations": 0,
            "bigint_crashes": [],
            "stalled_subagents": [],
            "healthy_conversations": [],
        }

    for conv_dir in sorted(root.iterdir()):
        if not conv_dir.is_dir():
            continue
        candidates = [
            conv_dir / ".system_generated" / "logs" / "transcript.jsonl",
            conv_dir / "transcript.jsonl",
        ]
        transcript_file = next((c for c in candidates if c.is_file()), None)
        if transcript_file is None:
            continue

        total_conversations += 1
        conv_id = conv_dir.name
        raw_text = transcript_file.read_text(encoding="utf-8", errors="replace")
        has_bigint = "Do not know how to serialize a BigInt" in raw_text or "BigInt" in raw_text

        last_status = "DONE"
        for line in raw_text.splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                if isinstance(obj, dict) and "status" in obj:
                    last_status = str(obj["status"])
            except Exception:
                pass

        if has_bigint:
            bigint_crashes.append(conv_id)
        elif last_status == "IN_PROGRESS":
            stalled_subagents.append(conv_id)
        else:
            healthy_conversations.append(conv_id)

    return {
        "brain_dir": str(root),
        "total_conversations": total_conversations,
        "bigint_crashes": bigint_crashes,
        "stalled_subagents": stalled_subagents,
        "healthy_conversations": healthy_conversations,
    }
