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
MAX_CONTINUATIONS = 4  # bounded auto-continue on text truncation
DEFAULT_MODEL = os.environ.get("SEIRA_MODEL", "claude-sonnet-5")

# Curated, current lineup (see product_information); Mythos-tier is
# restricted access and deliberately not offered here. 4.6 kept as an
# explicit legacy option since it was this deployment's original default.
AVAILABLE_MODELS = [
    {"id": "claude-sonnet-5", "label": "Claude Sonnet 5 (recommended)"},
    {"id": "claude-opus-4-8", "label": "Claude Opus 4.8"},
    {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 (fastest)"},
    {"id": "claude-fable-5", "label": "Claude Fable 5"},
    {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6 (legacy)"},
]

# Soft, instruction-based only — never a hard mid-sentence truncation,
# which would undo the truncation fix. She is asked to keep to it; she
# is not clipped to it.
# The web search tool's version string moves as Anthropic revises it
# (multiple versions have coexisted in the wild). Configurable rather
# than hard-guessed so a deprecation doesn't require a code change.
WEB_SEARCH_TOOL_TYPE = os.environ.get("SEIRA_WEB_SEARCH_TOOL", "web_search_20250305")
WEB_SEARCH_MAX_USES = int(os.environ.get("SEIRA_WEB_SEARCH_MAX_USES", "5"))

LENGTH_INSTRUCTIONS = {
    "short": "Keep this reply to roughly 100 characters or fewer — a single short sentence.",
    "medium": "Keep this reply to roughly 500 characters or fewer — a short paragraph.",
    "long": "Keep this reply to roughly 2000 characters or fewer.",
}
# Sonnet-class models support a high output ceiling; 2048 (the old default
# here) was far below it and is exactly what was truncating her replies
# and cutting comprehensive skill definitions mid-JSON. Configurable so it
# can be raised further per model without a code change.
DEFAULT_MAX_TOKENS = int(os.environ.get("SEIRA_MAX_TOKENS", "16000"))
# Larger generations take longer; the old 120s timeout would itself cut
# off a long, otherwise-successful response.
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("SEIRA_REQUEST_TIMEOUT", "600"))

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
    "seira_generate_image": "Generating an image",
}


class LLMClient(Protocol):
    def complete(self, system: str, messages: List[Dict[str, Any]],
                 tools: List[Dict[str, Any]]) -> Dict[str, Any]: ...


class AnthropicClient:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 max_tokens: int = DEFAULT_MAX_TOKENS):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._max_tokens = max_tokens
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; Seira cannot converse without "
                "her model.")

    def complete(self, system, messages, tools):
        payload: Dict[str, Any] = {
            "model": self._model, "max_tokens": self._max_tokens,
            "system": system, "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self._api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()


def _anthropic_tools(provider, web_search: bool = False) -> List[Dict[str, Any]]:
    tools = [{"name": s["name"], "description": s["description"],
             "input_schema": s["parameters"]}
            for s in provider.get_tool_schemas()]
    if web_search:
        # Anthropic's native server-side tool: no seira_core write path,
        # no filesystem/shell access — safe to offer without touching the
        # per-tenant sandbox question (D40).
        tools.append({"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search",
                      "max_uses": WEB_SEARCH_MAX_USES})
    return tools


def _tool_input_is_complete(tool_use_block: Dict[str, Any]) -> bool:
    """A tool_use block cut off by max_tokens still deserializes (the API
    guarantees valid JSON for what was emitted) but is missing whatever
    came after the cut. The practical, generic signal is emptiness: a
    call truncated early enough to matter typically loses its content
    fields (e.g. a skill's paradigm text) before it loses everything.
    This only matters combined with the caller's stop_reason check.
    """
    inp = tool_use_block.get("input")
    return isinstance(inp, dict) and len(inp) > 0


def _drain_truncation(client, system, messages, tools, response, emit):
    """If a pure-text reply hit the max_tokens ceiling, transparently
    continue it (bounded) and concatenate — the fix for 'her replies get
    cut off, this should never happen' in the ordinary long-answer case.
    Tool-call truncation is handled by the caller instead: a call cut
    mid-JSON must not be silently stitched back together and executed.
    """
    content = response.get("content", [])
    stop_reason = response.get("stop_reason")
    tool_uses = [b for b in content if b.get("type") == "tool_use"]
    if stop_reason != "max_tokens" or tool_uses:
        return content, stop_reason

    continuations = 0
    while stop_reason == "max_tokens" and not tool_uses and continuations < MAX_CONTINUATIONS:
        emit({"event": "phase", "label": "Continuing her answer (it ran long)"})
        partial_text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        cont_messages = messages + [{"role": "assistant", "content": partial_text}]
        response = client.complete(system, cont_messages, tools)
        more = response.get("content", [])
        stop_reason = response.get("stop_reason")
        tool_uses = [b for b in more if b.get("type") == "tool_use"]
        more_text = "".join(b.get("text", "") for b in more if b.get("type") == "text")
        content = [{"type": "text", "text": partial_text + more_text}] + \
            [b for b in more if b.get("type") != "text"]
        continuations += 1
    return content, stop_reason


def run_turn(
    provider,
    client: LLMClient,
    conv_id: str,
    user_message: Optional[str],
    emit: Optional[Callable[[Dict[str, Any]], None]] = None,
    attachment: Optional[Dict[str, str]] = None,
    length_pref: Optional[str] = None,
    web_search: bool = False,
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
    if length_pref and length_pref in LENGTH_INSTRUCTIONS:
        system += (
            "\n\n---\n# RESPONSE LENGTH PREFERENCE (Architect's UI setting, "
            "not identity)\n" + LENGTH_INSTRUCTIONS[length_pref]
        )
    tools = _anthropic_tools(provider, web_search=web_search)

    if attachment is not None:
        if attachment.get("kind") == "image":
            convs.append(conv_id, "attachment", name=attachment["name"])
            user_message = (user_message or "").strip()
        else:
            convs.append(conv_id, "attachment", name=attachment["name"])
            user_message = (
                f"[Attached document: {attachment['name']}]\n"
                f"{attachment['text']}\n\n{user_message or ''}"
            ).strip()

    if user_message is not None:
        record_fields: Dict[str, Any] = {"text": user_message}
        if attachment is not None and attachment.get("kind") == "image":
            record_fields["image_ref"] = attachment["img_id"]
            record_fields["image_name"] = attachment["name"]
        rec = convs.append(conv_id, "user", **record_fields)
        convs.touch(conv_id, maybe_title_from=user_message)
        emit({"event": "user_recorded", "id": rec["id"]})

    messages: List[Dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]}
        for m in convs.model_history(conv_id)
    ]
    # The current turn's image, if any, replaces the plain-text last user
    # message with a proper multi-block message carrying the real bytes —
    # this is the one place a real image ever reaches the model; past
    # turns replay as a text marker only (see conversations.model_history).
    if attachment is not None and attachment.get("kind") == "image":
        from seira_web.images import get_image_block
        block = get_image_block(attachment["img_id"])
        if block is not None and messages and messages[-1]["role"] == "user":
            messages[-1] = {
                "role": "user",
                "content": [block, {"type": "text",
                                    "text": user_message or "What do you see?"}],
            }
    tool_events: List[Dict[str, Any]] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        emit({"event": "phase", "label": "Thinking"})
        response = client.complete(system, messages, tools)
        content, stop_reason = _drain_truncation(
            client, system, messages, tools, response, emit)
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]

        # Server-executed tools (currently: web_search) resolve entirely
        # within this same response — Anthropic returns the search and its
        # results as content blocks already. There is nothing to dispatch
        # and nothing to answer with a tool_result; we only announce it.
        for b in content:
            if b.get("type") == "server_tool_use" and b.get("name") == "web_search":
                emit({"event": "tool", "tool": "web_search", "label": "Searching the web"})
                convs.append(conv_id, "tool", tool="web_search",
                            label="Searching the web", input=b.get("input") or {})
                tool_events.append({"tool": "web_search", "label": "Searching the web",
                                    "result": "(resolved server-side by Anthropic)"})
        truncated_tool = (
            stop_reason == "max_tokens"
            and tool_uses
            and not _tool_input_is_complete(tool_uses[-1])
        )

        if truncated_tool:
            # The model's own attempt was cut mid-JSON: never execute a
            # malformed tool call. Tell it plainly and let it retry —
            # this is the honest fix for "comprehensive skill blocked by
            # a length limit", not a silent failure.
            bad = tool_uses[-1]
            emit({"event": "phase",
                 "label": "That was too long for one step — asking her to split it"})
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": bad["id"], "is_error": True,
                "content": (
                    f"Your {bad['name']} call was cut off by the output length "
                    "limit before it finished — nothing was written. Please "
                    "resend it, either more concisely or split into multiple "
                    "calls (e.g. author a shorter paradigm first, then revise "
                    "it to add detail in a follow-up call)."
                ),
            }]})
            continue

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
            try:
                result_str = provider.handle_tool_call(tu["name"], tu.get("input") or {})
            except Exception as e:  # a bug or bad input must not crash the turn
                result_str = json.dumps({
                    "ok": False,
                    "error": f"Internal error handling {tu['name']}: {e}",
                })
            tool_events.append({"tool": tu["name"], "label": label,
                                "result": result_str})
            if tu["name"] == "seira_create_file":
                try:
                    parsed_file = json.loads(result_str)
                    if parsed_file.get("ok"):
                        emit({"event": "file_created",
                             "filename": parsed_file.get("filename"),
                             "download_path": parsed_file.get("download_path")})
                except (json.JSONDecodeError, TypeError):
                    pass
            if tu["name"] == "seira_generate_image":
                try:
                    parsed_img = json.loads(result_str)
                    if parsed_img.get("ok") and parsed_img.get("__image_created__"):
                        emit({"event": "image_created",
                             "img_id": parsed_img.get("img_id"),
                             "tag": parsed_img.get("tag"),
                             "used_references": parsed_img.get("used_references", [])})
                except (json.JSONDecodeError, TypeError):
                    pass
            # Image recall is stored/logged as text (the marker, not raw
            # bytes — same bounded-context discipline as everywhere else),
            # but the tool_result actually sent to the model carries the
            # real image block when present.
            image_block = None
            try:
                parsed = json.loads(result_str)
                if isinstance(parsed, dict) and parsed.get("__image_block__"):
                    image_block = parsed.pop("__image_block__")
                    result_str_for_log = json.dumps(parsed)
                else:
                    result_str_for_log = result_str
            except (json.JSONDecodeError, TypeError):
                result_str_for_log = result_str
            convs.append(conv_id, "tool", tool=tu["name"], label=label,
                         input=tu.get("input") or {}, result=result_str_for_log)
            if image_block is not None:
                results.append({"type": "tool_result", "tool_use_id": tu["id"],
                                "content": [image_block,
                                           {"type": "text", "text": result_str_for_log}]})
            else:
                results.append({"type": "tool_result", "tool_use_id": tu["id"],
                                "content": result_str})
        messages.append({"role": "user", "content": results})

    final = ("(Seira reached her tool-iteration bound this turn; "
             "her records hold what was done.)")
    rec = convs.append(conv_id, "assistant", text=final)
    emit({"event": "reply", "text": final, "assistant_id": rec["id"]})
    return {"reply": final, "assistant_id": rec["id"], "tool_events": tool_events}


def regenerate(provider, client, conv_id: str, emit=None,
              length_pref: Optional[str] = None) -> Dict[str, Any]:
    """Supersede her last answer (recorded, never deleted) and answer the
    same live user message again."""
    last_a = convs.last_live_assistant(conv_id)
    if last_a is None:
        raise ValueError("Nothing to regenerate yet.")
    convs.supersede_from(conv_id, last_a["id"])
    return run_turn(provider, client, conv_id, user_message=None, emit=emit,
                    length_pref=length_pref)


def edit_and_rerun(provider, client, conv_id: str, target_id: int,
                   new_text: str, emit=None,
                   length_pref: Optional[str] = None) -> Dict[str, Any]:
    """Supersede a user message (and everything after it) and continue
    from the edited text. The abandoned branch remains in the record."""
    if not new_text.strip():
        raise ValueError("Edited message must not be empty.")
    convs.supersede_from(conv_id, target_id)
    return run_turn(provider, client, conv_id, user_message=new_text.strip(),
                    emit=emit, length_pref=length_pref)
