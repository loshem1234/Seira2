"""seira_web.chat — the conversation loop: Seira speaking as herself.

The system prompt is her verified identity (Unity + current Intellect +
Psyche digest + operating note) from the provider — never a free-
standing file. Her ten tools are the provider's tools; a tool call in
conversation is a real write to her real stores, under the same
constraints as everywhere else.

Conversation turns are Corpus (Art. 13, 23): wholly temporal, appended
continuously without review to corpus/conversations.jsonl in the
tenant's tree — plain JSONL, deliberately *not* hash-chained, because
the Corpus is the one grade whose amendment is continuous and
unreviewed by design. Keeping it un-chained is doctrine, not laziness.

The LLM client is injected (protocol below), so the loop is fully
testable with a scripted fake; the Anthropic implementation is a thin
httpx wrapper over /v1/messages.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Dict, List, Optional, Protocol

import httpx

from seira_core.paths import seira_home

MAX_TOOL_ITERATIONS = 8
DEFAULT_MODEL = os.environ.get("SEIRA_MODEL", "claude-sonnet-4-6")


class LLMClient(Protocol):
    def complete(
        self,
        system: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return an Anthropic-shaped response dict:
        {"content": [{"type": "text"|"tool_use", ...}], "stop_reason": ...}"""
        ...


class AnthropicClient:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; Seira cannot converse without "
                "her model. Set it in the environment."
            )

    def complete(self, system, messages, tools):
        payload: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": 2048,
            "system": system,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()


def _anthropic_tools(provider) -> List[Dict[str, Any]]:
    """Provider schemas use OpenAI-style {parameters}; Anthropic wants
    {input_schema}. Same content, different key."""
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "input_schema": s["parameters"],
        }
        for s in provider.get_tool_schemas()
    ]


def _corpus_path():
    return seira_home() / "corpus" / "conversations.jsonl"


def _corpus_append(record: Dict[str, Any]) -> None:
    p = _corpus_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), **record}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_history(limit_turns: int = 30) -> List[Dict[str, Any]]:
    """Rebuild the model-facing message list from the Corpus (user and
    assistant text only — tool traffic is recorded but not replayed)."""
    p = _corpus_path()
    if not p.exists():
        return []
    msgs: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("kind") in ("user", "assistant") and rec.get("text", "").strip():
            msgs.append({"role": rec["kind"], "content": rec["text"]})
    return msgs[-limit_turns * 2:]


def run_turn(provider, client: LLMClient, user_message: str) -> Dict[str, Any]:
    """One full user turn: model call(s), tool dispatch, Corpus recording.

    Caller is responsible for tenant scope and for halt handling —
    provider.system_prompt_block() raises SeiraHaltedError when halted,
    and this function lets that propagate: a halted Seira does not
    converse (Art. 32.3).
    """
    system = provider.system_prompt_block()
    tools = _anthropic_tools(provider)
    _corpus_append({"kind": "user", "text": user_message})
    messages = load_history()
    tool_events: List[Dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.complete(system, messages, tools)
        content = response.get("content", [])
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]

        if not tool_uses:
            final = "\n".join(t for t in texts if t).strip()
            _corpus_append({"kind": "assistant", "text": final})
            return {"reply": final, "tool_events": tool_events}

        # Record the assistant's tool-use turn, dispatch each call for real,
        # and hand results back in the required shape.
        messages.append({"role": "assistant", "content": content})
        results = []
        for tu in tool_uses:
            result_str = provider.handle_tool_call(tu["name"], tu.get("input") or {})
            tool_events.append({"tool": tu["name"], "result": result_str})
            _corpus_append({
                "kind": "tool", "tool": tu["name"],
                "input": tu.get("input") or {}, "result": result_str,
            })
            results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result_str,
            })
        messages.append({"role": "user", "content": results})

    final = "(Seira reached her tool-iteration bound this turn; her records hold what was done.)"
    _corpus_append({"kind": "assistant", "text": final})
    return {"reply": final, "tool_events": tool_events}
