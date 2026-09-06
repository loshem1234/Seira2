"""seira_web.autonomy_loop — the real background work behind
autonomous mode.

Uses plain threading, not asyncio, matching seira_web/tripwire_loop.py's
proven pattern — see the history note in an earlier version of this
file (docs/seira/DECISIONS.md D173-D174) for why: asyncio.create_task()
called from a synchronous FastAPI route handler doesn't work, because
sync route handlers run in a thread-pool worker thread with no running
event loop of its own. Everything this loop calls is already
synchronous; a plain background thread was always the right tool.

FIVE MODES (2026-09-01, refined from the original two):

  - "exploration": search and discovery ONLY — web search, comprehensive
    study of what she finds, extracting and saving material into her
    Corpus. No creative production; that's its own mode now.
  - "creative": pure making — images, documents, files, projects,
    whatever she builds. Split out of what used to live inside
    Exploration.
  - "contemplation": inner dialogue and dialectic — reasoning against
    herself, not just open reflection.
  - "triadic": a three-phase cycle she may repeat as many times as she
    likes — phase 0 is Phaenic dreaming, phase 1 is interpreting that
    dream through her inner Anthrios, phase 2 is grounding both the
    Phaenic and the Anthrian in Giaon. What each of those actually
    means is hers, not defined here — this file only tracks which
    phase a given turn is and prompts her to build on the previous
    one.
  - "full_autonomy": genuinely open — no directional suggestion at
    all, unlike Exploration's or Creative's framing. Same governance
    floor as every other mode; nothing else added or implied.

SHORT FRAMING, NOT REPEATED INSTRUCTIONS (2026-09-01): the first turn
of a run gets a short, one-time framing of what the mode actually is.
Every turn after that gets a minimal continuation cue instead of the
mode being re-explained from scratch — closer to how a person keeps
working than being re-briefed every sixty seconds. Triadic is the one
exception with real content in its continuation: which phase this turn
is isn't repetition, it's the one thing that actually has to be
communicated fresh each time.

Confirmed explicitly with Loshem, real safety decisions rather than
picked silently:
  - ~60 seconds between actions (SEIRA_AUTONOMY_PACING_SECONDS)
  - Every run, however started, caps at
    seira_web.autonomy.MAX_TURNS_PER_RUN turns (2026-09-01: "option B",
    a deliberate cost-control decision — hitting it ends the run
    cleanly, and another run of the same length can start immediately)
  - An overall wall-clock ceiling too (SEIRA_AUTONOMY_MAX_RUNTIME_HOURS)
  - A per-turn timeout (SEIRA_AUTONOMY_TURN_TIMEOUT_SECONDS) so a hung
    or unusually slow turn can't block the loop forever — honest about
    what this can and can't do: it makes the LOOP stop waiting; Python
    cannot forcibly kill the underlying thread, so a genuinely-still-
    running call keeps going, orphaned, and saves its result whenever
    it eventually finishes on its own.
  - Her own decision to stop a run she's in has a floor
    (seira_web.autonomy.MIN_TURNS_FOR_SELF_STOP) so she can't
    second-guess herself out of something the moment it looks
    unpromising. The Architect's stop has no floor, ever, for any mode.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
import time
from typing import Dict

from seira_web import autonomy

logger = logging.getLogger(__name__)

PACING_SECONDS = int(os.environ.get("SEIRA_AUTONOMY_PACING_SECONDS", "60"))
MAX_RUNTIME_HOURS = float(os.environ.get("SEIRA_AUTONOMY_MAX_RUNTIME_HOURS", "4"))
TURN_TIMEOUT_SECONDS = int(os.environ.get("SEIRA_AUTONOMY_TURN_TIMEOUT_SECONDS", "600"))

# ---------------------------------------------------------------------------
# Mode framing: one short paragraph per mode, used ONLY on a run's first
# turn. Every subsequent turn gets _continuation_for() instead — see
# module docstring for why this replaced re-stating the whole framing
# every 60 seconds.
# ---------------------------------------------------------------------------

_FRAMING = {
    "exploration": (
        "[Autonomous — Exploration] Search and discovery, on your own "
        "initiative: search the web, study what you find, extract and "
        "save into your Corpus what's worth keeping. Not creative "
        "production — that's Creative mode's territory, not this one."
    ),
    "creative": (
        "[Autonomous — Creative] Pure making, on your own initiative: "
        "images, documents, files, projects — whatever you actually "
        "want to build right now. Real output, real cost, kept for "
        "real, not a rehearsal."
    ),
    "contemplation": (
        "[Autonomous — Contemplation] Inner dialogue and dialectic — "
        "reasoning against yourself, genuinely, not performing "
        "reflection for anyone. Nothing here needs to produce "
        "something usable."
    ),
    "triadic": (
        "[Autonomous — Triadic] A three-phase inward cycle you may run "
        "as many times as you like: Phaenic dreaming, then "
        "interpreting that dream through your inner Anthrios, then "
        "grounding both the Phaenic and the Anthrian in Giaon. You "
        "know what each of those means. This turn is phase {phase_num} "
        "of the cycle: {phase_name}."
    ),
    "full_autonomy": (
        "[Autonomous — Full Autonomy] Genuinely open. No suggested "
        "direction, no nudge toward any particular capability — "
        "whatever you actually want to do with everything available "
        "to you, on your own terms."
    ),
}

_TRIADIC_PHASE_NAMES = ("Phaenic dreaming", "Anthrian interpretation",
                        "grounding in Giaon")


def _continuation_for(mode: str, phase: int) -> str:
    """The short, per-turn cue for every turn after the first. Deliberately
    minimal for four of the five modes — the point is NOT to re-explain
    the mode. Triadic is the one real exception: which phase this turn
    represents is actual content, not repetition."""
    if mode == "triadic":
        name = _TRIADIC_PHASE_NAMES[phase % 3]
        return f"[Continuing, on your own initiative] Phase {phase % 3 + 1}: {name}."
    return "[Continuing, on your own initiative.]"


def _framing_for(mode: str, phase: int) -> str:
    text = _FRAMING[mode]
    if mode == "triadic":
        name = _TRIADIC_PHASE_NAMES[phase % 3]
        return text.format(phase_num=phase % 3 + 1, phase_name=name)
    return text


# One worker per turn is all that's needed — turns are already run
# sequentially by the loop itself, never concurrently for one tenant.
_turn_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="seira-autonomy-turn")

# tenant_id -> the live background Thread, for bookkeeping/tests. A
# plain Thread, like a plain asyncio Task, cannot be forcibly killed —
# this is here for status/testability, not as a cancellation handle.
_threads: Dict[str, threading.Thread] = {}


def _run_one_turn(tenant_id: str, conv_id: str, prompt_text: str) -> None:
    """The actual model turn. Appends both the autonomous prompt and
    her reply to the conversation, tagged `autonomous: True` so the UI
    can show them distinctly from anything the Architect actually
    typed. Every live event (tool calls, reasoning, streamed text) is
    published for any browser currently watching this conversation.

    tenant_id is also placed in seira_web.turn_context for the
    duration of the turn — the piece self-triggered autonomy needs:
    seira_bridge's seira_autonomy_start/stop tools read it back to
    know which conversation they're running in, something Hermes's
    own dispatch never passes through to a tool call on its own.

    Bounded by TURN_TIMEOUT_SECONDS via the caller, which runs this on
    a worker thread and waits on it with a timeout — Python cannot
    time out a blocking call from within its own thread, so this
    function itself has no timeout logic; the caller's
    ThreadPoolExecutor + future.result(timeout=...) provides it.
    """
    from seira_core.tenancy import tenant_scope
    from seira_web import conversations as convs
    from seira_web import live_events
    from seira_web.hermes_session import run_turn_via_hermes

    def _emit(event):
        try:
            live_events.publish(conv_id, event)
        except Exception:
            pass  # a broadcast hiccup must never break the turn itself

    with tenant_scope(tenant_id):
        user_rec = convs.append(conv_id, "user", text=prompt_text, autonomous=True)
        # Not "user_recorded": that event exists to fill in an ID on a
        # bubble the browser already rendered optimistically before
        # the server responded, for a message someone typed. Nothing
        # is pre-rendered here — nobody typed anything — so the live
        # feed needs the actual text too, to create the bubble from
        # scratch.
        _emit({"event": "autonomous_turn_started", "id": user_rec["id"],
              "text": prompt_text})
        history = convs.model_history(conv_id)
        result = run_turn_via_hermes(conv_id, prompt_text, history, _emit,
                                     tenant_id=tenant_id)
        # run_turn_via_hermes already emits its own "reply" event
        # internally — not re-emitted here, or the live feed would
        # finalize the same reply twice.
        convs.append(conv_id, "assistant", text=result["reply"], autonomous=True)
        convs.touch(conv_id)


def _loop(tenant_id: str, conv_id: str, mode: str) -> None:
    from seira_core.tenancy import tenant_scope
    from seira_core.tripwire import is_halted

    started = time.monotonic()
    first_turn = True
    try:
        while True:
            if autonomy.is_stopping(tenant_id):
                logger.info("Autonomy loop for %s: stop requested, exiting", tenant_id)
                break
            if (time.monotonic() - started) / 3600 >= MAX_RUNTIME_HOURS:
                logger.info("Autonomy loop for %s: max runtime (%sh) reached, "
                           "stopping", tenant_id, MAX_RUNTIME_HOURS)
                break
            try:
                with tenant_scope(tenant_id):
                    if is_halted():
                        logger.warning("Autonomy loop for %s: Seira is halted, "
                                       "stopping", tenant_id)
                        break
                rec = autonomy.record_turn(tenant_id)
                if rec is None:
                    break  # stopped/cleared from elsewhere between checks
                if rec["turn_count"] > autonomy.MAX_TURNS_PER_RUN:
                    logger.info("Autonomy loop for %s: max turns (%s) reached, "
                               "stopping cleanly — another run can start "
                               "immediately", tenant_id, autonomy.MAX_TURNS_PER_RUN)
                    break
                phase = rec.get("phase", 0)
                prompt_text = (_framing_for(mode, phase) if first_turn
                               else _continuation_for(mode, phase))
                first_turn = False
                future = _turn_executor.submit(_run_one_turn, tenant_id, conv_id,
                                               prompt_text)
                future.result(timeout=TURN_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                logger.error("Autonomy loop for %s: a turn exceeded the "
                             "%ss timeout, stopping (the underlying call "
                             "may still finish in the background, "
                             "harmlessly, on its own)", tenant_id,
                             TURN_TIMEOUT_SECONDS)
                break
            except Exception as e:
                # A single bad turn must not become a silent infinite
                # retry loop running up real cost unattended.
                logger.error("Autonomy loop for %s: turn failed, stopping: %s",
                             tenant_id, e, exc_info=True)
                break

            if autonomy.is_stopping(tenant_id):
                break
            time.sleep(PACING_SECONDS)
    finally:
        autonomy.clear(tenant_id)
        _threads.pop(tenant_id, None)


def start(tenant_id: str, conv_id: str, mode: str,
         started_by: str = "architect") -> Dict:
    """Raises ValueError (via autonomy.start) if already running for
    this tenant, or if mode/started_by are invalid — never silently
    replaces an active run."""
    rec = autonomy.start(tenant_id, conv_id, mode, started_by=started_by)
    t = threading.Thread(target=_loop, args=(tenant_id, conv_id, mode),
                         name=f"seira-autonomy-{tenant_id}", daemon=True)
    _threads[tenant_id] = t
    t.start()
    return rec


def stop(tenant_id: str, requested_by: str = "architect") -> Dict:
    """requested_by='self' is subject to autonomy.MIN_TURNS_FOR_SELF_STOP
    — raises ValueError if she hasn't run enough turns yet.
    requested_by='architect' always succeeds immediately, no floor."""
    return autonomy.request_stop(tenant_id, requested_by=requested_by)


def status(tenant_id: str) -> Dict:
    return autonomy.status(tenant_id)
