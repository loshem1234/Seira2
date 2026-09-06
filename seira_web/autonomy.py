"""seira_web.autonomy — state for autonomous mode: whether she's
currently running unprompted, in which mode, which conversation, how
many turns, which phase (for Triadic), who started it, and whether a
stop has been requested.

Deliberately in-memory, not persisted to disk. After a process
restart, nothing should silently resume running without a fresh,
explicit start from the Architect or from her — that's a safety
property, not a missing feature. One autonomous run per tenant at a
time; starting a second while one is already active is refused, not
queued or silently replacing the first.

Five continuous modes, per Loshem's direction (2026-08-31, refined
2026-09-01): exploration, creative, contemplation, triadic,
full_autonomy. Every one of them can be started or stopped by either
the Architect or by her (self-triggered — see
seira_bridge's seira_autonomy_start/stop and
seira_web.turn_context). The Architect's stop is an unconditional,
instant kill switch, always, for every mode, no floor. HER OWN
decision to stop something SHE is currently running has one
restriction: a minimum of three turns must have run first
(``MIN_TURNS_FOR_SELF_STOP``) — a floor against her second-guessing
herself the moment something looks unpromising, not against genuine
completion. This floor does not apply to the Architect's kill switch
under any circumstance.

Every run — however it started — is capped at MAX_TURNS_PER_RUN
turns (a real, deliberate cost-control decision, not a technical
limit: confirmed explicitly, "option B", 2026-09-01). Hitting the cap
ends the run cleanly, not as an error; either the Architect or she can
simply start another run of up to that many turns again immediately.
"""

from __future__ import annotations

import datetime as _dt
import threading
from typing import Any, Dict, Optional

MODES = ("exploration", "creative", "contemplation", "triadic", "full_autonomy")

# Confirmed explicitly with Loshem (2026-09-01): a real, deliberate
# cost-control cap, not a technical ceiling. Every run, however
# started, stops cleanly after this many turns; starting again is
# always available immediately after. Expected to be raised or
# removed later as costs come down — kept as a plain constant, not an
# env var, since this one is a policy choice meant to be revisited
# deliberately, not silently overridden by a stray environment
# variable at deploy time.
MAX_TURNS_PER_RUN = 10

# Confirmed explicitly with Loshem (2026-09-01): the floor on HER OWN
# decision to end a run she's currently in. Never applies to the
# Architect's kill switch.
MIN_TURNS_FOR_SELF_STOP = 3

_lock = threading.Lock()
_state: Dict[str, Dict[str, Any]] = {}  # tenant_id -> record


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def start(tenant_id: str, conv_id: str, mode: str,
         started_by: str = "architect") -> Dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}.")
    if started_by not in ("architect", "self"):
        raise ValueError("started_by must be 'architect' or 'self'.")
    with _lock:
        existing = _state.get(tenant_id)
        if existing and existing.get("active"):
            raise ValueError("Autonomous mode is already running.")
        rec = {
            "active": True, "mode": mode, "conv_id": conv_id,
            "started_at": _now_iso(), "turn_count": 0, "stopping": False,
            "started_by": started_by,
            # Triadic-specific; harmless and unused for every other
            # mode. Cycles 0 (Phaenic dreaming) -> 1 (Anthrian
            # interpretation) -> 2 (grounding in Giaon) -> 0 again.
            "phase": 0,
        }
        _state[tenant_id] = rec
        return dict(rec)


def request_stop(tenant_id: str, requested_by: str = "architect") -> Dict[str, Any]:
    """Marks the run for stopping. Honest about what this means: takes
    effect before the NEXT turn starts — immediately if the loop is
    between turns, or after the current in-flight turn finishes if one
    is already running (its output is kept, not discarded). This is
    not an instant mid-generation interrupt; the underlying turn call
    is synchronous and Python cannot forcibly kill a running thread.

    requested_by='self' is subject to MIN_TURNS_FOR_SELF_STOP — raises
    ValueError if she hasn't run enough turns yet to end it herself.
    requested_by='architect' has no such floor, ever.
    """
    with _lock:
        rec = _state.get(tenant_id)
        if rec is None or not rec.get("active"):
            return {"active": False}
        if requested_by == "self" and rec["turn_count"] < MIN_TURNS_FOR_SELF_STOP:
            raise ValueError(
                f"Not yet — at least {MIN_TURNS_FOR_SELF_STOP} turns must run "
                f"before you can end this yourself (currently {rec['turn_count']}). "
                f"The Architect can still stop it at any time."
            )
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
    """Increments turn_count and returns the record with `phase` set to
    the phase THIS upcoming turn should use (0 on the very first call
    for a run, since a fresh Triadic run should open with Phaenic
    dreaming, not skip straight to phase 1) — the cycle advances for
    the *next* call, not this one."""
    with _lock:
        rec = _state.get(tenant_id)
        if rec is None:
            return None
        current_phase = rec["phase"]
        rec["turn_count"] += 1
        rec["phase"] = (current_phase + 1) % 3
        result = dict(rec)
        result["phase"] = current_phase
        return result


def can_self_stop(tenant_id: str) -> bool:
    with _lock:
        rec = _state.get(tenant_id)
        return bool(rec) and rec.get("active") and rec["turn_count"] >= MIN_TURNS_FOR_SELF_STOP


def is_stopping(tenant_id: str) -> bool:
    with _lock:
        rec = _state.get(tenant_id)
        return rec is None or not rec.get("active") or bool(rec.get("stopping"))
