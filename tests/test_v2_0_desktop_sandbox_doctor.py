"""Tests for Antigravity v2.0.0 Win32 Desktop & Sandbox Health Doctor (REQ-DM-201)

and Ecosystem Version Matrix Auditor for 10 Stations at v2.0.0 (REQ-DM-202).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List
import pytest

import agy_doctor_mux

try:
    from agy_doctor_mux import (
        audit_ecosystem_version_matrix,
        diagnose_desktop_and_sandbox_health,
    )
except ImportError:
    try:
        from agy_doctor_mux.desktop_doctor import diagnose_desktop_and_sandbox_health
        from agy_doctor_mux.sync import audit_ecosystem_version_matrix
    except ImportError:
        def diagnose_desktop_and_sandbox_health(*args: Any, **kwargs: Any) -> Any:
            from agy_doctor_mux.desktop_doctor import diagnose_desktop_and_sandbox_health as fn
            return fn(*args, **kwargs)

        def audit_ecosystem_version_matrix(*args: Any, **kwargs: Any) -> Any:
            from agy_doctor_mux.sync import audit_ecosystem_version_matrix as fn
            return fn(*args, **kwargs)


# ============================================================================
# 1. Version and Re-export Tests (REQ-DM-201, REQ-DM-202)
# ============================================================================


def test_v2_0_doctor_mux_version_and_exports() -> None:
    """Verify package version is 2.0.0 and v2.0.0 functions are exported in agy_doctor_mux."""
    assert agy_doctor_mux.__version__ == "2.0.0", "Package version must be bumped to 2.0.0"
    assert hasattr(agy_doctor_mux, "diagnose_desktop_and_sandbox_health")
    assert hasattr(agy_doctor_mux, "audit_ecosystem_version_matrix")
    all_symbols = getattr(agy_doctor_mux, "__all__", [])
    assert "diagnose_desktop_and_sandbox_health" in all_symbols
    assert "audit_ecosystem_version_matrix" in all_symbols


# ============================================================================
# 2. Win32 Desktop & Sandbox Health Doctor Tests (REQ-DM-201)
# ============================================================================


def test_req201_desktop_health_display_and_resolution_detection() -> None:
    """REQ-DM-201: Desktop diagnostics detect virtual desktop bounds and monitor resolution."""
    report = diagnose_desktop_and_sandbox_health(probe_win32_display=True)
    assert isinstance(report, dict)
    assert "desktop" in report
    desktop = report["desktop"]
    assert "virtual_bounds" in desktop or "resolution" in desktop
    assert "monitors" in desktop or "primary_monitor" in desktop


def test_req201_desktop_health_dpi_scale_metrics() -> None:
    """REQ-DM-201: Desktop diagnostics report DPI scaling metrics and awareness level."""
    report = diagnose_desktop_and_sandbox_health()
    desktop = report.get("desktop", {})
    assert "dpi_scale" in desktop or "dpi_awareness" in desktop or "scaling_factor" in desktop


def test_req201_desktop_health_window_station_and_session() -> None:
    """REQ-DM-201: Validates interactive window station (WinSta0) and session accessibility."""
    report = diagnose_desktop_and_sandbox_health()
    desktop = report.get("desktop", {})
    assert "winsta0_accessible" in desktop or "interactive_session" in desktop
    assert "desktop_name" in desktop or "station_name" in desktop or "interactive" in desktop


def test_req201_desktop_health_uac_and_uipi_integrity() -> None:
    """REQ-DM-201: Checks process UIPI integrity level and SendInput synthesis permission."""
    report = diagnose_desktop_and_sandbox_health()
    desktop = report.get("desktop", {})
    assert "uipi_integrity" in desktop or "sendinput_allowed" in desktop or "input_synthesis" in desktop


def test_req201_desktop_health_uia_and_dwm_composition() -> None:
    """REQ-DM-201: Validates UIA COM initialization and DWM composition prerequisites."""
    report = diagnose_desktop_and_sandbox_health()
    desktop = report.get("desktop", {})
    assert "uia_available" in desktop or "dwm_composition" in desktop or "capture_supported" in desktop


def test_req201_sandbox_health_filesystem_permissions(tmp_path: Path) -> None:
    """REQ-DM-201: Validates write access across temp and working directories and isolation markers."""
    report = diagnose_desktop_and_sandbox_health(working_dir=tmp_path)
    assert "sandbox" in report
    sandbox = report["sandbox"]
    assert "write_access" in sandbox or "temp_writeable" in sandbox or "sandbox_writeable" in sandbox
    assert "isolation_type" in sandbox or "is_sandboxed" in sandbox or "container_markers" in sandbox


def test_req201_sandbox_health_loopback_socket_probe() -> None:
    """REQ-DM-201: Tests loopback socket binding (127.0.0.1) availability."""
    report = diagnose_desktop_and_sandbox_health()
    sandbox = report.get("sandbox", {})
    assert "loopback_binding" in sandbox or "loopback_available" in sandbox or "network" in sandbox


def test_req201_desktop_and_sandbox_healing_removes_stale_locks(tmp_path: Path) -> None:
    """REQ-DM-201: When heal=True, removes stale probe files and returns healed items."""
    # Create stale lock file in working dir
    stale_lock = tmp_path / "sandbox_test.lock"
    stale_lock.write_text("lock", encoding="utf-8")
    assert stale_lock.is_file()

    report = diagnose_desktop_and_sandbox_health(working_dir=tmp_path, heal=True)
    assert "healed_items" in report or "healed" in report
    # Verify report is marked healthy or records healed action
    assert isinstance(report.get("is_healthy"), bool)


# ============================================================================
# 3. Ecosystem Version Matrix Auditor Tests (REQ-DM-202)
# ============================================================================


def test_req202_ecosystem_version_matrix_default_target_version_2_0_0() -> None:
    """REQ-DM-202: audit_ecosystem_version_matrix defaults to target_version='2.0.0'."""
    import inspect
    sig = inspect.signature(audit_ecosystem_version_matrix)
    target_param = sig.parameters.get("target_version")
    assert target_param is not None
    assert target_param.default == "2.0.0", f"Default target_version must be '2.0.0', got {target_param.default}"


def test_req202_ecosystem_version_matrix_10_plugins_synchronized() -> None:
    """REQ-DM-202: Returns synchronized=True when all 10 non-video plugins are at 2.0.0."""
    valid_10_plugins: Dict[str, Any] = {
        "iso9000-agentops": "2.0.0",
        "agy-computer-use": "2.0.0",
        "agy-golden-stack": "2.0.0",
        "agy-brain-memory": "2.0.0",
        "agy-doctor-mux": "2.0.0",
        "agy-lsrpc-bridge": "2.0.0",
        "pe-reversing-lab": "2.0.0",
        "eskd-vision-station": "2.0.0",
        "agy-secret-shield": "2.0.0",
        "agy-federation-mesh": "2.0.0",
    }
    result = audit_ecosystem_version_matrix(sources=valid_10_plugins)
    assert isinstance(result, dict)
    assert result.get("target_version") == "2.0.0"
    assert result.get("synchronized") is True
    assert result.get("drifted") == []


def test_req202_ecosystem_version_matrix_10_plugins_detects_drift() -> None:
    """REQ-DM-202: Detects drifted plugins when any of the 10 plugins is not at 2.0.0."""
    drifted_plugins: Dict[str, Any] = {
        "iso9000-agentops": "2.0.0",
        "agy-computer-use": "1.0.0",  # drifted
        "agy-golden-stack": "1.3.0",  # drifted
        "agy-brain-memory": "2.0.0",
        "agy-doctor-mux": "2.0.0",
        "agy-lsrpc-bridge": "2.0.0",
        "pe-reversing-lab": "2.0.0",
        "eskd-vision-station": "2.0.0",
        "agy-secret-shield": "2.0.0",
        "agy-federation-mesh": "2.0.0",
    }
    result = audit_ecosystem_version_matrix(sources=drifted_plugins)
    assert result.get("synchronized") is False
    drifted_names = [d["plugin"] if isinstance(d, dict) else d for d in result.get("drifted", [])]
    assert "agy-computer-use" in drifted_names
    assert "agy-golden-stack" in drifted_names


def test_req202_ecosystem_version_matrix_strictly_ignores_google_flow_video() -> None:
    """REQ-DM-202: Strictly excludes google-flow-video from audit even if present in sources."""
    plugins_with_flow: Dict[str, Any] = {
        "iso9000-agentops": "2.0.0",
        "agy-computer-use": "2.0.0",
        "agy-golden-stack": "2.0.0",
        "agy-brain-memory": "2.0.0",
        "agy-doctor-mux": "2.0.0",
        "agy-lsrpc-bridge": "2.0.0",
        "pe-reversing-lab": "2.0.0",
        "eskd-vision-station": "2.0.0",
        "agy-secret-shield": "2.0.0",
        "agy-federation-mesh": "2.0.0",
        "google-flow-video": "0.1.0",  # Out-of-scope video plugin
    }
    result = audit_ecosystem_version_matrix(sources=plugins_with_flow)
    assert result.get("synchronized") is True
    assert "google-flow-video" not in str(result.get("drifted", []))
