
---

## Provider Routing Specification for the Lumina Sovereign Harness

**Ticket: C-000003916**

This specification defines how the nano-claude-code fork will intelligently route tasks to the best-fit AI provider based on task classification, capability traits, cost constraints, and privacy requirements.

---

### 1. Current Architecture Summary

The routing insertion point is the `agent.py:run()` function at line 88, where `config["model"]` is passed to `providers.stream()`. Currently, the model is static per session (set via `/model` command or `config.json`). The router will intercept at this point, dynamically selecting the model per-turn based on task analysis.

Key integration points:
- **`/home/mlesn/my_projects/nano-claude-code/agent.py`** -- the agent loop calls `stream(model=config["model"], ...)`. The router replaces `config["model"]` with a per-turn selection.
- **`/home/mlesn/my_projects/nano-claude-code/providers.py`** -- contains `PROVIDERS` registry, `COSTS` dict, `detect_provider()`, and `calc_cost()`. The router reads these as its ground truth.
- **`/home/mlesn/my_projects/nano-claude-code/config.py`** -- manages `~/.nano_claude/config.json`. Router config (default strategy, cost ceiling, privacy mode) lives here.
- **`/home/mlesn/my_projects/nano-claude-code/nano_claude.py`** -- REPL and slash commands. New `/route` command exposes routing state.

---

### 2. Trait Matrix Definition

Each model gets a trait vector. The data structure in Python:

```python
@dataclass
class ModelTraits:
    model_id: str                    # e.g. "claude-opus-4-6"
    provider: str                    # e.g. "anthropic"
    reasoning_depth: int             # 1-10
    code_generation_speed: int       # 1-10
    vision: bool                     # multimodal image input
    tool_calling_quality: int        # 1-10
    context_window: int              # tokens
    cost_input_per_1m: float         # USD per 1M input tokens
    cost_output_per_1m: float        # USD per 1M output tokens
    local: bool                      # runs locally, no data leaves machine
    web_search: bool                 # native web search capability
    available: bool = True           # runtime: has API key configured
```

### 3. Provider-to-Trait Mapping

Derived from the existing `PROVIDERS` and `COSTS` dicts in `providers.py`:

| Model | reasoning | code_speed | vision | tool_call | context | cost_in/1M | cost_out/1M | local | web_search |
|---|---|---|---|---|---|---|---|---|---|
| claude-opus-4-6 | 10 | 6 | True | 10 | 200K | 15.0 | 75.0 | False | False |
| claude-sonnet-4-6 | 8 | 8 | True | 9 | 200K | 3.0 | 15.0 | False | False |
| claude-haiku-4-5 | 6 | 9 | True | 7 | 200K | 0.8 | 4.0 | False | False |
| gpt-4o | 7 | 9 | True | 8 | 128K | 2.5 | 10.0 | False | False |
| gpt-4o-mini | 5 | 10 | True | 6 | 128K | 0.15 | 0.6 | False | False |
| o3-mini | 8 | 7 | False | 5 | 128K | 1.1 | 4.4 | False | False |
| gemini-2.5-pro | 9 | 7 | True | 7 | 1M | 1.25 | 10.0 | False | True |
| gemini-2.0-flash | 5 | 10 | True | 6 | 1M | 0.075 | 0.3 | False | True |
| deepseek-chat | 7 | 8 | False | 6 | 64K | 0.27 | 1.1 | False | False |
| deepseek-reasoner | 9 | 6 | False | 5 | 64K | 0.55 | 2.19 | False | False |
| ollama/* | 4 | 7 | False | 3 | 128K | 0.0 | 0.0 | True | False |
| lmstudio/* | 4 | 7 | False | 3 | 128K | 0.0 | 0.0 | True | False |
| qwen-max | 7 | 7 | False | 6 | 1M | 2.4 | 9.6 | False | False |
| glm-4-plus | 6 | 8 | False | 5 | 128K | 0.7 | 0.7 | False | False |

The `TRAIT_MATRIX` dict will live in a new file `routing.py` and will be populated from `PROVIDERS` and `COSTS` at import time, with trait scores as static configuration. The `available` field is computed at runtime by checking whether `get_api_key()` returns a non-empty string.

### 4. Task Classification

The router classifies each user message into a `TaskType` enum before selecting a provider. Classification uses keyword/pattern matching first (fast, free), with an optional LLM-based classifier for ambiguous cases.

```python
class TaskType(Enum):
    ARCHITECTURE = "architecture"        # system design, complex decisions
    CODE_GEN = "code_gen"                # write new code, boilerplate
    CODE_REVIEW = "code_review"          # review, refactor existing code
    DEBUGGING = "debugging"              # find and fix bugs
    EXPLANATION = "explanation"          # explain code or concepts
    IMAGE_ANALYSIS = "image_analysis"    # analyze screenshots, diagrams
    WEB_SEARCH = "web_search"            # find information online
    LONG_CONTEXT = "long_context"        # analyze large files, repos
    SENSITIVE = "sensitive"              # private/proprietary code
    TRIVIAL = "trivial"                  # simple questions, formatting
```

Classification rules (pattern-based, evaluated top-to-bottom):

1. **SENSITIVE** -- user message contains `/private`, or `config["routing_privacy"]` is `"local_only"`, or the project has a `.local-only` marker file.
2. **IMAGE_ANALYSIS** -- message references an image file path (`.png`, `.jpg`, `.svg`, `.gif`) or contains "screenshot", "diagram", "image".
3. **WEB_SEARCH** -- message contains "search for", "look up", "find online", "what is the latest", or references a URL.
4. **LONG_CONTEXT** -- the current context window usage exceeds 80% of the active model's limit, or message asks to "analyze entire repo/file".
5. **ARCHITECTURE** -- contains "architect", "design", "system design", "tradeoff", "RFC", "spec", or message length exceeds 500 chars with technical terms.
6. **DEBUGGING** -- contains "bug", "error", "traceback", "fix", "broken", "failing".
7. **CODE_REVIEW** -- contains "review", "refactor", "improve", "clean up".
8. **CODE_GEN** -- contains "generate", "create", "write", "boilerplate", "scaffold", "implement".
9. **EXPLANATION** -- contains "explain", "how does", "what is", "why".
10. **TRIVIAL** -- message is under 50 characters and no technical keywords.
11. **Default** -- falls back to `CODE_GEN`.

### 5. Routing Rules (TaskType to Model)

Each `TaskType` maps to a ranked list of preferred models. The router picks the first available model from the list.

```python
ROUTING_TABLE: dict[TaskType, list[str]] = {
    TaskType.ARCHITECTURE: [
        "claude-opus-4-6",
        "deepseek-reasoner",
        "gemini-2.5-pro-preview-03-25",
        "claude-sonnet-4-6",
    ],
    TaskType.CODE_GEN: [
        "claude-sonnet-4-6",
        "gpt-4o",
        "deepseek-chat",
        "gpt-4o-mini",
        "ollama/qwen2.5-coder",
    ],
    TaskType.CODE_REVIEW: [
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "deepseek-chat",
    ],
    TaskType.DEBUGGING: [
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "gpt-4o",
        "deepseek-chat",
    ],
    TaskType.EXPLANATION: [
        "claude-sonnet-4-6",
        "gpt-4o",
        "gemini-2.0-flash",
        "deepseek-chat",
    ],
    TaskType.IMAGE_ANALYSIS: [
        "gemini-2.5-pro-preview-03-25",
        "gpt-4o",
        "claude-sonnet-4-6",
    ],
    TaskType.WEB_SEARCH: [
        "gemini-2.5-pro-preview-03-25",
        "gemini-2.0-flash",
    ],
    TaskType.LONG_CONTEXT: [
        "gemini-2.5-pro-preview-03-25",
        "gemini-1.5-pro",
        "qwen-max",
        "claude-opus-4-6",
    ],
    TaskType.SENSITIVE: [
        "ollama/qwen2.5-coder",
        "ollama/deepseek-r1",
        "ollama/llama3.3",
        "lmstudio/*",
    ],
    TaskType.TRIVIAL: [
        "gemini-2.0-flash",
        "gpt-4o-mini",
        "claude-haiku-4-5-20251001",
        "ollama/gemma3",
    ],
}
```

### 6. Cost Optimizer Design

The cost optimizer wraps the routing decision with budget awareness.

```python
@dataclass
class CostTracker:
    session_costs: dict[str, float] = field(default_factory=dict)  # model -> cumulative $
    session_tokens: dict[str, tuple[int, int]] = field(default_factory=dict)  # model -> (in, out)
    budget_ceiling: float | None = None  # USD, None = unlimited
    warnings: list[str] = field(default_factory=list)
```

Cost rules:
1. **Downgrade suggestion** -- If the selected model costs more than 5x the cheapest alternative for that task type, and the quality delta (reasoning_depth difference) is 2 or less, suggest the cheaper model. Print: `"[Router] Suggesting deepseek-chat instead of claude-opus-4-6 (saves ~$X/1K tokens, similar quality for code_gen)"`.
2. **Trivial task guard** -- If task is classified `TRIVIAL` and the selected model's cost_input_per_1m exceeds $2.0, warn: `"[Router] Expensive model for a simple task. Use /model to override or /route auto to let me pick."`.
3. **Budget ceiling** -- If `budget_ceiling` is set and cumulative session cost exceeds 80%, warn. At 100%, force-downgrade to cheapest available model.
4. **Per-turn cost display** -- In verbose mode, show cost per turn and cumulative.

### 7. Python Class Interface

New file: `/home/mlesn/my_projects/nano-claude-code/routing.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskType(Enum):
    ARCHITECTURE = "architecture"
    CODE_GEN = "code_gen"
    CODE_REVIEW = "code_review"
    DEBUGGING = "debugging"
    EXPLANATION = "explanation"
    IMAGE_ANALYSIS = "image_analysis"
    WEB_SEARCH = "web_search"
    LONG_CONTEXT = "long_context"
    SENSITIVE = "sensitive"
    TRIVIAL = "trivial"


class RoutingStrategy(Enum):
    AUTO = "auto"           # full intelligent routing
    COST = "cost"           # always pick cheapest that meets minimum quality
    QUALITY = "quality"     # always pick best available
    LOCAL = "local"         # only local models
    FIXED = "fixed"         # use config["model"], no routing (current behavior)


@dataclass
class ModelTraits:
    model_id: str
    provider: str
    reasoning_depth: int
    code_generation_speed: int
    vision: bool
    tool_calling_quality: int
    context_window: int
    cost_input_per_1m: float
    cost_output_per_1m: float
    local: bool
    web_search: bool
    available: bool = True


@dataclass
class RoutingDecision:
    task_type: TaskType
    selected_model: str
    reason: str
    alternatives: list[str]
    estimated_cost_per_1k: float


class ProviderRouter:
    """Intelligent provider routing for multi-model sessions."""

    def __init__(self, config: dict):
        self._config = config
        self._override: Optional[str] = None
        self._strategy = RoutingStrategy(config.get("routing_strategy", "fixed"))
        self._cost_tracker = CostTracker(
            budget_ceiling=config.get("routing_budget", None)
        )
        self._trait_matrix: dict[str, ModelTraits] = _build_trait_matrix(config)

    def classify(self, user_message: str, context: dict) -> TaskType:
        """Classify a user message into a TaskType using pattern matching."""
        ...

    def select(self, task_type: TaskType, context: dict) -> RoutingDecision:
        """Select the best model for a given task type and context.
        
        Args:
            task_type: classified task type
            context: dict with keys like 'context_usage_pct', 'has_image',
                     'message_length', 'privacy_required'
        Returns:
            RoutingDecision with selected model and metadata
        """
        if self._override:
            return RoutingDecision(
                task_type=task_type,
                selected_model=self._override,
                reason="manual override",
                alternatives=[],
                estimated_cost_per_1k=0.0,
            )
        ...

    def override(self, model: Optional[str]) -> None:
        """Set or clear a manual model override. None clears it."""
        self._override = model

    def record_usage(self, model: str, in_tokens: int, out_tokens: int) -> None:
        """Record token usage for cost tracking."""
        self._cost_tracker.record(model, in_tokens, out_tokens)

    def cost_report(self) -> dict:
        """Return session cost breakdown by provider.
        
        Returns:
            {
                "total_usd": float,
                "by_model": {"claude-opus-4-6": {"usd": 0.12, "in_tokens": 8000, "out_tokens": 2000}},
                "budget_remaining": float | None,
                "warnings": ["..."],
            }
        """
        return self._cost_tracker.report()

    def available_models(self) -> list[ModelTraits]:
        """Return all models that have API keys configured."""
        return [t for t in self._trait_matrix.values() if t.available]
```

### 8. Integration Plan into `agent.py`

The change to `agent.py` is minimal. In the `run()` function, before the `stream()` call at line 88:

```python
# Current (line 88-94):
for event in stream(
    model=config["model"],
    ...
):

# Proposed:
router = config.get("_router")  # injected by nano_claude.py at session start
if router and router._strategy != RoutingStrategy.FIXED:
    task_type = router.classify(user_message, {
        "context_usage_pct": _context_usage(state, config),
        "message_length": len(user_message),
    })
    decision = router.select(task_type, {})
    effective_model = decision.selected_model
    # Print routing decision in verbose mode
    if config.get("verbose"):
        yield TextChunk(f"\n[Router: {task_type.value} -> {effective_model} ({decision.reason})]\n")
else:
    effective_model = config["model"]

for event in stream(
    model=effective_model,
    ...
):
```

After the turn completes (line 110-112), add:

```python
if router:
    router.record_usage(effective_model, assistant_turn.in_tokens, assistant_turn.out_tokens)
```

### 9. New Config Keys

Added to `config.py` `DEFAULTS`:

```python
"routing_strategy":  "fixed",    # auto | cost | quality | local | fixed
"routing_budget":    None,       # USD ceiling per session, None = unlimited
"routing_privacy":   "default",  # default | local_only
```

### 10. New Slash Commands

Added to `nano_claude.py` command table:

- `/route` -- Show current routing strategy, last decision, and available models
- `/route auto|cost|quality|local|fixed` -- Set routing strategy
- `/route budget <amount>` -- Set session budget ceiling in USD
- `/route explain` -- Show why the last model was selected
- `/route cost` -- Alias for cost_report() with per-model breakdown

### 11. File Creation Plan

| File | Action | Purpose |
|------|--------|---------|
| `routing.py` | **NEW** | `ProviderRouter`, `TaskType`, `ModelTraits`, `CostTracker`, `TRAIT_MATRIX`, `ROUTING_TABLE`, classifier logic |
| `agent.py` | **MODIFY** | Insert router hook before `stream()` call (lines 86-94), record usage after turn |
| `config.py` | **MODIFY** | Add 3 new defaults: `routing_strategy`, `routing_budget`, `routing_privacy` |
| `nano_claude.py` | **MODIFY** | Instantiate `ProviderRouter` at session start (line ~1088), add `/route` command handler, inject router into config |
| `providers.py` | **NO CHANGE** | Read-only dependency; `COSTS` and `PROVIDERS` are consumed by router |
| `docs/PROVIDER_ROUTING.md` | **NEW** | This specification document |
| `tests/test_routing.py` | **NEW** | Unit tests for classifier, routing table, cost tracker |

### 12. Implementation Sequence

**Phase 1 (Day 1):** Create `routing.py` with `ModelTraits`, `TaskType`, `TRAIT_MATRIX`, and `ROUTING_TABLE`. Implement `ProviderRouter.classify()` using regex/keyword patterns. Implement `ProviderRouter.select()` with fallback chain. Write `tests/test_routing.py`.

**Phase 2 (Day 2):** Implement `CostTracker` with budget ceiling logic. Add downgrade suggestion and trivial-task guard. Add config keys to `config.py`.

**Phase 3 (Day 3):** Integrate into `agent.py` (the 10-line diff described above). Add `/route` slash command to `nano_claude.py`. Wire up `ProviderRouter` instantiation at session start.

**Phase 4 (Day 4):** End-to-end testing. Verify that `routing_strategy: "fixed"` produces identical behavior to current codebase (zero regression). Test `auto` strategy with different prompt types.

### 13. Risks and Mitigations

- **Regression risk**: The `"fixed"` strategy is the default and bypasses all routing logic entirely, making it a no-op. Existing behavior is preserved unless the user explicitly enables routing.
- **Classifier accuracy**: Pattern-based classification will misclassify some prompts. Mitigation: always show the routing decision in verbose mode, and allow `/model` override to take immediate effect (sets `self._override`).
- **Multi-turn context**: When the router switches models mid-session, the conversation history format must be compatible. This is already handled by the neutral message format in `agent.py` and the `messages_to_anthropic()` / `messages_to_openai()` converters in `providers.py`.
- **API key availability**: The router must check `get_api_key()` at decision time, not just at startup, because keys can be added via `/config` during a session. The `available` field in `ModelTraits` should be recomputed lazily.

---

### Critical Files for Implementation
- /home/mlesn/my_projects/nano-claude-code/agent.py
- /home/mlesn/my_projects/nano-claude-code/providers.py
- /home/mlesn/my_projects/nano-claude-code/config.py
- /home/mlesn/my_projects/nano-claude-code/nano_claude.py
