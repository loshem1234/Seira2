"""seira_web.cron_loop — starts Hermes's own built-in cron ticker
(cron.scheduler_provider.InProcessCronScheduler) as a background
thread within Sanctum's own process.

Real, live bug (2026-09-06): "Gateway is not running — jobs won't
fire automatically." Confirmed precisely why, not guessed at: the
ticker that actually checks "is a job due yet" only ever ran as part
of gateway/run.py's own boot sequence, and Sanctum deliberately
doesn't run the gateway — a real architectural decision (Part 9),
Sanctum being one lean FastAPI process rather than Hermes's full
multi-service deployment. Jobs were being scheduled (recorded)
correctly the entire time; nothing was ever checking the clock to
actually fire them.

The fix is smaller than "Gateway is not running" makes it sound.
InProcessCronScheduler is explicitly documented as portable — "the
caller runs it in a daemon thread" — with every gateway-specific
parameter (adapters, loop, can_dispatch) optional and gracefully
None-able. Nothing about job execution or delivery is reimplemented
here; this runs the exact same scheduler and the exact same
cron.scheduler.tick / _deliver_result logic every other Hermes
deployment uses, just started directly instead of as a gateway
subsystem — the same "reuse the proven pattern, don't invent a
parallel one" approach already used for seira_web/tripwire_loop.py.

Checked before writing this: a real external provider (Chronos)
exists as a documented extension point but requires a Nous Research
account and a new publicly-reachable webhook endpoint for their
infrastructure to call back into — a genuinely different, third-party
dependency, not a lighter version of this fix. Starting the real
built-in ticker ourselves is both simpler and requires nothing new
from outside this deployment.

HERMES_HOME is a single, global, process-wide value in this
deployment (confirmed: seira_web/hermes_tools.py notes the skills
directory — and, by the same architecture, the cron store — are
HERMES_HOME-scoped, not per-tenant), so this runs the scheduler's
single-profile path, not its multi-profile fan-out.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None


def start_background_cron(interval: int = 60) -> None:
    """Start the real cron ticker once, for the life of this process.
    Safe to call more than once — a later call is a no-op while the
    ticker thread is already alive, matching
    seira_web.tripwire_loop.start_background_tripwire's own contract."""
    global _stop_event, _thread
    if _thread is not None and _thread.is_alive():
        return

    from cron.scheduler_provider import InProcessCronScheduler

    _stop_event = threading.Event()
    scheduler = InProcessCronScheduler()
    local_stop_event = _stop_event

    def _run() -> None:
        try:
            scheduler.start(local_stop_event, interval=interval)
        except Exception:
            # A crashed ticker thread must be loud in the logs — a
            # cron job silently never firing again is exactly the
            # failure mode this whole fix exists to close.
            logger.error("Sanctum cron ticker thread crashed", exc_info=True)

    _thread = threading.Thread(target=_run, name="seira-cron-ticker", daemon=True)
    _thread.start()
    logger.info("Sanctum cron ticker started (interval=%ds)", interval)


def stop_background_cron() -> None:
    if _stop_event is not None:
        _stop_event.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
