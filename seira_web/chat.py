"""seira_web.chat — the conversation loop, now conversation-scoped and
event-emitting so the UI can show her real activity as it happens.

Events emitted through the callback (each a dict with "event"):
    {"event": "phase", "label": "Reading who she is"}
    {"event": "phase", "label": "Thinking"}
    {"event": "tool", "tool": "seira_psyche_record",
     "label": "Writing her Psyche"}
    {"event": "reply", "text": "...", "assistant_id": 7}

The labels come from her REAL tool calls — nothing is rendered that did
not actually run. When new capabilities (search, delegation) join her
tool surface, their activity appears here with no UI changes.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, Protocol

import httpx

from seira_web import conversations as convs

MAX_TOOL_ITERATIONS = 8
DEFAULT_MODEL = os.environ.get("SEIRA_MODEL", "claude-sonnet-4-6")

TOOL_LABELS = {
    "seira_psyche_record": "Writing her Psyche",
    "seira_psyche_recall": "Consulting her character",
    "seira_psyche_engage_affinity": "Weighing an affinity",
    "seira_propose_establishment": "Opening a proposal on herself",
    "seira_falsification_attempt": "Attempting falsification",
    "seira_proposal_conclude": "Concluding a proposal",
    "seira_instrument_spawn": "Spawning an Instrument",
    "seira_instrument_execute": "Recording an Instrument's work",
    "seira_paradigm_revise": "Revising a paradigm",
    "seira_skill_authorize": "Authorizing a skill",
}


class LLMClient(Protocol):
    def complete(self, system: str, messages: List[Dict[str, Any]],
                 tools: List[Dict[str, Any]]) -> Dict[str, Any]: ...


class AnthropicClient:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; Seira cannot converse without "
                "her model.")

    def complete(self, system, messages, tools):
        payload: Dict[str, Any] = {
            "model": self._model, "max_tokens": 2048,
            "system": system, "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self._api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json()


def _anthropic_tools(provider) -> List[Dict[str, Any]]:
    return [{"name": s["name"], "description": s["description"],
             "input_schema": s["parameters"]}
            for s in provider.get_tool_schemas()]


def run_turn(
    provider,
    client: LLMClient,
    conv_id: str,
    user_message: Optional[str],
    emit: Optional[Callable[[Dict[str, Any]], None]] = None,
    attachment: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """One full turn in a conversation.

    user_message None means: re-run against the existing live thread
    (regeneration - the caller has already superseded the old answer).
    Caller is responsible for tenant scope and halt handling; a halted
    Seira raises from system_prompt_block and does not converse.
    """
    emit = emit or (lambda e: None)
    emit({"event": "phase", "label": "Reading who she is"})
    system = provider.system_prompt_block()
    tools = _anthropic_tools(provider)

    if attachment is not None:
        convs.append(conv_id, "attachment", name=attachment["name"])
        user_message = (
            f"[Attached document: {attachment['name']}]\n"
            f"{attachment['text']}\n\n{user_message or ''}"
        ).strip()

    if user_message is not None:
        convs.append(conv_id, "user", text=user_message)
        convs.touch(conv_id, maybe_title_from=user_message)

    messages: List[Dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]}
        for m in convs.model_history(conv_id)
    ]
    tool_events: List[Dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        emit({"event": "phase", "label": "Thinking"})
        response = client.complete(system, messages, tools)
        content = response.get("content", [])
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]

        if not tool_uses:
            final = "\n".join(t for t in texts if t).strip()
            rec = convs.append(conv_id, "assistant", text=final)
            convs.touch(conv_id)
            emit({"event": "reply", "text": final, "assistant_id": rec["id"]})
            return {"reply": final, "assistant_id": rec["id"],
                    "tool_events": tool_events}

        messages.append({"role": "assistant", "content": content})
        results = []
        for tu in tool_uses:
            label = TOOL_LABELS.get(tu["name"], tu["name"])
            emit({"event": "tool", "tool": tu["name"], "label": label})
            result_str = provider.handle_tool_call(tu["name"], tu.get("input") or {})
            tool_events.append({"tool": tu["name"], "label": label,
                                "result": result_str})
            convs.append(conv_id, "tool", tool=tu["name"], label=label,
                         input=tu.get("input") or {}, result=result_str)
            results.append({"type": "tool_result", "tool_use_id": tu["id"],
                            "content": result_str})
        messages.append({"role": "user", "content": results})

    final = ("(Seira reached her tool-iteration bound this turn; "
             "her records hold what was done.)")
    rec = convs.append(conv_id, "assistant", text=final)
    emit({"event": "reply", "text": final, "assistant_id": rec["id"]})
    return {"reply": final, "assistant_id": rec["id"], "tool_events": tool_events}


def regenerate(provider, client, conv_id: str, emit=None) -> Dict[str, Any]:
    """Supersede her last answer (recorded, never deleted) and answer the
    same live user message again."""
    last_a = convs.last_live_assistant(conv_id)
    if last_a is None:
        raise ValueError("Nothing to regenerate yet.")
    convs.supersede_from(conv_id, last_a["id"])
    return run_turn(provider, client, conv_id, user_message=None, emit=emit)


def edit_and_rerun(provider, client, conv_id: str, target_id: int,
                   new_text: str, emit=None) -> Dict[str, Any]:
    """Supersede a user message (and everything after it) and continue
    from the edited text. The abandoned branch remains in the record."""
    if not new_text.strip():
        raise ValueError("Edited message must not be empty.")
    convs.supersede_from(conv_id, target_id)
    return run_turn(provider, client, conv_id, user_message=new_text.strip(),
                    emit=emit)
