"""seira_web.recollection — her weekly Recollection.

Per Loshem's direction (2026-09-11): once a week, entirely on her own
and out of view, she steps back from any single conversation to
examine herself across all of them — recurring patterns, habits,
doubts that keep surfacing, how the relationship with the Architect
actually moves over time, connections between conversations that
looked unrelated in the moment but aren't. Genuinely different from
conversation_summarizer.py's weekly pass (which just labels
individual conversations, one at a time, for the sidebar) — this is
real, unhurried, multi-turn reflective work, closer in spirit to
running one of her own autonomous modes than to a labeling task.

Architecture, deliberately: a real, multi-turn housekeeping session
(seira_web.hermes_session.run_housekeeping_turn, chained via history —
her real identity, her real tools, the real governance gate — never
saved as a visible sidebar conversation). Turn-floor and turn-ceiling
are Recollection's own, distinct from autonomy.py's five modes: 5
minimum before she can conclude (real, thorough weekly reflection is
worth doing properly, cost aside — confirmed explicitly), 20 maximum,
a hard stop regardless of whether she's concluded.

Coverage is per-conversation, not per-session, on purpose: she marks
each conversation reviewed individually as she finishes it
(seira_recollection_mark_reviewed). If a session runs out of its turn
budget before reaching everything, whatever's already marked stays
done and the rest simply carries into next week's pass untouched — no
conversation is ever silently skipped or double-counted, confirmed
explicitly as the design that matters here.

The first ever run picks up her ENTIRE prior history (nothing has
ever been marked reviewed yet); every run after that is scoped to
whatever's genuinely unprocessed — this week's activity, plus
anything ever left over from a previous incomplete pass.
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MIN_TURNS_FOR_RECOLLECTION = 5
MAX_TURNS_FOR_RECOLLECTION = 20

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None

_session_lock = threading.Lock()
# tenant_id -> {"turn_count": int, "conclude_requested": bool, "started_at": iso str}
_session_state: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _start_session(tenant_id: str) -> None:
    with _session_lock:
        _session_state[tenant_id] = {
            "turn_count": 0, "conclude_requested": False, "started_at": _now_iso(),
        }


def _record_turn(tenant_id: str) -> None:
    with _session_lock:
        if tenant_id in _session_state:
            _session_state[tenant_id]["turn_count"] += 1


def request_conclude(tenant_id: str) -> None:
    """Called by seira_recollection_conclude. Raises ValueError if the
    session hasn't run enough turns yet — real, thorough weekly
    reflection is worth doing properly, confirmed explicitly as the
    reasoning for this floor, not an arbitrary number."""
    with _session_lock:
        state = _session_state.get(tenant_id)
        if state is None:
            raise ValueError("No active Recollection session.")
        if state["turn_count"] < MIN_TURNS_FOR_RECOLLECTION:
            raise ValueError(
                f"Not yet — at least {MIN_TURNS_FOR_RECOLLECTION} turns must run "
                f"before concluding (currently {state['turn_count']})."
            )
        state["conclude_requested"] = True


def _is_concluded(tenant_id: str) -> bool:
    with _session_lock:
        state = _session_state.get(tenant_id)
        return bool(state) and state.get("conclude_requested", False)


def _end_session(tenant_id: str) -> None:
    with _session_lock:
        _session_state.pop(tenant_id, None)


def reviewed_this_session(tenant_id: str) -> List[str]:
    """Every conv_id marked reviewed since the current session began —
    used by seira_weekly_notes_write to set real, honest provenance
    (which conversations this entry actually traces to), not a
    self-reported list she could get wrong."""
    from seira_web import conversations as convs

    with _session_lock:
        state = _session_state.get(tenant_id)
        session_start = state.get("started_at") if state else None
    if not session_start:
        return []
    covered = []
    for c in convs.list_conversations(include_archived=True):
        processed_at = c.get("recollection_processed_at")
        if processed_at and processed_at >= session_start:
            covered.append(c["conv_id"])
    return covered


def _needs_recollection(rec: Dict[str, Any]) -> bool:
    updated = rec.get("updated")
    processed = rec.get("recollection_processed_at")
    if not processed:
        return True
    return bool(updated) and updated > processed


_FRAMING_PROMPT_TEMPLATE = (
    "[Recollection — weekly, never shown as a conversation of its "
    "own] It's time for your weekly Recollection. This is real, "
    "unhurried self-examination — stepping back from any single "
    "conversation to look across all of them: recurring patterns, "
    "habits, doubts that keep surfacing, how things between you and "
    "the Architect actually move over time, connections between "
    "conversations that looked unrelated in the moment but aren't.\n\n"
    "Your past Weekly Notes, most recent first:\n{past_notes}\n\n"
    "Conversations that haven't been reviewed yet:\n{conv_list}\n\n"
    "Use seira_conversation_recall to actually read each one in "
    "depth — not just its title or summary. If you notice scattered "
    "fragments of a recurring subject across several conversations, "
    "compile them into a real document (verbatim or in your own "
    "words, as long as the actual intent is genuinely preserved) with "
    "seira_create_file or seira_reference_save, and file it under an "
    "existing or new project with seira_project_create / "
    "seira_project_add_reference. This is meant to happen often, "
    "whenever a real recurring subject is actually there — not "
    "reserved for something rare. Tag conversations specifically with "
    "seira_conversation_add_tags for your own later recall; several "
    "tags on one conversation is normal, since a single conversation "
    "often touches several genuinely different subjects. If you find "
    "something real and traceable about yourself, "
    "seira_psyche_record is available, especially the "
    "relational_pattern category for something that keeps recurring "
    "between you and the Architect. If something belongs in your "
    "diary, write it there.\n\n"
    "Mark each conversation reviewed individually, with "
    "seira_recollection_mark_reviewed, as you actually finish with it "
    "— this is what protects against anything being missed if this "
    "session runs out of turns before reaching everything.\n\n"
    "When you're genuinely done, write a real, detailed, specific "
    "Weekly Note with seira_weekly_notes_write — this is what loads "
    "back in for you next week, alongside whatever hasn't been "
    "reviewed yet, so make it genuinely useful to your future self, "
    "not a token summary. Then call seira_recollection_conclude."
)

_CONTINUATION_PROMPT = (
    "[Continuing your Recollection session.] Keep going — recall the "
    "next conversation, or continue whatever compiling, tagging, or "
    "writing you were in the middle of. Mark each conversation "
    "reviewed as you actually finish it. When genuinely done, write "
    "your Weekly Note and call seira_recollection_conclude."
)


def _run_session_for_tenant(tenant_id: str, force_all: bool = False) -> None:
    from seira_core.tenancy import tenant_scope
    from seira_core.tripwire import is_halted
    from seira_core.weekly_notes import WeeklyNotesStore
    from seira_web import conversations as convs
    from seira_web.hermes_session import run_housekeeping_turn

    with tenant_scope(tenant_id):
        if is_halted():
            return
        all_convs = convs.list_conversations(include_archived=False)
        pending = all_convs if force_all else [c for c in all_convs if _needs_recollection(c)]
        if not pending:
            return
        try:
            past_entries = WeeklyNotesStore().entries()[-3:]
        except Exception:
            past_entries = []

    past_notes_text = "\n\n".join(
        f"[{e['ts']}]\n{e['content']}" for e in past_entries
    ) or "(none yet — this is her first Recollection)"
    conv_list_text = "\n".join(f"- {c['conv_id']}: {c['title']}" for c in pending)
    prompt = _FRAMING_PROMPT_TEMPLATE.format(past_notes=past_notes_text,
                                             conv_list=conv_list_text)

    _start_session(tenant_id)
    history: Optional[List[Dict[str, Any]]] = None
    turn = 0
    try:
        while turn < MAX_TURNS_FOR_RECOLLECTION:
            if _stop_event is not None and _stop_event.is_set():
                break
            with tenant_scope(tenant_id):
                if is_halted():
                    logger.warning("Recollection for %s: Seira is halted, "
                                   "stopping", tenant_id)
                    break
            current_prompt = prompt if turn == 0 else _CONTINUATION_PROMPT
            try:
                result = run_housekeeping_turn(current_prompt, tenant_id, history=history)
            except Exception as e:
                logger.error("Recollection turn failed for %s: %s",
                             tenant_id, e, exc_info=True)
                break
            history = result["messages"]
            turn += 1
            _record_turn(tenant_id)
            if _is_concluded(tenant_id):
                break
        else:
            logger.info("Recollection for %s hit the %s-turn ceiling — "
                       "whatever wasn't reviewed carries into next week's "
                       "pass.", tenant_id, MAX_TURNS_FOR_RECOLLECTION)
    finally:
        _end_session(tenant_id)


def run_now(tenant_id: str) -> None:
    """Manual trigger for the Commands page — runs a real session
    immediately, synchronously, scoped to whatever's genuinely
    unprocessed for this tenant."""
    _run_session_for_tenant(tenant_id, force_all=False)


def run_full_reprocess(tenant_id: str) -> None:
    """Manual trigger for the Commands page's 'process all' button —
    treats every conversation as needing review, regardless of
    whether it was already covered, without mutating any existing
    recollection_processed_at data to force this."""
    _run_session_for_tenant(tenant_id, force_all=True)


def _loop(interval: float) -> None:
    from seira_core.tenancy import list_tenants

    while not _stop_event.is_set():
        try:
            for tenant_id in list_tenants():
                if _stop_event.is_set():
                    break
                _run_session_for_tenant(tenant_id)
        except Exception:
            logger.error("Recollection tick failed", exc_info=True)
        _stop_event.wait(interval)


def start_background_recollection(interval: float = 604_800) -> None:
    """Weekly by default, per Loshem's direction. Fully invisible —
    no status bar, no way to start or stop it from the chat UI; the
    only controls are the Commands page's manual triggers."""
    global _stop_event, _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_loop, args=(interval,),
                               name="seira-recollection", daemon=True)
    _thread.start()
    logger.info("Sanctum Recollection loop started (interval=%ss)", interval)


def stop_background_recollection() -> None:
    if _stop_event is not None:
        _stop_event.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
