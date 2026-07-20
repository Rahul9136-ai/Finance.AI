"""Pluggable LLM provider. Selects OpenAI -> Anthropic -> None (rule-based).

The rest of the AI layer treats the LLM as optional: when no key is configured,
`complete()` returns None and skills use deterministic logic. This keeps the
whole system runnable and testable with zero external dependencies.
"""
from __future__ import annotations

import time

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
            out = _openai(prompt, system, max_tokens)
        else:
            out = _anthropic(prompt, system, max_tokens)
        _open_until.pop(provider, None)  # success resets the breaker
        return out
    except Exception:
        # Never let an AI outage break a finance operation — fall back silently,
        # and back off so the next requests stay fast.
        _open_until[provider] = time.time() + _COOLDOWN_SECS
        return None


def _openai(prompt: str, system: str, max_tokens: int) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.ai_model_openai,
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
