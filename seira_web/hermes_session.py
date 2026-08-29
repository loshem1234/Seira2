"""seira_web.hermes_session — Sanctum speaking to her REAL self.

This replaces the premise of ``seira_web/chat.py``'s original design.
That module talked to ``api.anthropic.com`` directly and hand-rolled a
tool-calling loop against a narrow, separately-maintained tool list
(her Psyche tools, plus later a manually curated ``hermes_tools``
whitelist). That was never the intended architecture: **she is the
Psyche, persona, and governance layer sitting atop the Hermes agent —
not a lighter-weight impersonation running beside it.**

``run_agent.AIAgent`` is Hermes's own stateless, per-call agent
interface — the same thing subagent delegation and the CLI use
underneath. Constructing one, per turn, IS running her as a real
Hermes agent:

* ``load_soul_identity=True`` serves her identity through the exact
  ``load_soul_md`` path wired in agent/prompt_builder.py — Unity +
  Intellect + Psyche, integrity-verified, halt-aware.
* ``skip_memory=False`` (the default) makes ``agent_init.init_agent``
  read ``memory.provider`` from config.yaml itself and load whatever
  is configured there — normally ``seira-psyche`` — giving her the
  full Psyche self-write tool surface with NO Sanctum-side tool list
  to maintain. ``seira_web/hermes_tools.py`` and its narrow whitelist
  are superseded by this; that module is no longer imported by
  ``chat.py`` in this mode. (It remains for reference/rollback, and is
  fully covered by its own tests.)
* ``enabled_toolsets`` / ``disabled_toolsets`` are read straight from
  config.yaml's own toolset settings when left ``None`` — an operator
  configures her tools exactly the way they'd configure any Hermes
  deployment (``hermes tools``), not through a second, Sanctum-only
  mechanism.
* The ``seira_governance`` plugin (Art. 26/35 delegation gate),
  registered once at plugin-manager init the same way any Hermes
  plugin is, governs her regardless of which front end reaches her —
  Sanctum included, automatically, with zero code here.

## What conversation_history round-trips as

Sanctum already stores her conversation turns via
``seira_web/conversations.py``. This module converts that stored
history into the plain ``{"role": ..., "content": ...}`` message list
``agent.conversation_loop.run_conversation`` expects, and reads
``result["messages"]`` back out to persist — the same shape, so no
migration of stored conversations is needed.

## Honesty about what could and couldn't be verified here

Every piece of this wiring is confirmed against the real
``run_agent.py`` / ``agent/agent_init.py`` / ``agent/conversation_loop.py``
source: constructor signature, config-driven memory-provider loading,
callback call sites (``agent/tool_executor.py``), and the
``run_conversation`` return shape. What could NOT be verified in this
sandbox is a live end-to-end turn — that needs a real
``ANTHROPIC_API_KEY``, the full Hermes dependency tree installed, and
the toolsets/model your deployment actually has configured. Test this
in a real environment before relying on it, the same way you would
test any first deployment of new infrastructure.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SEIRA_MODEL = os.environ.get("SEIRA_MODEL", "claude-sonnet-5")


def _build_agent(session_id: str, emit: Callable[[Dict[str, Any]], None]):
    """Construct one AIAgent for this turn, wired to speak as her real
    self and to report tool activity through Sanctum's existing
    ``emit()`` event contract — no UI-side changes needed; the events
    her real tools produce simply replace the narrower set that used
    to originate from the hand-rolled loop."""
    from run_agent import AIAgent

    def _tool_start(tool_call_id, name, display_args):
        emit({"event": "tool", "tool": name, "label": name,
             "input": display_args, "tool_call_id": tool_call_id})

    def _tool_complete(tool_call_id, name, display_args, display_result):
        emit({"event": "tool_result", "tool": name,
             "result": display_result, "tool_call_id": tool_call_id})

    def _reasoning(reasoning_text):
        # agent/chat_completion_helpers.py calls this with a plain string
        # of reasoning text as it arrives — her live reasoning, shown in
        # the chat the way the Hermes UI shows it.
        emit({"event": "reasoning", "text": reasoning_text})

    def _thinking(label):
        # Called with short status strings ("🤔 Thinking..."), and with
        # "" to clear — map to the existing phase/activity line.
        if label:
            emit({"event": "phase", "label": label})

    def _stream_delta(delta):
        # agent/conversation_loop.py streams text deltas here and sends
        # None as the end-of-stream flush marker.
        if delta is None:
            emit({"event": "delta_end"})
        else:
            emit({"event": "delta", "text": delta})

    return AIAgent(
        provider="anthropic",
        api_mode="anthropic_messages",
        model=SEIRA_MODEL,
        session_id=session_id,
        load_soul_identity=True,   # her real identity, verified, halt-aware
        skip_memory=False,         # config-driven: loads memory.provider from config.yaml
        skip_context_files=True,   # a web chat has no project cwd to layer in
        tool_start_callback=_tool_start,
        tool_complete_callback=_tool_complete,
        reasoning_callback=_reasoning,
        thinking_callback=_thinking,
        stream_delta_callback=_stream_delta,
        platform="sanctum",
    )


def run_turn_via_hermes(
    conv_id: str,
    user_message: str,
    history: List[Dict[str, Any]],
    emit: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Run one turn as a real Hermes agent turn.

    ``history`` is Sanctum's already-stored prior messages, in the
    same ``{"role", "content"}`` shape ``run_conversation`` expects.
    Returns ``{"reply": str, "messages": List[Dict]}`` — persist
    ``messages`` as the new history for the next turn, exactly as the
    direct-API path in chat.py already does with its own message list.
    """
    emit({"event": "phase", "label": "Thinking"})
    agent = _build_agent(session_id=conv_id or str(uuid.uuid4()), emit=emit)
    from agent.conversation_loop import run_conversation

    result = run_conversation(
        agent,
        user_message=user_message,
        conversation_history=history,
    )
    final = result.get("final_response") or result.get("error") or ""
    emit({"event": "reply", "text": final})
    return {"reply": final, "messages": result.get("messages", history)}
