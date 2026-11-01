"""SSE Stream Chunking Shield for Tool Execution.

Traceability:
- REQ-DM-CHUNK-01: Pre-tool SSE stream EOF chunking shield enforcing <=180 line write limits.

Quality Framework: ISO 9001:2015, ISO/IEC 42001:2023, Agile V.
Hygiene: 100% English-only (0 Cyrillic characters).
"""

from __future__ import annotations

from typing import Any, Dict, List
from agy_doctor_mux.mux import HookEntry


def validate_write_chunk_limit(payload: str, max_lines: int = 180) -> Dict[str, Any]:
    """Validate that payload line count does not exceed max_lines (REQ-DM-CHUNK-01)."""
    if not isinstance(payload, str):
        payload = str(payload)
    lines = payload.splitlines()
    line_count = len(lines)
    if line_count > max_lines:
        return {
            "is_valid": False,
            "line_count": line_count,
            "max_lines": max_lines,
            "error": f"Payload line count {line_count} exceeds maximum allowed limit of {max_lines} lines (REQ-DM-CHUNK-01)",
        }
    return {
        "is_valid": True,
        "line_count": line_count,
        "max_lines": max_lines,
        "error": None,
    }


def chunk_content_into_blocks(content: str, block_size: int = 180) -> List[str]:
    """Split multi-line text into sequential blocks of up to block_size lines (REQ-DM-CHUNK-01)."""
    lines = content.splitlines(keepends=True)
    if not lines:
        return [""]
    blocks: List[str] = []
    for i in range(0, len(lines), block_size):
        blocks.append("".join(lines[i : i + block_size]))
    return blocks


def pre_tool_write_guard(payload: Dict[str, Any], max_lines: int = 180) -> Dict[str, Any]:
    """Evaluate PreToolUse payload for write operations exceeding max_lines (REQ-DM-CHUNK-01)."""
    tool_name = str(payload.get("tool_name", "")).lower()
    tool_args = payload.get("tool_args", {})
    if not isinstance(tool_args, dict):
        return {"decision": "allow"}

    write_tool_markers = ("write", "edit", "append", "replace", "patch", "create")
    is_write = any(m in tool_name for m in write_tool_markers) and "read" not in tool_name
    if not is_write:
        return {"decision": "allow"}

    candidate_keys = ("CodeContent", "ReplacementContent", "content", "text", "TargetContent")
    for key in candidate_keys:
        if key in tool_args and isinstance(tool_args[key], str):
            val_res = validate_write_chunk_limit(tool_args[key], max_lines=max_lines)
            if not val_res["is_valid"]:
                return {
                    "decision": "deny",
                    "reason": (
                        f"Write payload ({val_res['line_count']} lines) exceeds "
                        f"max chunk limit of {max_lines} lines (REQ-DM-CHUNK-01)"
                    ),
                    "line_count": val_res["line_count"],
                    "max_lines": max_lines,
                }
    return {"decision": "allow"}


def create_chunk_shield_hook(max_lines: int = 180, priority: int = 10) -> HookEntry:
    """Create a PreToolUse HookEntry registering the chunk shield (REQ-DM-CHUNK-01)."""

    def _handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        return pre_tool_write_guard(payload, max_lines=max_lines)

    return HookEntry(
        name="sse_chunk_shield",
        event="PreToolUse",
        priority=priority,
        handler=_handler,
    )


class SSEChunkShield:
    """Object-oriented wrapper for SSE chunking shield policies (REQ-DM-CHUNK-01)."""

    def __init__(self, max_lines: int = 180) -> None:
        self.max_lines = max_lines

    def validate(self, content: str) -> Dict[str, Any]:
        return validate_write_chunk_limit(content, max_lines=self.max_lines)

    def chunk(self, content: str) -> List[str]:
        return chunk_content_into_blocks(content, block_size=self.max_lines)

    def guard(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return pre_tool_write_guard(payload, max_lines=self.max_lines)

    def create_hook(self, priority: int = 10) -> HookEntry:
        return create_chunk_shield_hook(max_lines=self.max_lines, priority=priority)
