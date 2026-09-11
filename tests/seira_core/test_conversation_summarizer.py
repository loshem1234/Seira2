"""Tests for seira_web.conversation_summarizer — auto-titling and
bullet-point summaries for the sidebar, per Loshem's direction
(2026-09-07, refined 2026-09-11): "so I can always know what and
where the chats are" — and she should be the one doing the renaming
and summarizing herself, not a silent system completion.
"""

import sys
import time
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_web import conversation_summarizer as summarizer  # noqa: E402
from seira_web import conversations as convs  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


@pytest.fixture(autouse=True)
def _reset_summarizer_state():
    summarizer.stop_background_summarizer()
    if summarizer._thread is not None:
        summarizer._thread.join(timeout=2)
    summarizer._thread = None
    summarizer._stop_event = None
    yield
    summarizer.stop_background_summarizer()
    if summarizer._thread is not None:
        summarizer._thread.join(timeout=2)
    summarizer._thread = None
    summarizer._stop_event = None


# ---------------- cadence: weekly, per explicit direction (2026-09-11) ----------------

def test_default_interval_is_weekly_not_daily():
    import inspect
    default = inspect.signature(summarizer.start_background_summarizer).parameters["interval"].default
    assert default == 604_800  # 7 days, not the original 86_400 (1 day)


# ---------------- transcript building ----------------

def test_transcript_bounded_to_most_recent_content():
    text = summarizer._build_transcript_text("x" * 20_000, max_chars=100)
    assert len(text) < 200  # bounded, not the full 20,000 chars


def test_transcript_under_the_bound_is_unchanged():
    text = summarizer._build_transcript_text("short text", max_chars=100)
    assert text == "short text"


# ---------------- summarize_one: real behavior, real tool-driven turn ----------------

def test_summarize_one_skips_a_conversation_with_too_few_turns(home, monkeypatch):
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="just one message")

    called = {"n": 0}
    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1))
    result = summarizer.summarize_one(conv["conv_id"], "tenant-a")
    assert result is False
    assert called["n"] == 0  # never even attempted a turn


def test_summarize_one_gives_her_a_real_housekeeping_turn(home, monkeypatch):
    """The core of the redesign: this is HER doing the work, through a
    real turn, not a raw system completion — verified by confirming
    run_housekeeping_turn is actually called, with the real conv_id
    and transcript content reaching the prompt."""
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="let's plan the Q3 launch")
    convs.append(conv["conv_id"], "assistant", text="sure, what's the budget?")
    convs.append(conv["conv_id"], "user", text="fifty thousand, launching in July")

    captured = {}

    def fake_housekeeping(prompt, tenant_id, emit=None):
        captured["prompt"] = prompt
        captured["tenant_id"] = tenant_id
        return "done"

    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn", fake_housekeeping)
    result = summarizer.summarize_one(conv["conv_id"], "tenant-a")
    assert result is True
    assert conv["conv_id"] in captured["prompt"]
    assert "Q3 launch" in captured["prompt"]
    assert "fifty thousand" in captured["prompt"]
    assert captured["tenant_id"] == "tenant-a"
    assert "seira_conversation_rename" in captured["prompt"]
    assert "seira_conversation_set_summary" in captured["prompt"]


def test_summarize_one_prompt_demands_specificity_not_genericness(home, monkeypatch):
    """Real, explicit ask (2026-09-11): summaries must be specific
    enough to recall where/what a chat was, not a vague gist."""
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="message one")
    convs.append(conv["conv_id"], "assistant", text="reply one")
    convs.append(conv["conv_id"], "user", text="message two")

    captured = {}
    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn",
                        lambda prompt, tenant_id, emit=None: captured.setdefault("prompt", prompt))
    summarizer.summarize_one(conv["conv_id"], "tenant-a")
    assert "SPECIFIC" in captured["prompt"] or "specific" in captured["prompt"]
    assert "General Chat" in captured["prompt"]  # named as an example of what NOT to do


def test_summarize_one_handles_a_failed_turn_gracefully(home, monkeypatch):
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="message one")
    convs.append(conv["conv_id"], "assistant", text="reply one")

    def failing(*a, **kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn", failing)
    result = summarizer.summarize_one(conv["conv_id"], "tenant-a")  # must not raise
    assert result is False


# ---------------- her new tools work end to end (via seira_bridge) ----------------

def test_she_can_rename_and_summarize_through_her_own_tools(home):
    """Not mocked — the actual tools she'd call during a real
    housekeeping turn, exercised directly."""
    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis([{"category": "self_model", "content": "I keep my own record."}],
                          architect="L")
    from seira_bridge import SeiraPsycheProvider
    import json

    provider = SeiraPsycheProvider()
    conv = convs.create_conversation()

    out = json.loads(provider.handle_tool_call("seira_conversation_rename",
                                                {"conv_id": conv["conv_id"],
                                                 "title": "Q3 Launch Planning"}))
    assert out["ok"] is True and out["title"] == "Q3 Launch Planning"

    out = json.loads(provider.handle_tool_call("seira_conversation_set_summary",
                                                {"conv_id": conv["conv_id"],
                                                 "bullets": ["budget: $50k", "launch: July"]}))
    assert out["ok"] is True
    assert out["summary_bullets"] == ["budget: $50k", "launch: July"]


def test_she_can_recall_a_past_conversation_in_full(home):
    from seira_bridge import SeiraPsycheProvider
    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis([{"category": "self_model", "content": "test"}], architect="L")
    import json

    provider = SeiraPsycheProvider()
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="what happened with the kitchen renovation")
    convs.append(conv["conv_id"], "assistant", text="we settled on the oak cabinets")

    out = json.loads(provider.handle_tool_call("seira_conversation_recall",
                                                {"conv_id": conv["conv_id"]}))
    assert out["ok"] is True
    assert "kitchen renovation" in out["text"]
    assert "oak cabinets" in out["text"]


def test_she_can_list_conversations_to_find_one_to_recall(home):
    from seira_bridge import SeiraPsycheProvider
    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis([{"category": "self_model", "content": "test"}], architect="L")
    import json

    provider = SeiraPsycheProvider()
    convs.create_conversation("First Conversation")
    convs.create_conversation("Second Conversation")

    out = json.loads(provider.handle_tool_call("seira_conversation_list", {}))
    assert out["ok"] is True
    titles = {c["title"] for c in out["conversations"]}
    assert "First Conversation" in titles and "Second Conversation" in titles


def test_conversation_recall_of_unknown_conv_id_is_honest(home):
    from seira_bridge import SeiraPsycheProvider
    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis([{"category": "self_model", "content": "test"}], architect="L")
    import json

    provider = SeiraPsycheProvider()
    out = json.loads(provider.handle_tool_call("seira_conversation_recall",
                                                {"conv_id": "conv-does-not-exist"}))
    assert out["ok"] is False


# ---------------- respecting a user-chosen title (unchanged behavior) ----------------

def test_auto_update_respects_a_user_renamed_title(home):
    conv = convs.create_conversation()
    convs.rename_conversation(conv["conv_id"], "My Own Name For This")
    convs.auto_update_title_and_summary(conv["conv_id"], "Auto Generated Title",
                                        ["a bullet"])
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert rec["title"] == "My Own Name For This"  # never overwritten
    assert rec["summary_bullets"] == ["a bullet"]  # bullets still refresh regardless


def test_auto_update_does_not_bump_the_updated_timestamp(home):
    """A background summary refresh must never reorder the sidebar by
    itself — only real activity should move a conversation to the
    top."""
    conv = convs.create_conversation()
    original_updated = conv["updated"]
    time.sleep(0.01)
    convs.auto_update_title_and_summary(conv["conv_id"], "New Title", ["a point"])
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert rec["updated"] == original_updated


def test_auto_update_returns_none_for_a_deleted_conversation(home):
    assert convs.auto_update_title_and_summary("conv-does-not-exist", "t", []) is None


# ---------------- refresh-needed logic (unchanged behavior) ----------------

def test_needs_refresh_true_when_never_summarized():
    assert summarizer._needs_refresh({"updated": "2026-01-01T00:00:00"}) is True


def test_needs_refresh_true_when_updated_after_last_summary():
    rec = {"updated": "2026-01-02T00:00:00", "summary_updated_at": "2026-01-01T00:00:00"}
    assert summarizer._needs_refresh(rec) is True


def test_needs_refresh_false_when_summary_is_current():
    rec = {"updated": "2026-01-01T00:00:00", "summary_updated_at": "2026-01-02T00:00:00"}
    assert summarizer._needs_refresh(rec) is False


# ---------------- the background loop itself ----------------

def test_summarizer_starts_and_stops_cleanly():
    assert summarizer.is_running() is False
    summarizer.start_background_summarizer(interval=0.1)
    assert summarizer.is_running() is True
    summarizer.stop_background_summarizer()
    summarizer._thread.join(timeout=2)
    assert summarizer.is_running() is False


def test_starting_twice_does_not_spawn_a_second_thread():
    summarizer.start_background_summarizer(interval=0.1)
    first = summarizer._thread
    summarizer.start_background_summarizer(interval=0.1)
    assert summarizer._thread is first
