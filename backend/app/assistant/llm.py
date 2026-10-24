"""Minimal client for any OpenAI-compatible Chat Completions endpoint (Groq, Gemini,
Hugging Face, Ollama, ...), using the httpx dependency the app already has."""

import logging
import time
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 2
MAX_RETRY_WAIT_S = 10.0


class LLMError(Exception):
    """A provider failure, with a message safe to show to the user (never contains the key)."""


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300]
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)[:300]
    return str(err or body)[:300]


def _raise_for(resp: httpx.Response, settings: Settings) -> None:
    status = resp.status_code
    if status in (401, 403):
        raise LLMError(f"{settings.llm_provider} rejected the API key. Check LLM_API_KEY.")
    if status == 404:
        raise LLMError(f"Model '{settings.llm_model}' was not found at {settings.llm_provider}. Check LLM_MODEL.")
    if status == 429:
        raise LLMError("The free AI quota is used up for the moment. Please try again in a minute.")
    if status >= 500:
        raise LLMError(f"{settings.llm_provider} is having problems right now. Please try again shortly.")
    detail = _error_detail(resp)
    if "tool" in detail.lower():
        # e.g. Groq's "tool_use_failed": the model wrote a malformed tool call.
        raise LLMError("The AI model made a mistake looking up the data. Please rephrase or try again.")
    raise LLMError(f"The AI request was rejected: {detail}")


def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    settings: Settings,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """POST /chat/completions and return the parsed JSON response."""
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.2,  # factual answers from tool data, little creativity needed
        "max_tokens": 1500,
    }
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    own_client = client is None
    client = client or httpx.Client(timeout=settings.llm_timeout_seconds)
    try:
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException:
                raise LLMError(f"{settings.llm_provider} took too long to answer. Please try again.")
            except httpx.HTTPError:
                raise LLMError(f"Could not reach {settings.llm_provider}. Check the internet connection and LLM_BASE_URL.")
            if resp.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                try:
                    wait = float(resp.headers.get("retry-after", 2 ** attempt))
                except ValueError:
                    wait = 2 ** attempt
                if wait <= MAX_RETRY_WAIT_S:
                    time.sleep(wait)
                    continue
            if resp.status_code >= 400:
                _raise_for(resp, settings)
            return resp.json()
        raise LLMError("The AI provider did not answer.")  # unreachable; keeps type checkers happy
    finally:
        if own_client:
            client.close()
