"""Tests for seira_web.recollection — her weekly Recollection session.
Per Loshem's direction (2026-09-11): a 5-turn floor before she can
conclude, a 20-turn hard ceiling, per-conversation (not per-session)
coverage tracking so nothing is missed if a session runs out of
budget, and a first-run-takes-everything / subsequent-runs-scoped-to-
whats-unprocessed cadence.
"""

import sys
import threading
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_web import conversations as convs  # noqa: E402
from seira_web import recollection  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


@pytest.fixture(autouse=True)
def _clean_session_state():
    with recollection._session_lock:
        recollection._session_state.clear()
    yield
    with recollection._session_lock:
        recollection._session_state.clear()


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ---------------- the floor and ceiling, directly ----------------

def test_conclude_refused_before_the_floor():
    recollection._start_session("tenant-a")
    for _ in range(recollection.MIN_TURNS_FOR_RECOLLECTION - 1):
        recollection._record_turn("tenant-a")
    with pytest.raises(ValueError):
        recollection.request_conclude("tenant-a")


def test_conclude_allowed_exactly_at_the_floor():
    recollection._start_session("tenant-a")
    for _ in range(recollection.MIN_TURNS_FOR_RECOLLECTION):
        recollection._record_turn("tenant-a")
    recollection.request_conclude("tenant-a")  # must not raise
    assert recollection._is_concluded("tenant-a") is True


def test_conclude_with_no_active_session_raises():
    with pytest.raises(ValueError):
        recollection.request_conclude("tenant-with-no-session")


def test_floor_and_ceiling_are_distinct_from_autonomy_modes():
    """Real, deliberate numbers of their own — not reused from the
    five autonomous modes' 3-turn floor / 10-turn cap."""
    from seira_web import autonomy
    assert recollection.MIN_TURNS_FOR_RECOLLECTION == 5
    assert recollection.MAX_TURNS_FOR_RECOLLECTION == 20
    assert recollection.MIN_TURNS_FOR_RECOLLECTION != autonomy.MIN_TURNS_FOR_SELF_STOP
    assert recollection.MAX_TURNS_FOR_RECOLLECTION != autonomy.MAX_TURNS_PER_RUN


# ---------------- needs-recollection / first-run-takes-everything ----------------

def test_needs_recollection_true_for_a_never_reviewed_conversation():
    assert recollection._needs_recollection({"updated": "2026-01-01T00:00:00"}) is True


def test_needs_recollection_true_when_updated_after_last_review():
    rec = {"updated": "2026-01-02T00:00:00",
          "recollection_processed_at": "2026-01-01T00:00:00"}
    assert recollection._needs_recollection(rec) is True


def test_needs_recollection_false_when_review_is_current():
    rec = {"updated": "2026-01-01T00:00:00",
          "recollection_processed_at": "2026-01-02T00:00:00"}
    assert recollection._needs_recollection(rec) is False


# ---------------- the real session loop ----------------

def test_session_stops_at_the_ceiling_if_never_concluded(home, monkeypatch):
    """The hard ceiling: even if she never calls conclude, the loop
    itself must stop at MAX_TURNS_FOR_RECOLLECTION."""
    conv = convs.create_conversation()
    monkeypatch.setattr(recollection, "MAX_TURNS_FOR_RECOLLECTION", 3)
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda *a, **kw: _NullContext())

    call_count = {"n": 0}

    def fake_housekeeping(prompt, tenant_id, history=None, emit=None):
        call_count["n"] += 1
        return {"reply": "reflecting", "messages": (history or []) + [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "reflecting"},
        ]}

    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn", fake_housekeeping)

    recollection._run_session_for_tenant("tenant-a")

    assert call_count["n"] == 3  # stopped at the (patched) ceiling, not fewer or more
    assert "tenant-a" not in recollection._session_state  # session cleaned up


def test_session_stops_when_she_concludes_past_the_floor(home, monkeypatch):
    conv = convs.create_conversation()
    monkeypatch.setattr(recollection, "MIN_TURNS_FOR_RECOLLECTION", 2)
    monkeypatch.setattr(recollection, "MAX_TURNS_FOR_RECOLLECTION", 100)
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda *a, **kw: _NullContext())

    call_count = {"n": 0}

    def fake_housekeeping(prompt, tenant_id, history=None, emit=None):
        call_count["n"] += 1
        if call_count["n"] == 2:
            recollection.request_conclude(tenant_id)  # she decides she's done
        return {"reply": "ok", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn", fake_housekeeping)

    recollection._run_session_for_tenant("tenant-a")

    assert call_count["n"] == 2  # stopped right after concluding, not all 100


def test_a_halted_seira_never_runs_recollection(home, monkeypatch):
    convs.create_conversation()
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: True)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda *a, **kw: _NullContext())

    called = {"n": 0}
    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1))

    recollection._run_session_for_tenant("tenant-a")
    assert called["n"] == 0  # never even attempted a turn


def test_session_with_nothing_pending_never_starts(home, monkeypatch):
    """No conversations at all — a session should never even begin,
    not run zero turns and exit."""
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda *a, **kw: _NullContext())
    called = {"n": 0}
    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1))
    recollection._run_session_for_tenant("tenant-a")
    assert called["n"] == 0
    assert "tenant-a" not in recollection._session_state


def test_already_reviewed_conversation_is_not_reprocessed(home, monkeypatch):
    """Real coverage tracking: a conversation marked reviewed and with
    no new activity since must not trigger another session."""
    conv = convs.create_conversation()
    convs.mark_recollection_reviewed(conv["conv_id"])
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda *a, **kw: _NullContext())
    called = {"n": 0}
    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1))
    recollection._run_session_for_tenant("tenant-a")
    assert called["n"] == 0


# ---------------- run_full_reprocess: forces everything, without mutating data ----------------

def test_run_full_reprocess_includes_already_reviewed_conversations(home, monkeypatch):
    conv = convs.create_conversation()
    convs.mark_recollection_reviewed(conv["conv_id"])  # already "done"

    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda *a, **kw: _NullContext())
    monkeypatch.setattr(recollection, "MIN_TURNS_FOR_RECOLLECTION", 1)

    captured = {}

    def fake_housekeeping(prompt, tenant_id, history=None, emit=None):
        captured["prompt"] = prompt
        recollection.request_conclude(tenant_id)
        return {"reply": "ok", "messages": []}

    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn", fake_housekeeping)

    recollection.run_full_reprocess("tenant-a")
    assert conv["conv_id"] in captured["prompt"]  # included despite being already reviewed


def test_run_full_reprocess_does_not_mutate_existing_review_data(home, monkeypatch):
    """The force-all behavior must not clear real
    recollection_processed_at data on other, untouched conversations —
    it only affects which conversations THIS run considers pending."""
    conv = convs.create_conversation()
    rec_before = convs.mark_recollection_reviewed(conv["conv_id"])

    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: False)
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda *a, **kw: _NullContext())
    monkeypatch.setattr(recollection, "MIN_TURNS_FOR_RECOLLECTION", 1)
    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn",
                        lambda prompt, tenant_id, history=None, emit=None:
                        {"reply": "ok", "messages": []} if
                        recollection.request_conclude(tenant_id) is None else None)

    recollection.run_full_reprocess("tenant-a")

    rec_after = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    # Not re-marked by run_full_reprocess itself — only her own
    # seira_recollection_mark_reviewed calls (not exercised by this
    # mock) would update it further.
    assert rec_after["recollection_processed_at"] == rec_before["recollection_processed_at"]


# ---------------- reviewed_this_session ----------------

def test_reviewed_this_session_tracks_conversations_marked_after_session_start(home):
    conv_a = convs.create_conversation()
    conv_b = convs.create_conversation()
    convs.mark_recollection_reviewed(conv_a["conv_id"])  # before any session

    recollection._start_session("tenant-a")
    convs.mark_recollection_reviewed(conv_b["conv_id"])  # during the session

    covered = recollection.reviewed_this_session("tenant-a")
    assert conv_b["conv_id"] in covered


def test_reviewed_this_session_empty_with_no_active_session(home):
    assert recollection.reviewed_this_session("tenant-with-no-session") == []


# ---------------- background loop lifecycle ----------------

def test_recollection_loop_starts_and_stops_cleanly():
    assert recollection.is_running() is False
    recollection.start_background_recollection(interval=0.1)
    assert recollection.is_running() is True
    recollection.stop_background_recollection()
    recollection._thread.join(timeout=2)
    assert recollection.is_running() is False


def test_starting_twice_does_not_spawn_a_second_thread():
    recollection.start_background_recollection(interval=0.1)
    first = recollection._thread
    recollection.start_background_recollection(interval=0.1)
    assert recollection._thread is first
    recollection.stop_background_recollection()
    recollection._thread.join(timeout=2)
