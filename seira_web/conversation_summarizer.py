"""seira_web.conversation_summarizer — she keeps her own conversation
history labeled, so Loshem can always tell what and where the chats
are.

Per Loshem's direction (2026-09-07, refined 2026-09-11): a genuine
weekly pass over conversations that had real activity since their
last summary — but the renaming and summarizing is hers to do, not a
silent, tool-free system completion. She reads the conversation
herself and calls seira_conversation_rename /
seira_conversation_set_summary using her own judgment about what's
actually specific and memorable, the same way any other tool-driven
work is hers.

Runs through seira_web.hermes_session.run_housekeeping_turn — a real,
fully governed turn (her identity, her tools, the real governance
gate) that is deliberately never saved as a visible sidebar
conversation, so a "let me rename this" exchange never pollutes the
actual conversation being labeled. Her real work — the rename, the
summary — is genuinely persisted and visible, through the tools she
calls, which write to the same conversation index the sidebar reads;
only the scaffolding turn asking her to do it stays out of view.

A title the Architect has explicitly set (via the rename button, or
by her own seira_conversation_rename call at his request) is never
overwritten — see conversations.auto_update_title_and_summary.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None

# A conversation with less than this many real turns rarely has
# anything meaningful to summarize yet — skip it rather than spend a
# real turn on "just started talking."
MIN_TURNS_TO_SUMMARIZE = 2

_HOUSEKEEPING_PROMPT_TEMPLATE = (
    "[Housekeeping — not shown to the Architect as a conversation of "
    "its own] One of your conversations needs a title and summary "
    "refresh. This is genuinely yours to do — read it and use your "
    "own judgment, the same as any other tool-driven work.\n\n"
    "Conversation id: {conv_id}\n\n"
    "Transcript:\n{transcript}\n\n"
    "Call seira_conversation_rename with a short, SPECIFIC title (4-8 "
    "words) that names the actual thing discussed — a project name, a "
    "decision, a concrete topic — precise enough to recognize this "
    "conversation among many others at a glance. Not a generic "
    "description like 'General Chat' or 'Technical Discussion'.\n\n"
    "Then call seira_conversation_set_summary with 2-4 bullets, each "
    "naming something concrete and specific enough that reading it "
    "tells you exactly WHERE and WHAT this conversation was about — "
    "real names, real decisions, real numbers where they exist. Not "
    "'discussed various topics' or 'talked about the project.'\n\n"
    "If the title the Architect already set was chosen by him "
    "directly, seira_conversation_rename will refuse to overwrite it — "
    "that's expected; call seira_conversation_set_summary regardless, "
    "since the summary always refreshes."
)


def _build_transcript_text(text: str, max_chars: int = 12_000) -> str:
    """Bounded, since this is a labeling task, not a task that needs
    the full transcript verbatim. Takes the most RECENT content up to
    the bound, since that's most representative of where the
    conversation actually is now."""
    if len(text) > max_chars:
        return "...\n" + text[-max_chars:]
    return text


def summarize_one(conv_id: str, tenant_id: str) -> bool:
    """Gives HER one real, tool-enabled turn to rename and summarize
    this conversation herself. Returns True if the housekeeping turn
    ran (regardless of whether she actually called both tools — that's
    her judgment to make), False if skipped for having too little
    content yet. Never raises — this runs unattended in a background
    loop."""
    from seira_web import conversations as convs
    from seira_web.hermes_session import run_housekeeping_turn

    history = convs.model_history(conv_id)
    if len([m for m in history if m.get("role") == "user"]) < MIN_TURNS_TO_SUMMARIZE:
        return False

    slice_result = convs.read_transcript_slice(conv_id, 0, 40_000)
    if not slice_result.get("found") or not slice_result.get("text", "").strip():
        return False

    transcript = _build_transcript_text(slice_result["text"])
    prompt = _HOUSEKEEPING_PROMPT_TEMPLATE.format(conv_id=conv_id, transcript=transcript)

    try:
        run_housekeeping_turn(prompt, tenant_id)
    except Exception as e:
        logger.warning("Conversation summarizer: housekeeping turn failed "
                       "for %s: %s", conv_id, e)
        return False
    return True


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
            summarize_one(rec["conv_id"], tenant_id)
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


def start_background_summarizer(interval: float = 604_800) -> None:
    """Default interval is once a week, per Loshem's direction
    (2026-09-11, revised from an original daily default) — but only
    conversations with genuinely new activity since their last summary
    are actually re-summarized on a given pass; an untouched
    conversation costs nothing."""
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
