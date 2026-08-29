"""In-process tripwire AND backup loop for single-service Railway
deployments.

Railway volumes attach to exactly one service; there is no shared-
volume mechanism for a second cron service to reach the same disk.
Rather than fight that (a lesson learned the first time, the hard
way — see DECISIONS.md D45), everything that needs to run on a
schedule against this volume runs as ONE background thread inside the
Sanctum's own web process: the tripwire, and now the daily/monthly
backup checks. A second scheduled concern is a reason to extend this
loop, not to spin up a second thread or a second service.

Started from seira_web.__main__ alongside uvicorn. Failures are
logged, never raised — a bug in either check must not take the site
down; the tripwire's OWN halts are the only thing meant to do that,
and a failed backup attempt should be visible in the logs, not fatal.
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

    _backup_tick()


def _backup_tick() -> None:
    from seira_web.backup import run_if_due
    for kind in ("daily", "monthly"):
        try:
            result = run_if_due(kind)
            if result is not None:
                logger.info("Seira backup: created %s backup (%s, %d bytes).",
                           kind, result["path"], result["size_bytes"])
                r2 = result.get("r2", {})
                if r2.get("shipped"):
                    logger.info("Seira backup: shipped to R2 (%s).", r2.get("uploaded_key"))
                elif r2.get("reason") != "not configured":
                    logger.error("Seira backup: R2 shipping failed: %s", r2.get("error"))
        except Exception as e:  # a backup failure must never break the loop
            logger.error("Seira %s backup failed: %s", kind, e)


def start_background_tripwire(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> threading.Thread:
    def loop():
        while True:
            _tick()
            time.sleep(interval_seconds)
    t = threading.Thread(target=loop, name="seira-tripwire", daemon=True)
    t.start()
    return t
