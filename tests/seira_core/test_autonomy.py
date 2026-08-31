"""Tests for seira_web.autonomy and seira_web.autonomy_loop —
autonomous mode's state tracking and the actual background loop,
including its real safety caps and the honest (not oversold)
kill-switch semantics: stop takes effect before the next turn, not
mid-generation.
"""

import asyncio
import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_web import autonomy  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state():
    """autonomy's state is a module-level dict — clear it around every
    test so tests can't see each other's tenants."""
    autonomy._state.clear()
    yield
    autonomy._state.clear()


# ---------------- state module ----------------

def test_start_records_the_run():
    rec = autonomy.start("tenant-a", "conv-1", "exploration")
    assert rec["active"] is True
    assert rec["mode"] == "exploration"
    assert rec["conv_id"] == "conv-1"
    assert rec["turn_count"] == 0
    assert rec["stopping"] is False


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        autonomy.start("tenant-a", "conv-1", "not-a-real-mode")


def test_cannot_start_a_second_run_while_one_is_active():
    autonomy.start("tenant-a", "conv-1", "exploration")
    with pytest.raises(ValueError):
        autonomy.start("tenant-a", "conv-2", "contemplation")


def test_different_tenants_are_independent():
    autonomy.start("tenant-a", "conv-1", "exploration")
    rec = autonomy.start("tenant-b", "conv-2", "contemplation")
    assert rec["active"] is True  # not blocked by tenant-a's run


def test_status_of_unknown_tenant_is_inactive():
    assert autonomy.status("never-started")["active"] is False


def test_request_stop_marks_stopping_not_immediately_inactive():
    """The honest kill-switch contract: requesting a stop doesn't
    instantly clear the run — it marks it for the loop to notice and
    exit on its own, since a turn may already be in flight."""
    autonomy.start("tenant-a", "conv-1", "exploration")
    rec = autonomy.request_stop("tenant-a")
    assert rec["stopping"] is True
    assert autonomy.status("tenant-a")["active"] is True  # still active until the loop exits


def test_stop_of_unknown_tenant_is_a_safe_noop():
    assert autonomy.request_stop("never-started") == {"active": False}


def test_record_turn_increments_count():
    autonomy.start("tenant-a", "conv-1", "exploration")
    autonomy.record_turn("tenant-a")
    autonomy.record_turn("tenant-a")
    assert autonomy.status("tenant-a")["turn_count"] == 2


def test_record_turn_of_unknown_tenant_returns_none():
    assert autonomy.record_turn("never-started") is None


def test_is_stopping_true_when_no_run_active():
    assert autonomy.is_stopping("never-started") is True


def test_is_stopping_true_once_stop_requested():
    autonomy.start("tenant-a", "conv-1", "exploration")
    assert autonomy.is_stopping("tenant-a") is False
    autonomy.request_stop("tenant-a")
    assert autonomy.is_stopping("tenant-a") is True


def test_clear_removes_the_run_entirely():
    autonomy.start("tenant-a", "conv-1", "exploration")
    autonomy.clear("tenant-a")
    assert autonomy.status("tenant-a")["active"] is False
    # And a new run can start again, since nothing is "active" anymore.
    rec = autonomy.start("tenant-a", "conv-1", "exploration")
    assert rec["active"] is True


# ---------------- the actual background loop ----------------

class _FakeConvs:
    """Records every append() call so tests can inspect exactly what
    the loop wrote, without touching real disk storage."""
    def __init__(self):
        self.appended = []

    def append(self, conv_id, kind, **fields):
        self.appended.append((conv_id, kind, fields))

    def model_history(self, conv_id):
        return []

    def touch(self, conv_id):
        pass


@pytest.mark.asyncio
async def test_loop_stops_at_max_turns_safety_cap(monkeypatch):
    """The automatic safety cap Loshem confirmed (2026-08-31): even
    with no manual stop, the loop must not run forever unattended."""
    from seira_web import autonomy_loop
    monkeypatch.setattr(autonomy_loop, "MAX_TURNS", 3)
    monkeypatch.setattr(autonomy_loop, "PACING_SECONDS", 0)
    monkeypatch.setattr(autonomy_loop, "MAX_RUNTIME_HOURS", 999)

    fake_convs = _FakeConvs()
    monkeypatch.setattr("seira_web.conversations.append", fake_convs.append)
    monkeypatch.setattr("seira_web.conversations.model_history", fake_convs.model_history)
    monkeypatch.setattr("seira_web.conversations.touch", fake_convs.touch)
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope",
                        lambda *a, **kw: _NullContext())

    call_count = {"n": 0}

    def fake_run_turn(conv_id, prompt, history, emit):
        call_count["n"] += 1
        return {"reply": f"turn {call_count['n']}", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes", fake_run_turn)

    autonomy.start("tenant-a", "conv-1", "exploration")
    await autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    # Stopped at MAX_TURNS=3, not run indefinitely.
    assert call_count["n"] == 3
    assert autonomy.status("tenant-a")["active"] is False  # cleared on exit


@pytest.mark.asyncio
async def test_loop_stops_when_stop_is_requested_between_turns(monkeypatch):
    from seira_web import autonomy_loop
    monkeypatch.setattr(autonomy_loop, "MAX_TURNS", 1000)
    monkeypatch.setattr(autonomy_loop, "PACING_SECONDS", 0)
    monkeypatch.setattr(autonomy_loop, "MAX_RUNTIME_HOURS", 999)

    fake_convs = _FakeConvs()
    monkeypatch.setattr("seira_web.conversations.append", fake_convs.append)
    monkeypatch.setattr("seira_web.conversations.model_history", fake_convs.model_history)
    monkeypatch.setattr("seira_web.conversations.touch", fake_convs.touch)
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope",
                        lambda *a, **kw: _NullContext())

    call_count = {"n": 0}

    def fake_run_turn(conv_id, prompt, history, emit):
        call_count["n"] += 1
        if call_count["n"] == 2:
            autonomy.request_stop("tenant-a")  # simulate the Architect hitting Stop
        return {"reply": "ok", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes", fake_run_turn)

    autonomy.start("tenant-a", "conv-1", "exploration")
    await autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    # The in-flight turn (2) finished and was kept; no turn 3 started.
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_loop_stops_immediately_if_seira_is_halted(monkeypatch):
    """A halted Seira must not act autonomously either — Art. 32.3
    applies here exactly as it does to a normal turn."""
    from seira_web import autonomy_loop
    monkeypatch.setattr(autonomy_loop, "PACING_SECONDS", 0)
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: True)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope",
                        lambda *a, **kw: _NullContext())

    called = {"n": 0}
    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1))

    autonomy.start("tenant-a", "conv-1", "exploration")
    await autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    assert called["n"] == 0  # never even attempted a turn


class _NullContext:
    def __enter__(self): return self
    def __exit__(self, *a): return False
