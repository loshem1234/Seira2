"""Tests for seira_web.cron_loop — the fix for a live bug (2026-09-06):
'Gateway is not running — jobs won't fire automatically.' Confirmed
cause: the only thing that ever checks whether a cron job is due is
Hermes's own ticker, which previously only ran as part of the gateway
process — which Sanctum deliberately doesn't run. This starts that
same, portable, already-proven ticker directly.

These tests mock the underlying cron_tick function specifically —
that function's own job-execution and delivery logic is Hermes's own,
already-tested code, not something to re-prove here. What's being
verified is narrower and specific to this fix: does a real background
thread actually start, and does it actually call the tick function
periodically, the way seira_web/__main__.py now relies on.
"""

import sys
import threading
import time
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_web import cron_loop  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cron_loop_state():
    """Module-level thread/event state — stop any ticker a previous
    test left running and reset before/after each test."""
    cron_loop.stop_background_cron()
    if cron_loop._thread is not None:
        cron_loop._thread.join(timeout=2)
    cron_loop._thread = None
    cron_loop._stop_event = None
    yield
    cron_loop.stop_background_cron()
    if cron_loop._thread is not None:
        cron_loop._thread.join(timeout=2)
    cron_loop._thread = None
    cron_loop._stop_event = None


def test_is_running_false_before_start():
    assert cron_loop.is_running() is False


def test_ticker_actually_starts_a_real_background_thread(monkeypatch):
    tick_calls = []
    monkeypatch.setattr("cron.scheduler.tick",
                        lambda **kw: tick_calls.append(kw))

    cron_loop.start_background_cron(interval=0.05)
    # Give the real thread real wall-clock time to actually run.
    for _ in range(40):
        if tick_calls:
            break
        time.sleep(0.05)

    assert cron_loop.is_running() is True
    assert len(tick_calls) >= 1, "the ticker thread never actually called tick()"


def test_ticker_ticks_more_than_once_over_time(monkeypatch):
    """Not a one-shot — a real periodic loop."""
    tick_calls = []
    monkeypatch.setattr("cron.scheduler.tick",
                        lambda **kw: tick_calls.append(kw))

    cron_loop.start_background_cron(interval=0.02)
    time.sleep(0.5)

    assert len(tick_calls) >= 3, f"expected several ticks, got {len(tick_calls)}"


def test_starting_twice_does_not_spawn_a_second_thread(monkeypatch):
    monkeypatch.setattr("cron.scheduler.tick", lambda **kw: None)
    cron_loop.start_background_cron(interval=0.05)
    first_thread = cron_loop._thread
    cron_loop.start_background_cron(interval=0.05)
    assert cron_loop._thread is first_thread  # no-op, same thread object


def test_stop_actually_stops_the_thread(monkeypatch):
    tick_calls = []
    monkeypatch.setattr("cron.scheduler.tick",
                        lambda **kw: tick_calls.append(kw))
    cron_loop.start_background_cron(interval=0.02)
    time.sleep(0.1)
    assert cron_loop.is_running() is True

    cron_loop.stop_background_cron()
    cron_loop._thread.join(timeout=2)
    assert cron_loop.is_running() is False


def test_a_crashing_tick_does_not_kill_the_ticker_thread(monkeypatch):
    """The real scheduler's own tick loop catches BaseException per
    tick specifically so one bad tick doesn't end the ticker forever —
    confirms that resilience actually holds when driven from here."""
    call_count = {"n": 0}

    def flaky_tick(**kw):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise RuntimeError("simulated tick failure")

    monkeypatch.setattr("cron.scheduler.tick", flaky_tick)
    cron_loop.start_background_cron(interval=0.02)

    for _ in range(60):
        if call_count["n"] >= 4:
            break
        time.sleep(0.05)

    assert call_count["n"] >= 4, "ticker stopped after a failure instead of continuing"
    assert cron_loop.is_running() is True
