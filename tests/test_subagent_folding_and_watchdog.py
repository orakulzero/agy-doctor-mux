"""Verification tests for Subagent Folding Router (REQ-DOC-FOLD-01)
and Freeze Watchdog / V8 BigInt Shield (REQ-DOC-WATCH-01).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from agy_doctor_mux.freeze_watchdog import FreezeWatchdog, WatchdogStatus
from agy_doctor_mux.subagent_folding import FoldingDecision, SubagentFoldingRouter


# ============================================================================
# Module 1: agy_doctor_mux.subagent_folding (REQ-DOC-FOLD-01)
# ============================================================================


def test_folding_decision_linear_task_folds_in_process() -> None:
    """@requirement("REQ-DOC-FOLD-01"): Linear tasks under 500 lines fold in-process."""
    router = SubagentFoldingRouter()
    decision = router.evaluate(
        estimated_context_lines=120,
        requires_agile_v_isolation=False,
        is_embarrassingly_parallel=False,
        parallel_branches=1,
        is_untrusted_sandbox=False,
        task_kind="linear_query",
    )
    assert isinstance(decision, FoldingDecision)
    assert dataclasses.is_dataclass(decision)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.action = "mutated"  # type: ignore[misc]

    assert decision.action == "fold_in_process"
    assert decision.estimated_saved_ms > 0
    assert decision.estimated_saved_tokens > 0
    assert "fold_linear_in_process" in decision.criteria_triggered
    assert bool(decision.reason.strip())

    # Boundary: exactly 500 lines and parallel_branches=1 still fold in-process
    boundary = router.evaluate(
        estimated_context_lines=500,
        is_embarrassingly_parallel=True,
        parallel_branches=1,
    )
    assert boundary.action == "fold_in_process"
    assert "fold_linear_in_process" in boundary.criteria_triggered


def test_folding_router_four_anthropic_spawn_criteria() -> None:
    """@requirement("REQ-DOC-FOLD-01"): Spawns subagent only on the 4 keep-subagent criteria."""
    router = SubagentFoldingRouter()

    c1 = router.evaluate(estimated_context_lines=501)
    assert c1.action == "spawn_subagent"
    assert "context_firewall_gt_500_lines" in c1.criteria_triggered

    c2 = router.evaluate(requires_agile_v_isolation=True)
    assert c2.action == "spawn_subagent"
    assert "agile_v_role_isolation" in c2.criteria_triggered

    c3 = router.evaluate(is_embarrassingly_parallel=True, parallel_branches=3)
    assert c3.action == "spawn_subagent"
    assert "parallel_execution" in c3.criteria_triggered

    c4 = router.evaluate(is_untrusted_sandbox=True)
    assert c4.action == "spawn_subagent"
    assert "untrusted_sandbox_isolation" in c4.criteria_triggered


def test_recommend_execution_plan_batch_aggregation() -> None:
    """@requirement("REQ-DOC-FOLD-01"): Batch execution plan aggregates savings and counts."""
    router = SubagentFoldingRouter()
    tasks: list[dict[str, Any]] = [
        {"estimated_context_lines": 80, "task_kind": "status_check"},
        {"estimated_context_lines": 200, "task_kind": "single_file_edit"},
        {"estimated_context_lines": 900, "task_kind": "transcript_dump"},
        {"requires_agile_v_isolation": True, "task_kind": "p30_test_design"},
    ]
    plan = router.recommend_execution_plan(tasks)
    assert plan["total_tasks"] == 4
    assert plan["folded_count"] == 2
    assert plan["spawned_count"] == 2
    assert plan["total_saved_ms"] > 0
    assert plan["total_saved_tokens"] > 0
    assert len(plan["decisions"]) == 4


# ============================================================================
# Module 2: agy_doctor_mux.freeze_watchdog (REQ-DOC-WATCH-01)
# ============================================================================


def test_dead_man_switch_arm_and_disarm_lifecycle(tmp_path: Path) -> None:
    """@requirement("REQ-DOC-WATCH-01"): Dead-man switch arms timer condition and disarms cleanly."""
    watchdog = FreezeWatchdog(workspace_root=tmp_path, default_heartbeat_timeout_s=60)
    armed = watchdog.arm_dead_man_switch(
        task_id="task-99",
        timeout_seconds=75,
        conv_id="conv-123",
    )
    assert armed["task_id"] == "task-99"
    assert armed["timeout_seconds"] == 75
    assert armed["timer_condition"] == "conv-123/task-99"
    assert armed["armed"] is True
    assert "task-99" in armed["prompt"]

    assert watchdog.disarm_dead_man_switch("task-99") is True
    assert watchdog.disarm_dead_man_switch("task-99") is False


def test_inject_v8_bigint_shield_sanitizes_unsafe_integers(tmp_path: Path) -> None:
    """@requirement("REQ-DOC-WATCH-01"): V8 BigInt shield quotes unsafe >53-bit integers and n-literals."""
    watchdog = FreezeWatchdog(workspace_root=tmp_path)
    transcript = tmp_path / "transcript.jsonl"
    raw_line = (
        '{"step": 1, "unsafe_id": 9007199254740999, '
        '"bigint_lit": 12345678901234567890n, "safe_num": 42}\n'
    )
    transcript.write_text(raw_line, encoding="utf-8")

    result = watchdog.inject_v8_bigint_shield(transcript)
    assert result["sanitized_count"] >= 2
    assert result["clean"] is True
    assert Path(result["path"]).name == "transcript.jsonl"

    parsed = json.loads(transcript.read_text(encoding="utf-8").strip())
    assert parsed["unsafe_id"] == "9007199254740999"
    assert str(parsed["bigint_lit"]).startswith("12345678901234567890")
    assert parsed["safe_num"] == 42


def test_audit_and_heal_freeze_conditions_heals_locks_and_detects_stalls(
    tmp_path: Path,
) -> None:
    """@requirement("REQ-DOC-WATCH-01"): Heals stale .git/index.lock and detects 0-byte stalled logs."""
    repo_dir = tmp_path / "repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True)
    stale_lock = git_dir / "index.lock"
    stale_lock.write_text("", encoding="utf-8")

    brain_dir = tmp_path / "brain"
    conv_dir = brain_dir / "conv-frozen" / ".system_generated" / "logs"
    conv_dir.mkdir(parents=True)
    stalled_log = conv_dir / "task-hung.log"
    stalled_log.write_text("", encoding="utf-8")
    crash_transcript = conv_dir / "transcript.jsonl"
    crash_transcript.write_text(
        '{"status": "ERROR", "error": "TypeError: Do not know how to serialize a BigInt"}\n',
        encoding="utf-8",
    )

    watchdog = FreezeWatchdog(workspace_root=repo_dir, brain_dir=brain_dir)
    status = watchdog.audit_and_heal_freeze_conditions(
        auto_heal=True,
        stale_lock_age_s=0.0,
    )
    assert isinstance(status, WatchdogStatus)
    assert dataclasses.is_dataclass(status)
    assert not stale_lock.exists()
    assert len(status.deadlocked_worktrees) >= 1
    assert any("task-hung" in t for t in status.stalled_task_ids)
    assert "conv-frozen" in status.bigint_crash_conversations
    assert len(status.actions_taken) >= 1
    assert status.system_latency_ms >= 0.0
