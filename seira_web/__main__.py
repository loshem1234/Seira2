import os

import uvicorn

from seira_web.cron_loop import start_background_cron
from seira_web.delegation_watcher import start_background_delegation_watcher
from seira_web.tripwire_loop import start_background_tripwire
from seira_web.weekly_scheduler import start_weekly_scheduler

if __name__ == "__main__":
    if os.environ.get("SEIRA_DISABLE_BACKGROUND_TRIPWIRE") != "1":
        start_background_tripwire()
    if os.environ.get("SEIRA_DISABLE_BACKGROUND_CRON") != "1":
        start_background_cron()
    if os.environ.get("SEIRA_DISABLE_DELEGATION_WATCHER") != "1":
        start_background_delegation_watcher()
    # Summaries, Recollection and Distillation share ONE scheduler with fixed
    # weekly slots (see seira_web/weekly_scheduler.py). Each can still be
    # disabled individually via its SEIRA_DISABLE_* variable.
    if os.environ.get("SEIRA_DISABLE_WEEKLY_SCHEDULER") != "1":
        start_weekly_scheduler()
    uvicorn.run("seira_web.app:app",
                host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
