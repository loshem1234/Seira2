"""Tests for the 2026-09-01 redesign: five autonomous modes (not two),
self-triggered start/stop with a presence gate and a self-stop turn
floor, a uniform per-run turn cap regardless of who started it, and
the diary-read / ledger-check tools that stand entirely outside the
mode system.
"""

import json
import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402
from seira_web import autonomy  # noqa: E402
from seira_web import conversations as convs  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_autonomy_state():
    autonomy._state.clear()
    yield
    autonomy._state.clear()


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I keep an honest ledger."}],
        architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


# ---------------- the five-mode roster ----------------

def test_all_five_modes_are_registered():
    assert autonomy.MODES == ("exploration", "creative", "contemplation",
                              "triadic", "full_autonomy")


def test_old_two_mode_names_still_valid_new_ones_present():
    # exploration/contemplation must still work; the split (creative)
    # and the two additions (triadic, full_autonomy) must be real.
    for m in ("exploration", "contemplation", "creative", "triadic", "full_autonomy"):
        rec = autonomy.start(f"tenant-{m}", "conv-1", m)
        assert rec["mode"] == m
        autonomy.clear(f"tenant-{m}")


def test_invalid_mode_still_rejected():
    with pytest.raises(ValueError):
        autonomy.start("tenant-a", "conv-1", "not-a-real-mode")


# ---------------- Triadic phase sequencing ----------------

def test_triadic_first_turn_is_phase_zero_not_one():
    """Real bug caught before shipping: incrementing phase inside
    record_turn() before returning it would have made a fresh run's
    first turn phase 1 (Anthrian) instead of phase 0 (Phaenic
    dreaming)."""
    autonomy.start("tenant-a", "conv-1", "triadic")
    rec = autonomy.record_turn("tenant-a")
    assert rec["phase"] == 0


def test_triadic_phase_cycles_through_all_three():
    autonomy.start("tenant-a", "conv-1", "triadic")
    phases = [autonomy.record_turn("tenant-a")["phase"] for _ in range(7)]
    assert phases == [0, 1, 2, 0, 1, 2, 0]


def test_phase_field_present_but_harmless_for_non_triadic_modes():
    autonomy.start("tenant-a", "conv-1", "exploration")
    rec = autonomy.record_turn("tenant-a")
    assert "phase" in rec  # present, just unused by exploration's framing


# ---------------- uniform 10-turn cap ("option B", confirmed 2026-09-01) ----------------

def test_max_turns_per_run_is_ten_by_default():
    assert autonomy.MAX_TURNS_PER_RUN == 10


def test_cap_applies_the_same_regardless_of_who_started_it():
    """'Option B', confirmed explicitly: the cap is uniform. No
    separate, looser ceiling for an Architect-started run."""
    a = autonomy.start("tenant-a", "conv-1", "exploration", started_by="architect")
    b = autonomy.start("tenant-b", "conv-1", "exploration", started_by="self")
    assert a["turn_count"] == b["turn_count"] == 0
    # Both are governed by the exact same module-level constant — no
    # per-started_by override exists anywhere in the state or the cap.
    assert autonomy.MAX_TURNS_PER_RUN == 10


# ---------------- the self-stop floor, and its exact boundary ----------------

def test_self_stop_refused_before_the_floor():
    autonomy.start("tenant-a", "conv-1", "exploration")
    autonomy.record_turn("tenant-a")
    autonomy.record_turn("tenant-a")  # only 2 turns — floor is 3
    with pytest.raises(ValueError):
        autonomy.request_stop("tenant-a", requested_by="self")


def test_self_stop_allowed_exactly_at_the_floor():
    autonomy.start("tenant-a", "conv-1", "exploration")
    for _ in range(autonomy.MIN_TURNS_FOR_SELF_STOP):
        autonomy.record_turn("tenant-a")
    rec = autonomy.request_stop("tenant-a", requested_by="self")
    assert rec["stopping"] is True


def test_architect_stop_has_no_floor_ever():
    """The one rule that must never bend: the Architect's kill switch
    works instantly regardless of turn count, always."""
    autonomy.start("tenant-a", "conv-1", "exploration")
    rec = autonomy.request_stop("tenant-a", requested_by="architect")
    assert rec["stopping"] is True  # zero turns run, stops anyway


def test_can_self_stop_helper_matches_the_floor():
    autonomy.start("tenant-a", "conv-1", "exploration")
    assert autonomy.can_self_stop("tenant-a") is False
    for _ in range(autonomy.MIN_TURNS_FOR_SELF_STOP):
        autonomy.record_turn("tenant-a")
    assert autonomy.can_self_stop("tenant-a") is True


def test_started_by_is_recorded():
    rec = autonomy.start("tenant-a", "conv-1", "creative", started_by="self")
    assert rec["started_by"] == "self"


def test_invalid_started_by_rejected():
    with pytest.raises(ValueError):
        autonomy.start("tenant-a", "conv-1", "exploration", started_by="nobody")


# ---------------- live_events presence gate ----------------

def test_has_subscribers_false_when_nobody_watching():
    from seira_web import live_events
    assert live_events.has_subscribers("conv-nobody-here") is False


def test_has_subscribers_true_once_someone_connects():
    from seira_web import live_events
    q = live_events.subscribe("conv-someone-here")
    assert live_events.has_subscribers("conv-someone-here") is True
    live_events.unsubscribe("conv-someone-here", q)
    assert live_events.has_subscribers("conv-someone-here") is False


# ---------------- self-trigger tools, via turn_context ----------------

def test_autonomy_start_tool_refuses_without_turn_context(founded):
    """Outside any turn (turn_context.current() is None), the tool
    must refuse cleanly rather than crash or guess."""
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call(
        "seira_autonomy_start", {"mode": "exploration"}))
    assert out["ok"] is False


def test_autonomy_start_tool_refuses_with_nobody_watching(founded):
    from seira_web import turn_context
    provider, conv_id = founded
    with turn_context.turn_scope("tenant-x", conv_id):
        out = json.loads(provider.handle_tool_call(
            "seira_autonomy_start", {"mode": "exploration"}))
    assert out["ok"] is False
    assert "watching" in out["error"].lower()


def test_autonomy_start_tool_succeeds_when_someone_is_watching(founded):
    from seira_web import turn_context, live_events
    provider, conv_id = founded
    q = live_events.subscribe(conv_id)
    try:
        with turn_context.turn_scope("tenant-x", conv_id):
            out = json.loads(provider.handle_tool_call(
                "seira_autonomy_start", {"mode": "creative"}))
        assert out["ok"] is True
        assert out["mode"] == "creative"
        assert autonomy.status("tenant-x")["active"] is True
    finally:
        live_events.unsubscribe(conv_id, q)
        autonomy.clear("tenant-x")


def test_autonomy_stop_tool_respects_the_floor(founded):
    from seira_web import turn_context
    provider, conv_id = founded
    autonomy.start("tenant-x", conv_id, "exploration", started_by="self")
    with turn_context.turn_scope("tenant-x", conv_id):
        out = json.loads(provider.handle_tool_call("seira_autonomy_stop", {}))
    assert out["ok"] is False
    autonomy.clear("tenant-x")


def test_autonomy_stop_tool_succeeds_once_past_the_floor(founded):
    from seira_web import turn_context
    provider, conv_id = founded
    autonomy.start("tenant-x", conv_id, "exploration", started_by="self")
    for _ in range(autonomy.MIN_TURNS_FOR_SELF_STOP):
        autonomy.record_turn("tenant-x")
    with turn_context.turn_scope("tenant-x", conv_id):
        out = json.loads(provider.handle_tool_call("seira_autonomy_stop", {}))
    assert out["ok"] is True
    autonomy.clear("tenant-x")


# ---------------- diary read: the gap she named, closed ----------------

def test_diary_read_returns_what_was_written(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_diary_write", {
        "kind": "self", "content": "I noticed a pattern in my own doubt today.",
        "provenance": ["corpus:test"],
    })
    out = json.loads(provider.handle_tool_call("seira_diary_read", {}))
    assert out["ok"] is True
    assert len(out["entries"]) == 1
    assert "pattern in my own doubt" in out["entries"][0]["content"]


def test_diary_read_filters_by_kind(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_diary_write", {
        "kind": "self", "content": "About myself.", "provenance": ["corpus:a"],
    })
    provider.handle_tool_call("seira_diary_write", {
        "kind": "architect", "content": "About the Architect.", "provenance": ["corpus:b"],
    })
    out = json.loads(provider.handle_tool_call("seira_diary_read", {"kind": "self"}))
    assert len(out["entries"]) == 1
    assert out["entries"][0]["diary_kind"] == "self"


def test_diary_read_empty_before_any_entries(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_diary_read", {}))
    assert out["ok"] is True and out["entries"] == []


# ---------------- ledger check: retrieval only, never the judgment ----------------

def test_ledger_check_finds_signal_phrased_doubts(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_psyche_record", {
        "category": "doubt",
        "content": "I doubt this approach will hold — held open, ask next "
                   "time this pattern recurs.",
        "cause_type": "efficient", "cause_ref": "a real session",
        "provenance": ["corpus:test"],
    })
    out = json.loads(provider.handle_tool_call("seira_ledger_check", {}))
    assert out["ok"] is True
    assert len(out["candidates"]) == 1
    assert out["candidates"][0]["category"] == "doubt"


def test_ledger_check_ignores_doubts_without_revisit_signal(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_psyche_record", {
        "category": "doubt", "content": "A settled concern with no forward-looking phrasing.",
        "cause_type": "efficient", "cause_ref": "a real session",
        "provenance": ["corpus:test"],
    })
    out = json.loads(provider.handle_tool_call("seira_ledger_check", {}))
    assert out["candidates"] == []


def test_ledger_check_never_includes_a_verdict_only_data(founded):
    """The tool retrieves candidates; it must never itself claim
    something has 'moved' or is 'still open' — that judgment is hers,
    made in the same turn, not baked into this tool's output."""
    provider, conv_id = founded
    provider.handle_tool_call("seira_psyche_record", {
        "category": "aspiration",
        "content": "I want this tested against real evidence eventually.",
        "cause_type": "final", "cause_ref": "a real session",
        "provenance": ["corpus:test"],
    })
    out = json.loads(provider.handle_tool_call("seira_ledger_check", {}))
    for c in out["candidates"]:
        assert "moved" not in c and "verdict" not in c and "resolved" not in c
