from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
VALID_TOOL_RE = re.compile(r"^[a-zA-Z0-9_.\-:]+$")

# Dynamically construct forbidden strings at runtime so this test file itself
# never contains any raw personal path, drive, or email substrings.
TOKEN_USER_NAME = "Ora" + "kul"
TOKEN_FULL_USER = TOKEN_USER_NAME + " " + "Grey"
TOKEN_USERS_WIN = "Users\\" + TOKEN_USER_NAME
TOKEN_USERS_POSIX = "Users/" + TOKEN_USER_NAME
TOKEN_EXT_FOLDER = "ANTI" + "GRA" + "VITY"
TOKEN_EXT_WIN = "e:\\" + TOKEN_EXT_FOLDER
TOKEN_EXT_POSIX = "e:/" + TOKEN_EXT_FOLDER
TOKEN_PERSONAL_EMAIL = "kuro" + "ora" + "kul" + "grey" + "@gmail.com"
EXPECTED_OSS_EMAIL = "129319184+orakulzero@users.noreply.github.com"


def _git_output(*args: str, cwd: Path = REPO_ROOT) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout


def _git_ls_files() -> list[str]:
    out = _git_output("ls-files")
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _iter_tracked_text_files() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for rel_path in _git_ls_files():
        full_path = REPO_ROOT / rel_path
        if not full_path.is_file():
            continue
        try:
            raw = full_path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:
            continue
        items.append((rel_path, raw.decode("utf-8", errors="replace")))
    return items


# ============================================================================
# REQ-001: Single-Process Hook Multiplexer (agy_doctor_mux.mux)
# ============================================================================


def test_req001_mux_ascending_priority_and_fail_fast_short_circuit() -> None:
    from agy_doctor_mux.mux import HookEntry, HookMultiplexer

    mux = HookMultiplexer()
    executed_order: list[int] = []

    for prio in (50, 10, 30, 20, 40):
        mux.register(
            HookEntry(
                name=f"hook_p{prio}",
                event="PreToolUse",
                priority=prio,
                handler=lambda payload, p=prio: (
                    executed_order.append(p) or {"decision": "allow"}
                ),
            )
        )

    res_allow = mux.dispatch("PreToolUse", {"tool_name": "read_file"})
    assert res_allow["decision"] == "allow"
    assert executed_order == [10, 20, 30, 40, 50]

    # Now register a blocking P30 hook on a fresh multiplexer and verify CRIT-01 short-circuit
    mux_block = HookMultiplexer()
    block_order: list[int] = []
    for prio in (50, 10, 30, 20, 40):
        if prio == 30:
            handler = lambda payload, p=prio: (
                block_order.append(p)
                or {"decision": "deny", "reason": "Blocked by SuperGraph"}
            )
        else:
            handler = lambda payload, p=prio: (
                block_order.append(p) or {"decision": "allow"}
            )
        mux_block.register(
            HookEntry(
                name=f"hook_p{prio}",
                event="PreToolUse",
                priority=prio,
                handler=handler,
            )
        )

    res_deny = mux_block.dispatch("PreToolUse", {"tool_name": "write_file"})
    assert res_deny["decision"] == "deny"
    assert res_deny["blocked_by_priority"] == 30
    assert "Blocked by SuperGraph" in res_deny.get("reason", "")
    assert block_order == [10, 20, 30], (
        f"P40 and P50 must be short-circuited on P30 deny, got {block_order}"
    )


def test_req001_mux_deferred_stop_consolidation_and_anti_loop_guard() -> None:
    from agy_doctor_mux.mux import HookEntry, HookMultiplexer

    mux = HookMultiplexer(max_stop_continuations=3)
    events_log: list[str] = []
    gate_should_deny = True

    mux.register(
        HookEntry(
            name="memory_consolidator",
            event="Stop",
            priority=20,
            deferred_until_allow=True,
            handler=lambda payload: (
                events_log.append("consolidated") or {"decision": "allow"}
            ),
        )
    )
    mux.register(
        HookEntry(
            name="dag_stop_gate",
            event="Stop",
            priority=30,
            handler=lambda payload: (
                {"decision": "deny", "reason": "Verification still failing"}
                if gate_should_deny
                else {"decision": "allow"}
            ),
        )
    )

    # First 3 Stop dispatches on session 's1' are denied; deferred P20 must NOT run (CRIT-02)
    for attempt in range(3):
        r = mux.dispatch("Stop", {"session_id": "s1"})
        assert r["decision"] == "deny", f"Attempt {attempt + 1} should deny"
        assert "consolidated" not in events_log, (
            "Deferred memory consolidator must not run while P30 gate denies"
        )

    # 4th consecutive Stop continuation triggers Anti-Loop Guard (HIGH-02)
    r4 = mux.dispatch("Stop", {"session_id": "s1"})
    assert r4["decision"] == "allow"
    assert r4.get("loop_breaker_triggered") is True

    # When P30 gate allows on session 's2', deferred P20 consolidator runs normally
    gate_should_deny = False
    r_ok = mux.dispatch("Stop", {"session_id": "s2"})
    assert r_ok["decision"] == "allow"
    assert "consolidated" in events_log


def test_req001_mux_in_process_latency_speedup_benchmark() -> None:
    from agy_doctor_mux.mux import measure_mux_speedup

    res = measure_mux_speedup(iterations=5)
    assert res["in_process_avg_ms"] < res["subprocess_avg_ms"]
    assert res["speedup_factor"] >= 5.0
    assert res["in_process_avg_ms"] < 40.0


# ============================================================================
# REQ-002: Git Worktree Deadlock & Zombie Subagent Doctor
# ============================================================================


def test_req002_diagnose_and_heal_worktree_deadlock(tmp_path: Path) -> None:
    from agy_doctor_mux.worktree_doctor import diagnose_and_heal_worktrees

    repo = tmp_path / "repo"
    repo.mkdir()
    _git_output("init", cwd=repo)
    _git_output("config", "extensions.worktreeConfig", "true", cwd=repo)
    _git_output("config", "core.repositoryformatversion", "1", cwd=repo)

    index_lock = repo / ".git" / "index.lock"
    index_lock.write_text("stale lock", encoding="utf-8")

    wt_dir = repo / ".git" / "worktrees" / "ghost_subagent"
    wt_dir.mkdir(parents=True)
    (wt_dir / "gitdir").write_text(
        str(tmp_path / "missing_worktree" / ".git"), encoding="utf-8"
    )
    (wt_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    diag = diagnose_and_heal_worktrees(repo, dry_run=True)
    assert diag["has_deadlock_risk"] is True
    assert diag["issues_count"] >= 4
    assert index_lock.exists(), "dry_run=True must not delete index.lock"

    heal = diagnose_and_heal_worktrees(repo, dry_run=False)
    assert heal["healed"] is True
    assert not index_lock.exists(), "index.lock must be removed"
    assert not wt_dir.exists(), "dangling worktree entry must be pruned"

    post_diag = diagnose_and_heal_worktrees(repo, dry_run=True)
    assert post_diag["has_deadlock_risk"] is False
    assert post_diag["issues_count"] == 0


def test_req002_scan_brain_subagents_detects_bigint_and_stalled_tasks(
    tmp_path: Path,
) -> None:
    from agy_doctor_mux.worktree_doctor import scan_brain_subagents

    brain = tmp_path / "brain"
    conv_ok = brain / "conv_healthy" / ".system_generated" / "logs"
    conv_bigint = brain / "conv_bigint" / ".system_generated" / "logs"
    conv_stalled = brain / "conv_stalled" / ".system_generated" / "logs"
    for d in (conv_ok, conv_bigint, conv_stalled):
        d.mkdir(parents=True)

    (conv_ok / "transcript.jsonl").write_text(
        json.dumps({"step_index": 1, "status": "DONE", "content": "Completed task"})
        + "\n",
        encoding="utf-8",
    )
    (conv_bigint / "transcript.jsonl").write_text(
        json.dumps(
            {
                "step_index": 2,
                "status": "ERROR",
                "content": "TypeError: Do not know how to serialize a BigInt",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (conv_stalled / "transcript.jsonl").write_text(
        json.dumps(
            {
                "step_index": 3,
                "status": "IN_PROGRESS",
                "content": "Waiting on tool call",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = scan_brain_subagents(brain)
    assert report["total_conversations"] == 3
    assert "conv_bigint" in report["bigint_crashes"]
    assert "conv_stalled" in report["stalled_subagents"]


# ============================================================================
# REQ-003: MCP Schema Linter, <64-Char Sanitizer & Timeout Injector
# ============================================================================


def test_req003_mcp_doctor_detects_overlong_and_invalid_tool_names() -> None:
    from agy_doctor_mux.mcp_doctor import audit_mcp_config

    cfg = {
        "mcpServers": {
            "enterprise-analytics-production-cluster-v2": {
                "command": "node",
                "args": ["server.js"],
                "tools": [
                    "execute_deep_bigquery_federated_sql_analytical_query",
                    "run$query!now",
                ],
            }
        }
    }
    res = audit_mcp_config(cfg, auto_fix=False)
    assert res["valid"] is False
    violation_types = {v["type"] for v in res["violations"]}
    assert "overlong_identifier" in violation_types
    assert "invalid_characters" in violation_types
    assert "missing_timeout" in violation_types


def test_req003_mcp_doctor_auto_fix_sanitizes_names_and_injects_timeouts() -> None:
    from agy_doctor_mux.mcp_doctor import audit_mcp_config

    cfg = {
        "mcpServers": {
            "enterprise-analytics-production-cluster-v2": {
                "command": "node",
                "args": ["server.js"],
                "tools": [
                    "execute_deep_bigquery_federated_sql_analytical_query",
                    "run$query!now",
                ],
            }
        }
    }
    res = audit_mcp_config(cfg, auto_fix=True)
    assert res["valid"] is True
    assert res["alias_map"], "alias_map must record shortened/sanitized identifiers"

    fixed_servers = res["config"]["mcpServers"]
    for srv_name, srv_cfg in fixed_servers.items():
        assert srv_cfg.get("timeout_ms") == 15000
        for tool_name in srv_cfg.get("tools", []):
            composite = f"mcp_{srv_name}_{tool_name}"
            assert len(composite) <= 64, f"Composite {composite} exceeds 64 chars"
            assert VALID_TOOL_RE.match(composite), (
                f"Composite {composite} fails regex check"
            )


def test_req003_mcp_doctor_alias_map_round_trip() -> None:
    from agy_doctor_mux.mcp_doctor import audit_mcp_config

    cfg = {
        "mcpServers": {
            "extremely-long-mcp-server-identifier-for-cloud-deployment-pipeline": {
                "command": "python",
                "args": ["-m", "server"],
                "tools": [
                    "trigger_asynchronous_multi_region_canary_deployment_verification"
                ],
            }
        }
    }
    res1 = audit_mcp_config(cfg, auto_fix=True)
    assert res1["valid"] is True
    assert len(res1["alias_map"]) >= 1

    # Auditing the already-fixed config must report valid=True with 0 violations
    res2 = audit_mcp_config(res1["config"], auto_fix=False)
    assert res2["valid"] is True
    assert res2["violations"] == []


# ============================================================================
# REQ-004: Cross-Surface Config Synchronizer & Plugin Manifest Validator
# ============================================================================


def test_req004_validate_plugin_manifest_schema_and_unsupported_features() -> None:
    from agy_doctor_mux.sync import validate_plugin_manifest

    bad_manifest = {
        "name": "My Invalid Plugin!",
        "version": "1.0.0",
        "workflows": ["legacy.md"],
        "sidecars": ["daemon.exe"],
    }
    res_bad = validate_plugin_manifest(bad_manifest)
    assert res_bad["valid"] is False
    assert len(res_bad["errors"]) >= 2

    good_manifest = {
        "name": "agy-golden-stack",
        "version": "0.1.0",
        "description": "Agent Plugins 1.0 compliant manifest",
        "hooks": "./hooks/hooks.json",
    }
    res_good = validate_plugin_manifest(good_manifest)
    assert res_good["valid"] is True
    assert res_good["errors"] == []


def test_req004_sync_surfaces_bridges_ide_cli_and_claude_code(tmp_path: Path) -> None:
    from agy_doctor_mux.sync import sync_surfaces

    ws_dir = tmp_path / "ws"
    global_dir = tmp_path / "global"
    ws_dir.mkdir()
    global_dir.mkdir()

    res = sync_surfaces(
        workspace_dir=ws_dir,
        global_dir=global_dir,
        targets=("antigravity-ide", "agy-cli", "claude-code"),
    )
    assert res["synced"] is True
    assert (ws_dir / ".agents" / "mux_hooks.json").is_file()
    assert (global_dir / "plugins" / "agy-doctor-mux" / "hooks" / "hooks.json").is_file()
    assert (ws_dir / ".claude" / "settings.json").is_file()


# ============================================================================
# REQ-005: Unified CLI, MCP Server & 4-Sandbox Benchmark Suite
# ============================================================================


def test_req005_cli_diagnose_heal_and_benchmark(tmp_path: Path) -> None:
    from agy_doctor_mux.cli import run_cli

    repo = tmp_path / "ws"
    repo.mkdir()
    _git_output("init", cwd=repo)
    (repo / ".git" / "index.lock").write_text("stale", encoding="utf-8")

    diag_res = run_cli(["--workspace", str(repo), "diagnose"])
    assert diag_res["worktree"]["has_deadlock_risk"] is True

    heal_res = run_cli(["--workspace", str(repo), "heal"])
    assert heal_res["worktree"]["healed"] is True
    assert not (repo / ".git" / "index.lock").exists()

    bench_res = run_cli(["benchmark"])
    assert bench_res["all_passed"] is True


def test_req005_cli_mux_dispatch_round_trip(tmp_path: Path) -> None:
    from agy_doctor_mux.cli import run_cli

    res = run_cli(
        [
            "--workspace",
            str(tmp_path),
            "mux-dispatch",
            "--event",
            "PreToolUse",
            "--payload",
            json.dumps({"tool_name": "read_file"}),
        ]
    )
    assert res["decision"] in ("allow", "deny")


def test_req005_mcp_server_initialize_and_tools_list(tmp_path: Path) -> None:
    from agy_doctor_mux.mcp_server import handle_mcp_request

    init_resp = handle_mcp_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        workspace=tmp_path,
    )
    assert init_resp["result"]["serverInfo"]["name"] == "agy-doctor-mux-mcp"

    list_resp = handle_mcp_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        workspace=tmp_path,
    )
    tool_names = {t["name"] for t in list_resp["result"]["tools"]}
    expected = {
        "agy_diagnose_workspace",
        "agy_heal_worktree_deadlock",
        "agy_audit_mcp_config",
        "agy_benchmark_hook_mux",
        "agy_sync_surfaces",
    }
    assert expected.issubset(tool_names)


def test_req005_mcp_server_tool_calls(tmp_path: Path) -> None:
    from agy_doctor_mux.mcp_server import handle_mcp_request

    ws = tmp_path / "mcp_ws"
    ws.mkdir()
    _git_output("init", cwd=ws)

    calls = [
        ("agy_diagnose_workspace", {}),
        ("agy_heal_worktree_deadlock", {"dry_run": False}),
        (
            "agy_audit_mcp_config",
            {
                "config": {
                    "mcpServers": {
                        "srv": {"command": "node", "tools": ["ok_tool"]}
                    }
                },
                "auto_fix": True,
            },
        ),
        ("agy_benchmark_hook_mux", {"iterations": 3}),
        ("agy_sync_surfaces", {"global_dir": str(tmp_path / "global")}),
    ]
    for idx, (tool_name, args) in enumerate(calls, start=10):
        resp = handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": idx,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": args},
            },
            workspace=ws,
        )
        assert "result" in resp, f"Missing result for {tool_name}: {resp}"
        assert resp["result"].get("isError", False) is False


def test_req005_benchmark_suite_four_sandboxes_pass() -> None:
    from agy_doctor_mux.benchmarks import run_benchmark_suite

    res = run_benchmark_suite()
    assert res["all_passed"] is True
    assert len(res["sandboxes"]) == 4
    expected_names = {
        "SB1_HookMux_LatencyAndCollisions",
        "SB2_WorktreeDeadlock_And_BigInt_Heal",
        "SB3_MCP_64Char_And_Timeout_Shield",
        "SB4_CrossSurface_Sync_And_PluginAudit",
    }
    actual_names = {sb["name"] for sb in res["sandboxes"]}
    assert actual_names == expected_names
    for sb in res["sandboxes"]:
        assert sb["passed"] is True


# ============================================================================
# REQ-006: Git OSS Publication Readiness (agy_doctor_mux.oss_audit)
# ============================================================================


def test_req006_oss_audit_git_repository_passes() -> None:
    from agy_doctor_mux.oss_audit import audit_git_repository

    report = audit_git_repository(REPO_ROOT)
    assert report["passed"] is True, f"OSS repository audit failed: {report}"


def test_req006_required_oss_files_and_mit_license_tracked() -> None:
    required_files = {
        "LICENSE",
        "README.md",
        "pyproject.toml",
        ".gitignore",
        ".github/workflows/ci.yml",
    }
    tracked = set(_git_ls_files())
    missing = required_files - tracked
    assert not missing, f"Required OSS files missing from git index: {sorted(missing)}"

    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8", errors="replace")
    assert "MIT License" in license_text
    assert "orakulzero" in license_text
    assert "Permission is hereby granted, free of charge" in license_text


def test_req006_zero_cyrillic_in_tracked_files_and_git_history() -> None:
    offenders: list[str] = []
    for rel_path, content in _iter_tracked_text_files():
        matches = CYRILLIC_RE.findall(content)
        if matches:
            offenders.append(f"{rel_path} ({len(matches)} Cyrillic chars)")
    assert not offenders, f"Tracked files contain Cyrillic characters: {offenders}"

    history_diffs = _git_output("log", "-p", "--all")
    assert not bool(CYRILLIC_RE.search(history_diffs)), (
        "Git commit history contains Cyrillic characters"
    )


def test_req006_zero_personal_paths_or_external_drives_in_repo_and_history() -> None:
    forbidden = (
        TOKEN_FULL_USER.lower(),
        TOKEN_USERS_WIN.lower(),
        TOKEN_USERS_POSIX.lower(),
        TOKEN_EXT_WIN.lower(),
        TOKEN_EXT_POSIX.lower(),
        TOKEN_PERSONAL_EMAIL.lower(),
    )
    offenders: list[str] = []
    for rel_path, content in _iter_tracked_text_files():
        lowered = content.lower()
        for pat in forbidden:
            if pat in lowered:
                offenders.append(f"{rel_path} (matched: {pat!r})")
                break
    assert not offenders, f"Tracked files contain forbidden personal/drive paths: {offenders}"

    history_diffs = _git_output("log", "-p", "--all").lower()
    for pat in forbidden:
        assert pat not in history_diffs, (
            f"Git commit history diffs contain forbidden token: {pat!r}"
        )


def test_req006_git_commit_authors_locked_to_orakulzero() -> None:
    emails_out = _git_output("log", "--all", "--format=%ae")
    emails = [line.strip() for line in emails_out.splitlines() if line.strip()]
    assert emails, "Repository must have at least one git commit"
    invalid = [e for e in emails if e != EXPECTED_OSS_EMAIL]
    assert not invalid, (
        f"Git commit authors do not match {EXPECTED_OSS_EMAIL}: {set(invalid)}"
    )
