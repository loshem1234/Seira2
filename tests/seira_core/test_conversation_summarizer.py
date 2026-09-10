"""Tests for seira_web.conversation_summarizer — auto-titling and
bullet-point summaries for the sidebar, per Loshem's direction
(2026-09-07): "so I can always know what and where the chats are."
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


# ---------------- response parsing ----------------

def test_parse_valid_json_response():
    raw = '{"title": "Planning the Q3 launch", "bullets": ["budget set", "date confirmed"]}'
    result = summarizer._parse_summary_response(raw)
    assert result == ("Planning the Q3 launch", ["budget set", "date confirmed"])


def test_parse_response_wrapped_in_markdown_fences():
    raw = '```json\n{"title": "A title", "bullets": ["one"]}\n```'
    result = summarizer._parse_summary_response(raw)
    assert result == ("A title", ["one"])


def test_parse_invalid_json_returns_none():
    assert summarizer._parse_summary_response("not json at all") is None


def test_parse_missing_fields_returns_none():
    assert summarizer._parse_summary_response('{"title": "only a title"}') is None


def test_parse_caps_bullets_at_six():
    bullets = [f"point {i}" for i in range(10)]
    import json
    raw = json.dumps({"title": "t", "bullets": bullets})
    _, parsed_bullets = summarizer._parse_summary_response(raw)
    assert len(parsed_bullets) == 6


def test_parse_filters_non_string_bullets():
    raw = '{"title": "t", "bullets": ["real one", 42, null, "another real one"]}'
    _, bullets = summarizer._parse_summary_response(raw)
    assert bullets == ["real one", "another real one"]


# ---------------- transcript building ----------------

def test_transcript_labels_roles():
    history = [{"role": "user", "content": "hello"},
              {"role": "assistant", "content": "hi there"}]
    text = summarizer._build_transcript_text(history)
    assert "Architect: hello" in text
    assert "Seira: hi there" in text


def test_transcript_bounded_to_most_recent_content():
    history = [{"role": "user", "content": "x" * 20_000}]
    text = summarizer._build_transcript_text(history, max_chars=100)
    assert len(text) < 200  # bounded, not the full 20,000 chars


# ---------------- summarize_one: the real, testable behavior ----------------

def test_summarize_one_skips_a_conversation_with_too_few_turns(home, monkeypatch):
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="just one message")

    called = {"n": 0}
    monkeypatch.setattr("seira_web.chat.AnthropicClient",
                        lambda **kw: called.__setitem__("n", called["n"] + 1))
    result = summarizer.summarize_one(conv["conv_id"])
    assert result is False
    assert called["n"] == 0  # never even attempted an API call


def test_summarize_one_stores_title_and_bullets_on_success(home, monkeypatch):
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="let's plan the launch")
    convs.append(conv["conv_id"], "assistant", text="sure, what's the date?")
    convs.append(conv["conv_id"], "user", text="Q3, budget is set")

    class FakeClient:
        def __init__(self, **kw):
            pass

        def complete(self, system, messages, tools):
            return {"content": [{"type": "text", "text":
                    '{"title": "Q3 Launch Planning", "bullets": ["budget set", "Q3 target"]}'}]}

    monkeypatch.setattr("seira_web.chat.AnthropicClient", FakeClient)
    result = summarizer.summarize_one(conv["conv_id"])
    assert result is True

    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert rec["title"] == "Q3 Launch Planning"
    assert rec["summary_bullets"] == ["budget set", "Q3 target"]
    assert rec["summary_updated_at"]


def test_summarize_one_handles_api_failure_gracefully(home, monkeypatch):
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="message one")
    convs.append(conv["conv_id"], "assistant", text="reply one")

    class FailingClient:
        def __init__(self, **kw):
            pass

        def complete(self, *a, **kw):
            raise RuntimeError("simulated API failure")

    monkeypatch.setattr("seira_web.chat.AnthropicClient", FailingClient)
    result = summarizer.summarize_one(conv["conv_id"])  # must not raise
    assert result is False


def test_summarize_one_handles_unparseable_response_gracefully(home, monkeypatch):
    conv = convs.create_conversation()
    convs.append(conv["conv_id"], "user", text="message one")
    convs.append(conv["conv_id"], "assistant", text="reply one")

    class GarbageClient:
        def __init__(self, **kw):
            pass

        def complete(self, *a, **kw):
            return {"content": [{"type": "text", "text": "not valid json"}]}

    monkeypatch.setattr("seira_web.chat.AnthropicClient", GarbageClient)
    result = summarizer.summarize_one(conv["conv_id"])
    assert result is False


# ---------------- respecting a user-chosen title ----------------

def test_auto_update_respects_a_user_renamed_title(home):
    conv = convs.create_conversation()
    convs.rename_conversation(conv["conv_id"], "My Own Name For This")
    convs.auto_update_title_and_summary(conv["conv_id"], "Auto Generated Title",
                                        ["a bullet"])
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert rec["title"] == "My Own Name For This"  # never overwritten
    assert rec["summary_bullets"] == ["a bullet"]  # bullets still refresh regardless


def test_auto_update_sets_title_when_never_manually_renamed(home):
    conv = convs.create_conversation("New conversation")
    convs.auto_update_title_and_summary(conv["conv_id"], "A Real Descriptive Title",
                                        ["point one"])
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert rec["title"] == "A Real Descriptive Title"


def test_rename_marks_title_as_user_set(home):
    conv = convs.create_conversation()
    convs.rename_conversation(conv["conv_id"], "Chosen By Me")
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert rec["title_user_set"] is True


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


# ---------------- refresh-needed logic ----------------

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
