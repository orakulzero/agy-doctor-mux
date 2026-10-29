"""Freeze Watchdog, Dead-Man Switch & V8 BigInt Shield (REQ-DOC-WATCH-01).

Prevents and heals Antigravity 2.0 "Dead Silence" IDE freezes caused by:
1. Unmonitored background tasks with 0-byte stalled logs (Dead-Man Switch).
2. Unquoted >53-bit integers or BigInt literals crashing V8 JSON.stringify.
3. Stale .git/index.lock or deadlocked Git worktrees during parallel subagent runs.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agy_doctor_mux.worktree_doctor import (
    diagnose_and_heal_worktrees,
    scan_brain_subagents,
)

MAX_SAFE_V8_INTEGER = 9007199254740991  # (2**53) - 1
_UNSAFE_INT_PATTERN = re.compile(r"([:\[,]\s*)(-?\d+)(n?)(?=\s*[,\]\}])")


@dataclass
class WatchdogStatus:
    """@requirement("REQ-DOC-WATCH-01"): Snapshot of freeze conditions and automated healing actions."""

    deadlocked_worktrees: list[str] = field(default_factory=list)
    stalled_task_ids: list[str] = field(default_factory=list)
    bigint_crash_conversations: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    system_latency_ms: float = 0.0
    armed_switches_count: int = 0


class FreezeWatchdog:
    """@requirement("REQ-DOC-WATCH-01"): Proactive freeze detector, V8 BigInt sanitizer, and lock healer."""

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        brain_dir: Path | str | None = None,
        default_heartbeat_timeout_s: int = 60,
    ) -> None:
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        )
        self.brain_dir = Path(brain_dir).resolve() if brain_dir else None
        self.default_heartbeat_timeout_s = default_heartbeat_timeout_s
        self._armed_switches: dict[str, dict[str, Any]] = {}

    def arm_dead_man_switch(
        self,
        task_id: str,
        timeout_seconds: int | None = None,
        conv_id: str = "default",
    ) -> dict[str, Any]:
        """@requirement("REQ-DOC-WATCH-01"): Arm a Dead-Man Switch schedule descriptor for a background task."""
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self.default_heartbeat_timeout_s
        )
        timer_condition = f"{conv_id}/{task_id}"
        prompt = (
            f"Watchdog: check {task_id}; if 0-byte log or hung, "
            "kill via manage_task and re-run with explicit timeout"
        )
        descriptor: dict[str, Any] = {
            "task_id": task_id,
            "conv_id": conv_id,
            "timeout_seconds": timeout,
            "timer_condition": timer_condition,
            "armed": True,
            "prompt": prompt,
        }
        self._armed_switches[task_id] = descriptor
        return descriptor

    def disarm_dead_man_switch(self, task_id: str) -> bool:
        """@requirement("REQ-DOC-WATCH-01"): Disarm an active Dead-Man Switch when a task completes."""
        return self._armed_switches.pop(task_id, None) is not None

    def inject_v8_bigint_shield(self, transcript_path: Path | str) -> dict[str, Any]:
        """@requirement("REQ-DOC-WATCH-01"): Quote unsafe >53-bit integers and BigInt literals in JSONL."""
        target = Path(transcript_path).resolve()
        if not target.is_file():
            return {"path": str(target), "sanitized_count": 0, "clean": False}

        raw_text = target.read_text(encoding="utf-8", errors="replace")
        sanitized_count = 0

        def _replace_match(match: re.Match[str]) -> str:
            nonlocal sanitized_count
            prefix, digits, n_suffix = match.group(1), match.group(2), match.group(3)
            try:
                val = abs(int(digits))
            except ValueError:
                return match.group(0)
            if n_suffix == "n" or val > MAX_SAFE_V8_INTEGER:
                sanitized_count += 1
                return f'{prefix}"{digits}"'
            return match.group(0)

        sanitized_text = _UNSAFE_INT_PATTERN.sub(_replace_match, raw_text)
        if sanitized_count > 0:
            target.write_text(sanitized_text, encoding="utf-8")

        return {
            "path": str(target),
            "sanitized_count": sanitized_count,
            "clean": True,
        }

    def audit_and_heal_freeze_conditions(
        self,
        auto_heal: bool = True,
        stale_lock_age_s: float = 30.0,
    ) -> WatchdogStatus:
        """@requirement("REQ-DOC-WATCH-01"): Audit and optionally heal worktree locks, stalled logs, and BigInt crashes."""
        t0 = time.perf_counter()
        deadlocked_worktrees: list[str] = []
        stalled_task_ids: list[str] = []
        bigint_crash_conversations: list[str] = []
        actions_taken: list[str] = []

        git_dir = self.workspace_root / ".git"
        index_lock = git_dir / "index.lock"
        if index_lock.is_file():
            age_s = max(0.0, time.time() - index_lock.stat().st_mtime)
            if age_s >= stale_lock_age_s:
                deadlocked_worktrees.append(str(self.workspace_root))
                if auto_heal:
                    index_lock.unlink(missing_ok=True)
                    actions_taken.append(f"removed stale lock {index_lock}")

        wt_report = diagnose_and_heal_worktrees(
            self.workspace_root, dry_run=not auto_heal
        )
        if wt_report.get("has_deadlock_risk") and str(self.workspace_root) not in deadlocked_worktrees:
            deadlocked_worktrees.append(str(self.workspace_root))
        for act in wt_report.get("actions_taken", []):
            if act not in actions_taken:
                actions_taken.append(act)

        if self.brain_dir and self.brain_dir.is_dir():
            brain_report = scan_brain_subagents(self.brain_dir)
            bigint_crash_conversations.extend(brain_report.get("bigint_crashes", []))
            stalled_task_ids.extend(brain_report.get("stalled_subagents", []))

            for conv_dir in sorted(self.brain_dir.iterdir()):
                if not conv_dir.is_dir():
                    continue
                logs_dir = conv_dir / ".system_generated" / "logs"
                if not logs_dir.is_dir():
                    continue
                for log_file in sorted(logs_dir.glob("*.log")):
                    if log_file.is_file() and log_file.stat().st_size == 0:
                        stalled_id = log_file.stem
                        if stalled_id not in stalled_task_ids:
                            stalled_task_ids.append(stalled_id)
                        if auto_heal:
                            actions_taken.append(
                                f"flagged 0-byte stalled task log {conv_dir.name}/{log_file.name}"
                            )
                if auto_heal and conv_dir.name in bigint_crash_conversations:
                    transcript_f = logs_dir / "transcript.jsonl"
                    if transcript_f.is_file():
                        self.inject_v8_bigint_shield(transcript_f)
                        actions_taken.append(
                            f"applied V8 BigInt shield to {conv_dir.name}/transcript.jsonl"
                        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return WatchdogStatus(
            deadlocked_worktrees=deadlocked_worktrees,
            stalled_task_ids=stalled_task_ids,
            bigint_crash_conversations=bigint_crash_conversations,
            actions_taken=actions_taken,
            system_latency_ms=elapsed_ms,
            armed_switches_count=len(self._armed_switches),
        )
