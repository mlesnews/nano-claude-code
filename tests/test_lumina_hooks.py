"""Tests for Lumina Hook Engine integration. [C-000003916]"""
from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Mock HookResult that matches the real interface ──────────────────────

@dataclass
class MockHookResult:
    allowed: bool = True
    exit_code: int = 0
    additional_context: list = field(default_factory=list)
    system_messages: list = field(default_factory=list)
    block_reason: str | None = None
    stderr: str = ""
    raw_outputs: list = field(default_factory=list)


class TestLuminaHooksGracefulDegradation(unittest.TestCase):
    """Test that hooks degrade gracefully when engine is absent."""

    def test_noop_result_when_engine_missing(self):
        """All fire_* functions should return a permissive result when engine is None."""
        import lumina_hooks
        original_engine = lumina_hooks._ENGINE
        try:
            lumina_hooks._ENGINE = None
            result = lumina_hooks.fire_pre_tool_use("Bash", {"command": "ls"})
            self.assertTrue(result.allowed)
            self.assertEqual(result.additional_context, [])
        finally:
            lumina_hooks._ENGINE = original_engine

    def test_all_fire_functions_return_without_engine(self):
        """Every public fire_* function should work with engine=None."""
        import lumina_hooks
        original_engine = lumina_hooks._ENGINE
        try:
            lumina_hooks._ENGINE = None

            # Session events
            r = lumina_hooks.fire_session_start({"model": "test"}, MagicMock())
            self.assertTrue(r.allowed)

            r = lumina_hooks.fire_session_stop(MagicMock())
            self.assertTrue(r.allowed)

            # User prompt
            r = lumina_hooks.fire_user_prompt_submit("hello", MagicMock())
            self.assertTrue(r.allowed)

            # Tool events
            r = lumina_hooks.fire_pre_tool_use("Bash", {"command": "ls"})
            self.assertTrue(r.allowed)

            r = lumina_hooks.fire_post_tool_use("Bash", "output")
            self.assertTrue(r.allowed)

            # Compact events
            r = lumina_hooks.fire_pre_compact([])
            self.assertTrue(r.allowed)

            r = lumina_hooks.fire_post_compact("summary")
            self.assertTrue(r.allowed)

            # Subagent events
            r = lumina_hooks.fire_subagent_start(None, 0)
            self.assertTrue(r.allowed)

            r = lumina_hooks.fire_subagent_stop("task1", "done", "completed")
            self.assertTrue(r.allowed)
        finally:
            lumina_hooks._ENGINE = original_engine


class TestLuminaHooksWithMockEngine(unittest.TestCase):
    """Test hooks with a mock engine that returns controlled results."""

    def setUp(self):
        import lumina_hooks
        self._original_engine = lumina_hooks._ENGINE
        self._original_hr = lumina_hooks._HookResult
        self.mock_engine = MagicMock()
        lumina_hooks._ENGINE = self.mock_engine
        lumina_hooks._HookResult = MockHookResult

    def tearDown(self):
        import lumina_hooks
        lumina_hooks._ENGINE = self._original_engine
        lumina_hooks._HookResult = self._original_hr

    def test_pre_tool_use_fires_with_correct_event(self):
        """PreToolUse should call engine.fire with correct event and tool."""
        self.mock_engine.fire.return_value = MockHookResult()
        import lumina_hooks
        lumina_hooks.fire_pre_tool_use("Bash", {"command": "rm -rf /"})
        self.mock_engine.fire.assert_called_once()
        call_args = self.mock_engine.fire.call_args
        self.assertEqual(call_args[0][0], "PreToolUse")
        self.assertEqual(call_args[1].get("tool", call_args[0][1] if len(call_args[0]) > 1 else ""), "Bash")

    def test_blocking_pre_tool_use(self):
        """A hook that blocks should return allowed=False."""
        blocked = MockHookResult(allowed=False, block_reason="dangerous command")
        self.mock_engine.fire.return_value = blocked
        import lumina_hooks
        result = lumina_hooks.fire_pre_tool_use("Bash", {"command": "rm -rf /"})
        self.assertFalse(result.allowed)
        self.assertEqual(result.block_reason, "dangerous command")

    def test_post_tool_use_with_additional_context(self):
        """PostToolUse should pass through additional_context from hooks."""
        with_ctx = MockHookResult(additional_context=["extra info from hook"])
        self.mock_engine.fire.return_value = with_ctx
        import lumina_hooks
        result = lumina_hooks.fire_post_tool_use("Read", "file contents")
        self.assertEqual(result.additional_context, ["extra info from hook"])

    def test_engine_exception_returns_permissive(self):
        """If engine.fire raises, we should get a permissive fallback result."""
        self.mock_engine.fire.side_effect = RuntimeError("hook script crashed")
        import lumina_hooks
        result = lumina_hooks.fire_pre_tool_use("Bash", {"command": "ls"})
        self.assertTrue(result.allowed)

    def test_session_start_passes_config(self):
        """SessionStart should include model in context."""
        self.mock_engine.fire.return_value = MockHookResult()
        import lumina_hooks
        state = MagicMock()
        state.turn_count = 0
        lumina_hooks.fire_session_start({"model": "claude-opus-4-6"}, state)
        call_args = self.mock_engine.fire.call_args
        context = call_args[1].get("context", call_args[0][2] if len(call_args[0]) > 2 else {})
        self.assertIn("model", context)

    def test_subagent_start_fires(self):
        """SubAgentStart should fire with agent info."""
        self.mock_engine.fire.return_value = MockHookResult()
        import lumina_hooks

        agent_def = MagicMock()
        agent_def.name = "coder"
        agent_def.model = "claude-haiku-4-5-20251001"

        lumina_hooks.fire_subagent_start(agent_def, depth=1)
        self.mock_engine.fire.assert_called_once()
        call_args = self.mock_engine.fire.call_args
        self.assertEqual(call_args[0][0], "SubAgentStart")


class TestIsEngineAvailable(unittest.TestCase):
    """Test the is_engine_available convenience function."""

    def test_returns_bool(self):
        import lumina_hooks
        result = lumina_hooks.is_engine_available()
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
