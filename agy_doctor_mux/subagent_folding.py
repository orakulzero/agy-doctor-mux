"""Subagent Folding Router for Antigravity 2.0 (REQ-DOC-FOLD-01).

Implements the Anthropic 2026 subagent folding pattern: linear/single-file tasks
under 500 lines fold directly into the in-process HookMultiplexer, whereas tasks
requiring context firewalling (>500 lines), Agile V P30 role separation,
embarrassingly parallel branches, or untrusted sandboxing spawn isolated subagents.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

MAX_IN_PROCESS_CONTEXT_LINES = 500
DEFAULT_FOLD_SAVED_MS = 1800
DEFAULT_FOLD_SAVED_TOKENS = 3500


@dataclass(frozen=True)
class FoldingDecision:
    """@requirement("REQ-DOC-FOLD-01"): Immutable routing decision for subagent vs in-process execution."""

    action: str
    reason: str
    estimated_saved_ms: int
    estimated_saved_tokens: int
    criteria_triggered: tuple[str, ...]
    task_kind: str = "linear_query"


def validate_folding_decision(decision: FoldingDecision) -> list[str]:
    """Validates structural integrity and consistency of a folding decision."""
    errors: list[str] = []
    if decision.action not in ("fold_in_process", "spawn_subagent"):
        errors.append(f"action must be 'fold_in_process' or 'spawn_subagent', got: {decision.action}")
    
    if decision.action == "fold_in_process":
        if decision.estimated_saved_ms <= 0 or decision.estimated_saved_tokens <= 0:
            errors.append("fold_in_process decisions should have positive savings")
            
    return errors


class SubagentFoldingRouter:
    """@requirement("REQ-DOC-FOLD-01"): Evaluates tasks against the 4 keep-subagent criteria."""

    def __init__(
        self,
        max_in_process_lines: int = MAX_IN_PROCESS_CONTEXT_LINES,
        saved_ms_per_fold: int = DEFAULT_FOLD_SAVED_MS,
        saved_tokens_per_fold: int = DEFAULT_FOLD_SAVED_TOKENS,
    ) -> None:
        self.max_in_process_lines = max_in_process_lines
        self.saved_ms_per_fold = saved_ms_per_fold
        self.saved_tokens_per_fold = saved_tokens_per_fold

    def evaluate(
        self,
        *,
        estimated_context_lines: int = 0,
        requires_agile_v_isolation: bool = False,
        is_embarrassingly_parallel: bool = False,
        parallel_branches: int = 1,
        is_untrusted_sandbox: bool = False,
        task_kind: str = "linear_query",
    ) -> FoldingDecision:
        """@requirement("REQ-DOC-FOLD-01"): Decide whether to fold in-process or spawn a subagent."""
        triggered: list[str] = []

        if estimated_context_lines > self.max_in_process_lines:
            triggered.append("context_firewall_gt_500_lines")
        if requires_agile_v_isolation:
            triggered.append("agile_v_role_isolation")
        if is_embarrassingly_parallel and parallel_branches > 1:
            triggered.append("parallel_execution")
        if is_untrusted_sandbox:
            triggered.append("untrusted_sandbox_isolation")

        if triggered:
            return FoldingDecision(
                action="spawn_subagent",
                reason=(
                    f"Spawn subagent for '{task_kind}': triggered keep-subagent "
                    f"criteria ({', '.join(triggered)})."
                ),
                estimated_saved_ms=0,
                estimated_saved_tokens=0,
                criteria_triggered=tuple(triggered),
                task_kind=task_kind,
            )

        return FoldingDecision(
            action="fold_in_process",
            reason=(
                f"Fold '{task_kind}' ({estimated_context_lines} lines) in-process "
                "via HookMultiplexer to avoid subagent startup overhead."
            ),
            estimated_saved_ms=self.saved_ms_per_fold,
            estimated_saved_tokens=self.saved_tokens_per_fold,
            criteria_triggered=("fold_linear_in_process",),
            task_kind=task_kind,
        )

    def recommend_execution_plan(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """@requirement("REQ-DOC-FOLD-01"): Evaluate a batch of tasks and aggregate folding savings."""
        decisions: list[FoldingDecision] = []
        for task in tasks:
            decision = self.evaluate(
                estimated_context_lines=int(task.get("estimated_context_lines", 0)),
                requires_agile_v_isolation=bool(
                    task.get("requires_agile_v_isolation", False)
                ),
                is_embarrassingly_parallel=bool(
                    task.get("is_embarrassingly_parallel", False)
                ),
                parallel_branches=int(task.get("parallel_branches", 1)),
                is_untrusted_sandbox=bool(task.get("is_untrusted_sandbox", False)),
                task_kind=str(task.get("task_kind", "linear_query")),
            )
            decisions.append(decision)

        folded_count = sum(1 for d in decisions if d.action == "fold_in_process")
        spawned_count = sum(1 for d in decisions if d.action == "spawn_subagent")
        total_saved_ms = sum(d.estimated_saved_ms for d in decisions)
        total_saved_tokens = sum(d.estimated_saved_tokens for d in decisions)

        return {
            "total_tasks": len(decisions),
            "folded_count": folded_count,
            "spawned_count": spawned_count,
            "total_saved_ms": total_saved_ms,
            "total_saved_tokens": total_saved_tokens,
            "decisions": [dataclasses.asdict(d) for d in decisions],
        }
