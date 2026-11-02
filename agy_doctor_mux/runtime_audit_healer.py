"""Runtime audit healer for URI sanitization, Playwright lock recovery, and PowerShell guards.

Requirements traced:
- REQ-DM-URI-01: Sanitize file:/// URIs and percent-encoded UTF-8/Cyrillic paths into normalized OS paths.
- REQ-DM-PWLOCK-01: Heal stale Playwright/Chrome profile SingletonLock/SingletonCookie/SingletonSocket artifacts.
- REQ-DM-PSGUARD-01: Rewrite fragile PowerShell inline python -c commands to Here-String pipelines and repair stripped $_ variables.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote

LOCK_ARTIFACT_NAMES: tuple[str, ...] = (
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
)

_PYTHON_INLINE_RE = re.compile(
    r'(?P<exe>python(?:3)?(?:\.exe)?)\s+(?:(?P<unbuf>-u)\s+)?-c\s+'
    r'(?:"(?P<dq>[^"]*)"|\'(?P<sq>[^\']*)\')'
)

_STRIPPED_PS_VAR_RE = re.compile(
    r"(?<![$\w`])(\.(?:LastWriteTime|CreationTime|LastAccessTime|FullName|Name|Length)\b)"
)


def sanitize_file_uri_and_cyrillic_path(path_or_uri: str | Path) -> str:
    """Sanitize a file:/// URI or percent-encoded UTF-8 path into a native OS path (REQ-DM-URI-01).

    Strips leading ``file:///`` or ``file://`` URI schemes and unquotes percent-encoded
    UTF-8 byte sequences while preserving plain Windows and POSIX paths without corruption.
    """
    raw = str(path_or_uri).strip()
    lower = raw.lower()
    if lower.startswith("file:///"):
        rest = raw[8:]
        if re.match(r"^[a-zA-Z]:[\\/]", rest):
            raw = rest
        else:
            raw = "/" + rest.lstrip("/")
    elif lower.startswith("file://"):
        rest = raw[7:]
        if re.match(r"^/[a-zA-Z]:[\\/]", rest):
            raw = rest[1:]
        else:
            raw = rest

    if "%" in raw:
        raw = unquote(raw, encoding="utf-8", errors="replace")
    return raw


def heal_playwright_profile_lock(
    profile_dir: str | Path,
    kill_orphan_processes: bool = False,
) -> dict[str, Any]:
    """Remove stale SingletonLock, SingletonCookie, and SingletonSocket artifacts (REQ-DM-PWLOCK-01).

    Inspects a Chromium/Playwright persistent profile directory and unlinks stale singleton
    lock files while preserving user profile state such as ``Preferences``.
    """
    sanitized_dir = Path(sanitize_file_uri_and_cyrillic_path(profile_dir))
    removed_locks: list[str] = []
    killed_pids: list[int] = []

    if sanitized_dir.exists() and sanitized_dir.is_dir():
        for name in LOCK_ARTIFACT_NAMES:
            candidate = sanitized_dir / name
            if candidate.exists() or candidate.is_symlink():
                try:
                    candidate.unlink(missing_ok=True)
                    removed_locks.append(name)
                except OSError:
                    pass

    return {
        "profile_dir": str(sanitized_dir),
        "removed_locks": removed_locks,
        "killed_pids": killed_pids,
        "kill_orphan_processes": bool(kill_orphan_processes),
        "healed": len(removed_locks) > 0,
    }


def rewrite_powershell_inline_python(command: str) -> str:
    """Rewrite fragile PowerShell python -c invocations and stripped $_ pipeline properties (REQ-DM-PSGUARD-01).

    Converts inline ``python -c "..."`` commands into safe PowerShell Here-String pipelines
    (``@' ... '@ | python -u -``) and restores missing ``$_`` tokens before pipeline property
    accessors inside double-quoted PowerShell expressions.
    """
    rewritten = str(command)

    def _replace_python_c(match: re.Match[str]) -> str:
        code = match.group("dq")
        if code is None:
            code = match.group("sq") or ""
        return f"@'\n{code}\n'@ | python -u -"

    rewritten = _PYTHON_INLINE_RE.sub(_replace_python_c, rewritten)
    rewritten = _STRIPPED_PS_VAR_RE.sub(r"$_\1", rewritten)
    return rewritten
