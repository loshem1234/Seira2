"""Tests for seira_web.delegation_watcher — the fix for delegated
subagent work vanishing (2026-09-06). Confirmed cause: the work
genuinely dispatches and runs, but nothing in Sanctum's stack ever
drained the completion queue to deliver results back — every consumer
of it lives in gateway/run.py, gateway/platforms/api_server.py, or
tui_gateway/server.py, none of which run here.
"""

import queue
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

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402
from seira_web import conversations as convs  # noqa: E402
from seira_web import delegation_watcher  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    delegation_watcher.stop_background_delegation_watcher()
    if delegation_watcher._thread is not None:
        delegation_watcher._thread.join(timeout=2)
    delegation_watcher._thread = None
    delegation_watcher._stop_event = None
    yield
    delegation_watcher.stop_background_delegation_watcher()
    if delegation_watcher._thread is not None:
        delegation_watcher._thread.join(timeout=2)
    delegation_watcher._thread = None
    delegation_watcher._stop_event = None


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    from seira_web import accounts as acct
    from seira_core.tenancy import tenant_scope
    acct.create_account("a@example.com", "long-enough-password")
    account = acct.verify_login("a@example.com", "long-enough-password")
    tenant_id = account["tenant_id"]
    with tenant_scope(tenant_id):
        perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
        perform_psyche_genesis(
            [{"category": "self_model", "content": "I receive what returns to me."}],
            architect="L")
        conv = convs.create_conversation()
    return tenant_id, conv["conv_id"]


# ---------------- notification formatting ----------------

def test_format_notification_includes_goal_and_results():
    evt = {
        "goal": "research three topics",
        "results": [
            {"status": "completed", "result": "topic A findings"},
            {"status": "error", "error": "topic B failed: timeout"},
        ],
    }
    text = delegation_watcher._format_notification(evt)
    assert "research three topics" in text
    assert "topic A findings" in text
    assert "topic B failed: timeout" in text
    assert "completed" in text and "error" in text


def test_format_notification_handles_no_results_gracefully():
    text = delegation_watcher._format_notification({"goal": "a task"})
    assert "a task" in text
    assert "No structured results" in text


# ---------------- routing: finding the owning tenant ----------------

def test_find_owning_tenant_locates_the_right_tenant(founded):
    tenant_id, conv_id = founded
    found = delegation_watcher._find_owning_tenant(conv_id)
    assert found == tenant_id


def test_find_owning_tenant_returns_none_for_unknown_conv(founded):
    assert delegation_watcher._find_owning_tenant("conv-does-not-exist") is None


def test_find_owning_tenant_works_for_a_conversation_with_no_messages_yet(founded):
    """Real bug caught while building this: records() correctly
    returns an empty list for a conversation with no messages, and an
    empty list is falsy in Python — checking 'if records(conv_id)'
    would incorrectly treat a genuinely-existing, just-empty
    conversation as not found. Fixed by checking the conversation
    index instead."""
    tenant_id, conv_id = founded
    from seira_core.tenancy import tenant_scope
    with tenant_scope(tenant_id):
        assert convs.records(conv_id) == []  # confirms the precondition
    found = delegation_watcher._find_owning_tenant(conv_id)
    assert found == tenant_id


# ---------------- delivery: the real, governed turn ----------------

def test_deliver_one_appends_notification_and_reply(founded, monkeypatch):
    tenant_id, conv_id = founded

    def fake_run_turn(cid, prompt, history, emit, **kwargs):
        emit({"event": "reply", "text": "I received the delegated results."})
        return {"reply": "I received the delegated results.", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes", fake_run_turn)

    evt = {"type": "async_delegation", "goal": "test task",
          "parent_session_id": conv_id,
          "results": [{"status": "completed", "result": "done"}]}
    delegation_watcher._deliver_one(evt)

    from seira_core.tenancy import tenant_scope
    with tenant_scope(tenant_id):
        recs = convs.records(conv_id)
    kinds = [(r["kind"], r.get("autonomous")) for r in recs]
    assert ("user", True) in kinds
    assert ("assistant", True) in kinds
    user_rec = [r for r in recs if r["kind"] == "user"][-1]
    assert "test task" in user_rec["text"]
    assert "done" in user_rec["text"]


def test_deliver_one_with_no_parent_session_id_is_a_safe_noop(founded, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1))
    delegation_watcher._deliver_one({"type": "async_delegation", "goal": "x", "results": []})
    assert called["n"] == 0  # never attempted a turn with nowhere to route it


def test_deliver_one_with_unknown_conversation_is_a_safe_noop(founded, monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1))
    evt = {"type": "async_delegation", "goal": "x", "results": [],
          "parent_session_id": "conv-nonexistent"}
    delegation_watcher._deliver_one(evt)
    assert called["n"] == 0


def test_deliver_one_failure_is_logged_not_raised(founded, monkeypatch):
    """A failed delivery must never crash the watcher loop."""
    tenant_id, conv_id = founded

    def failing_run_turn(*a, **kw):
        raise RuntimeError("simulated API failure")

    monkeypatch.setattr("seira_web.hermes_session.run_turn_via_hermes", failing_run_turn)
    evt = {"type": "async_delegation", "goal": "x", "results": [],
          "parent_session_id": conv_id}
    delegation_watcher._deliver_one(evt)  # must not raise


# ---------------- the background loop itself ----------------

def test_loop_only_consumes_async_delegation_events_not_others(monkeypatch):
    """Non-delegation completion events (e.g. watch-pattern events)
    must be requeued untouched, not consumed — other consumers own
    those."""
    from tools.process_registry import process_registry

    process_registry.completion_queue.put({"type": "watch_pattern", "data": "not mine"})
    process_registry.completion_queue.put(
        {"type": "async_delegation", "goal": "x", "results": []})  # no parent_session_id -> safe drop

    delegation_watcher.start_background_delegation_watcher(interval=0.05)
    time.sleep(0.3)
    delegation_watcher.stop_background_delegation_watcher()

    remaining = []
    while not process_registry.completion_queue.empty():
        remaining.append(process_registry.completion_queue.get_nowait())
    assert any(e.get("type") == "watch_pattern" for e in remaining), \
        "a non-delegation event was consumed instead of left for its real owner"
    assert not any(e.get("type") == "async_delegation" for e in remaining), \
        "the delegation event was never actually processed"


def test_watcher_starts_and_stops_cleanly():
    assert delegation_watcher.is_running() is False
    delegation_watcher.start_background_delegation_watcher(interval=0.05)
    assert delegation_watcher.is_running() is True
    delegation_watcher.stop_background_delegation_watcher()
    delegation_watcher._thread.join(timeout=2)
    assert delegation_watcher.is_running() is False


def test_starting_twice_does_not_spawn_a_second_thread():
    delegation_watcher.start_background_delegation_watcher(interval=0.05)
    first = delegation_watcher._thread
    delegation_watcher.start_background_delegation_watcher(interval=0.05)
    assert delegation_watcher._thread is first
