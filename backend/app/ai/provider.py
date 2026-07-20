"""Pluggable LLM provider. Selects OpenAI -> Anthropic -> None (rule-based).

The rest of the AI layer treats the LLM as optional: when no key is configured,
`complete()` returns None and skills use deterministic logic. This keeps the
whole system runnable and testable with zero external dependencies.
"""
from __future__ import annotations

import httpx

from app.core.config import settings


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


def complete(prompt: str, system: str = "", *, max_tokens: int = 500) -> str | None:
    """Return LLM completion text, or None if no provider is available/failing."""
    provider = active_provider()
    try:
        if provider == "openai":
            return _openai(prompt, system, max_tokens)
        if provider == "anthropic":
            return _anthropic(prompt, system, max_tokens)
    except Exception:
        # Never let an AI outage break a finance operation — fall back silently.
        return None
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
        timeout=30,
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
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()
