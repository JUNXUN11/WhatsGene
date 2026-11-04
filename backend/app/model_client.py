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


def completions_url(base_url: str | None = None) -> str:
    base = (base_url or config.MUSE_BASE_URL or "").strip().rstrip("/")
    if not base:
        raise ModelError("MUSE_BASE_URL is not set.")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def chat_completion(*, system: str, user: str, max_tokens: int,
                    api_key: str | None = None, base_url: str | None = None,
                    model: str | None = None, timeout: float | None = None) -> dict[str, Any]:
    """Return {"text": str, "usage": dict | None}. Raises ModelError.

    Per-user credentials (Settings) override the server env when given.
    """
    import httpx

    key = (api_key or config.MUSE_API_KEY or "").strip()
    if not key:
        raise ModelError("MUSE_API_KEY is not set.")
    body: dict[str, Any] = {"model": (model or config.MUSE_MODEL),
                            "messages": [{"role": "system", "content": system},
                                         {"role": "user", "content": user}],
                            "max_tokens": max_tokens,
                            "temperature": 0.2}
    if config.MODEL_REASONING_EFFORT:
        body["reasoning_effort"] = config.MODEL_REASONING_EFFORT
    try:
        with httpx.Client(timeout=timeout or config.MODEL_TIMEOUT_SECONDS) as client:
            response = client.post(
                completions_url(base_url),
                headers={"Authorization": f"Bearer {key}"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ModelError(f"Muse call failed: {exc}") from exc
    try:
        choice = payload["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError(f"Muse returned an unexpected payload: {exc}") from exc
    if not text.strip():
        if choice.get("finish_reason") == "length":
            raise ModelError(f"Muse ran out of tokens before answering (max_tokens={max_tokens}); "
                             "raise MODEL_MAX_TOKENS.")
        raise ModelError("Muse returned an empty answer.")
    return {"text": text.strip(), "usage": payload.get("usage")}
