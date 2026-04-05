"""Lumina Hook Engine integration layer for nano-claude-code. [C-000003916]

Provides wrapper functions for all 9 hook events. Gracefully degrades to
no-op when lumina_hook_engine is not installed or a hook raises an exception.
"""
from __future__ import annotations

import sys
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("lumina_hooks")

# ── Attempt to import HookEngine from lumina-hook-engine ─────────────────
_ENGINE = None
_HookResult = None

try:
    # Try local hook_engine first (inline implementation), then external package
    try:
        from hook_engine import HookEngine, HookResult as _HR
    except ImportError:
        import importlib
        try:
            importlib.import_module("lumina_hook_engine")
        except ImportError:
            import os
            _HOOK_ENGINE_PATH = os.path.join(
                os.environ.get("PROJECT_ROOT", os.path.expanduser("~/my_projects")),
                "lumina-hook-engine",
            )
            if _HOOK_ENGINE_PATH not in sys.path:
                sys.path.insert(0, _HOOK_ENGINE_PATH)
        from lumina_hook_engine import HookEngine, HookResult as _HR

    _ENGINE = HookEngine()
    _HookResult = _HR
    logger.debug("Hook engine loaded successfully (%d events configured)",
                 len(_ENGINE.events))
except Exception as exc:
    logger.debug("Hook engine not available: %s — hooks disabled", exc)


# ── Fallback HookResult when engine is absent ────────────────────────────

@dataclass
class _FallbackHookResult:
    """Minimal stand-in for HookResult when engine is not installed."""
    allowed: bool = True
    exit_code: int = 0
    additional_context: list = field(default_factory=list)
    system_messages: list = field(default_factory=list)
    block_reason: str | None = None
    stderr: str = ""
    raw_outputs: list = field(default_factory=list)


def _noop_result():
    """Return a permissive no-op result."""
    if _HookResult is not None:
        return _HookResult()
    return _FallbackHookResult()


def _safe_fire(event: str, tool: str = "", context: dict | None = None):
    """Fire a hook event with full exception safety.

    Returns a HookResult (real or fallback). Never raises.
    """
    if _ENGINE is None:
        return _noop_result()
    try:
        result = _ENGINE.fire(event, tool=tool, context=context or {})
        logger.debug("Hook %s (tool=%s) -> allowed=%s ctx=%d sys=%d",
                     event, tool, result.allowed,
                     len(result.additional_context), len(result.system_messages))
        return result
    except Exception as exc:
        logger.warning("Hook %s raised %s: %s — returning permissive default",
                       event, type(exc).__name__, exc)
        return _noop_result()


# ── Public API: one wrapper per event ────────────────────────────────────

def fire_session_start(config: dict, state) -> object:
    """Fire SessionStart event at REPL/CLI startup."""
    return _safe_fire("SessionStart", context={
        "model": config.get("model", ""),
        "permission_mode": config.get("permission_mode", "auto"),
        "turn_count": getattr(state, "turn_count", 0),
    })


def fire_session_stop(state, cost: dict | None = None) -> object:
    """Fire SessionStop event at session exit."""
    return _safe_fire("SessionStop", context={
        "turn_count": getattr(state, "turn_count", 0),
        "total_input_tokens": getattr(state, "total_input_tokens", 0),
        "total_output_tokens": getattr(state, "total_output_tokens", 0),
        **(cost or {}),
    })


def fire_user_prompt_submit(prompt: str, state) -> object:
    """Fire UserPromptSubmit before processing a user message."""
    return _safe_fire("UserPromptSubmit", context={
        "prompt": prompt,
        "turn_count": getattr(state, "turn_count", 0),
        "message_count": len(getattr(state, "messages", [])),
    })


def fire_pre_tool_use(tool_name: str, params: dict) -> object:
    """Fire PreToolUse before executing a tool. Check result.allowed."""
    return _safe_fire("PreToolUse", tool=tool_name, context=params)


def fire_post_tool_use(tool_name: str, result: str) -> object:
    """Fire PostToolUse after a tool completes."""
    return _safe_fire("PostToolUse", tool=tool_name, context={
        "result_length": len(result) if isinstance(result, str) else 0,
        "result_preview": (result[:500] if isinstance(result, str) else ""),
    })


def fire_pre_compact(messages: list) -> object:
    """Fire PreCompact before context compaction."""
    return _safe_fire("PreCompact", context={
        "message_count": len(messages),
    })


def fire_post_compact(summary: str) -> object:
    """Fire PostCompact after context compaction."""
    return _safe_fire("PostCompact", context={
        "summary_length": len(summary) if isinstance(summary, str) else 0,
    })


def fire_subagent_start(agent_def, depth: int) -> object:
    """Fire SubAgentStart before spawning a sub-agent thread."""
    return _safe_fire("SubAgentStart", context={
        "agent_name": getattr(agent_def, "name", ""),
        "agent_model": getattr(agent_def, "model", ""),
        "depth": depth,
    })


def fire_subagent_stop(task_id: str, result: str | None, status: str) -> object:
    """Fire SubAgentStop after a sub-agent thread completes."""
    return _safe_fire("SubAgentStop", context={
        "task_id": task_id,
        "status": status,
        "result_length": len(result) if isinstance(result, str) else 0,
    })


# ── Convenience ──────────────────────────────────────────────────────────

def is_engine_available() -> bool:
    """Return True if the hook engine loaded successfully."""
    return _ENGINE is not None
