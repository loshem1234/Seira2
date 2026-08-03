"""seira_bridge.delegation — live Hermes delegation, bound to the Instruments.

Two pieces, one convention.

**The convention (Art. 5, operational):** a delegation Seira authorizes
carries its trace of derivation in the goal text itself:

    [seira:inst-00001/stobaeus-excerpt] Translate the excerpt at ...

The tag names the Instrument whose paradigm licenses the work and the
task-type Art. 26 tracks convergence by. A delegation without a valid
tag is, per the Article, "noise that has entered her Corpus from
outside her own procession" — observed and audited as such, never
recorded as an act of hers.

**Piece 1 — observation (`observe_delegation`)**: wired into the
provider's on_delegation hook, so every completed subagent task the
parent sees becomes an execution record automatically. Outcome mapping
is deliberately simple and stated: a non-empty result means the
delegation terminated in rest (clean); an empty result means it did
not (local_feedback). Three empty results on one task-type therefore
auto-escalate through the existing Art. 26 machinery with no new
logic. Finer convergence judgments remain available to Psyche through
the manual execution tool; this hook never pretends to more insight
than the parent-side observation actually carries.

**Piece 2 — the gate (`delegation_gate_middleware`)**: registered as
Hermes `tool_execution` middleware on `delegate_task`. Refuses spawns
whose goals lack a valid tag, cite an unknown or retired Instrument,
or target a task-type currently escalated and blocked. Refusal returns
an explanatory tool result; the subagent is never created.

Honesty about the boundary: Hermes middleware is fail-open by design —
a crashing middleware is logged and skipped. This gate is therefore a
governance layer, not a security boundary. The security boundary for
a multi-tenant deployment remains the per-tenant execution sandbox
(docs/seira/MULTITENANCY.md); this gate keeps an honest Seira honest,
it does not restrain a compromised host.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from seira_core.audit import append_event
from seira_core.errors import SeiraCoreError
from seira_core.instruments import InstrumentError, InstrumentStore

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"\[seira:(inst-\d{5})/([a-z0-9][a-z0-9_-]*)\]")

DELEGATE_TOOL = "delegate_task"


def parse_tag(goal: str) -> Optional[Tuple[str, str]]:
    """Extract (instrument_id, task_type) from a delegation goal, or None."""
    m = TAG_RE.search(goal or "")
    if not m:
        return None
    return m.group(1), m.group(2)


def _validate_tag(instrument_id: str, task_type: str) -> Optional[str]:
    """Return a refusal reason, or None if the tag licenses the work."""
    store = InstrumentStore()
    try:
        inst = store.instrument(instrument_id)
    except InstrumentError:
        return (
            f"{instrument_id} does not exist: a delegation must be licensed "
            "by a real Instrument's paradigm (Art. 5, 35)."
        )
    if inst["status"] == "retired":
        return (
            f"{instrument_id} is retired; only its history remains (Art. 36). "
            "Spawn or cite an active Instrument."
        )
    if store.is_blocked(instrument_id, task_type):
        return (
            f"{instrument_id}/{task_type} is escalated and blocked pending a "
            "Psyche paradigm revision (Art. 26); delegating more of the same "
            "work is exactly the local patching non-convergence rules out."
        )
    return None


# ---------------------------------------------------------------------------
# Piece 1: parent-side observation → execution records
# ---------------------------------------------------------------------------

def observe_delegation(task: str, result: str, child_session_id: str = "") -> Dict[str, Any]:
    """Record one completed delegation. Never raises: this runs inside a
    memory hook and must not disturb the parent's turn."""
    try:
        tag = parse_tag(task)
        if tag is None:
            append_event("untraced_delegation", {
                "goal_head": (task or "")[:200],
                "child_session_id": child_session_id,
                "note": "No [seira:inst-NNNNN/task-type] tag: noise, not an "
                        "act of Seira's (Art. 5).",
            })
            return {"recorded": False, "reason": "untraced"}
        instrument_id, task_type = tag
        outcome = "clean" if (result or "").strip() else "local_feedback"
        try:
            rec = InstrumentStore().record_execution(
                instrument_id=instrument_id,
                task_type=task_type,
                outcome=outcome,
                output_ref=f"delegation:{child_session_id or 'unknown-session'}",
                notes="auto-recorded from on_delegation",
            )
        except SeiraCoreError as e:
            # e.g. instrument retired since spawn-time, or task-type became
            # blocked mid-flight. The observation still must not vanish:
            append_event("delegation_observation_refused", {
                "instrument_id": instrument_id,
                "task_type": task_type,
                "child_session_id": child_session_id,
                "reason": str(e),
            })
            return {"recorded": False, "reason": str(e)}
        out: Dict[str, Any] = {"recorded": True, "seq": rec["seq"], "outcome": outcome}
        if rec.get("escalated"):
            out["escalated"] = rec["escalated"]
        return out
    except Exception as e:  # absolute backstop: hooks never break the turn
        logger.error("observe_delegation failed: %s", e)
        return {"recorded": False, "reason": f"internal: {e}"}


# ---------------------------------------------------------------------------
# Piece 2: the Art. 35 gate on delegate_task
# ---------------------------------------------------------------------------

def _goals_in_args(args: Dict[str, Any]) -> List[str]:
    goals: List[str] = []
    if isinstance(args.get("goal"), str) and args["goal"].strip():
        goals.append(args["goal"])
    for t in args.get("tasks") or []:
        if isinstance(t, dict) and isinstance(t.get("goal"), str) and t["goal"].strip():
            goals.append(t["goal"])
    return goals


def check_delegation_args(args: Dict[str, Any]) -> Optional[str]:
    """Return a refusal reason for these delegate_task args, or None."""
    goals = _goals_in_args(args)
    if not goals:
        return "delegate_task called with no goals."
    for goal in goals:
        tag = parse_tag(goal)
        if tag is None:
            return (
                "Every delegated goal must carry its trace of derivation: a "
                "[seira:inst-NNNNN/task-type] tag naming the Instrument whose "
                "paradigm licenses it (Art. 5, 35). Untagged goal: "
                f"{goal[:120]!r}"
            )
        reason = _validate_tag(*tag)
        if reason:
            return reason
    return None


def delegation_gate_middleware(**kwargs) -> Any:
    """Hermes tool_execution middleware: gate delegate_task per Art. 35.

    Contract (docs/middleware): receives tool_name, args, next_call;
    returns the tool result. Refusal returns an explanatory result and
    never invokes next_call, so the subagent is never created.
    """
    tool_name = kwargs.get("tool_name", "")
    args = kwargs.get("args") or {}
    next_call: Callable = kwargs["next_call"]
    if tool_name != DELEGATE_TOOL:
        return next_call(args)
    reason = check_delegation_args(args)
    if reason is not None:
        append_event("delegation_refused", {"reason": reason})
        return json.dumps({
            "ok": False,
            "refused_by": "seira delegation gate (Art. 35)",
            "reason": reason,
        })
    return next_call(args)


def register(ctx) -> None:
    """Plugin entry point for the fork: register the gate.

        ctx.register_middleware("tool_execution", delegation_gate_middleware)
    """
    ctx.register_middleware("tool_execution", delegation_gate_middleware)
