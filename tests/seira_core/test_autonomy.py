"""Tests for seira_web.autonomy and seira_web.autonomy_loop —
autonomous mode's state tracking and the actual background loop,
including its real safety caps and the honest (not oversold)
kill-switch semantics: stop takes effect before the next turn, not
mid-generation.
"""

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
        self._next_id = 1

    def append(self, conv_id, kind, **fields):
        rec = {"id": self._next_id, "kind": kind, **fields}
        self._next_id += 1
        self.appended.append((conv_id, kind, fields))
        return rec

    def model_history(self, conv_id):
        return []

    def touch(self, conv_id):
        pass


def test_loop_stops_at_max_turns_safety_cap(monkeypatch):
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
    autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    # Stopped at MAX_TURNS=3, not run indefinitely.
    assert call_count["n"] == 3
    assert autonomy.status("tenant-a")["active"] is False  # cleared on exit


def test_loop_stops_when_stop_is_requested_between_turns(monkeypatch):
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
    autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    # The in-flight turn (2) finished and was kept; no turn 3 started.
    assert call_count["n"] == 2


def test_loop_stops_immediately_if_seira_is_halted(monkeypatch):
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
    autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    assert called["n"] == 0  # never even attempted a turn


class _NullContext:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_turn_timeout_stops_the_loop_cleanly(monkeypatch):
    """The likely real cause of the live-reported symptom (2026-08-31):
    'finishing her current turn, then stopping' stuck with no bound. A
    hung or unusually slow turn must not block the loop forever."""
    from seira_web import autonomy_loop
    monkeypatch.setattr(autonomy_loop, "TURN_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(autonomy_loop, "PACING_SECONDS", 0)
    monkeypatch.setattr(autonomy_loop, "MAX_RUNTIME_HOURS", 999)

    fake_convs = _FakeConvs()
    monkeypatch.setattr("seira_web.conversations.append", fake_convs.append)
    monkeypatch.setattr("seira_web.conversations.model_history", fake_convs.model_history)
    monkeypatch.setattr("seira_web.conversations.touch", fake_convs.touch)
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope",
                        lambda *a, **kw: _NullContext())

    def hanging_run_turn(conv_id, prompt, history, emit):
        import time
        time.sleep(2)  # far longer than the 0.05s timeout
        return {"reply": "should never get here", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes", hanging_run_turn)

    autonomy.start("tenant-a", "conv-1", "exploration")
    autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    # The loop exited (didn't hang forever) and cleared state.
    assert autonomy.status("tenant-a")["active"] is False


def test_live_events_are_published_during_a_turn(monkeypatch):
    """The real fix for 'I wanted to see what she's doing live':
    events must actually reach the broadcast registry, not be
    discarded (the first version of this loop used emit=lambda e: None)."""
    from seira_web import autonomy_loop, live_events
    monkeypatch.setattr(autonomy_loop, "PACING_SECONDS", 0)
    monkeypatch.setattr(autonomy_loop, "MAX_TURNS", 1)
    monkeypatch.setattr(autonomy_loop, "MAX_RUNTIME_HOURS", 999)

    fake_convs = _FakeConvs()
    monkeypatch.setattr("seira_web.conversations.append", fake_convs.append)
    monkeypatch.setattr("seira_web.conversations.model_history", fake_convs.model_history)
    monkeypatch.setattr("seira_web.conversations.touch", fake_convs.touch)
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope",
                        lambda *a, **kw: _NullContext())

    def fake_run_turn(conv_id, prompt, history, emit):
        emit({"event": "tool", "tool": "web_search"})
        emit({"event": "reply", "text": "found something"})
        return {"reply": "found something", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes", fake_run_turn)

    subscriber = live_events.subscribe("conv-1")
    autonomy.start("tenant-a", "conv-1", "exploration")
    autonomy_loop._loop("tenant-a", "conv-1", "exploration")

    received = []
    while not subscriber.empty():
        received.append(subscriber.get_nowait())
    live_events.unsubscribe("conv-1", subscriber)

    kinds = [e["event"] for e in received]
    assert "autonomous_turn_started" in kinds  # the prompt bubble, from scratch
    assert "tool" in kinds
    assert "reply" in kinds
    # run_turn_via_hermes emits its own reply — must not be duplicated
    # by autonomy_loop emitting a second one.
    assert kinds.count("reply") == 1


# ---------------- live_events: the pub/sub registry itself ----------------

def test_publish_reaches_a_subscriber():
    from seira_web import live_events
    q = live_events.subscribe("conv-x")
    live_events.publish("conv-x", {"event": "tool", "tool": "web_search"})
    assert q.get_nowait()["tool"] == "web_search"
    live_events.unsubscribe("conv-x", q)


def test_publish_to_a_conversation_with_no_subscribers_is_a_safe_noop():
    from seira_web import live_events
    live_events.publish("conv-nobody-is-watching", {"event": "tool"})  # must not raise


def test_publish_does_not_cross_conversations():
    from seira_web import live_events
    q1 = live_events.subscribe("conv-a")
    q2 = live_events.subscribe("conv-b")
    live_events.publish("conv-a", {"event": "tool", "tool": "only-for-a"})
    assert q1.get_nowait()["tool"] == "only-for-a"
    assert q2.empty()
    live_events.unsubscribe("conv-a", q1)
    live_events.unsubscribe("conv-b", q2)


def test_multiple_subscribers_to_the_same_conversation_both_receive():
    from seira_web import live_events
    q1 = live_events.subscribe("conv-shared")
    q2 = live_events.subscribe("conv-shared")
    live_events.publish("conv-shared", {"event": "reply", "text": "hi"})
    assert q1.get_nowait()["text"] == "hi"
    assert q2.get_nowait()["text"] == "hi"
    live_events.unsubscribe("conv-shared", q1)
    live_events.unsubscribe("conv-shared", q2)


def test_unsubscribe_stops_further_delivery():
    from seira_web import live_events
    q = live_events.subscribe("conv-y")
    live_events.unsubscribe("conv-y", q)
    live_events.publish("conv-y", {"event": "tool"})
    assert q.empty()


# ---------------- the actual original bug, reproduced and proven fixed ----------------

def test_start_works_when_called_from_a_worker_thread(monkeypatch):
    """The real, live bug (2026-08-31): 'stuck at turn 0, running 2
    minutes, nothing enters the chat.' Root cause, confirmed by
    reproduction before writing this fix: the first version scheduled
    the loop via asyncio.create_task() from inside a synchronous
    FastAPI route handler — which runs in a thread-pool worker thread,
    not on the event loop. asyncio.create_task() requires a running
    event loop IN THE CALLING THREAD and raised RuntimeError every
    time, silently, after autonomy.start() had already marked the run
    "active" — leaving it stuck forever with no loop ever actually
    running. This test simulates that exact calling context (start()
    invoked from a worker thread while a real event loop runs
    elsewhere) and proves the loop now actually executes."""
    import threading
    import time as _time
    from seira_web import autonomy_loop

    monkeypatch.setattr(autonomy_loop, "PACING_SECONDS", 0.05)
    monkeypatch.setattr(autonomy_loop, "MAX_TURNS", 1)
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
        return {"reply": "did something", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes", fake_run_turn)

    result_holder = {}

    def worker():
        # Exactly what a sync FastAPI route handler does: call
        # autonomy_loop.start() from a plain (non-event-loop) thread.
        result_holder["rec"] = autonomy_loop.start("tenant-worker", "conv-1", "exploration")

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=2)

    assert "rec" in result_holder, "start() must not raise when called from a worker thread"
    assert result_holder["rec"]["active"] is True

    # Give the real background loop actual wall-clock time to run.
    for _ in range(40):  # up to ~2s
        if not autonomy.status("tenant-worker")["active"]:
            break
        _time.sleep(0.05)

    assert call_count["n"] >= 1, (
        "the loop must have actually executed a turn — this is exactly "
        "what 'stuck at turn 0' looked like when it didn't"
    )
    assert autonomy.status("tenant-worker")["active"] is False  # completed and cleared
