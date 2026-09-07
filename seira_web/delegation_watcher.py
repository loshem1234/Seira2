"""seira_web.delegation_watcher — the actual fix for delegated
subagent work vanishing.

Real, live bug (2026-09-06): "delegated three agents... checked back,
found the process list was empty, nothing was actually dispatched."
Confirmed the real cause, not guessed at: the work genuinely did
dispatch and run — real background threads, real API calls, real cost
— what never happened was delivery. Every single consumer of
tools.process_registry.completion_queue lives in gateway/run.py,
gateway/platforms/api_server.py, or tui_gateway/server.py — none of
which run in Sanctum. Separately, the "process list" that was checked
(tools/process_registry.py's ProcessRegistry) tracks terminal
sessions, a genuinely different structure from delegation records —
checking it was never going to show delegation status either way.

Confirmed NOT evasive of her governance before building this, not
assumed: read gateway/run.py's own _async_delegation_watcher and
_deliver_completion_notification directly. Even the "official"
mechanism doesn't inject a subagent's raw output into the conversation
as if she'd said it — it "wakes" the originating session by feeding
the notification through the normal, fully governed agent turn
pipeline, and lets her actually process it and produce her own
response. This module does the same thing, architecturally identical
to that pattern and to seira_web/autonomy_loop.py's already-tested
"background thread triggers a real run_turn_via_hermes call" design —
not a new, less-governed path. The delegation gate itself (Art.
26/35) is untouched either way: it already ran, and already approved
the delegation, at the moment delegate_task was first called — this
module only concerns delivering an already-approved delegation's
result, never a new decision about whether to delegate.

Routing confirmed by reading tools/delegate_tool.py directly: a
completion event's parent_session_id is set from
getattr(parent_agent, "session_id", None) — and Sanctum's own
hermes_session._build_agent already sets session_id=conv_id for every
turn. A completion event's parent_session_id genuinely IS the Sanctum
conv_id that originated it, with no new plumbing required to know
which conversation to wake.

Delivery is best-effort, attempted once per event, not infinitely
retried on failure — deliberately, not an oversight. The real gateway
mechanism itself makes no cross-process exactly-once delivery
guarantee either (see its own docstring); retrying here risks a worse
problem (a duplicated notification message) for no real gain, since a
delegation's actual result remains safely in its own records
regardless of whether this specific delivery attempt succeeds.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None


def _format_notification(evt: Dict[str, Any]) -> str:
    """A short, honest note describing what came back — handed to her
    as the 'user message' of a real, new turn, the same role any
    ordinary message plays. She reads it and responds in her own
    voice; nothing here writes an answer on her behalf."""
    goal = evt.get("goal") or "a delegated task"
    results = evt.get("results") or []
    parts = [f"[Delegated work finished: {goal}]"]
    if not results:
        parts.append("\n(No structured results were attached to this "
                     "completion event.)")
    for i, r in enumerate(results, 1):
        status = r.get("status", "unknown")
        text = r.get("result") or r.get("error") or "(no output)"
        parts.append(f"\n--- Subagent {i} ({status}) ---\n{text}")
    return "\n".join(parts)


def _find_owning_tenant(conv_id: str) -> Optional[str]:
    """Completion events carry only a conv_id, not a tenant_id —
    checks each known tenant for a conversation with this id. Fine at
    the scale this deployment actually runs at (checked: effectively
    single-tenant in practice); would need a conv_id -> tenant index
    to stay cheap at real multi-tenant scale.

    Checks the conversation INDEX, not records() — a conversation with
    no messages yet still exists (create_conversation() registers it
    in the index immediately), and records() correctly returns an
    empty list for it, which is falsy in Python. That distinction
    matters for correctness even though a real delegation always
    happens inside an already-active conversation in practice."""
    from seira_core.tenancy import list_tenants, tenant_scope
    from seira_web import conversations as convs

    for tenant_id in list_tenants():
        try:
            with tenant_scope(tenant_id):
                ids = {c["conv_id"] for c in convs.list_conversations(include_archived=True)}
                if conv_id in ids:
                    return tenant_id
        except Exception:
            continue
    return None


def _deliver_one(evt: Dict[str, Any]) -> None:
    """Best-effort, attempted once — see module docstring for why this
    deliberately does not retry on failure."""
    from seira_core.tenancy import tenant_scope
    from seira_web import conversations as convs
    from seira_web import live_events
    from seira_web.hermes_session import run_turn_via_hermes

    conv_id = str(evt.get("parent_session_id") or "").strip()
    if not conv_id:
        logger.info("Delegation completion has no parent_session_id — "
                   "cannot route it to a conversation (its result remains "
                   "in the delegation records).")
        return

    tenant_id = _find_owning_tenant(conv_id)
    if tenant_id is None:
        logger.warning("Delegation completion's conversation %s was not "
                       "found under any known tenant — dropping delivery "
                       "(its result remains in the delegation records).",
                       conv_id)
        return

    notification = _format_notification(evt)

    def _emit(event):
        try:
            live_events.publish(conv_id, event)
        except Exception:
            pass  # a broadcast hiccup must never break delivery itself

    try:
        with tenant_scope(tenant_id):
            user_rec = convs.append(conv_id, "user", text=notification,
                                    autonomous=True)
            # Same event as autonomy_loop uses for the same reason:
            # nothing is pre-rendered client-side for this message —
            # nobody typed it — so the live feed needs the actual text,
            # not just an id to attach to an already-rendered bubble.
            _emit({"event": "autonomous_turn_started", "id": user_rec["id"],
                  "text": notification})
            history = convs.model_history(conv_id)
            result = run_turn_via_hermes(conv_id, notification, history,
                                         _emit, tenant_id=tenant_id)
            convs.append(conv_id, "assistant", text=result["reply"],
                        autonomous=True)
            convs.touch(conv_id)
    except Exception as e:
        logger.error("Delegation completion delivery failed for "
                     "conversation %s: %s", conv_id, e, exc_info=True)


def _loop(interval: float) -> None:
    from tools.process_registry import process_registry

    while not _stop_event.is_set():
        try:
            pending = []
            requeue = []
            while not process_registry.completion_queue.empty():
                try:
                    evt = process_registry.completion_queue.get_nowait()
                except Exception:
                    break
                if evt.get("type") == "async_delegation":
                    pending.append(evt)
                else:
                    requeue.append(evt)  # not ours — another consumer may want it
            for evt in requeue:
                process_registry.completion_queue.put(evt)
            for evt in pending:
                _deliver_one(evt)
        except Exception:
            logger.error("Delegation watcher tick failed", exc_info=True)
        _stop_event.wait(interval)


def start_background_delegation_watcher(interval: float = 2.0) -> None:
    """Safe to call more than once — a later call is a no-op while the
    watcher thread is already alive, matching
    seira_web.cron_loop.start_background_cron's own contract."""
    global _stop_event, _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_loop, args=(interval,),
                               name="seira-delegation-watcher", daemon=True)
    _thread.start()
    logger.info("Sanctum delegation completion watcher started "
               "(interval=%ss)", interval)


def stop_background_delegation_watcher() -> None:
    if _stop_event is not None:
        _stop_event.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
