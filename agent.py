"""Core agent loop: neutral message format, multi-provider streaming."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Generator

from tool_registry import get_tool_schemas
from tools import execute_tool
import tools as _tools_init  # ensure built-in tools are registered on import
from providers import stream, AssistantTurn, TextChunk, ThinkingChunk, detect_provider, get_trading_context
from compaction import maybe_compact
from lumina_hooks import (  # [C-000003916] hook engine integration
    fire_user_prompt_submit, fire_pre_tool_use, fire_post_tool_use,
)

# ── Re-export event types (used by nano_claude.py) ────────────────────────
__all__ = [
    "AgentState", "run",
    "TextChunk", "ThinkingChunk",
    "ToolStart", "ToolEnd", "TurnDone", "PermissionRequest",
]


@dataclass
class AgentState:
    """Mutable session state. messages use the neutral provider-independent format."""
    messages: list = field(default_factory=list)
    total_input_tokens:  int = 0
    total_output_tokens: int = 0
    turn_count: int = 0


@dataclass
class ToolStart:
    name:   str
    inputs: dict

@dataclass
class ToolEnd:
    name:      str
    result:    str
    permitted: bool = True

@dataclass
class TurnDone:
    input_tokens:  int
    output_tokens: int

@dataclass
class PermissionRequest:
    description: str
    granted: bool = False


# ── Agent loop ─────────────────────────────────────────────────────────────

def run(
    user_message: str,
    state: AgentState,
    config: dict,
    system_prompt: str,
    depth: int = 0,
    cancel_check=None,
) -> Generator:
    """
    Multi-turn agent loop (generator).
    Yields: TextChunk | ThinkingChunk | ToolStart | ToolEnd |
            PermissionRequest | TurnDone

    Args:
        depth: sub-agent nesting depth, 0 for top-level
        cancel_check: callable returning True to abort the loop early
    """
    # [C-000003916] Fire UserPromptSubmit hook before processing
    hook_result = fire_user_prompt_submit(user_message, state)
    # Inject any additional context from hooks into the user message
    if hook_result.additional_context:
        user_message += "\n\n" + "\n".join(hook_result.additional_context)

    # Append user turn in neutral format
    state.messages.append({"role": "user", "content": user_message})

    # Inject runtime metadata into config so tools (e.g. Agent) can access it
    config = {**config, "_depth": depth, "_system_prompt": system_prompt}

    while True:
        if cancel_check and cancel_check():
            return
        state.turn_count += 1
        assistant_turn: AssistantTurn | None = None

        # Compact context if approaching window limit
        maybe_compact(state, config)

        # Inject trading context when query looks trading-related
        _effective_system = system_prompt
        if state.turn_count == 1:
            _trading_kw = {"btc", "eth", "sol", "xrp", "ada", "doge", "bnb", "crypto",
                           "trading", "confidence", "market", "portfolio", "position"}
            _last_msg = (state.messages[-1].get("content", "") or "").lower()
            if any(kw in _last_msg for kw in _trading_kw):
                _tc = get_trading_context()
                if _tc:
                    _effective_system = f"{_tc}\n\n{system_prompt}"

        # Stream from provider (auto-detected from model name)
        for event in stream(
            model=config["model"],
            system=_effective_system,
            messages=state.messages,
            tool_schemas=get_tool_schemas(),
            config=config,
        ):
            if isinstance(event, (TextChunk, ThinkingChunk)):
                yield event
            elif isinstance(event, AssistantTurn):
                assistant_turn = event

        if assistant_turn is None:
            break

        # Record assistant turn in neutral format
        state.messages.append({
            "role":       "assistant",
            "content":    assistant_turn.text,
            "tool_calls": assistant_turn.tool_calls,
        })

        state.total_input_tokens  += assistant_turn.in_tokens
        state.total_output_tokens += assistant_turn.out_tokens
        yield TurnDone(assistant_turn.in_tokens, assistant_turn.out_tokens)

        if not assistant_turn.tool_calls:
            break   # No tools → conversation turn complete

        # ── Execute tools ────────────────────────────────────────────────
        for tc in assistant_turn.tool_calls:
            yield ToolStart(tc["name"], tc["input"])

            # [C-000003916] PreToolUse hook — may block execution
            pre_hook = fire_pre_tool_use(tc["name"], tc["input"])
            if not pre_hook.allowed:
                result = f"Blocked by hook: {pre_hook.block_reason or 'policy violation'}"
                yield ToolEnd(tc["name"], result, False)
                state.messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "name":         tc["name"],
                    "content":      result,
                })
                continue

            # Permission gate
            permitted = _check_permission(tc, config)
            if not permitted:
                req = PermissionRequest(description=_permission_desc(tc))
                yield req
                permitted = req.granted

            if not permitted:
                result = "Denied: user rejected this operation"
            else:
                result = execute_tool(
                    tc["name"], tc["input"],
                    permission_mode="accept-all",  # already gate-checked above
                    config=config,
                )

            # [C-000003916] PostToolUse hook — may inject additional context
            post_hook = fire_post_tool_use(tc["name"], result)
            if post_hook.additional_context:
                result += "\n\n[Hook context]\n" + "\n".join(post_hook.additional_context)

            yield ToolEnd(tc["name"], result, permitted)

            # Append tool result in neutral format
            state.messages.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "name":         tc["name"],
                "content":      result,
            })


# ── Helpers ───────────────────────────────────────────────────────────────

def _check_permission(tc: dict, config: dict) -> bool:
    """Return True if operation is auto-approved (no need to ask user)."""
    perm_mode = config.get("permission_mode", "auto")
    if perm_mode == "accept-all":
        return True
    if perm_mode == "manual":
        return False   # always ask

    # "auto" mode: only ask for writes and non-safe bash
    name = tc["name"]
    if name in ("Read", "Glob", "Grep", "WebFetch", "WebSearch"):
        return True
    if name == "Bash":
        from tools import _is_safe_bash
        return _is_safe_bash(tc["input"].get("command", ""))
    return False   # Write, Edit → ask


def _permission_desc(tc: dict) -> str:
    name = tc["name"]
    inp  = tc["input"]
    if name == "Bash":   return f"Run: {inp.get('command', '')}"
    if name == "Write":  return f"Write to: {inp.get('file_path', '')}"
    if name == "Edit":   return f"Edit: {inp.get('file_path', '')}"
    return f"{name}({list(inp.values())[:1]})"
