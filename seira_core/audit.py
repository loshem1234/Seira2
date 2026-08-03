"""Append-only audit trail of core events.

Serves two Articles directly:

* Art. 43 — learning events (ratification, restoration) must be visibly
  distinguishable from routine activity (tripwire heartbeats). The
  ``event`` field carries that distinction; the Archive (Book IX, later
  phase) will filter on it.
* Art. 38 — the Archive is a read-only *view* over records that already
  exist. This log is one of those underlying records: append-only,
  never edited.

Events are JSON Lines. Writing uses O_APPEND so concurrent appenders
cannot interleave partial lines on POSIX filesystems for reasonably
sized records.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Dict, Optional

from seira_core.paths import audit_dir, audit_log_path

# Event types. Learning events (Art. 43) are marked with "learning": True
# when logged; routine events are not.
EVENT_GENESIS = "genesis"
EVENT_INTELLECT_RATIFIED = "intellect_ratified"
EVENT_INTELLECT_RESTORED = "intellect_restored"
EVENT_TRIPWIRE_OK = "tripwire_ok"
EVENT_TRIPWIRE_HALT = "tripwire_halt"

_LEARNING_EVENTS = {EVENT_INTELLECT_RATIFIED, EVENT_INTELLECT_RESTORED}


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def append_event(event: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Append one event to the audit log and return the record written."""
    audit_dir().mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {
        "ts": _utc_now_iso(),
        "event": event,
        "learning": event in _LEARNING_EVENTS,
        "details": details or {},
    }
    line = json.dumps(record, sort_keys=True, ensure_ascii=False)
    fd = os.open(str(audit_log_path()), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return record
