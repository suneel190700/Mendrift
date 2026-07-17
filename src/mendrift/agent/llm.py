"""LLM layer with a deliberately thin interface.

Nodes never import the Anthropic SDK directly. They call:
    llm.invoke(messages, tools=None) -> {"content": str, "tool_calls": [...]}

Two implementations:
  AnthropicLLM — production, wraps anthropic.Anthropic()
  ScriptedLLM  — tests, replays fixture scripts deterministically (Phase 6)

This is also where MODEL ROUTING lives: each graph step asks for its role
and ROUTER_TABLE maps role -> model. Routing in a code table, not prompts.
"""
from __future__ import annotations

import json
from typing import Any

import re

ROUTER_TABLE = {
    "classify": "claude-haiku-4-5-20251001",
    "diagnose": "claude-sonnet-4-6",
    "verify": "claude-haiku-4-5-20251001",
}


class AnthropicLLM:
    """Production adapter. One instance per role so usage is attributable."""

    def __init__(self, role: str):
        import anthropic  # lazy import: tests never need the SDK

        self.role = role
        self.model = ROUTER_TABLE[role]
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.usage: list[dict] = []

    def invoke(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        resp = self.client.messages.create(**kwargs)
        self.usage.append({"in": resp.usage.input_tokens, "out": resp.usage.output_tokens})

        content, tool_calls = "", []
        for block in resp.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "args": block.input})
        return {"content": content, "tool_calls": tool_calls}


class ScriptedLLM:
    """Deterministic test double for Phase 6: pops canned responses off a script."""

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

    # 1) the whole message is JSON
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) last ```json fenced block anywhere in the message
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for block in reversed(blocks):
        try:
            return json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue

    # 3) last raw {...} object in the text
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    decoder = json.JSONDecoder()
    for i in reversed(starts):
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    return fallback if fallback is not None else {}