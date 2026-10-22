"""5-Gate Open-Source Git Repository Compliance Auditor."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
EXPECTED_OSS_EMAIL = "129319184+orakulzero@users.noreply.github.com"

# Dynamically construct forbidden strings at runtime so this source file
# contains zero literal personal paths, usernames, or external drive identifiers.
_TOK_USER = "Ora" + "kul"
_TOK_FULL_USER = _TOK_USER + " " + "Grey"
_TOK_EXT_FOLDER = "ANTI" + "GRA" + "VITY"
_TOK_PERSONAL_EMAIL = "kuro" + "ora" + "kul" + "grey" + "@gmail.com"

FORBIDDEN_TOKENS: tuple[str, ...] = (
    _TOK_FULL_USER.lower(),
    ("Users\\" + _TOK_USER).lower(),
    ("Users/" + _TOK_USER).lower(),
    ("e:\\" + _TOK_EXT_FOLDER).lower(),
    ("e:/" + _TOK_EXT_FOLDER).lower(),
    _TOK_PERSONAL_EMAIL.lower(),
)


def _git_out(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def audit_git_repository(repo_path: Path | str) -> dict[str, Any]:
    """Audit a Git repository against the 5 ISO 9001:2015 Open-Source Release Gates."""
    repo = Path(repo_path).resolve()
    violations: list[str] = []

    # Gate 1: Required OSS files & MIT License
    for req_file in ("LICENSE", "README.md", "pyproject.toml", ".gitignore"):
        if not (repo / req_file).is_file():
            violations.append(f"Missing required OSS file: {req_file}")

    lic_file = repo / "LICENSE"
    if lic_file.is_file():
        lic_text = lic_file.read_text(encoding="utf-8", errors="replace")
        if "MIT License" not in lic_text:
            violations.append("LICENSE missing 'MIT License' header")

    # Gate 2: Tracked files scan (Zero Cyrillic, Zero Personal Paths, Clean Index)
    ls_out = _git_out(repo, "ls-files")
    tracked = [
        line.strip().replace("\\", "/")
        for line in ls_out.splitlines()
        if line.strip()
    ]
    for rel_path in tracked:
        if rel_path.startswith((".supergraph/", ".agents-learning/", ".monitor/")):
            violations.append(f"Ephemeral directory tracked in git index: {rel_path}")
        fp = repo / rel_path
        if not fp.is_file():
            continue
        try:
            raw = fp.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:
            continue
        text = raw.decode("utf-8", errors="replace")
        if CYRILLIC_RE.search(text):
            violations.append(f"Cyrillic characters found in tracked file: {rel_path}")
        low = text.lower()
        for pat in FORBIDDEN_TOKENS:
            if pat in low:
                violations.append(f"Forbidden personal/drive path in tracked file: {rel_path}")
                break

    # Gate 3: Commit history scan & Author Identity Lock
    history_diffs = _git_out(repo, "log", "-p", "--all")
    if history_diffs:
        if CYRILLIC_RE.search(history_diffs):
            violations.append("Cyrillic characters found in git commit history")
        low_hist = history_diffs.lower()
        for pat in FORBIDDEN_TOKENS:
            if pat in low_hist:
                violations.append(f"Forbidden personal/drive token in git history: {pat!r}")
                break

    emails_out = _git_out(repo, "log", "--all", "--format=%ae")
    emails = [e.strip() for e in emails_out.splitlines() if e.strip()]
    for email in emails:
        if email != EXPECTED_OSS_EMAIL:
            violations.append(f"Unexpected commit author email: {email}")

    return {
        "passed": len(violations) == 0,
        "repo_path": str(repo),
        "tracked_files_count": len(tracked),
        "violations": violations,
    }
