"""In-process tripwire loop for single-service Railway deployments.

Railway volumes attach to exactly one service; there is no shared-
volume mechanism for a second cron service to reach the same disk.
Rather than fight that, the tripwire runs as a background thread
inside the Sanctum's own web process, sharing its volume for free.

Started from seira_web.__main__ alongside uvicorn. Failures are
logged, never raised — a tripwire bug must not take the site down;
the tripwire's OWN halts are the only thing meant to do that, and
those are exactly what run_tripwire()/tripwire_all() already handle.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 900  # 15 minutes


def _tick() -> None:
    from seira_core.tenancy import tripwire_all
    try:
        results = tripwire_all()
        halted = {t: r for t, r in results.items() if r.get("halted")}
        if halted:
            logger.warning("Seira tripwire: %d tenant(s) halted: %s",
                           len(halted), sorted(halted))
        else:
            logger.info("Seira tripwire: %d tenant(s) healthy.", len(results))
    except Exception as e:  # never let a sweep bug kill the loop
        logger.error("Seira tripwire sweep failed: %s", e)


def start_background_tripwire(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> threading.Thread:
    def loop():
        while True:
            _tick()
            time.sleep(interval_seconds)
    t = threading.Thread(target=loop, name="seira-tripwire", daemon=True)
    t.start()
    return t
