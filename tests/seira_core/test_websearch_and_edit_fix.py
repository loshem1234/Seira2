"""Tests for: web_search tool inclusion (server-executed, never
dispatched locally), and the fix for the inactive-edit-icon bug (the
user message's real id must reach the client before edit is usable)."""

import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402
from seira_web import conversations as convs  # noqa: E402
from seira_web.chat import _anthropic_tools, run_turn  # noqa: E402


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am careful."}], architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


def test_web_search_tool_only_added_when_enabled(founded):
    provider, _ = founded
    without = _anthropic_tools(provider, web_search=False)
    with_search = _anthropic_tools(provider, web_search=True)
    assert not any(t.get("name") == "web_search" for t in without)
    assert any(t.get("name") == "web_search" and "type" in t for t in with_search)


class WebSearchLLM:
    """Simulates Anthropic's actual shape for a server-executed tool: the
    search + its result + final text all arrive in ONE response, no
    tool_result round-trip required from us."""

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, tools):
        self.calls += 1
        assert any(t.get("name") == "web_search" for t in tools)
        return {
            "content": [
                {"type": "server_tool_use", "id": "srv1", "name": "web_search",
                 "input": {"query": "current weather Dayton Ohio"}},
                {"type": "web_search_tool_result", "tool_use_id": "srv1",
                 "content": [{"type": "web_search_result", "title": "...", "url": "..."}]},
                {"type": "text", "text": "It's mild in Dayton today."},
            ],
            "stop_reason": "end_turn",
        }


def test_web_search_resolves_in_one_round_no_local_dispatch(founded):
    provider, conv_id = founded
    events = []
    llm = WebSearchLLM()
    result = run_turn(provider, llm, conv_id, "what's the weather?",
                      emit=events.append, web_search=True)
    assert result["reply"] == "It's mild in Dayton today."
    assert llm.calls == 1  # resolved in one round, no fabricated tool_result loop
    assert any(e["event"] == "tool" and e["label"] == "Searching the web" for e in events)


def test_user_message_id_is_emitted_immediately(founded):
    """The bug: the DOM had no id for a just-sent message until reload,
    so 'edit' silently did nothing. Fixed by emitting the real id as soon
    as it's recorded, before the model is even called."""
    provider, conv_id = founded

    class SlowLLM:
        def complete(self, system, messages, tools):
            return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}

    events = []
    run_turn(provider, SlowLLM(), conv_id, "hello", emit=events.append)
    user_events = [e for e in events if e["event"] == "user_recorded"]
    assert len(user_events) == 1
    real_id = user_events[0]["id"]
    # And it matches the actual stored record — not a placeholder:
    stored = convs.last_live_user(conv_id)
    assert stored["id"] == real_id
    # Crucially: it arrives BEFORE the reply, so the UI can attach it
    # to the message bubble before the user could plausibly click edit.
    reply_index = next(i for i, e in enumerate(events) if e["event"] == "reply")
    user_index = next(i for i, e in enumerate(events) if e["event"] == "user_recorded")
    assert user_index < reply_index
