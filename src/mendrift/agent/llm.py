"""LLM layer with a deliberately thin interface.

Nodes call llm.invoke(messages, tools=None) -> {"content": str, "tool_calls": [...]}.
Production wraps LangChain's ChatAnthropic (bind_tools handles the tool-call
protocol); tests use ScriptedLLM. Model ROUTING lives in ROUTER_TABLE — role
-> model, in code, not prompts.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("mendrift.llm")

ROUTER_TABLE = {
    "classify": "claude-haiku-4-5-20251001",
    "diagnose": "claude-sonnet-4-6",
    "verify": "claude-haiku-4-5-20251001",
}

# Generous ceiling: a diagnosis narrative plus structured JSON must never be
# truncated mid-object (truncated JSON silently falls back to incident_only).
MAX_TOKENS = 4096


class AnthropicLLM:
    """Production adapter over LangChain ChatAnthropic. One instance per role."""

    def __init__(self, role: str):
        from langchain_anthropic import ChatAnthropic

        self.role = role
        self.model = ROUTER_TABLE[role]
        self._chat = ChatAnthropic(model=self.model, max_tokens=MAX_TOKENS)
        self.usage: list[dict] = []

    def invoke(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        lc_messages: list[Any] = []
        for m in messages:
            role, content = m["role"], m.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            elif role == "system":
                lc_messages.append(SystemMessage(content=content))

        chat = self._chat.bind_tools(tools) if tools else self._chat
        resp = chat.invoke(lc_messages)

        um = getattr(resp, "usage_metadata", None) or {}
        self.usage.append({"in": um.get("input_tokens", 0), "out": um.get("output_tokens", 0)})

        # Guard: a stop for length means the reply (and any JSON in it) is
        # likely cut off. Warn loudly — this is the failure that silently
        # dropped a correct rollback decision to the incident_only fallback.
        finish = (resp.response_metadata or {}).get("stop_reason")
        if finish == "max_tokens":
            logger.warning(
                "role=%s hit max_tokens (%d) — reply may be truncated, JSON parse may fall back",
                self.role, MAX_TOKENS,
            )

        text = resp.content if isinstance(resp.content, str) else _text_from_blocks(resp.content)
        tool_calls = [
            {"id": tc.get("id", ""), "name": tc["name"], "args": tc["args"]}
            for tc in (resp.tool_calls or [])
        ]
        return {"content": text, "tool_calls": tool_calls}


def _text_from_blocks(content: list) -> str:
    """ChatAnthropic may return content as a list of blocks; join the text ones.
    Handles dict-style blocks, object-style blocks, and bare strings."""
    parts = []
    for b in content:
        if isinstance(b, str):
            parts.append(b)
        elif isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif hasattr(b, "text"):
            parts.append(b.text)
    return "".join(parts)


class ScriptedLLM:
    """Deterministic test double: pops canned responses off a script."""

    def __init__(self, script: list[dict]):
        self.script = list(script)

    def invoke(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        if not self.script:
            return {"content": json.dumps({"error": "script exhausted"}), "tool_calls": []}
        step = self.script.pop(0)
        return {"content": step.get("content", ""), "tool_calls": step.get("tool_calls", [])}


def anthropic_factory(role: str) -> AnthropicLLM:
    return AnthropicLLM(role)


def parse_json_content(content: str, fallback: dict | None = None) -> dict:
    """Extract a JSON object from a model reply that may wrap it in prose/fences."""
    text = content.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for block in reversed(blocks):
        try:
            return json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    decoder = json.JSONDecoder()
    for i in reversed(starts):
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue
    if fallback is not None:
        logger.warning("parse_json_content fell back to default — reply had no parseable JSON")
        return fallback
    return {}