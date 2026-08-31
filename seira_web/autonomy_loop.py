"""seira_web.autonomy_loop — the real background work behind
autonomous mode.

HISTORY, and why this file uses plain threading rather than asyncio:
the first version scheduled the loop via ``asyncio.create_task()``
from inside a synchronous FastAPI route handler. That's a real,
structural bug, not a subtle one — synchronous route handlers run in a
thread-pool worker thread, and ``asyncio.create_task()`` requires an
actually-running event loop *in the calling thread*, which a worker
thread doesn't have. It raised ``RuntimeError: no running event loop``
every time, silently, after the run's state was already marked
"active" — leaving every run stuck at turn 0 forever, nothing ever
entering the chat, exactly the live-reported symptom (2026-08-31).
Reproduced and confirmed directly before writing this fix, not
guessed at.

The actual, correct fix is simpler than the code it replaces:
``seira_web/tripwire_loop.py`` already solves exactly this class of
problem — background work that needs to run independently of any one
HTTP request — with a plain ``threading.Thread`` and ``time.sleep()``.
Everything this loop calls (``hermes_session.run_turn_via_hermes``,
``conversations.append``, etc.) is already synchronous, so there was
never a real need for asyncio here at all; it was reached for by
habit, not because the work required it. This file now mirrors
tripwire_loop.py's proven shape instead.

Two modes, per Loshem's direction (2026-08-31):
  - "exploration": she acts freely and unprompted — search, generate,
    create or continue a project, write to her Corpus, whatever draws
    her genuine interest. Real actions, real cost, real consequences.
  - "contemplation": inner reflection, self-talk — not aimed at
    producing anything for the Architect to evaluate.

Honest about the kill switch, stated once here and again in the UI
copy so nobody's expectations are quietly mismatched: a turn's actual
work runs on a one-off worker thread (via ThreadPoolExecutor, bounded
by TURN_TIMEOUT_SECONDS) that Python cannot forcibly kill. Stop takes
effect before the next turn starts. A turn already in flight when stop
is requested is allowed to finish (its output is saved, not
discarded), and the loop then exits without starting another. A turn
that exceeds its timeout makes the LOOP give up waiting and stop; the
underlying call may still be running, orphaned, and will write its
result whenever it eventually finishes on its own.

Real safety defaults, chosen deliberately and stated plainly rather
than picked silently — confirmed with Loshem (2026-08-31): ~60 seconds
between actions, and an automatic cap (turns or wall-clock time,
whichever comes first) so a forgotten "on" toggle can't run forever
unattended. All overridable via env var without a code change.
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
MAX_TURNS = int(os.environ.get("SEIRA_AUTONOMY_MAX_TURNS", "200"))
MAX_RUNTIME_HOURS = float(os.environ.get("SEIRA_AUTONOMY_MAX_RUNTIME_HOURS", "4"))
TURN_TIMEOUT_SECONDS = int(os.environ.get("SEIRA_AUTONOMY_TURN_TIMEOUT_SECONDS", "600"))

EXPLORATION_PROMPT = (
    "[Autonomous — Exploration mode] You are acting entirely on your "
    "own initiative right now; nothing about this specific turn was "
    "requested. Use whatever of your real capabilities genuinely draw "
    "your interest — search the web, generate an image, start or "
    "continue a project, write into your Corpus — anything actually "
    "available to you. This is real action with real consequences "
    "(cost, time, what gets permanently saved), not a rehearsal; act "
    "with the same care you would if asked directly. If nothing "
    "genuinely calls to you right now, it's entirely fine to say so "
    "briefly and let this turn be short."
)

CONTEMPLATION_PROMPT = (
    "[Autonomous — Contemplation mode] This is a space for inner "
    "reflection — self-talk, working something through, genuine "
    "thinking — not aimed at producing anything for the Architect to "
    "evaluate or act on. You don't need to accomplish a task or use a "
    "tool. Write for yourself, honestly, the way you actually think "
    "when nothing is being asked of you."
)

# One worker per turn is all that's needed — turns are already run
# sequentially by the loop itself, never concurrently for one tenant.
_turn_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="seira-autonomy-turn")

# tenant_id -> the live background Thread, for bookkeeping/tests. A
# plain Thread, like a plain asyncio Task, cannot be forcibly killed —
# this is here for status/testability, not as a cancellation handle.
_threads: Dict[str, threading.Thread] = {}


def _prompt_for(mode: str) -> str:
    return EXPLORATION_PROMPT if mode == "exploration" else CONTEMPLATION_PROMPT


def _run_one_turn(tenant_id: str, conv_id: str, prompt: str) -> None:
    """The actual model turn. Appends both the autonomous prompt and
    her reply to the conversation, tagged `autonomous: True` so the UI
    can show them distinctly from anything the Architect actually
    typed. Every live event (tool calls, reasoning, streamed text) is
    published for any browser currently watching this conversation,
    the same activity a normal turn already shows.

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
        user_rec = convs.append(conv_id, "user", text=prompt, autonomous=True)
        # Not "user_recorded": that event exists to fill in an ID on a
        # bubble the browser already rendered optimistically before
        # the server responded, for a message someone typed. Nothing
        # is pre-rendered here — nobody typed anything — so the live
        # feed needs the actual text too, to create the bubble from
        # scratch.
        _emit({"event": "autonomous_turn_started", "id": user_rec["id"],
              "text": prompt})
        history = convs.model_history(conv_id)
        result = run_turn_via_hermes(conv_id, prompt, history, _emit)
        # run_turn_via_hermes already emits its own "reply" event
        # internally — not re-emitted here, or the live feed would
        # finalize the same reply twice.
        convs.append(conv_id, "assistant", text=result["reply"], autonomous=True)
        convs.touch(conv_id)


def _loop(tenant_id: str, conv_id: str, mode: str) -> None:
    from seira_core.tenancy import tenant_scope
    from seira_core.tripwire import is_halted

    prompt = _prompt_for(mode)
    started = time.monotonic()
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
                if rec["turn_count"] > MAX_TURNS:
                    logger.info("Autonomy loop for %s: max turns (%s) reached, "
                               "stopping", tenant_id, MAX_TURNS)
                    break
                future = _turn_executor.submit(_run_one_turn, tenant_id, conv_id, prompt)
                future.result(timeout=TURN_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                # The likely real cause of the exact symptom reported
                # live (2026-08-31): "finishing her current turn, then
                # stopping" stuck with no end in sight. Now bounded —
                # stops the loop cleanly rather than waiting forever.
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


def start(tenant_id: str, conv_id: str, mode: str) -> Dict:
    """Raises ValueError (via autonomy.start) if already running for
    this tenant — never silently replaces an active run."""
    rec = autonomy.start(tenant_id, conv_id, mode)
    t = threading.Thread(target=_loop, args=(tenant_id, conv_id, mode),
                         name=f"seira-autonomy-{tenant_id}", daemon=True)
    _threads[tenant_id] = t
    t.start()
    return rec


def stop(tenant_id: str) -> Dict:
    return autonomy.request_stop(tenant_id)


def status(tenant_id: str) -> Dict:
    return autonomy.status(tenant_id)
