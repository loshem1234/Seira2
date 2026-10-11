"""seira_web.weekly_scheduler — one scheduler for all her weekly routines.

Before this, the chat summarizer, Recollection and Distillation each ran
their own loop, all anchored to process start — so every deploy fired
them together, and two of them re-triggered on restart. Now one loop
owns them: each has a fixed weekly slot, they run strictly one at a time
in slot order, and each routine's last scheduled run is saved to disk so
a restart can never re-trigger one that already ran this week.

Defaults (America/New_York, Sundays): summaries 02:00, recollection
04:00, distillation 07:00. Override with env:
  SEIRA_SCHEDULE_TZ=America/New_York
  SEIRA_SLOTS="summaries=sun 02:00,recollection=sun 04:00,distillation=sun 07:00"
Disable one routine: SEIRA_DISABLE_CONVERSATION_SUMMARIZER=1,
SEIRA_DISABLE_RECOLLECTION=1, SEIRA_DISABLE_DISTILLATION=1; disable the
whole scheduler: SEIRA_DISABLE_WEEKLY_SCHEDULER=1.

Rules:
* A routine is due when its most recent slot time has passed and it has
  not run since that slot. If the server was down at slot time it catches
  up on return, but only within CATCHUP_HOURS; otherwise it waits.
* First time a routine is seen (no saved date) it is baselined to "now"
  — nothing fires on the first deploy; the first run is the next slot.
* Manual runs (Commands page) go through the same one-at-a-time lock and
  do not change the saved scheduled date.
* Each routine still applies its own "is there anything to do" check, so
  a quiet week costs nothing.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CATCHUP_HOURS = 48
CHECK_INTERVAL = 60.0
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DEFAULT_SLOTS = {
    "summaries": "sun 02:00",
    "recollection": "sun 04:00",
    "distillation": "sun 07:00",
}
ORDER = ["summaries", "recollection", "distillation"]
LABELS = {"summaries": "Chat summaries", "recollection": "Recollection",
          "distillation": "Psyche Distillation",
          "recollection_full": "Full Recollection reprocess"}
DISABLE_ENV = {
    "summaries": "SEIRA_DISABLE_CONVERSATION_SUMMARIZER",
    "recollection": "SEIRA_DISABLE_RECOLLECTION",
    "distillation": "SEIRA_DISABLE_DISTILLATION",
}

_stop_event: Optional[threading.Event] = None
_thread: Optional[threading.Thread] = None
_run_lock = threading.Lock()
_current: Optional[str] = None


# ---------------- configuration ----------------

def tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("SEIRA_SCHEDULE_TZ", "America/New_York"))


def parse_slot(text: str) -> Tuple[int, int, int]:
    day, hm = text.strip().lower().split()
    h, m = hm.split(":")
    return DAYS[day[:3]], int(h), int(m)


def slots() -> Dict[str, Tuple[int, int, int]]:
    spec = dict(DEFAULT_SLOTS)
    for part in os.environ.get("SEIRA_SLOTS", "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() in spec:
                spec[k.strip()] = v.strip()
    out = {}
    for k, v in spec.items():
        try:
            out[k] = parse_slot(v)
        except Exception:
            out[k] = parse_slot(DEFAULT_SLOTS[k])
    return out


def enabled(name: str) -> bool:
    return os.environ.get(DISABLE_ENV[name]) != "1"


def _slot_at(week_start: _dt.datetime, slot: Tuple[int, int, int]) -> _dt.datetime:
    d, h, m = slot
    return (week_start + _dt.timedelta(days=d)).replace(hour=h, minute=m)


def latest_slot(slot: Tuple[int, int, int], now: _dt.datetime) -> _dt.datetime:
    """Most recent occurrence of the slot at or before *now* (tz-aware)."""
    local = now.astimezone(tz())
    monday = (local - _dt.timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    cand = _slot_at(monday, slot)
    if cand > local:
        cand = _slot_at(monday - _dt.timedelta(days=7), slot)
    return cand


def next_slot(slot: Tuple[int, int, int], now: _dt.datetime) -> _dt.datetime:
    last = latest_slot(slot, now)
    nxt = last + _dt.timedelta(days=7)
    return nxt


# ---------------- saved state (per tenant) ----------------

def _state_file():
    from seira_core.paths import seira_home
    d = seira_home() / "schedule"
    d.mkdir(parents=True, exist_ok=True)
    return d / "last_run.json"


def _read_state() -> Dict[str, Any]:
    p = _state_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(st: Dict[str, Any]) -> None:
    _state_file().write_text(json.dumps(st, indent=1), encoding="utf-8")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def is_due(tenant_id: str, name: str, now: Optional[_dt.datetime] = None) -> bool:
    """Caller holds tenant_scope. Baselines an unseen routine to now."""
    now = now or _now()
    st = _read_state()
    rec = st.get(name)
    if not rec or not rec.get("last_run"):
        st[name] = {"last_run": now.isoformat(), "outcome": "baseline"}
        _write_state(st)
        return False
    slot_time = latest_slot(slots()[name], now)
    last_run = _dt.datetime.fromisoformat(rec["last_run"])
    if last_run >= slot_time.astimezone(_dt.timezone.utc):
        return False
    return (now - slot_time) <= _dt.timedelta(hours=CATCHUP_HOURS)


def _mark_ran(name: str, outcome: str, now: Optional[_dt.datetime] = None) -> None:
    st = _read_state()
    st[name] = {"last_run": (now or _now()).isoformat(), "outcome": outcome}
    _write_state(st)


# ---------------- routines ----------------

def _routine_fn(name: str) -> Callable[[str], Any]:
    if name == "summaries":
        from seira_web import conversation_summarizer as m
        return m._run_pass_for_tenant
    if name == "recollection":
        from seira_web import recollection as m
        return m._run_session_for_tenant
    from seira_web import distillation as m
    return m.run_for_tenant


def run_routine(name: str, tenant_id: str, manual: bool = False) -> None:
    if name == "recollection_full":
        from seira_web import recollection as _rec
        _rec.run_full_reprocess(tenant_id)
        return
    fn = _routine_fn(name)
    if name == "distillation":
        fn(tenant_id, manual=manual)
    elif name == "recollection" and manual:
        fn(tenant_id, force_all=False)
    else:
        fn(tenant_id)


# ---------------- the loop ----------------

def tick(now: Optional[_dt.datetime] = None) -> List[str]:
    """Run whatever is due, one routine at a time. Returns what ran."""
    from seira_core.tenancy import list_tenants, tenant_scope
    from seira_core.tripwire import is_halted

    global _current
    ran: List[str] = []
    if not _run_lock.acquire(blocking=False):
        return ran
    try:
        for name in ORDER:
            if not enabled(name):
                continue
            for tenant_id in list_tenants():
                if _stop_event is not None and _stop_event.is_set():
                    return ran
                with tenant_scope(tenant_id):
                    if is_halted() or not is_due(tenant_id, name, now):
                        continue
                _current = name
                outcome = "ok"
                try:
                    run_routine(name, tenant_id)
                except Exception as e:
                    outcome = f"error: {str(e)[:200]}"
                    logger.error("Scheduled %s failed for %s", name, tenant_id,
                                 exc_info=True)
                with tenant_scope(tenant_id):
                    _mark_ran(name, outcome, now)
                ran.append(f"{name}:{tenant_id}")
    finally:
        _current = None
        _run_lock.release()
    return ran


def try_start_manual(name: str, tenant_id: str) -> Tuple[bool, str]:
    """Commands-page trigger. One at a time, same lock as the scheduler."""
    global _current
    if name not in LABELS:
        return False, f"Unknown routine {name!r}."
    if not _run_lock.acquire(blocking=False):
        return False, (f"{LABELS.get(_current or '', 'Another routine')} is running "
                       "right now — try again when it finishes.")

    def _go():
        global _current
        _current = name
        try:
            run_routine(name, tenant_id, manual=True)
        except Exception:
            logger.error("Manual %s failed", name, exc_info=True)
        finally:
            _current = None
            _run_lock.release()

    threading.Thread(target=_go, name=f"seira-manual-{name}", daemon=True).start()
    return True, f"{LABELS[name]} started in the background."


def status(tenant_id: str) -> Dict[str, Any]:
    from seira_core.tenancy import tenant_scope
    now = _now()
    out = {"timezone": str(tz()), "running": _current, "routines": []}
    with tenant_scope(tenant_id):
        st = _read_state()
        for name in ORDER:
            sl = slots()[name]
            rec = st.get(name) or {}
            lt = latest_slot(sl, now)
            nxt = lt if is_pending(rec, sl, now) else lt + _dt.timedelta(days=7)
            out["routines"].append({
                "name": name, "label": LABELS[name], "enabled": enabled(name),
                "slot": f"{[k for k, v in DAYS.items() if v == sl[0]][0]} {sl[1]:02d}:{sl[2]:02d}",
                "last_run": rec.get("last_run"), "last_outcome": rec.get("outcome"),
                "next_run": nxt.isoformat(),
            })
    return out


def is_pending(rec: Dict[str, Any], sl, now) -> bool:
    """A slot has passed unrun and is still inside the catch-up window."""
    if not rec.get("last_run"):
        return False
    slot_time = latest_slot(sl, now)
    last = _dt.datetime.fromisoformat(rec["last_run"])
    return last < slot_time.astimezone(_dt.timezone.utc) and \
        (now - slot_time) <= _dt.timedelta(hours=CATCHUP_HOURS)


def _loop() -> None:
    while not _stop_event.is_set():
        try:
            tick()
        except Exception:
            logger.error("Weekly scheduler tick failed", exc_info=True)
        _stop_event.wait(CHECK_INTERVAL)


def start_weekly_scheduler() -> None:
    global _stop_event, _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_loop, name="seira-weekly-scheduler", daemon=True)
    _thread.start()
    logger.info("Weekly scheduler started: %s", {k: v for k, v in slots().items()})


def stop_weekly_scheduler() -> None:
    if _stop_event is not None:
        _stop_event.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
