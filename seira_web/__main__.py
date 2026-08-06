import os

import uvicorn

from seira_web.tripwire_loop import start_background_tripwire

if __name__ == "__main__":
    if os.environ.get("SEIRA_DISABLE_BACKGROUND_TRIPWIRE") != "1":
        start_background_tripwire()
    uvicorn.run("seira_web.app:app",
                host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
