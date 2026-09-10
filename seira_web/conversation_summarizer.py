"""seira_web.conversation_summarizer — keeps every conversation's
sidebar entry meaningfully labeled on its own, so Loshem can always
tell what and where a conversation actually is without opening it.

Per Loshem's direction (2026-09-07): a short, auto-updated title and
a handful of bullet points per conversation, refreshed roughly daily
— but only for conversations that actually had new activity since
their last summary, not on a blind schedule that would waste real
cost re-summarizing conversations nobody touched.

Deliberately a plain, tool-free text completion (seira_web.chat's
existing AnthropicClient), not a real Hermes agent turn — this isn't
her acting or speaking; it's a lightweight, system-level utility
labeling conversations for a sidebar, the same category of thing as
an auto-generated commit message, not a turn that needs her Psyche,
her tools, or the delegation/autonomy governance machinery. Genuinely
cheap: small max_tokens, no tool schemas, one short call per
conversation that actually needs refreshing.

A title the Architect has explicitly set (via the rename button) is
never overwritten — see conversations.auto_update_title_and_summary.
Bullets always refresh regardless, since they describe content, not
something anyone would "rename".
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None

# A conversation with less than this many real turns rarely has
# anything meaningful to summarize yet — skip it rather than spend a
# real API call on "just started talking."
MIN_TURNS_TO_SUMMARIZE = 2

_SYSTEM_PROMPT = (
    "You label chat conversations for a sidebar. Given a conversation's "
    "messages, respond with ONLY a JSON object, no markdown fences, no "
    "commentary: "
    '{"title": "a short, specific 4-8 word title", '
    '"bullets": ["a short specific point", "another one", ...]}. '
    "2 to 4 bullets, each under 12 words, each naming something concrete "
    "actually discussed — not generic descriptions like 'general chat'. "
    "The title should let someone recognize this conversation at a "
    "glance among many others, not describe the app itself."
)


def _build_transcript_text(history: List[Dict[str, str]], max_chars: int = 12_000) -> str:
    """A plain-text rendering of the conversation for the summarizer
    prompt — bounded, since this is a labeling task, not a task that
    needs the full transcript verbatim. Takes the most RECENT content
    up to the bound, since that's most representative of where the
    conversation actually is now."""
    lines = []
    for m in history:
        role = "Architect" if m.get("role") == "user" else "Seira"
        content = m.get("content", "")
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
    text = "\n\n".join(lines)
    if len(text) > max_chars:
        text = "...\n" + text[-max_chars:]
    return text


def _parse_summary_response(raw: str) -> Optional[Tuple[str, List[str]]]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    title = data.get("title")
    bullets = data.get("bullets")
    if not isinstance(title, str) or not isinstance(bullets, list):
        return None
    bullets = [b for b in bullets if isinstance(b, str) and b.strip()][:6]
    return title.strip(), bullets


def summarize_one(conv_id: str) -> bool:
    """Summarize a single conversation and store the result. Returns
    True if a summary was written, False if skipped or failed — never
    raises, since this runs unattended in a background loop."""
    from seira_web import conversations as convs
    from seira_web.chat import AnthropicClient

    history = convs.model_history(conv_id)
    if len([m for m in history if m.get("role") == "user"]) < MIN_TURNS_TO_SUMMARIZE:
        return False

    transcript = _build_transcript_text(history)
    if not transcript.strip():
        return False

    try:
        client = AnthropicClient(max_tokens=300)
        resp = client.complete(_SYSTEM_PROMPT,
                               [{"role": "user", "content": transcript}], [])
        blocks = resp.get("content", [])
        raw_text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except Exception as e:
        logger.warning("Conversation summarizer: completion failed for %s: %s",
                       conv_id, e)
        return False

    parsed = _parse_summary_response(raw_text)
    if parsed is None:
        logger.warning("Conversation summarizer: could not parse response "
                       "for %s: %r", conv_id, raw_text[:200])
        return False

    title, bullets = parsed
    rec = convs.auto_update_title_and_summary(conv_id, title, bullets)
    return rec is not None


def _needs_refresh(rec: Dict[str, Any]) -> bool:
    updated = rec.get("updated")
    summarized_at = rec.get("summary_updated_at")
    if not summarized_at:
        return True
    return bool(updated) and updated > summarized_at


def _run_pass_for_tenant(tenant_id: str) -> None:
    from seira_core.tenancy import tenant_scope
    from seira_web import conversations as convs

    with tenant_scope(tenant_id):
        pending = [c for c in convs.list_conversations(include_archived=False)
                  if _needs_refresh(c)]
    for rec in pending:
        if _stop_event is not None and _stop_event.is_set():
            return
        try:
            with tenant_scope(tenant_id):
                summarize_one(rec["conv_id"])
        except Exception:
            logger.error("Conversation summarizer: pass failed for %s/%s",
                        tenant_id, rec["conv_id"], exc_info=True)


def _loop(interval: float) -> None:
    from seira_core.tenancy import list_tenants

    while not _stop_event.is_set():
        try:
            for tenant_id in list_tenants():
                if _stop_event.is_set():
                    break
                _run_pass_for_tenant(tenant_id)
        except Exception:
            logger.error("Conversation summarizer tick failed", exc_info=True)
        _stop_event.wait(interval)


def start_background_summarizer(interval: float = 86_400) -> None:
    """Default interval is once a day, per Loshem's direction — but
    only conversations with genuinely new activity since their last
    summary are actually re-summarized on each pass; an untouched
    conversation costs nothing on a given day."""
    global _stop_event, _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_loop, args=(interval,),
                               name="seira-conversation-summarizer", daemon=True)
    _thread.start()
    logger.info("Sanctum conversation summarizer started (interval=%ss)", interval)


def stop_background_summarizer() -> None:
    if _stop_event is not None:
        _stop_event.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
