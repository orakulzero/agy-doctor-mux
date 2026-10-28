"""Unit and integration test suite for agy-doctor-mux v1.3.0:
Deterministic MCP Schema Description Compactor (>=35% token reduction, 100% constraint preservation)
and Ecosystem Version Matrix Auditor with target_version="1.3.0".
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Safe dynamic import resolution for Agile V TDD test collection
try:
    from agy_doctor_mux import (
        __version__,
        audit_ecosystem_version_matrix,
        compact_mcp_schema_descriptions,
    )
except ImportError:
    try:
        from agy_doctor_mux.mcp_doctor import compact_mcp_schema_descriptions
        from agy_doctor_mux.sync import audit_ecosystem_version_matrix
        from agy_doctor_mux import __version__
    except ImportError:
        compact_mcp_schema_descriptions = None
        audit_ecosystem_version_matrix = None
        __version__ = "1.2.0"


@pytest.fixture
def verbose_k8s_mcp_tool_schema() -> Dict[str, Any]:
    """Verbose MCP tool schema modeling realistic enterprise Kubernetes tool declarations."""
    return {
        "name": "audit_kubernetes_cluster_health",
        "description": (
            "This tool allows you to perform an in-depth, comprehensive operational audit "
            "and health check of all Kubernetes cluster nodes, evaluating pod density, memory "
            "saturation, filesystem pressure, and network interface error rates. "
            "Please note that running this diagnostic may take up to thirty seconds during high cluster load."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_identifier": {
                    "type": "string",
                    "description": (
                        "A required string specifying the unique cluster identifier or fully "
                        "qualified domain name of the production Kubernetes control plane that you wish to inspect."
                    ),
                },
                "audit_mode": {
                    "type": "string",
                    "enum": ["shallow", "deep", "forensic"],
                    "default": "deep",
                    "description": (
                        "An optional string parameter indicating the specific diagnostic inspection depth "
                        "that the health audit scanner should execute across target worker nodes."
                    ),
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 300,
                    "default": 30,
                    "description": (
                        "The optional integer representing the maximum network timeout threshold in seconds "
                        "before the health checker terminates unreachable RPC probes."
                    ),
                },
                "target_namespaces": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                    "description": (
                        "An optional array of strings denoting which isolated namespaces should be included "
                        "within the perimeter of the comprehensive node health assessment."
                    ),
                },
                "diagnostics_config": {
                    "type": "object",
                    "properties": {
                        "capture_kernel_dmesg": {
                            "type": "boolean",
                            "default": True,
                            "description": (
                                "A boolean flag indicating whether raw host kernel dmesg ring buffer logs "
                                "should be scraped and analyzed for hardware exceptions."
                            ),
                        },
                    },
                    "required": ["capture_kernel_dmesg"],
                },
            },
            "required": ["cluster_identifier"],
        },
    }


# ============================================================================
# 1. compact_mcp_schema_descriptions Tests
# ============================================================================


def test_v1_3_mcp_compactor_reduction_pct_exceeds_35_percent(
    verbose_k8s_mcp_tool_schema: Dict[str, Any],
) -> None:
    """Verify that verbose MCP tool schemas achieve >= 35% token reduction."""
    assert (
        compact_mcp_schema_descriptions is not None
    ), "compact_mcp_schema_descriptions must be implemented and exported"

    compacted, telemetry = compact_mcp_schema_descriptions(verbose_k8s_mcp_tool_schema)

    assert telemetry["reduction_pct"] >= 35.0, (
        f"Token reduction {telemetry['reduction_pct']}% did not meet the >= 35.0% threshold"
    )
    assert telemetry["original_chars"] > telemetry["compacted_chars"]
    assert telemetry["tokens_saved"] > 0
    assert telemetry["compacted_tokens"] < telemetry["original_tokens"]

    # Tool description must be stripped of boilerplate preamble
    assert "This tool allows you to" not in compacted["description"]
    assert len(compacted["description"]) < len(verbose_k8s_mcp_tool_schema["description"])


def test_v1_3_mcp_compactor_preserves_100_pct_json_schema_constraints(
    verbose_k8s_mcp_tool_schema: Dict[str, Any],
) -> None:
    """Verify 100% of JSON Schema constraints, types, enums, defaults, and bounds are preserved."""
    assert (
        compact_mcp_schema_descriptions is not None
    ), "compact_mcp_schema_descriptions must be implemented and exported"

    orig_copy = copy.deepcopy(verbose_k8s_mcp_tool_schema)
    compacted, _ = compact_mcp_schema_descriptions(verbose_k8s_mcp_tool_schema)

    # 1. Tool name and root schema structure
    assert compacted["name"] == orig_copy["name"]
    assert compacted["inputSchema"]["type"] == orig_copy["inputSchema"]["type"]
    assert compacted["inputSchema"]["required"] == orig_copy["inputSchema"]["required"]

    # 2. Check each property constraint
    orig_props = orig_copy["inputSchema"]["properties"]
    comp_props = compacted["inputSchema"]["properties"]
    assert set(orig_props.keys()) == set(comp_props.keys())

    for prop_name, orig_spec in orig_props.items():
        comp_spec = comp_props[prop_name]
        assert comp_spec["type"] == orig_spec["type"]

        if "enum" in orig_spec:
            assert comp_spec["enum"] == orig_spec["enum"]
        if "default" in orig_spec:
            assert comp_spec["default"] == orig_spec["default"]
        if "minimum" in orig_spec:
            assert comp_spec["minimum"] == orig_spec["minimum"]
        if "maximum" in orig_spec:
            assert comp_spec["maximum"] == orig_spec["maximum"]
        if "items" in orig_spec:
            assert comp_spec["items"] == orig_spec["items"]

    # 3. Check nested object constraints
    orig_nested = orig_props["diagnostics_config"]
    comp_nested = comp_props["diagnostics_config"]
    assert comp_nested["required"] == orig_nested["required"]
    assert comp_nested["properties"]["capture_kernel_dmesg"]["default"] is True


def test_v1_3_mcp_compactor_idempotency(
    verbose_k8s_mcp_tool_schema: Dict[str, Any],
) -> None:
    """Verify that compacting an already compacted schema is strictly idempotent."""
    assert (
        compact_mcp_schema_descriptions is not None
    ), "compact_mcp_schema_descriptions must be implemented and exported"

    compacted_1, _ = compact_mcp_schema_descriptions(verbose_k8s_mcp_tool_schema)
    compacted_2, telemetry_2 = compact_mcp_schema_descriptions(compacted_1)

    assert json.dumps(compacted_1, sort_keys=True) == json.dumps(compacted_2, sort_keys=True)
    assert telemetry_2["reduction_pct"] == 0.0
    assert telemetry_2["tokens_saved"] == 0


def test_v1_3_mcp_compactor_deeply_nested_schemas() -> None:
    """Verify recursive compaction cleans up descriptions inside deeply nested schemas."""
    assert (
        compact_mcp_schema_descriptions is not None
    ), "compact_mcp_schema_descriptions must be implemented and exported"

    nested_schema = {
        "name": "configure_security_policy",
        "description": "This tool is used to configure multi-tenant cluster policy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ingress_layer": {
                    "type": "object",
                    "description": "An optional object representing the ingress controller configuration.",
                    "properties": {
                        "tls_profile": {
                            "type": "object",
                            "description": "The required object specifying strict TLS cipher suites.",
                            "properties": {
                                "min_version": {
                                    "type": "string",
                                    "description": "A required string denoting minimum acceptable TLS version.",
                                    "default": "TLSv1.3",
                                },
                            },
                            "required": ["min_version"],
                        },
                    },
                },
            },
        },
    }

    compacted, _ = compact_mcp_schema_descriptions(nested_schema)
    leaf_desc = (
        compacted["inputSchema"]["properties"]["ingress_layer"]["properties"]["tls_profile"][
            "properties"
        ]["min_version"]["description"]
    )
    assert "A required string denoting" not in leaf_desc
    assert "minimum acceptable TLS version" in leaf_desc.lower() or "acceptable tls" in leaf_desc.lower()


def test_v1_3_mcp_compactor_multi_tool_server_manifest() -> None:
    """Verify multi-tool server manifests ({'tools': [...]}) are compacted in a single call."""
    assert (
        compact_mcp_schema_descriptions is not None
    ), "compact_mcp_schema_descriptions must be implemented and exported"

    manifest = {
        "server": "cluster-doctor",
        "tools": [
            {
                "name": "check_memory",
                "description": "This tool allows you to measure memory pressure across pods.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "check_storage",
                "description": "This tool is designed to diagnose filesystem volume latency.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ],
    }

    compacted, telemetry = compact_mcp_schema_descriptions(manifest)
    assert len(compacted["tools"]) == 2
    assert "This tool allows you to" not in compacted["tools"][0]["description"]
    assert "This tool is designed to" not in compacted["tools"][1]["description"]
    assert telemetry["tokens_saved"] > 0


def test_v1_3_mcp_compactor_preserves_concise_descriptions() -> None:
    """Verify already concise descriptions are left intact without truncation or corruption."""
    assert (
        compact_mcp_schema_descriptions is not None
    ), "compact_mcp_schema_descriptions must be implemented and exported"

    concise = {
        "name": "ping",
        "description": "Ping node.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Target hostname.",
                },
            },
            "required": ["host"],
        },
    }

    compacted, telemetry = compact_mcp_schema_descriptions(concise)
    assert compacted["description"] == "Ping node."
    assert compacted["inputSchema"]["properties"]["host"]["description"] == "Target hostname."
    assert telemetry["reduction_pct"] == 0.0


def test_v1_3_mcp_compactor_empty_and_minimal_schemas() -> None:
    """Verify empty dictionaries and minimal schemas are handled safely."""
    assert (
        compact_mcp_schema_descriptions is not None
    ), "compact_mcp_schema_descriptions must be implemented and exported"

    compacted_empty, telemetry_empty = compact_mcp_schema_descriptions({})
    assert compacted_empty == {}
    assert telemetry_empty["reduction_pct"] == 0.0

    no_props = {"type": "object", "properties": {}}
    compacted_no_props, _ = compact_mcp_schema_descriptions(no_props)
    assert compacted_no_props == no_props


# ============================================================================
# 2. Ecosystem Version Matrix v1.3.0 Tests
# ============================================================================


def test_v1_3_audit_ecosystem_version_matrix_default_target_1_3_0(tmp_path: Path) -> None:
    """Verify audit_ecosystem_version_matrix defaults to target_version='1.3.0'."""
    assert (
        audit_ecosystem_version_matrix is not None
    ), "audit_ecosystem_version_matrix must be implemented and exported"

    # Set up mock plugin directories
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    p1 = plugins_dir / "alpha-plugin"
    p1.mkdir(parents=True, exist_ok=True)
    (p1 / "plugin.json").write_text(
        json.dumps({"name": "alpha-plugin", "version": "1.3.0"}), encoding="utf-8"
    )

    report = audit_ecosystem_version_matrix(
        source_roots={}, plugins_dir=plugins_dir
    )
    assert report["target_version"] == "1.3.0"


def test_v1_3_audit_ecosystem_version_matrix_detects_1_2_0_drift(tmp_path: Path) -> None:
    """Verify plugins remaining on v1.2.0 are flagged as drifted against target v1.3.0."""
    assert (
        audit_ecosystem_version_matrix is not None
    ), "audit_ecosystem_version_matrix must be implemented and exported"

    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Plugin on 1.3.0
    p_synced = plugins_dir / "synced-plugin"
    p_synced.mkdir(parents=True, exist_ok=True)
    (p_synced / "plugin.json").write_text(
        json.dumps({"name": "synced-plugin", "version": "1.3.0"}), encoding="utf-8"
    )

    # Plugin on 1.2.0
    p_drift = plugins_dir / "lagging-plugin"
    p_drift.mkdir(parents=True, exist_ok=True)
    (p_drift / "plugin.json").write_text(
        json.dumps({"name": "lagging-plugin", "version": "1.2.0"}), encoding="utf-8"
    )

    report = audit_ecosystem_version_matrix(
        source_roots={}, plugins_dir=plugins_dir, target_version="1.3.0"
    )
    assert report["synchronized"] is False
    assert "lagging-plugin" in report["drifted"]
    assert "synced-plugin" not in report["drifted"]


def test_v1_3_doctor_mux_exports_and_version() -> None:
    """Verify v1.3.0 version bump and compact_mcp_schema_descriptions export."""
    assert __version__ in ("1.3.0", "2.0.0"), "Package __version__ must be bumped to 2.0.0"
    import agy_doctor_mux

    assert hasattr(
        agy_doctor_mux, "compact_mcp_schema_descriptions"
    ), "compact_mcp_schema_descriptions must be exported in agy_doctor_mux"
    assert (
        "compact_mcp_schema_descriptions" in agy_doctor_mux.__all__
    ), "compact_mcp_schema_descriptions must be listed in __all__"
