"""The assistant's tool-calling loop.

1. Send the system prompt, the conversation and the tool list to the model.
2. If it asks for tools, run them and send the results back.
3. Repeat until it answers in text, at most LLM_MAX_TOOL_ROUNDS times.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session

from app.assistant.llm import LLMError, chat_completion
from app.assistant.prompt import build_system_prompt
from app.assistant.tools import TOOL_SPECS, ToolContext, run_tool
from app.config import Settings

log = logging.getLogger(__name__)

GAVE_UP = ("I couldn't finish looking that up. Please try a narrower question, "
           "for example one week or one venue at a time.")


@dataclass
class ChatResult:
    reply: str
    tools_used: list[str] = field(default_factory=list)


def answer(
    db: Session,
    settings: Settings,
    history: list[dict[str, str]],
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> ChatResult:
    """Answer the last user message in `history` ([{role, content}, ...], plain text turns)."""
    now = now or datetime.now(ZoneInfo(settings.timezone))
    messages: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt(now)}, *history]
    ctx = ToolContext(db=db, settings=settings)
    tools_used: list[str] = []
    prompt_tokens = completion_tokens = 0

    for round_no in range(settings.llm_max_tool_rounds + 1):
        data = chat_completion(messages, TOOL_SPECS, settings, client=client)
        usage = data.get("usage") or {}
        prompt_tokens += usage.get("prompt_tokens") or 0
        completion_tokens += usage.get("completion_tokens") or 0
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("The AI provider sent an unexpected response.")

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            log.info("Assistant answered: model=%s rounds=%s tools=%s prompt_tokens=%s completion_tokens=%s",
                     settings.llm_model, round_no, tools_used, prompt_tokens, completion_tokens)
            reply = (message.get("content") or "").strip()
            return ChatResult(reply=reply or "Sorry, I have no answer to that.", tools_used=tools_used)

        if round_no == settings.llm_max_tool_rounds:
            break  # out of rounds; don't run more tools

        # Echo the model's tool request, then one result per call, matched by id.
        messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls})
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name", "")
            result = run_tool(name, fn.get("arguments"), ctx)
            if name and name not in tools_used:
                tools_used.append(name)
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

    log.warning("Assistant gave up after %s tool rounds: tools=%s", settings.llm_max_tool_rounds, tools_used)
    return ChatResult(reply=GAVE_UP, tools_used=tools_used)
