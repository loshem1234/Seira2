"""Tests for seira_web.weekly_scheduler — fixed slots, one at a time."""
import datetime as dt
import sys
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from seira_web import weekly_scheduler as W  # noqa: E402

NY = ZoneInfo("America/New_York")


def at(y, m, d, h=0, mi=0):
    return dt.datetime(y, m, d, h, mi, tzinfo=NY)


# 2026-10-11 is a Sunday.
SUN = (6, 4, 0)   # sun 04:00


class _Null:
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_SLOTS", raising=False)
    for v in W.DISABLE_ENV.values():
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda t: _Null())
    monkeypatch.setattr("seira_core.tenancy.list_tenants", lambda: ["t1"])
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    return tmp_path


def test_latest_slot_math():
    assert W.latest_slot(SUN, at(2026, 10, 11, 5)) == at(2026, 10, 11, 4)
    assert W.latest_slot(SUN, at(2026, 10, 11, 3)) == at(2026, 10, 4, 4)   # before slot -> last week
    assert W.latest_slot(SUN, at(2026, 10, 14, 12)) == at(2026, 10, 11, 4)  # midweek
    assert W.next_slot(SUN, at(2026, 10, 14, 12)) == at(2026, 10, 18, 4)


def test_default_slots_are_spaced_and_ordered():
    s = W.slots()
    assert s["summaries"] < s["recollection"] < s["distillation"]
    assert all(v[0] == 6 for v in s.values())


def test_env_override_and_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("SEIRA_SLOTS", "distillation=sat 23:30,recollection=nonsense")
    s = W.slots()
    assert s["distillation"] == (5, 23, 30)
    assert s["recollection"] == W.parse_slot(W.DEFAULT_SLOTS["recollection"])


def test_first_sight_is_baselined_not_run(env):
    now = at(2026, 10, 11, 5).astimezone(dt.timezone.utc)
    assert W.is_due("t1", "recollection", now) is False        # baseline written
    assert W._read_state()["recollection"]["outcome"] == "baseline"
    assert W.is_due("t1", "recollection", now) is False        # still not due


def test_due_after_slot_when_not_run_this_week(env):
    W._write_state({"recollection": {"last_run": at(2026, 10, 4, 4, 30).isoformat()}})
    assert W.is_due("t1", "recollection", at(2026, 10, 11, 3)) is False   # slot not reached
    assert W.is_due("t1", "recollection", at(2026, 10, 11, 4, 1)) is True


def test_restart_cannot_refire_a_routine_that_ran_this_week(env):
    W._write_state({"recollection": {"last_run": at(2026, 10, 11, 4, 20).isoformat()}})
    for now in (at(2026, 10, 11, 5), at(2026, 10, 12, 9), at(2026, 10, 15, 9)):
        assert W.is_due("t1", "recollection", now) is False


def test_catchup_window(env):
    W._write_state({"recollection": {"last_run": at(2026, 10, 4, 4, 30).isoformat()}})
    assert W.is_due("t1", "recollection", at(2026, 10, 12, 9)) is True      # ~29h late, within 48h
    assert W.is_due("t1", "recollection", at(2026, 10, 14, 9)) is False     # 3 days late -> wait for next slot


def test_tick_runs_due_routines_in_order_one_at_a_time(env, monkeypatch):
    sunday = at(2026, 10, 11, 8)           # all three slots passed
    last_week = at(2026, 10, 4, 12).isoformat()
    W._write_state({k: {"last_run": last_week} for k in W.ORDER})
    order, concurrent = [], {"n": 0, "max": 0}

    def fake(name, tenant, manual=False):
        concurrent["n"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["n"])
        order.append(name)
        concurrent["n"] -= 1

    monkeypatch.setattr(W, "run_routine", fake)
    ran = W.tick(sunday)
    assert order == ["summaries", "recollection", "distillation"]
    assert concurrent["max"] == 1 and len(ran) == 3
    assert W.tick(sunday) == []            # already ran this week


def test_disabled_routine_is_skipped(env, monkeypatch):
    monkeypatch.setenv("SEIRA_DISABLE_RECOLLECTION", "1")
    sunday = at(2026, 10, 11, 8)
    W._write_state({k: {"last_run": at(2026, 10, 4, 12).isoformat()} for k in W.ORDER})
    seen = []
    monkeypatch.setattr(W, "run_routine", lambda n, t, manual=False: seen.append(n))
    W.tick(sunday)
    assert "recollection" not in seen and "distillation" in seen


def test_failure_is_recorded_and_does_not_block_the_rest(env, monkeypatch):
    sunday = at(2026, 10, 11, 8)
    W._write_state({k: {"last_run": at(2026, 10, 4, 12).isoformat()} for k in W.ORDER})

    def fake(name, tenant, manual=False):
        if name == "recollection":
            raise RuntimeError("boom")

    monkeypatch.setattr(W, "run_routine", fake)
    W.tick(sunday)
    st = W._read_state()
    assert st["recollection"]["outcome"].startswith("error")
    assert st["distillation"]["outcome"] == "ok"


def test_manual_shares_the_lock_and_does_not_touch_saved_dates(env, monkeypatch):
    gate = threading.Event()
    done = threading.Event()

    def slow(name, tenant, manual=False):
        gate.wait(2)
        done.set()

    monkeypatch.setattr(W, "run_routine", slow)
    ok, msg = W.try_start_manual("distillation", "t1")
    assert ok
    ok2, msg2 = W.try_start_manual("recollection", "t1")
    assert not ok2 and "running" in msg2.lower()
    assert W.tick(at(2026, 10, 11, 8)) == []        # scheduler also yields
    gate.set(); done.wait(2)
    for _ in range(50):
        if W._run_lock.acquire(blocking=False):
            W._run_lock.release(); break
        threading.Event().wait(0.05)
    assert W._read_state().get("distillation") is None


def test_status_shape(env):
    s = W.status("t1")
    assert [r["name"] for r in s["routines"]] == W.ORDER
    assert all(r["slot"] and r["next_run"] for r in s["routines"])
