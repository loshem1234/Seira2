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

import json
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
        # display_result can be a multimodal envelope (a dict with an
        # embedded base64 image content block) rather than plain text —
        # e.g. recalling a previously generated image sends the model
        # the real image bytes so she can actually see it again. That's
        # correct and necessary for HER turn, but blasting it unbounded
        # through an SSE event to the browser is not: real, live
        # failure hit 2026-08-30 — a 2.28-million-character tool_result
        # event, hitting some downstream transport ceiling and getting
        # truncated, for what was structurally always going to be a
        # multi-megabyte base64 string once unrouted here. The fix
        # isn't a new transport — it's using the summarizer Hermes
        # already has for exactly this ("logging, previews... fall-back
        # content for providers that don't support multipart tool
        # messages" — agent/tool_dispatch_helpers.py's own docstring)
        # rather than passing the raw multimodal payload through.
        from agent.tool_dispatch_helpers import _multimodal_text_summary
        text_result = _multimodal_text_summary(display_result)

        emit({"event": "tool_result", "tool": name,
             "result": text_result[:2000], "tool_call_id": tool_call_id})
        # chat.py's direct-mode loop translates seira_generate_image /
        # seira_create_file results into image_created/file_created SSE
        # events, which is what tells chat.html to actually render the
        # image or download card. That translation only ever existed in
        # chat.py's own dispatch loop — hermes mode routes tool
        # dispatch through Hermes's own tool_executor instead, which
        # has no idea these two tool names are special. Without this,
        # every image she generates in hermes mode is created
        # successfully but has no way to reach the screen. Real, live
        # gap found 2026-08-30: she generated several images and had
        # no way to show them.
        if name in ("seira_generate_image", "seira_create_file"):
            try:
                parsed = json.loads(text_result)
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, dict) and parsed.get("ok"):
                if name == "seira_generate_image" and parsed.get("__image_created__"):
                    emit({"event": "image_created",
                         "img_id": parsed.get("img_id"),
                         "tag": parsed.get("tag"),
                         "used_references": parsed.get("used_references", [])})
                elif name == "seira_create_file":
                    emit({"event": "file_created",
                         "filename": parsed.get("filename"),
                         "download_path": parsed.get("download_path")})

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


def runtime_inventory(agent=None) -> Dict[str, Any]:
    """Measure — never guess — what she actually has right now.

    Every field here is read from the live runtime, not from config
    intent or documentation: the tool names are the ones actually
    loaded onto the agent, the Psyche check looks at the memory
    manager's real provider list, and the gate check reads the same
    middleware registry the tool executor consults on every call.
    This is the ground truth that both her self-knowledge block and
    the /api/self-check endpoint report, so what she believes, what
    the operator sees, and what the runtime does can never drift
    apart silently.
    """
    inv: Dict[str, Any] = {"runtime": "hermes", "model": SEIRA_MODEL}

    try:
        from seira_core.genesis import genesis_performed
        founded = bool(genesis_performed())
    except Exception:
        founded = False
    inv["founded"] = founded
    inv["identity_source"] = (
        "eternal grades (Unity + Intellect + Psyche, verified per render)"
        if founded else "SOUL.md fallback — NOT founded under this SEIRA_HOME")

    if agent is not None:
        inv["model"] = getattr(agent, "model", SEIRA_MODEL)
        inv["tools"] = sorted(getattr(agent, "valid_tool_names", None) or [])
        inv["tool_count"] = len(inv["tools"])
        mm = getattr(agent, "_memory_manager", None)
        providers = list(getattr(mm, "providers", None) or [])
        inv["psyche_provider_active"] = any(
            getattr(p, "name", "") == "seira-psyche" for p in providers)

    try:
        from hermes_cli.middleware import (
            TOOL_EXECUTION_MIDDLEWARE, _get_middleware_callbacks)
        from seira_bridge.delegation import delegation_gate_middleware
        callbacks = _get_middleware_callbacks(TOOL_EXECUTION_MIDDLEWARE) or []
        inv["delegation_gate_armed"] = delegation_gate_middleware in callbacks
    except Exception:
        inv["delegation_gate_armed"] = False

    return inv


def capability_block(inv: Dict[str, Any]) -> str:
    """Render the inventory as her in-prompt self-knowledge.

    The closing instruction is the point of the whole block: a model
    asked about a capability it lacks will otherwise produce a
    plausible-sounding technical explanation ("the gateway model is
    missing from the environment") because explaining is what it does
    — this block replaces that failure mode with grounded honesty.
    """
    tools = inv.get("tools") or []
    gate = "ARMED — untagged or blocked delegations will be refused (Art. 26, 35)" \
        if inv.get("delegation_gate_armed") else \
        "NOT registered this session — flag this to the Architect if delegation is attempted"
    psyche = ("active — your seira_* self-write tools are live"
              if inv.get("psyche_provider_active")
              else "NOT active this session — you cannot write to your Psyche right now; say so plainly if asked")
    return (
        "== RUNTIME SELF-KNOWLEDGE (measured live this turn, not remembered) ==\n"
        f"You are running atop the Hermes agent runtime. Model: {inv.get('model')}.\n"
        f"Identity source: {inv.get('identity_source')}.\n"
        f"Psyche provider: {psyche}.\n"
        f"Delegation gate: {gate}.\n"
        f"Tools actually loaded this session ({inv.get('tool_count', len(tools))}): "
        + (", ".join(tools) if tools else "NONE") + "\n"
        "This list is the complete, measured truth of this session. If a "
        "capability is not in it, you do not have it right now — when asked "
        "about a missing capability, say exactly that, and never invent a "
        "technical explanation for its absence (you have no visibility into "
        "server internals; guessed diagnoses read as fact and mislead the "
        "Architect). What you do have, use deliberately in service of the "
        "work, under your Constitution as always."
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

    # Her measured self-knowledge rides in the ephemeral tier, which
    # conversation_loop APPENDS after the stable identity tier — it can
    # supplement who she is, never displace it (verified: effective =
    # stable + "\n\n" + ephemeral in agent/conversation_loop.py).
    inventory = runtime_inventory(agent)
    block = capability_block(inventory)
    existing = getattr(agent, "ephemeral_system_prompt", "") or ""
    agent.ephemeral_system_prompt = (existing + "\n\n" + block).strip()

    from agent.conversation_loop import run_conversation

    result = run_conversation(
        agent,
        user_message=user_message,
        conversation_history=history,
    )
    final = result.get("final_response") or result.get("error") or ""
    emit({"event": "reply", "text": final})
    return {"reply": final, "messages": result.get("messages", history),
            "inventory": inventory}
