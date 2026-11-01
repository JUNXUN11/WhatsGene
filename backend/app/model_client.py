"""Minimal OpenAI-compatible chat client for Muse Spark Open via Modal.

One function, one timeout, no retries: callers (app/agent.py) decide when a
live call is allowed and always fall back to deterministic answers. Every
failure becomes ModelError so no stack trace decides user-visible behaviour.
"""
from __future__ import annotations

from typing import Any

from . import config


class ModelError(RuntimeError):
    pass


def completions_url() -> str:
    base = (config.MUSE_BASE_URL or "").strip().rstrip("/")
    if not base:
        raise ModelError("MUSE_BASE_URL is not set.")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def chat_completion(*, system: str, user: str, max_tokens: int) -> dict[str, Any]:
    """Return {"text": str, "usage": dict | None}. Raises ModelError."""
    import httpx

    if not (config.MUSE_API_KEY or "").strip():
        raise ModelError("MUSE_API_KEY is not set.")
    try:
        with httpx.Client(timeout=config.MODEL_TIMEOUT_SECONDS) as client:
            response = client.post(
                completions_url(),
                headers={"Authorization": f"Bearer {config.MUSE_API_KEY}"},
                json={"model": config.MUSE_MODEL,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}],
                      "max_tokens": max_tokens,
                      "temperature": 0.2},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ModelError(f"Muse call failed: {exc}") from exc
    try:
        text = payload["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError(f"Muse returned an unexpected payload: {exc}") from exc
    if not text.strip():
        raise ModelError("Muse returned an empty answer.")
    return {"text": text.strip(), "usage": payload.get("usage")}
