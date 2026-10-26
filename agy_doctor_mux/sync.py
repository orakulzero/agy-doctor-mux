"""Cross-Surface Config Synchronizer & Agent Plugins 1.0 Manifest Validator."""

from __future__ import annotations

from collections.abc import Sequence
import json
import re
from pathlib import Path
from typing import Any

PLUGIN_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UNSUPPORTED_MANIFEST_KEYS = {"workflows", "sidecars"}


def validate_plugin_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate an Antigravity Agent Plugins 1.0 manifest dictionary."""
    errors: list[str] = []

    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("Field 'name' must be a non-empty string.")
    elif not PLUGIN_KEBAB_RE.match(name):
        errors.append(
            f"Field 'name' ({name!r}) must be lowercase kebab-case matching {PLUGIN_KEBAB_RE.pattern}."
        )

    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("Field 'version' must be a non-empty semantic version string.")

    for bad_key in sorted(UNSUPPORTED_MANIFEST_KEYS):
        if bad_key in manifest:
            errors.append(
                f"Unsupported key {bad_key!r}: Agent Plugins 1.0 does not bundle workflows or sidecars."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def sync_surfaces(
    workspace_dir: Path | str,
    global_dir: Path | str,
    targets: Sequence[str] = ("antigravity-ide", "agy-cli", "claude-code"),
) -> dict[str, Any]:
    """Synchronize single-process multiplexer hooks across Antigravity IDE, agy CLI, and Claude Code."""
    ws = Path(workspace_dir).resolve()
    glob = Path(global_dir).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    glob.mkdir(parents=True, exist_ok=True)

    target_set = {t.lower().strip() for t in targets}
    written_files: list[str] = []

    mux_hook_spec = {
        "multiplexer": "agy-doctor-mux",
        "version": "1.0.0",
        "priority_order": [
            "P10_context_guard",
            "P20_memory_consolidator",
            "P30_supergraph_dag_gate",
            "P40_code_review_advisor",
            "P50_audit_logger",
        ],
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": ".*",
                    "command": "agy-doctor-mux mux-dispatch --event PreToolUse",
                }
            ],
            "PostToolUse": [
                {
                    "matcher": ".*",
                    "command": "agy-doctor-mux mux-dispatch --event PostToolUse",
                }
            ],
            "Stop": [
                {
                    "matcher": ".*",
                    "command": "agy-doctor-mux mux-dispatch --event Stop",
                }
            ],
        },
    }

    if "antigravity-ide" in target_set or "agy-cli" in target_set:
        agents_dir = ws / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        ws_mux_file = agents_dir / "mux_hooks.json"
        ws_mux_file.write_text(json.dumps(mux_hook_spec, indent=2), encoding="utf-8")
        written_files.append(str(ws_mux_file))

        plugin_root = glob / "plugins" / "agy-doctor-mux"
        hooks_dir = plugin_root / "hooks"
        manifest_dir = plugin_root / ".antigravity-plugin"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        manifest_dir.mkdir(parents=True, exist_ok=True)

        glob_hooks_file = hooks_dir / "hooks.json"
        glob_hooks_file.write_text(json.dumps(mux_hook_spec, indent=2), encoding="utf-8")
        written_files.append(str(glob_hooks_file))

        manifest_file = manifest_dir / "plugin.json"
        manifest_payload = {
            "name": "agy-doctor-mux",
            "version": "1.0.0",
            "description": "Single-process hook multiplexer and worktree/MCP doctor for Antigravity 2.0",
            "hooks": "./hooks/hooks.json",
        }
        manifest_file.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
        written_files.append(str(manifest_file))

    if "claude-code" in target_set:
        claude_dir = ws / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        claude_settings = claude_dir / "settings.json"
        claude_payload = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "agy-doctor-mux mux-dispatch --event PreToolUse",
                            }
                        ],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "agy-doctor-mux mux-dispatch --event PostToolUse",
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "agy-doctor-mux mux-dispatch --event Stop",
                            }
                        ],
                    }
                ],
            }
        }
        claude_settings.write_text(json.dumps(claude_payload, indent=2), encoding="utf-8")
        written_files.append(str(claude_settings))

    return {
        "synced": True,
        "targets": list(targets),
        "written_files": written_files,
    }


def detect_plugin_drift(
    source_roots: Sequence[Path | str],
    plugins_dir: Path | str,
) -> dict[str, Any]:
    """Detect manifest and version drift between source repos and installed plugins."""
    p_dir = Path(plugins_dir).resolve()
    drifted_plugins: list[dict[str, Any]] = []
    missing_in_plugins: list[str] = []
    found_names: set[str] = set()

    for s_root in source_roots:
        root = Path(s_root).resolve()
        if not root.is_dir():
            continue

        manifest_path: Path | None = None
        plugin_name: str = root.name
        source_manifest: dict[str, Any] = {}

        if (root / "plugin.json").is_file():
            manifest_path = root / "plugin.json"
        elif (root / "plugins").is_dir():
            for cand in (root / "plugins").iterdir():
                if cand.is_dir() and (cand / "plugin.json").is_file():
                    manifest_path = cand / "plugin.json"
                    plugin_name = cand.name
                    break

        if manifest_path and manifest_path.is_file():
            try:
                source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugin_name = str(source_manifest.get("name") or plugin_name)
            except Exception:
                pass
        else:
            pyproj = root / "pyproject.toml"
            if pyproj.is_file():
                try:
                    text = pyproj.read_text(encoding="utf-8")
                    m_name = re.search(r'name\s*=\s*["\']([^"\']+)["\']', text)
                    m_ver = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
                    if m_name:
                        plugin_name = m_name.group(1)
                    if m_ver:
                        source_manifest = {"name": plugin_name, "version": m_ver.group(1)}
                except Exception:
                    pass

        found_names.add(plugin_name)
        installed_plugin_dir = p_dir / plugin_name
        installed_manifest_path = installed_plugin_dir / "plugin.json"

        if not installed_manifest_path.is_file():
            missing_in_plugins.append(plugin_name)
            continue

        try:
            installed_manifest = json.loads(installed_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            installed_manifest = {}

        field_diffs: list[str] = []
        source_ver = str(source_manifest.get("version") or "")
        inst_ver = str(installed_manifest.get("version") or "")
        if source_ver and inst_ver and source_ver != inst_ver:
            field_diffs.append("version")

        source_desc = str(source_manifest.get("description") or "")
        inst_desc = str(installed_manifest.get("description") or "")
        if source_desc and inst_desc and source_desc != inst_desc:
            field_diffs.append("description")

        if field_diffs:
            drifted_plugins.append({
                "name": plugin_name,
                "source_version": source_ver,
                "installed_version": inst_ver,
                "field_diffs": field_diffs,
                "source_path": str(manifest_path or root),
                "installed_path": str(installed_manifest_path),
            })

    untracked_in_source: list[str] = []
    if p_dir.is_dir():
        for item in sorted(p_dir.iterdir()):
            if item.is_dir() and item.name not in found_names:
                untracked_in_source.append(item.name)

    return {
        "drift_detected": len(drifted_plugins) > 0 or len(missing_in_plugins) > 0,
        "drifted_plugins": drifted_plugins,
        "missing_in_plugins_dir": missing_in_plugins,
        "untracked_in_source": untracked_in_source,
    }


def reconcile_plugin_drift(
    drift_report: dict[str, Any],
    plugins_dir: Path | str,
    source_roots: Sequence[Path | str],
    auto_sync: bool = True,
) -> dict[str, Any]:
    """Reconcile detected drift by updating installed plugin manifests from source repositories."""
    if not auto_sync:
        return {"reconciled": False, "updated_plugins": []}

    p_dir = Path(plugins_dir).resolve()
    p_dir.mkdir(parents=True, exist_ok=True)
    updated: list[str] = []

    source_manifests: dict[str, tuple[dict[str, Any], Path]] = {}
    for s_root in source_roots:
        root = Path(s_root).resolve()
        if not root.is_dir():
            continue
        manifest_path: Path | None = None
        plugin_name: str = root.name
        if (root / "plugin.json").is_file():
            manifest_path = root / "plugin.json"
        elif (root / "plugins").is_dir():
            for cand in (root / "plugins").iterdir():
                if cand.is_dir() and (cand / "plugin.json").is_file():
                    manifest_path = cand / "plugin.json"
                    plugin_name = cand.name
                    break
        if manifest_path and manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                pname = str(data.get("name") or plugin_name)
                source_manifests[pname] = (data, manifest_path)
            except Exception:
                pass

    drifted = drift_report.get("drifted_plugins") or []
    for item in drifted:
        pname = item.get("name")
        if pname in source_manifests:
            src_data, _ = source_manifests[pname]
            target_manifest = p_dir / pname / "plugin.json"
            if target_manifest.is_file():
                try:
                    target_data = json.loads(target_manifest.read_text(encoding="utf-8"))
                    target_data.update({k: src_data[k] for k in src_data if k in ("version", "description", "suggestedPrompts")})
                    target_manifest.write_text(json.dumps(target_data, indent=2) + "\n", encoding="utf-8")
                    updated.append(pname)
                except Exception:
                    pass

    return {
        "reconciled": len(updated) > 0,
        "updated_plugins": updated,
    }


CORE_ECOSYSTEM_PACKAGES: tuple[str, ...] = (
    "iso9000-agentops",
    "agy-golden-stack",
    "agy-brain-memory",
    "agy-doctor-mux",
    "agy-lsrpc-bridge",
)


def audit_ecosystem_version_matrix(
    source_roots: Sequence[Path | str] | dict[str, Any] | None = None,
    plugins_dir: Path | str | None = None,
    target_version: str = "1.3.0",
) -> dict[str, Any]:
    """Audit version matrix across source packages and installed plugin manifests.

    Compares package versions in pyproject.toml, __version__, and plugin.json
    against target_version (default "1.3.0").
    Default plugins_dir is Path.home() / ".gemini" / "config" / "plugins".
    Ignores google-flow-video.

    Returns:
        target_version: str
        synchronized: bool
        packages: dict mapping package name to version & sync details
        drifted: list of package names with version mismatch
    """
    is_custom_plugins = plugins_dir is not None
    p_dir = Path(plugins_dir).resolve() if is_custom_plugins else (Path.home() / ".gemini" / "config" / "plugins")

    installed_map: dict[str, dict[str, Any]] = {}
    if p_dir.is_dir():
        for child in sorted(p_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name in ("google-flow-video", "flow_video_testbench"):
                continue
            manifest_file = child / "plugin.json"
            if not manifest_file.is_file():
                alt_manifest = child / ".antigravity-plugin" / "plugin.json"
                if alt_manifest.is_file():
                    manifest_file = alt_manifest
                else:
                    continue
            try:
                m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                p_name = str(m_data.get("name") or child.name)
                if p_name in ("google-flow-video", "flow_video_testbench"):
                    continue
                ver_val = m_data.get("version")
                installed_map[p_name] = {
                    "version": str(ver_val) if ver_val is not None else None,
                    "path": str(manifest_file),
                }
            except Exception:
                pass

    source_map: dict[str, dict[str, Any]] = {}
    if source_roots is None:
        # Discover core packages dynamically using relative parent and home directories
        repo_root = Path(__file__).resolve().parent.parent
        search_candidates = [
            repo_root.parent,
            Path.home() / "teamwork_projects",
            repo_root,
            Path.cwd(),
            Path.cwd().parent,
        ]
        raw_sources: dict[str, Path] = {}
        for pkg in CORE_ECOSYSTEM_PACKAGES:
            for base in search_candidates:
                cand = base / pkg if base.name != pkg else base
                if cand.is_dir() and (cand / "pyproject.toml").is_file():
                    raw_sources[pkg] = cand
                    break
    elif isinstance(source_roots, dict):
        raw_sources = source_roots
    else:
        raw_sources = {Path(p).name: Path(p) for p in source_roots}

    for k, v in raw_sources.items():
        if isinstance(v, (str, Path)) and (Path(v).is_dir() or Path(v).is_file()):
            root = Path(v).resolve()
            if root.is_file():
                root = root.parent
            pkg_name = k
            pkg_ver: str | None = None

            pyproj = root / "pyproject.toml"
            if pyproj.is_file():
                try:
                    text = pyproj.read_text(encoding="utf-8")
                    m_name = re.search(r'name\s*=\s*["\']([^"\']+)["\']', text)
                    m_ver = re.search(r'version\s*=\s*["\']([^"\']+)["\']', text)
                    if m_name:
                        pkg_name = m_name.group(1)
                    if m_ver:
                        pkg_ver = m_ver.group(1)
                except Exception:
                    pass

            if not pkg_ver:
                for cand_pj in (root / "plugin.json", root / "plugins" / pkg_name / "plugin.json"):
                    if cand_pj.is_file():
                        try:
                            pj_data = json.loads(cand_pj.read_text(encoding="utf-8"))
                            pkg_name = str(pj_data.get("name") or pkg_name)
                            pkg_ver = str(pj_data.get("version"))
                            break
                        except Exception:
                            pass

            if not pkg_ver:
                for init_file in root.glob("**/__init__.py"):
                    try:
                        text = init_file.read_text(encoding="utf-8")
                        m_ver = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
                        if m_ver:
                            pkg_ver = m_ver.group(1)
                            break
                    except Exception:
                        pass

            source_map[pkg_name] = {
                "version": pkg_ver,
                "path": str(root),
            }
        elif isinstance(v, str):
            source_map[k] = {
                "version": v,
                "path": None,
            }

    if source_roots is not None:
        target_pkgs = set(source_map.keys())
        if is_custom_plugins:
            target_pkgs |= set(installed_map.keys())
    else:
        if is_custom_plugins:
            target_pkgs = set(source_map.keys()) | set(installed_map.keys())
        else:
            target_pkgs = set(CORE_ECOSYSTEM_PACKAGES)

    packages: dict[str, Any] = {}
    drifted: list[str] = []

    for pname in sorted(target_pkgs):
        src_info = source_map.get(pname)
        inst_info = installed_map.get(pname)

        src_ver = src_info.get("version") if src_info else None
        inst_ver = inst_info.get("version") if inst_info else None

        has_drift = False
        if src_info is not None and src_ver != target_version:
            has_drift = True
        if inst_info is not None and inst_ver != target_version:
            has_drift = True
        if src_info is None and inst_info is None:
            has_drift = True

        if has_drift:
            drifted.append(pname)

        packages[pname] = {
            "source_version": src_ver,
            "installed_version": inst_ver,
            "source_path": src_info.get("path") if src_info else None,
            "installed_path": inst_info.get("path") if inst_info else None,
            "synchronized": not has_drift,
        }

    return {
        "target_version": target_version,
        "synchronized": len(drifted) == 0,
        "packages": packages,
        "drifted": drifted,
    }
