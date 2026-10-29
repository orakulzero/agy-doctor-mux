"""Native Antigravity L2 Plugin Bundle Scaffolder, Strict Manifest Validator, Healer, and Flagship Installer."""

from __future__ import annotations

from collections.abc import Sequence
import json
import re
from pathlib import Path
from typing import Any

from agy_doctor_mux.mcp_doctor import audit_mcp_config
from agy_doctor_mux.oss_audit import (
    CYRILLIC_RE,
    FORBIDDEN_TOKENS,
    audit_git_repository,
)

ALLOWED_MANIFEST_KEYS = {
    "name",
    "displayName",
    "description",
    "version",
    "logo",
    "suggestedPrompts",
    "disabled",
}
DISCARDED_OR_UNSUPPORTED_KEYS = {
    "author",
    "homepage",
    "workflows",
    "sidecars",
}
VALID_HOOK_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreInvocation",
    "PostInvocation",
    "UserPromptSubmit",
}
KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VALID_LOGO_EXTS = {".svg", ".png", ".jpg", ".jpeg", ".webp"}

_LOGO_SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128" fill="none">
  <rect x="6" y="6" width="116" height="116" rx="26" fill="#0B1120" stroke="#38BDF8" stroke-width="2.8"/>
  <rect x="12" y="12" width="104" height="104" rx="20" fill="#0F172A" stroke="#06B6D4" stroke-opacity="0.28" stroke-width="1.2"/>
  <circle cx="64" cy="68" r="38" fill="#38BDF8" fill-opacity="0.09"/>
  <path d="M20 68 H108 M64 34 V108" stroke="#94A3B8" stroke-opacity="0.12" stroke-width="1" stroke-dasharray="3 3"/>
  <path d="M18 96 V108 H30 M98 108 H110 V96" stroke="#06B6D4" stroke-opacity="0.65" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="18" y="16" width="38" height="15" rx="4.5" fill="#1E293B" stroke="#38BDF8" stroke-width="1.5"/>
  <text x="37" y="26.5" text-anchor="middle" fill="#38BDF8" font-family="monospace" font-size="8.5" font-weight="bold">P10</text>
  <circle cx="104" cy="23.5" r="7" fill="#10B981" fill-opacity="0.25"/>
  <circle cx="104" cy="23.5" r="3.8" fill="#10B981"/>
  <rect x="26" y="44" width="76" height="50" rx="10" fill="#1E293B" stroke="#38BDF8" stroke-width="2.4"/>
  <path d="M32 69 H46 L52 51 L60 87 L68 57 L74 75 L80 69 H96" stroke="#38BDF8" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="32" cy="69" r="3.5" fill="#38BDF8"/>
  <circle cx="96" cy="69" r="3.5" fill="#10B981"/>
  <path d="M58 35 H70 M64 29 V41" stroke="#10B981" stroke-width="3" stroke-linecap="round"/>
</svg>
"""

_MIT_LICENSE_TEXT = """MIT License

Copyright (c) 2026 orakulzero

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_GITIGNORE_TEXT = """.supergraph/
.agents-learning/
.monitor/
.agents/teamwork/
__pycache__/
*.py[cod]
.pytest_cache/
dist/
build/
*.egg-info/
*.db
*.key
.env
.env.*
"""


def _title_from_kebab(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-") if part)


def _to_kebab(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", raw.strip().lower()).strip("-")
    return s or "plugin"


def scaffold_native_plugin(
    target_dir: Path | str,
    name: str,
    display_name: str = "",
    description: str = "",
    version: str = "1.0.0",
    include_mcp: bool = True,
    include_hooks: bool = True,
    include_oss_gates: bool = True,
    suggested_prompts: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Scaffold a complete, official-schema-compliant Antigravity L2 native plugin bundle."""
    root = Path(target_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    created_files: list[str] = []

    disp = display_name.strip() or _title_from_kebab(name)
    desc = description.strip() or f"Native Antigravity L2 plugin bundle for {disp}."
    prompts = (
        list(suggested_prompts)[:3]
        if suggested_prompts
        else [
            f"Run {name} diagnostics on this workspace",
            f"Audit and verify {name} configuration",
            f"Check {name} operational status",
        ]
    )

    # 1. Root plugin.json (official 7-field schema)
    manifest: dict[str, Any] = {
        "name": name,
        "displayName": disp,
        "description": desc,
        "version": version,
        "logo": "assets/logo.svg",
        "suggestedPrompts": prompts,
    }
    manifest_path = root / "plugin.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    created_files.append(str(manifest_path))

    # 2. High-contrast 128x128 SVG logo with 10% margin baked in
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    logo_path = assets_dir / "logo.svg"
    logo_path.write_text(_LOGO_SVG_TEMPLATE, encoding="utf-8")
    created_files.append(str(logo_path))

    # 3. MCP configuration (prefixed with plugin name, <=64 char composite tool names, timeout_ms=15000)
    if include_mcp:
        mcp_cfg = {
            "mcpServers": {
                f"{name}-mcp": {
                    "command": "python",
                    "args": ["-W", "ignore::RuntimeWarning", "-m", "agy_doctor_mux.mcp_server"],
                    "timeout_ms": 15000,
                    "tools": [
                        "diagnose",
                        "heal",
                        "audit",
                    ],
                }
            }
        }
        mcp_path = root / "mcp_config.json"
        mcp_path.write_text(json.dumps(mcp_cfg, indent=2), encoding="utf-8")
        created_files.append(str(mcp_path))

    # 4. Hooks configuration (wired to single-process multiplexer + 5-Gate OSS pre-release check)
    if include_hooks:
        hooks_cfg = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": ".*",
                        "command": "python -W ignore::RuntimeWarning -m agy_doctor_mux.cli mux-dispatch --event PreToolUse",
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": ".*",
                        "command": "python -W ignore::RuntimeWarning -m agy_doctor_mux.cli mux-dispatch --event PostToolUse",
                    }
                ],
                "Stop": [
                    {
                        "matcher": ".*",
                        "command": "python -W ignore::RuntimeWarning -m agy_doctor_mux.cli mux-dispatch --event Stop",
                    }
                ],
            }
        }
        hooks_path = root / "hooks.json"
        hooks_path.write_text(json.dumps(hooks_cfg, indent=2), encoding="utf-8")
        created_files.append(str(hooks_path))

    # 5. Skill (skills/<name>/SKILL.md)
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n"
        f"# {disp} Skill (`{name}`)\n\n"
        f"Use this skill to execute `{name}` workflows, diagnostics, and automated verification.\n",
        encoding="utf-8",
    )
    created_files.append(str(skill_md))

    # 6. Specialized Subagent (agents/<name>-agent.md)
    agents_dir = root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agents_dir / f"{name}-agent.md"
    agent_md.write_text(
        f"---\nname: {name}-agent\ndescription: Specialized autonomous agent for {disp}.\n---\n\n"
        f"# {disp} Agent\n\n"
        f"Execute `{name}` verification and remediation tasks with deterministic evidence output.\n",
        encoding="utf-8",
    )
    created_files.append(str(agent_md))

    # 7. Rules (rules/AGENTS.md — plain Markdown, NO YAML frontmatter at top!)
    rules_dir = root / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_md = rules_dir / "AGENTS.md"
    rules_md.write_text(
        f"# {disp} Operational Rules\n\n"
        f"1. Maintain 100% English-only source, documentation, and commit messages.\n"
        f"2. Enforce dynamic relative paths and never commit personal credentials or ephemeral directories.\n"
        f"3. Route lifecycle hooks through the single-process `agy-doctor-mux` dispatcher.\n",
        encoding="utf-8",
    )
    created_files.append(str(rules_md))

    # 8. README.md
    readme_path = root / "README.md"
    readme_path.write_text(
        f"# {disp} (`{name}`)\n\n{desc}\n\n"
        f"## Bundled Components\n\n"
        f"- `plugin.json`: Native Antigravity L2 Plugin Manifest\n"
        f"- `skills/{name}/SKILL.md`: Specialized Skill\n"
        f"- `agents/{name}-agent.md`: Autonomous Subagent\n"
        f"- `rules/AGENTS.md`: Plain-Markdown Workspace Rules\n"
        f"- `hooks.json` & `mcp_config.json`: Multiplexed Hooks & Prefixed MCP Server\n",
        encoding="utf-8",
    )
    created_files.append(str(readme_path))

    # 9. OSS Release Gates (LICENSE, .gitignore, .github/workflows/ci.yml)
    if include_oss_gates:
        lic_path = root / "LICENSE"
        lic_path.write_text(_MIT_LICENSE_TEXT, encoding="utf-8")
        created_files.append(str(lic_path))

        gi_path = root / ".gitignore"
        gi_path.write_text(_GITIGNORE_TEXT, encoding="utf-8")
        created_files.append(str(gi_path))

        wf_dir = root / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        ci_path = wf_dir / "ci.yml"
        ci_path.write_text(
            "name: Antigravity Plugin CI\n\n"
            "on:\n  push:\n    branches: [ main ]\n  pull_request:\n    branches: [ main ]\n\n"
            "jobs:\n  validate:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n"
            "      - run: pip install agy-doctor-mux\n"
            "      - run: agy-doctor-mux validate-plugin --plugin-dir .\n",
            encoding="utf-8",
        )
        created_files.append(str(ci_path))

    return {
        "name": name,
        "target_dir": str(root),
        "created_files": created_files,
    }


def validate_native_plugin_bundle(
    plugin_dir: Path | str, check_oss_gates: bool = True
) -> dict[str, Any]:
    """Validate an Antigravity L2 plugin bundle against the official 7-field schema and 5 OSS Gates."""
    root = Path(plugin_dir).resolve()
    errors: list[str] = []
    oss_compliant = True

    manifest_path = root / "plugin.json"
    if not manifest_path.is_file():
        alt_manifest = root / ".antigravity-plugin" / "plugin.json"
        if alt_manifest.is_file():
            manifest_path = alt_manifest
        else:
            return {
                "valid": False,
                "oss_compliant": False,
                "errors": ["Missing root plugin.json manifest"],
                "components": {},
            }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "valid": False,
            "oss_compliant": False,
            "errors": [f"Invalid JSON in plugin.json: {exc}"],
            "components": {},
        }

    # 1. Check unknown or silently discarded keys (author, homepage, workflows, sidecars)
    extra_keys = set(manifest.keys()) - ALLOWED_MANIFEST_KEYS
    bad_keys = extra_keys | (set(manifest.keys()) & DISCARDED_OR_UNSUPPORTED_KEYS)
    if bad_keys:
        errors.append(
            f"Unsupported or silently discarded field(s) in plugin.json: {sorted(bad_keys)}"
        )

    # 2. Check kebab-case name
    plugin_name = manifest.get("name")
    if not isinstance(plugin_name, str) or not KEBAB_RE.match(plugin_name):
        errors.append(
            f"Plugin 'name' ({plugin_name!r}) must be lowercase kebab-case matching {KEBAB_RE.pattern}."
        )
        plugin_name_str = "unknown-plugin"
    else:
        plugin_name_str = plugin_name

    # 3. Check logo (relative path only, valid extension, file exists)
    logo = manifest.get("logo")
    if logo is not None:
        if not isinstance(logo, str) or not logo.strip():
            errors.append("Field 'logo' must be a non-empty relative path string.")
        elif (
            logo.startswith(("http://", "https://", "/", "\\"))
            or Path(logo).is_absolute()
        ):
            errors.append(
                f"Field 'logo' ({logo!r}) must be a relative path inside the plugin; remote URLs and absolute paths are forbidden."
            )
        else:
            logo_file = root / logo
            if logo_file.suffix.lower() not in VALID_LOGO_EXTS:
                errors.append(
                    f"Field 'logo' ({logo!r}) has unsupported extension; allowed: {sorted(VALID_LOGO_EXTS)}."
                )
            elif not logo_file.is_file():
                errors.append(f"Field 'logo' references missing file: {logo}")

    # 4. Check suggestedPrompts (max 3 non-empty strings)
    prompts = manifest.get("suggestedPrompts")
    if prompts is not None:
        if (
            not isinstance(prompts, list)
            or len(prompts) > 3
            or any(not isinstance(p, str) or not p.strip() for p in prompts)
        ):
            errors.append(
                "Field 'suggestedPrompts' must be a list of at most 3 non-empty strings."
            )

    # 5. Check hooks.json (must have top-level "hooks" dict; custom wrapper keys drop plugin in LS!)
    hooks_path = root / "hooks.json"
    has_hooks = hooks_path.is_file()
    if has_hooks:
        try:
            hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
            if not isinstance(hooks_data, dict) or not isinstance(
                hooks_data.get("hooks"), dict
            ):
                errors.append(
                    "hooks.json must contain a top-level 'hooks' object; custom wrapper keys cause Antigravity Language Server to drop the plugin."
                )
        except Exception as exc:
            errors.append(f"Invalid hooks.json: {exc}")

    # 6. Check mcp_config.json (prefix + <64-char composite names + timeout_ms)
    mcp_path = root / "mcp_config.json"
    has_mcp = mcp_path.is_file()
    if has_mcp:
        try:
            mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
            mcp_audit = audit_mcp_config(mcp_data, auto_fix=False)
            if not mcp_audit["valid"]:
                for v in mcp_audit["violations"]:
                    errors.append(f"MCP config violation: {v}")
            for srv_name in (mcp_data.get("mcpServers") or {}).keys():
                if not str(srv_name).startswith(plugin_name_str):
                    errors.append(
                        f"MCP server '{srv_name}' must be prefixed with plugin name '{plugin_name_str}'."
                    )
        except Exception as exc:
            errors.append(f"Invalid mcp_config.json: {exc}")

    # 7. Check rules/AGENTS.md (must NOT start with YAML frontmatter '---')
    rules_path = root / "rules" / "AGENTS.md"
    has_rules = rules_path.is_file()
    if has_rules:
        rules_text = rules_path.read_text(encoding="utf-8", errors="replace")
        if rules_text.lstrip().startswith("---"):
            errors.append(
                "rules/AGENTS.md must be plain markdown without YAML frontmatter ('---')."
            )

    # 8. Check 5 OSS Release Gates across all plugin files
    if check_oss_gates:
        lic_file = root / "LICENSE"
        if not lic_file.is_file():
            errors.append("Missing LICENSE file required by OSS Gate 5.")
            oss_compliant = False
        else:
            lic_txt = lic_file.read_text(encoding="utf-8", errors="replace")
            if "MIT License" not in lic_txt or "orakulzero" not in lic_txt:
                errors.append("LICENSE must be MIT License attributed to orakulzero.")
                oss_compliant = False

        if not (root / ".gitignore").is_file():
            errors.append("Missing .gitignore file required by OSS Gate 4.")
            oss_compliant = False

        for fpath in root.rglob("*"):
            if not fpath.is_file() or ".git" in fpath.parts:
                continue
            try:
                raw = fpath.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:8192]:
                continue
            txt = raw.decode("utf-8", errors="replace")
            rel_name = fpath.relative_to(root).as_posix()
            if CYRILLIC_RE.search(txt):
                errors.append(f"Plugin file '{rel_name}' contains Cyrillic characters.")
                oss_compliant = False
            low = txt.lower()
            for pat in FORBIDDEN_TOKENS:
                if pat in low:
                    errors.append(
                        f"Plugin file '{rel_name}' contains forbidden personal/drive path."
                    )
                    oss_compliant = False
                    break

        if (root / ".git").exists():
            git_rep = audit_git_repository(root)
            if not git_rep["passed"]:
                oss_compliant = False
                errors.extend(git_rep["violations"])

    components = {
        "skills": [
            p.parent.name
            for p in (root / "skills").glob("*/SKILL.md")
            if (root / "skills").is_dir()
        ],
        "agents": [
            p.stem
            for p in (root / "agents").glob("*.md")
            if (root / "agents").is_dir()
        ],
        "rules": has_rules,
        "hooks": has_hooks,
        "mcp": has_mcp,
    }

    return {
        "valid": len(errors) == 0,
        "oss_compliant": oss_compliant,
        "errors": errors,
        "components": components,
    }


def heal_plugin_bundle(plugin_dir: Path | str) -> dict[str, Any]:
    """Repair malformed plugin.json, hooks.json, mcp_config.json, and rules/AGENTS.md in place."""
    root = Path(plugin_dir).resolve()
    actions: list[str] = []

    manifest_path = root / "plugin.json"
    if not manifest_path.is_file():
        alt = root / ".antigravity-plugin" / "plugin.json"
        if alt.is_file():
            manifest_path = alt

    plugin_name = _to_kebab(root.name)
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        orig_manifest = dict(manifest)

        # Strip unsupported / silently discarded fields
        cleaned: dict[str, Any] = {
            k: v for k, v in manifest.items() if k in ALLOWED_MANIFEST_KEYS
        }
        raw_name = str(cleaned.get("name") or root.name)
        plugin_name = raw_name if KEBAB_RE.match(raw_name) else _to_kebab(raw_name)
        cleaned["name"] = plugin_name
        cleaned.setdefault("displayName", _title_from_kebab(plugin_name))
        cleaned.setdefault(
            "description", f"Native Antigravity L2 plugin bundle for {cleaned['displayName']}."
        )
        cleaned.setdefault("version", "1.0.0")

        logo_val = cleaned.get("logo")
        needs_local_logo = (
            not isinstance(logo_val, str)
            or not logo_val.strip()
            or logo_val.startswith(("http://", "https://", "/", "\\"))
            or Path(logo_val).is_absolute()
            or not (root / logo_val).is_file()
        )
        if needs_local_logo:
            assets_dir = root / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (assets_dir / "logo.svg").write_text(_LOGO_SVG_TEMPLATE, encoding="utf-8")
            cleaned["logo"] = "assets/logo.svg"
            actions.append("generated local assets/logo.svg and updated plugin.json logo path")

        prompts = cleaned.get("suggestedPrompts")
        if isinstance(prompts, list):
            cleaned["suggestedPrompts"] = [
                str(p).strip() for p in prompts if isinstance(p, str) and str(p).strip()
            ][:3]

        if cleaned != orig_manifest:
            manifest_path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
            actions.append("sanitized plugin.json to official 7-field schema")

    # Repair hooks.json (extract lifecycle event arrays into top-level {"hooks": ...})
    hooks_path = root / "hooks.json"
    if hooks_path.is_file():
        try:
            hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
            if isinstance(hooks_data, dict) and not isinstance(
                hooks_data.get("hooks"), dict
            ):
                merged_events: dict[str, list[Any]] = {}
                for k, v in hooks_data.items():
                    if k in VALID_HOOK_EVENTS and isinstance(v, list):
                        merged_events.setdefault(k, []).extend(v)
                    elif isinstance(v, dict):
                        for ek, ev in v.items():
                            if ek in VALID_HOOK_EVENTS and isinstance(ev, list):
                                merged_events.setdefault(ek, []).extend(ev)
                healed_hooks = {"hooks": merged_events}
                hooks_path.write_text(
                    json.dumps(healed_hooks, indent=2), encoding="utf-8"
                )
                actions.append("rewrote hooks.json with top-level 'hooks' object")
        except Exception:
            pass

    # Repair mcp_config.json (inject timeout_ms, sanitize names, prefix servers)
    mcp_path = root / "mcp_config.json"
    if mcp_path.is_file():
        try:
            mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
            fixed_res = audit_mcp_config(mcp_data, auto_fix=True)
            fixed_cfg = fixed_res["config"]
            servers = fixed_cfg.get("mcpServers") or {}
            prefixed_servers: dict[str, Any] = {}
            for srv_name, srv_body in servers.items():
                s_str = str(srv_name)
                if not s_str.startswith(plugin_name):
                    s_str = f"{plugin_name}-{s_str}"
                prefixed_servers[s_str] = srv_body
            fixed_cfg["mcpServers"] = prefixed_servers
            if fixed_cfg != mcp_data:
                mcp_path.write_text(json.dumps(fixed_cfg, indent=2), encoding="utf-8")
                actions.append("repaired mcp_config.json timeouts, tool names, and server prefixes")
        except Exception:
            pass

    # Repair rules/AGENTS.md (strip YAML frontmatter)
    rules_path = root / "rules" / "AGENTS.md"
    if rules_path.is_file():
        txt = rules_path.read_text(encoding="utf-8", errors="replace")
        if txt.lstrip().startswith("---"):
            parts = txt.lstrip().split("---", 2)
            if len(parts) == 3:
                rules_path.write_text(parts[2].lstrip(), encoding="utf-8")
                actions.append("stripped YAML frontmatter from rules/AGENTS.md")

    return {
        "plugin_dir": str(root),
        "healed": len(actions) > 0,
        "actions": actions,
    }


def heal_all_plugins(plugins_root: Path | str) -> dict[str, Any]:
    """Scan all plugin subdirectories in plugins_root and repair malformed bundles."""
    root = Path(plugins_root).resolve()
    results: list[dict[str, Any]] = []
    healed_count = 0

    if root.is_dir():
        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            if (sub / "plugin.json").is_file() or (
                sub / ".antigravity-plugin" / "plugin.json"
            ).is_file():
                res = heal_plugin_bundle(sub)
                results.append(res)
                if res["healed"]:
                    healed_count += 1

    return {
        "plugins_root": str(root),
        "healed_count": healed_count,
        "results": results,
    }


def install_flagship_plugins(plugins_root: Path | str) -> dict[str, Any]:
    """Scaffold and install the 3 flagship L2 native Antigravity plugins into plugins_root."""
    root = Path(plugins_root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    flagship_specs = [
        (
            "agy-doctor-mux",
            "Antigravity Runtime Doctor & Hook Mux",
            "Single-process hook multiplexer, Git worktree deadlock healer, and MCP <64-char schema shield.",
            [
                "Diagnose and heal workspace worktree deadlocks",
                "Audit MCP server tool names and inject timeouts",
                "Benchmark single-process hook multiplexer speedup",
            ],
        ),
        (
            "iso9000-agentops",
            "ISO 9001:2015 Agile V Quality Pipeline",
            "6-Echelon AgentOps QMS with HMAC Gate 1 seals, Self-Grading Bias guard, and Planarian rollback.",
            [
                "Initialize an L3 ISO 9001:2015 frozen baseline",
                "Verify independent test oracle and build W3C PROV-DM audit chain",
                "Run Echelon 6 CAPA ExpeL consolidation",
            ],
        ),
        (
            "git-oss-publisher",
            "5-Gate Git Open-Source Release Auditor",
            "Automated open-source release auditor enforcing English-only history, dynamic paths, and MIT licensing.",
            [
                "Audit repository against all 5 ISO 9001:2015 OSS release gates",
                "Scan tracked files and git log for Cyrillic or personal paths",
                "Prepare clean semantic release tags",
            ],
        ),
    ]

    installed: list[str] = []
    for name, disp, desc, prompts in flagship_specs:
        target = root / name
        scaffold_native_plugin(
            target_dir=target,
            name=name,
            display_name=disp,
            description=desc,
            version="1.3.0",
            include_mcp=True,
            include_hooks=True,
            include_oss_gates=True,
            suggested_prompts=prompts,
        )
        installed.append(name)

    return {
        "plugins_root": str(root),
        "installed": installed,
    }
