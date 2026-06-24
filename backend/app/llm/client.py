"""Thin LLM wrapper around the OpenAI-compatible API.

GLM 5.2 (Zhipu) and OpenRouter both expose an OpenAI-style /chat/completions
endpoint, so a single client works for both — we just swap base_url + key + model.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class LLMClient:
    """Single entry point for all LLM calls in the platform."""

    def __init__(self) -> None:
        cfg = settings.active_llm
        if not cfg["api_key"]:
            logger.warning(
                "No API key set for provider '{}'. LLM calls will fail until configured.",
                settings.llm_provider,
            )
        self.model = cfg["model"]
        # OpenRouter recommends these headers for free-tier attribution.
        default_headers = {}
        if settings.llm_provider == "openrouter":
            default_headers = {
                "HTTP-Referer": "https://localhost",
                "X-Title": "AI Lead Gen Platform",
            }
        self._client = OpenAI(
            api_key=cfg["api_key"] or "missing-key",
            base_url=cfg["base_url"],
            default_headers=default_headers or None,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> str:
        """Run a chat completion and return the assistant text."""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Run a chat completion expecting JSON, and parse it defensively."""
        raw = self.chat(system, user, temperature=temperature, max_tokens=max_tokens)
        return _extract_json(raw)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response, tolerating code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # strip ```json ... ``` fences
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        logger.error("LLM did not return JSON. Raw: {}", text[:300])
        return {}
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM JSON: {} | raw={}", exc, text[:300])
        return {}


# Module-level singleton — reused across requests.
llm = LLMClient()
