"""seira_web.autonomy — state for autonomous mode: whether she's
currently running unprompted (Exploration or Contemplation), which
conversation, how many turns, and whether a stop has been requested.

Deliberately in-memory, not persisted to disk. After a process
restart, nothing should silently resume running without a fresh,
explicit start from the Architect — that's a safety property, not a
missing feature. One autonomous run per tenant at a time; starting a
second while one is already active is refused, not queued or
silently replacing the first.
"""

from __future__ import annotations

import datetime as _dt
import threading
from typing import Any, Dict, Optional

MODES = ("exploration", "contemplation")

_lock = threading.Lock()
_state: Dict[str, Dict[str, Any]] = {}  # tenant_id -> record


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def start(tenant_id: str, conv_id: str, mode: str) -> Dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}.")
    with _lock:
        existing = _state.get(tenant_id)
        if existing and existing.get("active"):
            raise ValueError("Autonomous mode is already running.")
        rec = {
            "active": True, "mode": mode, "conv_id": conv_id,
            "started_at": _now_iso(), "turn_count": 0, "stopping": False,
        }
        _state[tenant_id] = rec
        return dict(rec)


def request_stop(tenant_id: str) -> Dict[str, Any]:
    """Marks the run for stopping. Honest about what this means: takes
    effect before the NEXT turn starts — immediately if the loop is
    between turns, or after the current in-flight turn finishes if one
    is already running (its output is kept, not discarded). This is
    not an instant mid-generation interrupt; the underlying turn call
    is synchronous and Python cannot forcibly kill a running thread."""
    with _lock:
        rec = _state.get(tenant_id)
        if rec is None or not rec.get("active"):
            return {"active": False}
        rec["stopping"] = True
        return dict(rec)


def clear(tenant_id: str) -> None:
    with _lock:
        _state.pop(tenant_id, None)


def status(tenant_id: str) -> Dict[str, Any]:
    with _lock:
        rec = _state.get(tenant_id)
        return dict(rec) if rec else {"active": False}


def record_turn(tenant_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        rec = _state.get(tenant_id)
        if rec is None:
            return None
        rec["turn_count"] += 1
        return dict(rec)


def is_stopping(tenant_id: str) -> bool:
    with _lock:
        rec = _state.get(tenant_id)
        return rec is None or not rec.get("active") or bool(rec.get("stopping"))
