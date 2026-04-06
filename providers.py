"""
Multi-provider support for nano claude.

Supported providers:
  anthropic  — Claude (claude-opus-4-6, claude-sonnet-4-6, ...)
  openai     — GPT (gpt-4o, o3-mini, ...)
  gemini     — Google Gemini (gemini-2.0-flash, gemini-1.5-pro, ...)
  kimi       — Moonshot AI (moonshot-v1-8k/32k/128k)
  qwen       — Alibaba DashScope (qwen-max, qwen-plus, ...)
  zhipu      — Zhipu GLM (glm-4, glm-4-plus, ...)
  deepseek   — DeepSeek (deepseek-chat, deepseek-reasoner, ...)
  ollama     — Local Ollama (llama3.3, qwen2.5-coder, ...)
  lmstudio   — Local LM Studio (any loaded model)
  custom     — Any OpenAI-compatible endpoint

Model string formats:
  "claude-opus-4-6"          auto-detected → anthropic
  "gpt-4o"                   auto-detected → openai
  "ollama/qwen2.5-coder"     explicit provider prefix
  "custom/my-model"          uses CUSTOM_BASE_URL from config
"""
from __future__ import annotations
import json
from typing import Generator

# ── Provider registry ──────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "type":       "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "context_limit": 200000,
        "models": [
            "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
            "claude-opus-4-5", "claude-sonnet-4-5",
            "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        ],
    },
    "openai": {
        "type":       "openai",
        "api_key_env": "OPENAI_API_KEY",
        "base_url":   "https://api.openai.com/v1",
        "context_limit": 128000,
        "models": [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
            "o3-mini", "o1", "o1-mini",
        ],
    },
    "gemini": {
        "type":       "openai",
        "api_key_env": "GEMINI_API_KEY",
        "base_url":   "https://generativelanguage.googleapis.com/v1beta/openai/",
        "context_limit": 1000000,
        "models": [
            "gemini-2.5-pro-preview-03-25",
            "gemini-2.0-flash", "gemini-2.0-flash-lite",
            "gemini-1.5-pro", "gemini-1.5-flash",
        ],
    },
    "kimi": {
        "type":       "openai",
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url":   "https://api.moonshot.cn/v1",
        "context_limit": 128000,
        "models": [
            "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k",
            "kimi-latest",
        ],
    },
    "qwen": {
        "type":       "openai",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url":   "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "context_limit": 1000000,
        "models": [
            "qwen-max", "qwen-plus", "qwen-turbo", "qwen-long",
            "qwen2.5-72b-instruct", "qwen2.5-coder-32b-instruct",
            "qwq-32b",
        ],
    },
    "zhipu": {
        "type":       "openai",
        "api_key_env": "ZHIPU_API_KEY",
        "base_url":   "https://open.bigmodel.cn/api/paas/v4/",
        "context_limit": 128000,
        "models": [
            "glm-4-plus", "glm-4", "glm-4-flash", "glm-4-air",
            "glm-z1-flash",
        ],
    },
    "deepseek": {
        "type":       "openai",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url":   "https://api.deepseek.com/v1",
        "context_limit": 64000,
        "models": [
            "deepseek-chat", "deepseek-coder", "deepseek-reasoner",
        ],
    },
    "ollama": {
        "type":       "openai",
        "api_key_env": None,
        "base_url":   "http://localhost:11434/v1",
        "api_key":    "ollama",
        "context_limit": 128000,
        "models": [
            "llama3.3", "llama3.2", "phi4", "mistral", "mixtral",
            "qwen2.5-coder", "deepseek-r1", "gemma3",
        ],
    },
    "lmstudio": {
        "type":       "openai",
        "api_key_env": None,
        "base_url":   "http://localhost:1234/v1",
        "api_key":    "lm-studio",
        "context_limit": 128000,
        "models": [],   # dynamic, depends on loaded model
    },
    "custom": {
        "type":       "openai",
        "api_key_env": "CUSTOM_API_KEY",
        "base_url":   None,   # read from config["custom_base_url"]
        "context_limit": 128000,
        "models": [],
    },
    "gateway": {
        "type":       "openai",
        "api_key_env": None,
        "base_url":   "http://localhost:8080/v1",
        "api_key":    "sk-lumina-gateway-2026",
        "context_limit": 32000,
        "models": [
            "local/fast", "local/code", "local/balanced",
            "cpu/fast", "kaiju/bitnet",
        ],
    },
}

# Cost per million tokens (approximate, fallback to 0 for unknown)
COSTS = {
    "claude-opus-4-6":          (15.0, 75.0),
    "claude-sonnet-4-6":        (3.0,  15.0),
    "claude-haiku-4-5-20251001": (0.8,  4.0),
    "gpt-4o":                   (2.5,  10.0),
    "gpt-4o-mini":              (0.15,  0.6),
    "o3-mini":                  (1.1,   4.4),
    "gemini-2.0-flash":         (0.075, 0.3),
    "gemini-1.5-pro":           (1.25,  5.0),
    "gemini-2.5-pro-preview-03-25": (1.25, 10.0),
    "moonshot-v1-8k":           (1.0,   3.0),
    "moonshot-v1-32k":          (2.4,   7.0),
    "moonshot-v1-128k":         (8.0,  24.0),
    "qwen-max":                 (2.4,   9.6),
    "qwen-plus":                (0.4,   1.2),
    "deepseek-chat":            (0.27,  1.1),
    "deepseek-reasoner":        (0.55,  2.19),
    "glm-4-plus":               (0.7,   0.7),
}

# Auto-detection: prefix → provider name
_PREFIXES = [
    ("claude-",       "anthropic"),
    ("gpt-",          "openai"),
    ("o1",            "openai"),
    ("o3",            "openai"),
    ("gemini-",       "gemini"),
    ("moonshot-",     "kimi"),
    ("kimi-",         "kimi"),
    ("qwen",          "qwen"),  # qwen-max, qwen2.5-...
    ("qwq-",          "qwen"),
    ("glm-",          "zhipu"),
    ("deepseek-",     "deepseek"),
    ("local/",        "gateway"),
    ("cpu/",          "gateway"),
    ("kaiju/",        "gateway"),
    ("llama",         "ollama"),
    ("mistral",       "ollama"),
    ("phi",           "ollama"),
    ("gemma",         "ollama"),
]


_GATEWAY_ALIASES = {"local", "cpu", "kaiju"}


def detect_provider(model: str) -> str:
    """Return provider name for a model string.
    Supports 'provider/model' explicit format, or auto-detect by prefix."""
    if "/" in model:
        prefix = model.split("/", 1)[0]
        if prefix in _GATEWAY_ALIASES:
            return "gateway"
        return prefix
    for pfx, pname in _PREFIXES:
        if model.lower().startswith(pfx):
            return pname
    return "openai"   # fallback


def bare_model(model: str) -> str:
    """Strip 'provider/' prefix if present.
    For gateway aliases (local/, cpu/, kaiju/), keep the full name since
    the gateway expects model names like 'local/fast'."""
    if "/" in model:
        prefix = model.split("/", 1)[0]
        if prefix in _GATEWAY_ALIASES:
            return model  # gateway needs full name e.g. "local/fast"
        return model.split("/", 1)[1]
    return model


def get_api_key(provider_name: str, config: dict) -> str:
    prov = PROVIDERS.get(provider_name, {})
    # 1. Check config dict (e.g. config["kimi_api_key"])
    cfg_key = config.get(f"{provider_name}_api_key", "")
    if cfg_key:
        return cfg_key
    # 2. Check env var
    env_var = prov.get("api_key_env")
    if env_var:
        import os
        return os.environ.get(env_var, "")
    # 3. Hardcoded (for local providers)
    return prov.get("api_key", "")


def calc_cost(model: str, in_tok: int, out_tok: int) -> float:
    ic, oc = COSTS.get(bare_model(model), (0.0, 0.0))
    return (in_tok * ic + out_tok * oc) / 1_000_000


# ── Tool schema conversion ─────────────────────────────────────────────────

def tools_to_openai(tool_schemas: list) -> list:
    """Convert Anthropic-style tool schemas to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"],
            },
        }
        for t in tool_schemas
    ]


# ── Message format conversion ──────────────────────────────────────────────
#
# Internal "neutral" message format:
#   {"role": "user",      "content": "text"}
#   {"role": "assistant", "content": "text", "tool_calls": [
#       {"id": "...", "name": "...", "input": {...}}
#   ]}
#   {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}

def messages_to_anthropic(messages: list) -> list:
    """Convert neutral messages → Anthropic API format."""
    result = []
    i = 0
    while i < len(messages):
        m = messages[i]
        role = m["role"]

        if role == "user":
            result.append({"role": "user", "content": m["content"]})
            i += 1

        elif role == "assistant":
            blocks = []
            text = m.get("content", "")
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.get("tool_calls", []):
                blocks.append({
                    "type":  "tool_use",
                    "id":    tc["id"],
                    "name":  tc["name"],
                    "input": tc["input"],
                })
            result.append({"role": "assistant", "content": blocks})
            i += 1

        elif role == "tool":
            # Collect consecutive tool results into one user message
            tool_blocks = []
            while i < len(messages) and messages[i]["role"] == "tool":
                t = messages[i]
                tool_blocks.append({
                    "type":        "tool_result",
                    "tool_use_id": t["tool_call_id"],
                    "content":     t["content"],
                })
                i += 1
            result.append({"role": "user", "content": tool_blocks})

        else:
            i += 1

    return result


def messages_to_openai(messages: list) -> list:
    """Convert neutral messages → OpenAI API format."""
    result = []
    for m in messages:
        role = m["role"]

        if role == "user":
            result.append({"role": "user", "content": m["content"]})

        elif role == "assistant":
            msg: dict = {"role": "assistant", "content": m.get("content") or None}
            tcs = m.get("tool_calls", [])
            if tcs:
                msg["tool_calls"] = []
                for tc in tcs:
                    tc_msg = {
                        "id":   tc["id"],
                        "type": "function",
                        "function": {
                            "name":      tc["name"],
                            "arguments": json.dumps(tc["input"], ensure_ascii=False),
                        },
                    }
                    # Pass through provider-specific fields (e.g. Gemini thought_signature)
                    if tc.get("extra_content"):
                        tc_msg["extra_content"] = tc["extra_content"]
                    msg["tool_calls"].append(tc_msg)
            result.append(msg)

        elif role == "tool":
            result.append({
                "role":         "tool",
                "tool_call_id": m["tool_call_id"],
                "content":      m["content"],
            })

    return result


# ── Streaming adapters ─────────────────────────────────────────────────────

class TextChunk:
    def __init__(self, text): self.text = text

class ThinkingChunk:
    def __init__(self, text): self.text = text

class AssistantTurn:
    """Completed assistant turn with text + tool_calls."""
    def __init__(self, text, tool_calls, in_tokens, out_tokens):
        self.text        = text
        self.tool_calls  = tool_calls   # list of {id, name, input}
        self.in_tokens   = in_tokens
        self.out_tokens  = out_tokens


def stream_anthropic(
    api_key: str,
    model: str,
    system: str,
    messages: list,
    tool_schemas: list,
    config: dict,
) -> Generator:
    """Stream from Anthropic API. Yields TextChunk/ThinkingChunk, then AssistantTurn."""
    import anthropic as _ant
    client = _ant.Anthropic(api_key=api_key)

    kwargs = {
        "model":      model,
        "max_tokens": config.get("max_tokens", 8192),
        "system":     system,
        "messages":   messages_to_anthropic(messages),
        "tools":      tool_schemas,
    }
    if config.get("thinking"):
        kwargs["thinking"] = {
            "type":          "enabled",
            "budget_tokens": config.get("thinking_budget", 10000),
        }

    tool_calls = []
    text       = ""

    with client.messages.stream(**kwargs) as stream:
        for event in stream:
            etype = getattr(event, "type", None)
            if etype == "content_block_delta":
                delta = event.delta
                dtype = getattr(delta, "type", None)
                if dtype == "text_delta":
                    text += delta.text
                    yield TextChunk(delta.text)
                elif dtype == "thinking_delta":
                    yield ThinkingChunk(delta.thinking)

        final = stream.get_final_message()
        for block in final.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "id":    block.id,
                    "name":  block.name,
                    "input": block.input,
                })

        yield AssistantTurn(
            text, tool_calls,
            final.usage.input_tokens,
            final.usage.output_tokens,
        )


def stream_openai_compat(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    messages: list,
    tool_schemas: list,
    config: dict,
) -> Generator:
    """Stream from any OpenAI-compatible API. Yields TextChunk, then AssistantTurn."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key or "dummy", base_url=base_url)

    oai_messages = [{"role": "system", "content": system}] + messages_to_openai(messages)

    use_stream = not config.get("no_stream", False)

    kwargs: dict = {
        "model":    model,
        "messages": oai_messages,
        "stream":   use_stream,
    }
    if tool_schemas and not config.get("no_tools"):
        kwargs["tools"] = tools_to_openai(tool_schemas)
        # "auto" requires vLLM --enable-auto-tool-choice; omit if server doesn't support it
        if not config.get("disable_tool_choice"):
            kwargs["tool_choice"] = "auto"
    if config.get("max_tokens"):
        kwargs["max_tokens"] = config["max_tokens"]

    text          = ""
    tool_buf: dict = {}   # index → {id, name, args_str}
    in_tok = out_tok = 0

    if not use_stream:
        # Non-streaming: single request, yield full response
        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""
        if text:
            yield TextChunk(text)
        if hasattr(resp, "usage") and resp.usage:
            in_tok = resp.usage.prompt_tokens or 0
            out_tok = resp.usage.completion_tokens or 0
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    inp = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    inp = {"_raw": tc.function.arguments}
                tool_calls.append({"id": tc.id, "name": tc.function.name, "input": inp})
        yield AssistantTurn(text, tool_calls, in_tok, out_tok)
        return

    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            # usage-only chunk (some providers send this last)
            if hasattr(chunk, "usage") and chunk.usage:
                in_tok  = chunk.usage.prompt_tokens
                out_tok = chunk.usage.completion_tokens
            continue

        choice = chunk.choices[0]
        delta  = choice.delta

        if delta.content:
            text += delta.content
            yield TextChunk(delta.content)

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_buf:
                    tool_buf[idx] = {"id": "", "name": "", "args": "", "extra_content": None}
                if tc.id:
                    tool_buf[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tool_buf[idx]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_buf[idx]["args"] += tc.function.arguments
                # Capture extra_content (e.g. Gemini thought_signature)
                extra = getattr(tc, "extra_content", None)
                if extra:
                    tool_buf[idx]["extra_content"] = extra

        # Some providers include usage in the last chunk
        if hasattr(chunk, "usage") and chunk.usage:
            in_tok  = chunk.usage.prompt_tokens  or in_tok
            out_tok = chunk.usage.completion_tokens or out_tok

    tool_calls = []
    for idx in sorted(tool_buf):
        v = tool_buf[idx]
        try:
            inp = json.loads(v["args"]) if v["args"] else {}
        except json.JSONDecodeError:
            inp = {"_raw": v["args"]}
        tc_entry = {"id": v["id"] or f"call_{idx}", "name": v["name"], "input": inp}
        if v.get("extra_content"):
            tc_entry["extra_content"] = v["extra_content"]
        tool_calls.append(tc_entry)

    yield AssistantTurn(text, tool_calls, in_tok, out_tok)


def is_gateway_healthy() -> bool:
    """Check if the Lumina LLM gateway is responsive (<1s timeout)."""
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8080/health/liveliness", timeout=1)
        return resp.status == 200
    except Exception:
        return False


def get_shift_model() -> str:
    """Pick the best gateway model based on current EST time shift."""
    from datetime import datetime
    try:
        import pytz
        hour = datetime.now(pytz.timezone("America/New_York")).hour
    except ImportError:
        hour = datetime.now().hour
    if hour < 8:
        return "gateway/local/fast"         # NIGHT: smallest, cheapest
    elif hour < 16:
        return "gateway/local/balanced"     # DAY: best quality
    return "gateway/local/code"             # EVENING: code-optimized


def get_trading_context() -> str:
    """Read confidence aggregator and return a 1-line trading summary, or empty string."""
    from pathlib import Path
    try:
        p = Path.home() / "my_projects" / "lumina" / "docker" / "cluster-ui" / "data" / "trading" / "state" / "confidence_aggregator.json"
        if not p.exists():
            return ""
        data = json.loads(p.read_text())
        pct = data.get("readiness_pct", 0)
        label = data.get("readiness_label", "UNKNOWN")
        cycle = data.get("cycle_count", 0)
        rec = data.get("recommendation", "")[:80]
        return f"[TRADING] Confidence: {pct:.1f}% ({label}), cycle {cycle}. {rec}"
    except Exception:
        return ""


_TRADING_KEYWORDS = frozenset({
    "btc", "eth", "sol", "ada", "xrp", "bnb", "doge", "crypto", "bitcoin",
    "ethereum", "trading", "confidence", "paper trading", "pnl", "p&l",
    "market", "regime", "signal", "grid bot", "backtest", "sharpe",
})


def _is_trading_query(messages: list) -> bool:
    """Check if the latest user message mentions trading-related terms."""
    for m in reversed(messages):
        if m.get("role") == "user":
            text = (m.get("content") or "").lower()
            return any(kw in text for kw in _TRADING_KEYWORDS)
    return False


def stream(
    model: str,
    system: str,
    messages: list,
    tool_schemas: list,
    config: dict,
) -> Generator:
    """
    Unified streaming entry point.
    Auto-detects provider from model string.
    Yields: TextChunk | ThinkingChunk | AssistantTurn
    """
    # Inject trading context when query is trading-related
    if _is_trading_query(messages):
        ctx = get_trading_context()
        if ctx:
            system = f"{ctx}\n\n{system}" if system else ctx

    provider_name = detect_provider(model)
    model_name    = bare_model(model)
    prov          = PROVIDERS.get(provider_name, PROVIDERS["openai"])
    api_key       = get_api_key(provider_name, config)

    # Gateway provider: health check with Ollama fallback
    if provider_name == "gateway" and not is_gateway_healthy():
        # Fallback to direct Ollama
        provider_name = "ollama"
        prov = PROVIDERS["ollama"]
        api_key = get_api_key("ollama", config)
        # Map gateway model names to Ollama equivalents
        _gw_to_ollama = {
            "local/fast": "llama3.2:3b",
            "local/code": "qwen2.5-coder:7b",
            "local/balanced": "qwen2.5:14b",
            "cpu/fast": "llama3.2:3b",
        }
        model_name = _gw_to_ollama.get(model_name, "llama3.2:3b")

    if prov["type"] == "anthropic":
        yield from stream_anthropic(api_key, model_name, system, messages, tool_schemas, config)
    else:
        import os as _os
        if provider_name == "custom":
            base_url = (config.get("custom_base_url")
                        or _os.environ.get("CUSTOM_BASE_URL", ""))
            if not base_url:
                raise ValueError(
                    "custom provider requires a base_url. "
                    "Set CUSTOM_BASE_URL env var or run: /config custom_base_url=http://..."
                )
        else:
            base_url = prov.get("base_url", "https://api.openai.com/v1")
        yield from stream_openai_compat(
            api_key, base_url, model_name, system, messages, tool_schemas, config
        )
