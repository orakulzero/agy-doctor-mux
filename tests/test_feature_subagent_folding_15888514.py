"""Test suite for validate_folding_decision helper in subagent_folding module."""

from __future__ import annotations

import pytest

from agy_doctor_mux.subagent_folding import (
    FoldingDecision,
    validate_folding_decision,
)


def test_validate_folding_decision_accepts_valid_fold_in_process():
    """Valid fold_in_process decision passes all structural checks."""
    decision = FoldingDecision(
        action="fold_in_process",
        reason="Fold 'linear_query' (200 lines) in-process via HookMultiplexer.",
        estimated_saved_ms=1800,
        estimated_saved_tokens=3500,
        criteria_triggered=("fold_linear_in_process",),
        task_kind="linear_query",
    )
    errors = validate_folding_decision(decision)
    assert len(errors) == 0, f"Expected no errors, got: {errors}"


def test_validate_folding_decision_rejects_invalid_action():
    """Decision with unrecognized action returns validation error."""
    decision = FoldingDecision(
        action="maybe_fold",
        reason="Unclear routing.",
        estimated_saved_ms=0,
        estimated_saved_tokens=0,
        criteria_triggered=(),
        task_kind="unknown",
    )
    errors = validate_folding_decision(decision)
    assert any("action must be" in e for e in errors), f"Expected action error, got: {errors}"


def test_validate_folding_decision_detects_fold_with_zero_savings():
    """fold_in_process with zero savings triggers logical inconsistency error."""
    decision = FoldingDecision(
        action="fold_in_process",
        reason="Fold in-process.",
        estimated_saved_ms=0,
        estimated_saved_tokens=0,
        criteria_triggered=("fold_linear_in_process",),
        task_kind="linear_query",
    )
    errors = validate_folding_decision(decision)
    assert any("should have positive savings" in e for e in errors), f"Expected savings error, got: {errors}"
