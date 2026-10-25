"""Tests for v1.2.0 Dead Loopback Proxy Healer and Ecosystem Version Matrix Auditor."""

from __future__ import annotations

import json
from pathlib import Path
import socket
from typing import Any

import pytest

from agy_doctor_mux.mcp_doctor import diagnose_and_heal_network_env
from agy_doctor_mux.sync import audit_ecosystem_version_matrix


def test_diagnose_and_heal_dead_loopback_proxy_ipv4_and_localhost() -> None:
    test_env = {
        "HTTP_PROXY": "http://127.0.0.1:59999",
        "HTTPS_PROXY": "http://localhost:59998",
        "OTHER_VAR": "keep_me",
    }
    result = diagnose_and_heal_network_env(env=test_env, heal=True, probe_timeout_s=0.1)

    assert result["clean"] is False
    assert result["healed"] is True
    assert result["env_healed"] is True
    assert sorted(result["stale_proxy_vars"]) == ["HTTPS_PROXY", "HTTP_PROXY"]
    assert sorted(result["healed_vars"]) == ["HTTPS_PROXY", "HTTP_PROXY"]
    assert "HTTP_PROXY" not in test_env
    assert "HTTPS_PROXY" not in test_env
    assert test_env["OTHER_VAR"] == "keep_me"
    assert "OTHER_VAR" in result["sanitized_env"]


def test_diagnose_dead_loopback_proxy_no_heal() -> None:
    test_env = {
        "ALL_PROXY": "socks5://127.0.0.1:59997",
    }
    result = diagnose_and_heal_network_env(env=test_env, heal=False, probe_timeout_s=0.1)

    assert result["clean"] is False
    assert result["healed"] is False
    assert result["env_healed"] is False
    assert result["stale_proxy_vars"] == ["ALL_PROXY"]
    assert result["healed_vars"] == []
    assert "ALL_PROXY" in test_env
    assert "ALL_PROXY" in result["sanitized_env"]


def test_diagnose_preserves_live_loopback_proxy() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    try:
        test_env = {
            "HTTP_PROXY": f"http://127.0.0.1:{port}",
        }
        result = diagnose_and_heal_network_env(env=test_env, heal=True, probe_timeout_s=0.2)
        assert result["clean"] is True
        assert result["healed"] is False
        assert result["stale_proxy_vars"] == []
        assert "HTTP_PROXY" in test_env
        assert len(result["probed_proxies"]) == 1
        assert result["probed_proxies"][0]["reachable"] is True
        assert result["probed_proxies"][0]["dead"] is False
    finally:
        server.close()


def test_diagnose_preserves_non_loopback_corporate_proxy() -> None:
    test_env = {
        "HTTP_PROXY": "http://proxy.corp.internal:3128",
        "HTTPS_PROXY": "http://10.200.1.5:8080",
    }
    result = diagnose_and_heal_network_env(env=test_env, heal=True, probe_timeout_s=0.05)

    assert result["clean"] is True
    assert result["healed"] is False
    assert result["stale_proxy_vars"] == []
    assert result["healed_vars"] == []
    assert "HTTP_PROXY" in test_env
    assert "HTTPS_PROXY" in test_env
    for probe in result["probed_proxies"]:
        assert probe["is_loopback"] is False
        assert probe["dead"] is False


def test_diagnose_handles_lowercase_and_mixed_proxy_vars() -> None:
    test_env = {
        "http_proxy": "http://127.0.0.1:59996",
        "https_proxy": "http://127.0.0.1:59995",
        "all_proxy": "http://127.0.0.1:59994",
    }
    result = diagnose_and_heal_network_env(env=test_env, heal=True, probe_timeout_s=0.1)

    assert result["clean"] is False
    assert result["healed"] is True
    assert sorted(result["stale_proxy_vars"]) == ["all_proxy", "http_proxy", "https_proxy"]
    assert sorted(result["healed_vars"]) == ["all_proxy", "http_proxy", "https_proxy"]
    assert len(test_env) == 0


def test_diagnose_handles_ipv6_loopback_and_schemeless_urls() -> None:
    test_env = {
        "HTTP_PROXY": "http://[::1]:59993",
        "ALL_PROXY": "127.0.0.1:59992",
        "HTTPS_PROXY": "",
    }
    result = diagnose_and_heal_network_env(env=test_env, heal=True, probe_timeout_s=0.1)

    assert result["healed"] is True
    assert "HTTP_PROXY" in result["healed_vars"]
    assert "ALL_PROXY" in result["healed_vars"]
    assert "HTTPS_PROXY" not in result["healed_vars"]
    assert "HTTP_PROXY" not in test_env
    assert "ALL_PROXY" not in test_env


def test_audit_ecosystem_version_matrix_synchronized(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    plugins_dir = tmp_path / "installed_plugins"
    sources_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Package A
    pkg_a_src = sources_dir / "pkg-alpha"
    pkg_a_src.mkdir(parents=True, exist_ok=True)
    (pkg_a_src / "pyproject.toml").write_text(
        '[project]\nname = "pkg-alpha"\nversion = "1.2.0"\n', encoding="utf-8"
    )

    pkg_a_inst = plugins_dir / "pkg-alpha"
    pkg_a_inst.mkdir(parents=True, exist_ok=True)
    (pkg_a_inst / "plugin.json").write_text(
        json.dumps({"name": "pkg-alpha", "version": "1.2.0"}), encoding="utf-8"
    )

    # Package B
    pkg_b_src = sources_dir / "pkg-beta"
    pkg_b_src.mkdir(parents=True, exist_ok=True)
    (pkg_b_src / "pyproject.toml").write_text(
        '[project]\nname = "pkg-beta"\nversion = "1.2.0"\n', encoding="utf-8"
    )

    pkg_b_inst = plugins_dir / "pkg-beta"
    pkg_b_inst.mkdir(parents=True, exist_ok=True)
    (pkg_b_inst / "plugin.json").write_text(
        json.dumps({"name": "pkg-beta", "version": "1.2.0"}), encoding="utf-8"
    )

    result = audit_ecosystem_version_matrix(
        source_roots=[pkg_a_src, pkg_b_src],
        plugins_dir=plugins_dir,
        target_version="1.2.0",
    )

    assert result["target_version"] == "1.2.0"
    assert result["synchronized"] is True
    assert result["drifted"] == []
    assert result["packages"]["pkg-alpha"]["synchronized"] is True
    assert result["packages"]["pkg-alpha"]["source_version"] == "1.2.0"
    assert result["packages"]["pkg-alpha"]["installed_version"] == "1.2.0"
    assert result["packages"]["pkg-beta"]["synchronized"] is True


def test_audit_ecosystem_version_matrix_drift_detected(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    plugins_dir = tmp_path / "installed_plugins"
    sources_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Synced package
    pkg_ok_src = sources_dir / "pkg-ok"
    pkg_ok_src.mkdir(parents=True, exist_ok=True)
    (pkg_ok_src / "pyproject.toml").write_text(
        '[project]\nname = "pkg-ok"\nversion = "1.2.0"\n', encoding="utf-8"
    )
    pkg_ok_inst = plugins_dir / "pkg-ok"
    pkg_ok_inst.mkdir(parents=True, exist_ok=True)
    (pkg_ok_inst / "plugin.json").write_text(
        json.dumps({"name": "pkg-ok", "version": "1.2.0"}), encoding="utf-8"
    )

    # Drift in source version
    pkg_drift_s = sources_dir / "pkg-drift-source"
    pkg_drift_s.mkdir(parents=True, exist_ok=True)
    (pkg_drift_s / "pyproject.toml").write_text(
        '[project]\nname = "pkg-drift-source"\nversion = "1.1.0"\n', encoding="utf-8"
    )

    # Drift in installed version
    pkg_drift_i = sources_dir / "pkg-drift-installed"
    pkg_drift_i.mkdir(parents=True, exist_ok=True)
    (pkg_drift_i / "pyproject.toml").write_text(
        '[project]\nname = "pkg-drift-installed"\nversion = "1.2.0"\n', encoding="utf-8"
    )
    pkg_drift_i_inst = plugins_dir / "pkg-drift-installed"
    pkg_drift_i_inst.mkdir(parents=True, exist_ok=True)
    (pkg_drift_i_inst / "plugin.json").write_text(
        json.dumps({"name": "pkg-drift-installed", "version": "1.0.0"}), encoding="utf-8"
    )

    result = audit_ecosystem_version_matrix(
        source_roots=[pkg_ok_src, pkg_drift_s, pkg_drift_i],
        plugins_dir=plugins_dir,
        target_version="1.2.0",
    )

    assert result["synchronized"] is False
    assert "pkg-drift-source" in result["drifted"]
    assert "pkg-drift-installed" in result["drifted"]
    assert "pkg-ok" not in result["drifted"]
    assert result["packages"]["pkg-ok"]["synchronized"] is True
    assert result["packages"]["pkg-drift-source"]["synchronized"] is False
    assert result["packages"]["pkg-drift-installed"]["synchronized"] is False


def test_audit_ecosystem_version_matrix_ignores_google_flow_video(tmp_path: Path) -> None:
    sources_dir = tmp_path / "sources"
    plugins_dir = tmp_path / "installed_plugins"
    sources_dir.mkdir(parents=True, exist_ok=True)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    pkg_src = sources_dir / "core-service"
    pkg_src.mkdir(parents=True, exist_ok=True)
    (pkg_src / "pyproject.toml").write_text(
        '[project]\nname = "core-service"\nversion = "1.2.0"\n', encoding="utf-8"
    )

    # Flow video installed plugin with mismatched version
    flow_inst = plugins_dir / "google-flow-video"
    flow_inst.mkdir(parents=True, exist_ok=True)
    (flow_inst / "plugin.json").write_text(
        json.dumps({"name": "google-flow-video", "version": "0.1.0"}), encoding="utf-8"
    )

    result = audit_ecosystem_version_matrix(
        source_roots=[pkg_src],
        plugins_dir=plugins_dir,
        target_version="1.2.0",
    )

    assert "google-flow-video" not in result["packages"]
    assert "google-flow-video" not in result["drifted"]
    assert result["synchronized"] is True


def test_audit_ecosystem_version_matrix_dict_sources_and_discovery(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    result = audit_ecosystem_version_matrix(
        source_roots={"pkg-x": "1.2.0", "pkg-y": "1.1.0"},
        plugins_dir=plugins_dir,
        target_version="1.2.0",
    )

    assert result["synchronized"] is False
    assert result["drifted"] == ["pkg-y"]
    assert result["packages"]["pkg-x"]["synchronized"] is True
    assert result["packages"]["pkg-y"]["synchronized"] is False
