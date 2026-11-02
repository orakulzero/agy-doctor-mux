"""Locked Agile V (P30) Verification Suite for Pre-Flight CI Workflow Simulator.

Requirement Traceability:
- REQ-DM-PREFLIGHT-01: Pre-Flight CI Workflow Simulator (`preflight_ci_simulator.py`)

Quality Framework: ISO 9001:2015, ISO/IEC 42001:2023, Agile V Role Separation.
Hygiene: 100% English-only (0 Cyrillic characters).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agy_doctor_mux.preflight_ci_simulator import (  # noqa: E402
    PreFlightCISimulator,
    WorkflowStepResult,
)

SAMPLE_WORKFLOW_YAML = """
name: CI Verification
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Linter
        run: ruff check .
      - name: Run Unit Tests
        run: pytest -q
"""


def test_extract_workflow_run_commands_from_yaml_text() -> None:
    """REQ-DM-PREFLIGHT-01: Verify extract_run_steps parses step names and run commands from GitHub Actions YAML."""
    sim = PreFlightCISimulator()
    steps = sim.extract_run_steps(SAMPLE_WORKFLOW_YAML)
    assert len(steps) == 2
    assert steps[0]["name"] == "Run Linter"
    assert steps[0]["run"] == "ruff check ."
    assert steps[1]["name"] == "Run Unit Tests"
    assert steps[1]["run"] == "pytest -q"


def test_classify_safe_local_steps_vs_external_deploy_steps() -> None:
    """REQ-DM-PREFLIGHT-01: Verify safe local test/lint steps are distinguished from external release/push commands."""
    sim = PreFlightCISimulator()
    assert sim.is_safe_local_step("pytest -q") is True
    assert sim.is_safe_local_step("ruff check src/") is True
    assert sim.is_safe_local_step("gh release create v1.0") is False
    assert sim.is_safe_local_step("docker push myorg/image:latest") is False


def test_simulate_workflow_executes_custom_runner_and_aggregates_status(tmp_path: Path) -> None:
    """REQ-DM-PREFLIGHT-01: Verify simulate_workflow runs safe steps via step_runner and aggregates passing status."""
    sim = PreFlightCISimulator()
    res = sim.simulate_workflow(
        SAMPLE_WORKFLOW_YAML,
        cwd=tmp_path,
        step_runner=lambda cmd, cwd: (0, "10 passed"),
    )
    assert res["passed"] is True
    assert res["executed_count"] == 2
    assert res["failed_steps"] == []
    assert len(res["results"]) == 2
    assert isinstance(res["results"][0], WorkflowStepResult)


def test_simulate_workflow_halts_on_first_failing_step(tmp_path: Path) -> None:
    """REQ-DM-PREFLIGHT-01: Verify fail_fast=True stops simulation immediately after the first failing step."""
    sim = PreFlightCISimulator()
    executed_cmds: List[str] = []

    def _failing_runner(cmd: str, cwd: Path) -> Tuple[int, str]:
        executed_cmds.append(cmd)
        if len(executed_cmds) == 1:
            return (1, "AssertionError: lint failure")
        return (0, "ok")

    res = sim.simulate_workflow(
        SAMPLE_WORKFLOW_YAML,
        cwd=tmp_path,
        step_runner=_failing_runner,
        fail_fast=True,
    )
    assert res["passed"] is False
    assert len(res["failed_steps"]) == 1
    assert res["executed_count"] == 1
    assert len(executed_cmds) == 1


def test_discover_repository_workflows(tmp_path: Path) -> None:
    """REQ-DM-PREFLIGHT-01: Verify discover_workflows finds .github/workflows/*.yml files in a repository."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    ci_yml = wf_dir / "ci.yml"
    ci_yml.write_text(SAMPLE_WORKFLOW_YAML, encoding="utf-8")

    sim = PreFlightCISimulator()
    found = sim.discover_workflows(tmp_path)
    assert found == [ci_yml]


def test_req_dm_preflight_01_traceability_and_english_hygiene() -> None:
    """REQ-DM-PREFLIGHT-01: Verify preflight_ci_simulator.py contains REQ-DM-PREFLIGHT-01 and 0 Cyrillic characters."""
    target_file = REPO_ROOT / "agy_doctor_mux" / "preflight_ci_simulator.py"
    assert target_file.is_file(), f"Missing target module: {target_file}"
    content = target_file.read_text(encoding="utf-8")
    assert "REQ-DM-PREFLIGHT-01" in content
    for ch in content:
        code = ord(ch)
        assert not (0x0400 <= code <= 0x04FF), f"Cyrillic character found: {ch!r}"
