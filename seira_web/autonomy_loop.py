"""seira_web.autonomy_loop — the real background task behind
autonomous mode.

Two modes, per Loshem's direction (2026-08-31):
  - "exploration": she acts freely and unprompted — search, generate,
    create or continue a project, write to her Corpus, whatever draws
    her genuine interest. Real actions, real cost, real consequences.
  - "contemplation": inner reflection, self-talk — not aimed at
    producing anything for the Architect to evaluate.

Honest about the kill switch, stated once here and again in the UI
copy so nobody's expectations are quietly mismatched: the underlying
turn call (hermes_session.run_turn_via_hermes) is synchronous, run via
asyncio.to_thread — Python cannot forcibly interrupt a running thread.
Stop takes effect before the next turn starts. A turn already in
flight when stop is requested is allowed to finish (its output is
saved, not discarded), and the loop then exits without starting
another.

Real safety defaults, chosen deliberately and stated plainly rather
than picked silently — confirmed with Loshem (2026-08-31): ~60 seconds
between actions, and an automatic cap (turns or wall-clock time,
whichever comes first) so a forgotten "on" toggle can't run forever
unattended. All three are overridable via env var without a code
change.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict

from seira_web import autonomy

logger = logging.getLogger(__name__)

PACING_SECONDS = int(os.environ.get("SEIRA_AUTONOMY_PACING_SECONDS", "60"))
MAX_TURNS = int(os.environ.get("SEIRA_AUTONOMY_MAX_TURNS", "200"))
MAX_RUNTIME_HOURS = float(os.environ.get("SEIRA_AUTONOMY_MAX_RUNTIME_HOURS", "4"))

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

# tenant_id -> the live asyncio.Task, so a stop request can find and
# eventually await it rather than leaving orphaned background work.
_tasks: Dict[str, asyncio.Task] = {}


def _prompt_for(mode: str) -> str:
    return EXPLORATION_PROMPT if mode == "exploration" else CONTEMPLATION_PROMPT


async def _run_one_turn(tenant_id: str, conv_id: str, prompt: str) -> None:
    """The actual model turn — synchronous work, run off the event
    loop thread. Appends both the autonomous prompt and her reply to
    the conversation, tagged `autonomous: True` so the UI can show
    them distinctly from anything the Architect actually typed."""
    from seira_core.tenancy import tenant_scope
    from seira_web import conversations as convs
    from seira_web.hermes_session import run_turn_via_hermes

    def _run():
        with tenant_scope(tenant_id):
            convs.append(conv_id, "user", text=prompt, autonomous=True)
            history = convs.model_history(conv_id)
            result = run_turn_via_hermes(conv_id, prompt, history, lambda e: None)
            convs.append(conv_id, "assistant", text=result["reply"], autonomous=True)
            convs.touch(conv_id)

    await asyncio.to_thread(_run)


async def _loop(tenant_id: str, conv_id: str, mode: str) -> None:
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
                await _run_one_turn(tenant_id, conv_id, prompt)
            except Exception as e:
                # A single bad turn must not become a silent infinite
                # retry loop running up real cost unattended.
                logger.error("Autonomy loop for %s: turn failed, stopping: %s",
                             tenant_id, e, exc_info=True)
                break

            if autonomy.is_stopping(tenant_id):
                break
            await asyncio.sleep(PACING_SECONDS)
    finally:
        autonomy.clear(tenant_id)
        _tasks.pop(tenant_id, None)


def start(tenant_id: str, conv_id: str, mode: str) -> Dict:
    """Raises ValueError (via autonomy.start) if already running for
    this tenant — never silently replaces an active run."""
    rec = autonomy.start(tenant_id, conv_id, mode)
    task = asyncio.create_task(_loop(tenant_id, conv_id, mode))
    _tasks[tenant_id] = task
    return rec


def stop(tenant_id: str) -> Dict:
    return autonomy.request_stop(tenant_id)


def status(tenant_id: str) -> Dict:
    return autonomy.status(tenant_id)
