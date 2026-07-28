"""Pluggable LLM provider. Selects OpenAI -> Anthropic -> Ollama -> None (rule-based).

The rest of the AI layer treats the LLM as optional: when no key is configured,
`complete()` returns None and skills use deterministic logic. This keeps the
whole system runnable and testable with zero external dependencies.
"""
from __future__ import annotations

import json
import time
from typing import Callable

import httpx

from app.core.config import settings

# Circuit breaker: once a provider call fails (no credits, outage, timeout), skip
# calling it for a cool-down window so we don't add ~1s of dead latency to every
# request. After the window we retry once — so it lights up automatically the
# moment credits/connectivity return.
_COOLDOWN_SECS = 300
_open_until: dict[str, float] = {}
_HTTP_TIMEOUT = 20


def active_provider() -> str:
    p = settings.ai_provider
    if p == "openai" and settings.openai_api_key:
        return "openai"
    if p == "anthropic" and settings.anthropic_api_key:
        return "anthropic"
    if p == "ollama":
        return "ollama"
    if p == "auto":
        if settings.openai_api_key:
            return "openai"
        if settings.anthropic_api_key:
            return "anthropic"
    return "rules"


def provider_healthy(provider: str) -> bool:
    return time.time() >= _open_until.get(provider, 0)


def complete(prompt: str, system: str = "", *, max_tokens: int = 500) -> str | None:
    """Return LLM completion text, or None if no provider is available/failing."""
    provider = active_provider()
    if provider == "rules":
        return None
    if not provider_healthy(provider):
        return None  # circuit open — don't pay the latency of a call we expect to fail
    try:
        if provider == "openai":
            out = _chat_completions(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {settings.openai_api_key}"},
                settings.ai_model_openai, prompt, system, max_tokens,
            )
        elif provider == "ollama":
            out = _chat_completions(
                f"{settings.ollama_base_url.rstrip('/')}/v1/chat/completions",
                {}, settings.ai_model_ollama, prompt, system, max_tokens,
            )
        else:
            out = _anthropic(prompt, system, max_tokens)
        _open_until.pop(provider, None)  # success resets the breaker
        return out
    except Exception:
        # Never let an AI outage break a finance operation — fall back silently,
        # and back off so the next requests stay fast.
        _open_until[provider] = time.time() + _COOLDOWN_SECS
        return None


ToolExecutor = Callable[[str, dict], dict]

_MAX_TOOL_TURNS = 4


def run_tool_loop(
    question: str, system: str, tools: list[dict], executor: ToolExecutor,
) -> dict | None:
    """Run an agentic tool-calling loop against the active LLM provider.

    `tools` are OpenAI-style function schemas: {"name", "description", "parameters"}.
    `executor(name, args)` performs the real, DB-grounded call and returns a JSON-able
    dict. Returns {"answer": str, "tool_calls": [{"name","arguments"}, ...]}, or None
    if no provider is configured/healthy or the call fails (caller should fall back to
    deterministic logic).
    """
    provider = active_provider()
    if provider == "rules" or not provider_healthy(provider):
        return None
    try:
        if provider == "openai":
            out = _chat_completions_tool_loop(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {settings.openai_api_key}"},
                settings.ai_model_openai, question, system, tools, executor,
            )
        elif provider == "ollama":
            out = _chat_completions_tool_loop(
                f"{settings.ollama_base_url.rstrip('/')}/v1/chat/completions",
                {}, settings.ai_model_ollama, question, system, tools, executor,
            )
        else:
            out = _anthropic_tool_loop(question, system, tools, executor)
        _open_until.pop(provider, None)
        return out
    except Exception:
        _open_until[provider] = time.time() + _COOLDOWN_SECS
        return None


def _chat_completions_tool_loop(
    url: str, headers: dict, model: str, question: str, system: str,
    tools: list[dict], executor: ToolExecutor,
) -> dict:
    """Tool-calling loop against any OpenAI-compatible /chat/completions API
    (OpenAI itself, or a local Ollama server, which mirrors the same wire format)."""
    oi_tools = [{"type": "function", "function": t} for t in tools]
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    calls_made: list[dict] = []
    for _ in range(_MAX_TOOL_TURNS):
        r = httpx.post(
            url,
            headers=headers,
            json={
                "model": model,
                "max_tokens": 700,
                "messages": messages,
                "tools": oi_tools,
            },
            timeout=_HTTP_TIMEOUT,
        )
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return {"answer": (msg.get("content") or "").strip(), "tool_calls": calls_made}
        messages.append(msg)
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except Exception:
                args = {}
            result = executor(name, args)
            calls_made.append({"name": name, "arguments": args})
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, default=str),
            })
    return {"answer": "I looked into that but couldn't finish in time — try rephrasing.",
            "tool_calls": calls_made}


def _anthropic_tool_loop(question: str, system: str, tools: list[dict], executor: ToolExecutor) -> dict:
    an_tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
        for t in tools
    ]
    messages: list[dict] = [{"role": "user", "content": question}]
    calls_made: list[dict] = []
    for _ in range(_MAX_TOOL_TURNS):
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": settings.ai_model_anthropic,
                "max_tokens": 700,
                "system": system,
                "messages": messages,
                "tools": an_tools,
            },
            timeout=_HTTP_TIMEOUT,
        )
        r.raise_for_status()
        content = r.json()["content"]
        messages.append({"role": "assistant", "content": content})
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        if not tool_uses:
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            return {"answer": text, "tool_calls": calls_made}
        results = []
        for tu in tool_uses:
            args = tu.get("input") or {}
            result = executor(tu["name"], args)
            calls_made.append({"name": tu["name"], "arguments": args})
            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": results})
    return {"answer": "I looked into that but couldn't finish in time — try rephrasing.",
            "tool_calls": calls_made}


def _chat_completions(url: str, headers: dict, model: str, prompt: str, system: str, max_tokens: int) -> str:
    r = httpx.post(
        url,
        headers=headers,
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system or "You are a finance assistant."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=_HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _anthropic(prompt: str, system: str, max_tokens: int) -> str:
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": settings.ai_model_anthropic,
            "max_tokens": max_tokens,
            "system": system or "You are a finance assistant.",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=_HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()
