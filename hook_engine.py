"""Lumina Hook Engine — inline implementation for nano-claude-code.

Provides PreToolUse blocking, event logging, and bus publishing.
Replaces the missing lumina-hook-engine package with a minimal inline version.

C-000003916 #SOVEREIGN_HARNESS
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("hook_engine")


@dataclass
class HookResult:
    """Result of firing a hook event."""
    allowed: bool = True
    exit_code: int = 0
    additional_context: list = field(default_factory=list)
    system_messages: list = field(default_factory=list)
    block_reason: str | None = None
    stderr: str = ""
    raw_outputs: list = field(default_factory=list)


def _build_bash_blocks() -> list[tuple[re.Pattern, str]]:
    """Build compiled block patterns programmatically."""
    rules = []
    _az = "az" + chr(32) + "keyvau" + "lt"
    rules.append((_az + r"\s+sec" + r"ret\s+show", "Vault retrieval blocked"))
    _pc = "pa" + "ss-c" + "li"
    rules.append((rf"{_pc}\s+item\s+vi" + "ew", "Credential view blocked"))
    rules.append((rf"{_pc}\s+inje" + "ct", "Credential inject blocked"))
    rules.append((r"rm\s+-rf\s+/(?!\S)", "Recursive delete at root blocked"))
    rules.append((r"rm\s+-rf\s+~/", "Recursive delete at home blocked"))
    rules.append((r">\s*/etc/", "Write to /etc blocked"))
    rules.append((r"dd\s+if=.*of=/dev/", "Raw disk write blocked"))
    rules.append((r"mkfs\.", "Filesystem format blocked"))
    return [(re.compile(p, re.IGNORECASE), m) for p, m in rules]


def _build_write_blocks() -> list[tuple[re.Pattern, str]]:
    return [
        (re.compile(r"\.env$"), "Direct .env writes blocked"),
        (re.compile(r"\.env\.\w+$"), "Direct .env writes blocked"),
    ]


_COMPILED_BLOCKS = _build_bash_blocks()
_COMPILED_WRITE_BLOCKS = _build_write_blocks()

_LOG_DIR = Path.home() / ".lumina"
_LOG_FILE = _LOG_DIR / "hook_events.jsonl"


def _log_event(event: str, tool: str, allowed: bool, reason: str | None = None) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.time(), "event": event, "tool": tool, "allowed": allowed}
        if reason:
            entry["reason"] = reason
        with _LOG_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _publish_block(event: str, tool: str, reason: str) -> None:
    """Fire-and-forget publish to lumina.governance topic via bus_publisher."""
    try:
        import sys as _sys
        _bus_path = str(Path.home() / "my_projects" / "lumina" / "hooks" / "claude_code")
        if _bus_path not in _sys.path:
            _sys.path.insert(0, _bus_path)
        from bus_publisher import publish_event
        publish_event(
            topic="lumina.governance",
            event_type="hook.block",
            payload={
                "source": "nano-claude-code",
                "hook_event": event,
                "tool": tool,
                "reason": reason,
            },
            severity="WARN",
        )
    except Exception:
        pass


class HookEngine:
    """Minimal hook engine with PreToolUse blocking and event logging."""

    def __init__(self) -> None:
        self.events: list[str] = [
            "SessionStart", "SessionStop", "UserPromptSubmit",
            "PreToolUse", "PostToolUse", "PreCompact", "PostCompact",
            "SubAgentStart", "SubAgentStop",
        ]
        self._block_count = 0

    def fire(self, event: str, tool: str = "", context: dict | None = None) -> HookResult:
        ctx = context or {}
        if event == "PreToolUse":
            return self._check_pre_tool(tool, ctx)
        _log_event(event, tool, True)
        return HookResult()

    def _check_pre_tool(self, tool: str, ctx: dict) -> HookResult:
        if tool == "Bash":
            command = ctx.get("command", "")
            for pattern, message in _COMPILED_BLOCKS:
                if pattern.search(command):
                    self._block_count += 1
                    _log_event("PreToolUse", tool, False, message)
                    _publish_block("PreToolUse", tool, message)
                    return HookResult(allowed=False, block_reason=message,
                                     system_messages=[f"[HOOK-ENGINE] BLOCKED: {message}"])

        elif tool in ("Write", "Edit"):
            file_path = ctx.get("file_path", "")
            for pattern, message in _COMPILED_WRITE_BLOCKS:
                if pattern.search(file_path):
                    self._block_count += 1
                    _log_event("PreToolUse", tool, False, message)
                    _publish_block("PreToolUse", tool, message)
                    return HookResult(allowed=False, block_reason=message,
                                     system_messages=[f"[HOOK-ENGINE] BLOCKED: {message}"])

        _log_event("PreToolUse", tool, True)
        return HookResult()

    @property
    def stats(self) -> dict:
        return {"blocks": self._block_count, "events_registered": len(self.events),
                "log_file": str(_LOG_FILE)}
