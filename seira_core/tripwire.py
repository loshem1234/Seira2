"""The tripwire (Const. Art. 32.3) and the halt discipline.

A periodic integrity check confirming:

1. Unity's content matches the Architect's last committed hash;
2. the Intellect chain is unbroken, correctly ordered, anchored to
   Unity, and untampered;
3. the Genesis manifest agrees with both.

Any failure **halts** Seira: a HALT file is written with the reason,
a halt event is appended to the audit trail, and runtime entry points
that call ``assert_not_halted()`` refuse to proceed. Per the Article,
a mismatch "halts the system and alerts immediately, rather than being
logged as a routine event."

Clearing a halt is deliberately manual: the Architect investigates,
resolves the cause, and removes the HALT file themselves. No function
here deletes it — an auto-clear would convert the tripwire into a
routine event, which is exactly what the Article forbids.

Scheduling: run ``python -m seira_core tripwire`` from the fork's cron
scheduler (the gateway ticks it every 60 seconds; see INTEGRATION.md).
Exit codes: 0 healthy, 2 halted.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Dict

from seira_core.audit import EVENT_TRIPWIRE_HALT, EVENT_TRIPWIRE_OK, append_event
from seira_core.errors import (
    IntellectIntegrityError,
    SeiraHaltedError,
    UnityIntegrityError,
)
from seira_core.paths import genesis_manifest_path, halt_path, seira_home


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def is_halted() -> bool:
    return halt_path().exists()


def assert_not_halted() -> None:
    """For runtime entry points: refuse to proceed while halted."""
    if is_halted():
        try:
            reason = halt_path().read_text(encoding="utf-8")
        except OSError:
            reason = "(HALT file unreadable)"
        raise SeiraHaltedError(
            f"Seira is halted (Art. 32.3). The Architect must investigate and "
            f"remove {halt_path()} to clear.\n{reason}"
        )


def _halt(reason: str) -> None:
    payload = {"ts": _utc_now_iso(), "reason": reason}
    halt_path().write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_event(EVENT_TRIPWIRE_HALT, payload)


def run_tripwire() -> Dict[str, Any]:
    """Run the full integrity check. Returns a status dict; on failure the
    HALT file is written and 'halted' is True."""
    from seira_core.intellect import IntellectStore
    from seira_core.unity import verify_unity

    result: Dict[str, Any] = {"ts": _utc_now_iso(), "halted": False, "checks": {}}

    # An existing halt is itself a failed state until the Architect clears it.
    if is_halted():
        result["halted"] = True
        result["checks"]["pre_existing_halt"] = str(halt_path())
        return result

    try:
        lock = verify_unity()
        result["checks"]["unity"] = "ok"

        store = IntellectStore()
        n = store.verify_chain()
        if n == 0:
            raise IntellectIntegrityError(
                "Intellect store is empty despite Unity existing — Genesis "
                "artifacts are inconsistent."
            )
        result["checks"]["intellect"] = f"ok ({n} version(s))"

        manifest_file = genesis_manifest_path()
        if not manifest_file.exists():
            raise UnityIntegrityError("Genesis manifest is missing.")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("unity_sha256") != lock.get("unity_sha256"):
            raise UnityIntegrityError(
                "Genesis manifest and Unity lock disagree on the committed hash."
            )
        history = store.history(verify=False)
        if history and history[0].get("hash") != manifest.get("intellect_v1_hash"):
            raise IntellectIntegrityError(
                "Genesis manifest and Intellect v1 disagree — the founding "
                "record has been altered."
            )
        result["checks"]["genesis_manifest"] = "ok"

    except (UnityIntegrityError, IntellectIntegrityError) as e:
        reason = f"{type(e).__name__}: {e}"
        _halt(reason)
        result["halted"] = True
        result["reason"] = reason
        return result
    except Exception as e:  # Unknown failure is treated as a trip, not ignored.
        reason = f"Unexpected tripwire failure ({type(e).__name__}): {e}"
        _halt(reason)
        result["halted"] = True
        result["reason"] = reason
        return result

    append_event(EVENT_TRIPWIRE_OK, {"seira_home": str(seira_home())})
    return result
