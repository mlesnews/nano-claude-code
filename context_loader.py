"""Context Loader — inject relay baton + trading state + roadmap into nano-claude.

Provides build_system_context() which returns a <500 token system prompt preamble
combining the latest relay baton, trading state, and top roadmap items.

C-000003916 #SOVEREIGN_HARNESS
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("context_loader")

_BATON_DIR = Path.home() / ".claude" / "data" / "relay" / "batons"
_ROADMAP = Path.home() / ".claude" / "projects" / "-home-mlesn" / "memory" / "roadmap.md"
_CONFIDENCE = (Path.home() / "my_projects" / "lumina" / "docker" / "cluster-ui"
               / "data" / "trading" / "state" / "confidence_aggregator.json")


def load_relay_context() -> str:
    """Read latest relay baton hot_tier (active tasks + directives). Max 200 chars."""
    try:
        if not _BATON_DIR.exists():
            return ""
        batons = sorted(_BATON_DIR.glob("relay_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not batons:
            return ""
        data = json.loads(batons[0].read_text())
        hot = data.get("hot_tier", {})
        tasks = hot.get("active_tasks", [])
        directives = hot.get("user_directives", [])
        parts = []
        if tasks:
            parts.append("Tasks: " + "; ".join(str(t)[:50] for t in tasks[:3]))
        if directives:
            parts.append("Directives: " + "; ".join(str(d)[:50] for d in directives[:2]))
        result = " | ".join(parts)
        return result[:200] if result else ""
    except Exception as e:
        logger.debug("Relay context load failed: %s", e)
        return ""


def load_trading_summary() -> str:
    """Read confidence aggregator and return 1-line trading state."""
    try:
        if not _CONFIDENCE.exists():
            return ""
        data = json.loads(_CONFIDENCE.read_text())
        pct = data.get("readiness_pct", 0)
        label = data.get("readiness_label", "UNKNOWN")
        cycle = data.get("cycle_count", 0)
        return f"Trading: {pct:.1f}% {label}, cycle {cycle}"
    except Exception as e:
        logger.debug("Trading summary load failed: %s", e)
        return ""


def load_roadmap_top3() -> str:
    """Read roadmap.md and return top 3 incomplete T1 items."""
    try:
        if not _ROADMAP.exists():
            return ""
        lines = _ROADMAP.read_text().splitlines()
        items = []
        in_t1 = False
        for line in lines:
            if "## T1" in line or "## T0" in line:
                in_t1 = True
                continue
            if line.startswith("## T2") or line.startswith("## T3"):
                break
            if in_t1 and line.startswith("|") and "%" in line and "100%" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5:
                    num = parts[1]
                    name = parts[2][:40]
                    pct = parts[3]
                    items.append(f"#{num} {name} ({pct})")
                if len(items) >= 3:
                    break
        return "Roadmap: " + " | ".join(items) if items else ""
    except Exception as e:
        logger.debug("Roadmap load failed: %s", e)
        return ""


def build_system_context() -> str:
    """Combine all context sources into a system prompt preamble (<500 tokens)."""
    parts = []

    trading = load_trading_summary()
    if trading:
        parts.append(trading)

    roadmap = load_roadmap_top3()
    if roadmap:
        parts.append(roadmap)

    relay = load_relay_context()
    if relay:
        parts.append(relay)

    if not parts:
        return ""

    return "[LUMINA CONTEXT] " + " | ".join(parts)
