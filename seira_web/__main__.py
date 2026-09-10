import os

import uvicorn

from seira_web.conversation_summarizer import start_background_summarizer
from seira_web.cron_loop import start_background_cron
from seira_web.delegation_watcher import start_background_delegation_watcher
from seira_web.tripwire_loop import start_background_tripwire

if __name__ == "__main__":
    if os.environ.get("SEIRA_DISABLE_BACKGROUND_TRIPWIRE") != "1":
        start_background_tripwire()
    if os.environ.get("SEIRA_DISABLE_BACKGROUND_CRON") != "1":
        start_background_cron()
    if os.environ.get("SEIRA_DISABLE_DELEGATION_WATCHER") != "1":
        start_background_delegation_watcher()
    if os.environ.get("SEIRA_DISABLE_CONVERSATION_SUMMARIZER") != "1":
        start_background_summarizer()
    uvicorn.run("seira_web.app:app",
                host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
