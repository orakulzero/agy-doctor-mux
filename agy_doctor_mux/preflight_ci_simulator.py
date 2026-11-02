"""Pre-Flight CI Workflow Simulator (REQ-DM-PREFLIGHT-01).

Parses `.github/workflows/*.yml` definitions and simulates safe local lint/test
steps prior to git push, preventing avoidable remote CI pipeline failures while
filtering out external release/deployment side-effect commands.

Requirement Traceability:
- REQ-DM-PREFLIGHT-01: Pre-Flight CI Workflow Simulator
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

UNSAFE_EXTERNAL_PATTERNS = (
    "gh release",
    "docker push",
    "git push",
    "twine upload",
    "npm publish",
    "cargo publish",
    "kubectl apply",
    "terraform apply",
)


@dataclass(frozen=True)
class WorkflowStepResult:
    """Execution outcome of a single simulated CI workflow step (REQ-DM-PREFLIGHT-01)."""

    name: str
    command: str
    exit_code: int
    output: str
    passed: bool


class PreFlightCISimulator:
    """Local simulator for GitHub Actions verification workflows (REQ-DM-PREFLIGHT-01)."""

    def extract_run_steps(self, workflow_yaml: str) -> List[Dict[str, str]]:
        """Extract ordered step names and `run:` commands from GitHub Actions YAML text (REQ-DM-PREFLIGHT-01)."""
        steps: List[Dict[str, str]] = []
        current_name: Optional[str] = None

        for raw_line in workflow_yaml.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- "):
                current_name = None
                stripped = stripped[2:].strip()

            if stripped.startswith("name:"):
                val = stripped[len("name:") :].strip().strip("'\"")
                current_name = val
            elif stripped.startswith("run:"):
                cmd = stripped[len("run:") :].strip().strip("'\"")
                step_name = current_name if current_name else cmd
                steps.append({"name": step_name, "run": cmd})
                current_name = None

        return steps

    def is_safe_local_step(self, command: str) -> bool:
        """Return True if the step is a safe local lint/test command without external side effects (REQ-DM-PREFLIGHT-01)."""
        normalized = command.strip().lower()
        if not normalized:
            return False
        for pattern in UNSAFE_EXTERNAL_PATTERNS:
            if pattern in normalized:
                return False
        return True

    def _default_step_runner(self, command: str, cwd: Path) -> Tuple[int, str]:
        """Execute a step command locally with an explicit timeout."""
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, combined.strip()

    def simulate_workflow(
        self,
        workflow_yaml: str,
        cwd: Path,
        step_runner: Optional[Callable[[str, Path], Tuple[int, str]]] = None,
        fail_fast: bool = True,
    ) -> Dict[str, Any]:
        """Simulate safe local steps from a workflow definition and aggregate status (REQ-DM-PREFLIGHT-01)."""
        runner = step_runner or self._default_step_runner
        extracted = self.extract_run_steps(workflow_yaml)
        results: List[WorkflowStepResult] = []
        failed_steps: List[str] = []

        for step in extracted:
            cmd = step["run"]
            if not self.is_safe_local_step(cmd):
                continue
            exit_code, output = runner(cmd, cwd)
            passed = exit_code == 0
            step_result = WorkflowStepResult(
                name=step["name"],
                command=cmd,
                exit_code=exit_code,
                output=output,
                passed=passed,
            )
            results.append(step_result)
            if not passed:
                failed_steps.append(step["name"])
                if fail_fast:
                    break

        return {
            "passed": len(failed_steps) == 0,
            "executed_count": len(results),
            "failed_steps": failed_steps,
            "results": results,
        }

    def discover_workflows(self, repo_root: Path) -> List[Path]:
        """Discover `.github/workflows/*.yml` and `*.yaml` files in a repository (REQ-DM-PREFLIGHT-01)."""
        wf_dir = Path(repo_root) / ".github" / "workflows"
        if not wf_dir.is_dir():
            return []
        ymls = list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))
        return sorted(ymls)
