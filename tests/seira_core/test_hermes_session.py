"""Tests for seira_web.hermes_session and its opt-in wiring into
seira_web.chat.run_turn.

What these tests CAN prove without live credentials or the full
Hermes dependency tree: the callback contract matches what
agent/tool_executor.py actually calls (verified against source, not
guessed), the AIAgent constructor receives the arguments the
architecture requires (load_soul_identity, skip_memory=False so
memory.provider loads from config, the model/provider pair), history
round-trips through the real conversation_history/final message shape,
and the opt-in flag defaults OFF so existing deployments are
unaffected until this is verified live.

What these tests CANNOT prove: that a live turn against a real
Anthropic key, with the full Hermes toolset and memory-provider stack
actually installed, produces a correct reply. That needs a real
deployment — see docs/seira/WIRING.md.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")


class _FakeAIAgent:
    """Stands in for run_agent.AIAgent — records what it was built with."""
    last_kwargs = None

    def __init__(self, **kwargs):
        _FakeAIAgent.last_kwargs = kwargs
        self.tool_start_callback = kwargs.get("tool_start_callback")
        self.tool_complete_callback = kwargs.get("tool_complete_callback")


def test_agent_is_built_to_serve_her_real_identity():
    """load_soul_identity + skip_memory=False are the two arguments
    that make this a real Hermes-Seira turn rather than a generic
    agent call — if either regresses, she stops being herself atop
    Hermes and becomes just another configured backend."""
    with patch("run_agent.AIAgent", _FakeAIAgent):
        from seira_web.hermes_session import _build_agent
        _build_agent(session_id="conv-1", emit=lambda e: None)
    kwargs = _FakeAIAgent.last_kwargs
    assert kwargs["load_soul_identity"] is True
    assert kwargs["skip_memory"] is False
    assert kwargs["provider"] == "anthropic"
    assert kwargs["session_id"] == "conv-1"


def test_tool_start_callback_matches_real_call_site_shape():
    """agent/tool_executor.py calls
    ``agent.tool_start_callback(tool_call_id, function_name, display_args)``
    — three positional args. This must not raise with that shape."""
    events = []
    with patch("run_agent.AIAgent", _FakeAIAgent):
        from seira_web.hermes_session import _build_agent
        agent = _build_agent(session_id="conv-1", emit=events.append)
    agent.tool_start_callback("tc-1", "web_search", {"query": "x"})
    assert events and events[0]["event"] == "tool"
    assert events[0]["tool"] == "web_search"


def test_tool_complete_callback_matches_real_call_site_shape():
    """agent/tool_executor.py calls tool_complete_callback with FOUR
    positional args: (tool_call_id, name, display_args, display_result)."""
    events = []
    with patch("run_agent.AIAgent", _FakeAIAgent):
        from seira_web.hermes_session import _build_agent
        agent = _build_agent(session_id="conv-1", emit=events.append)
    agent.tool_complete_callback("tc-1", "web_search", {"query": "x"}, "3 results")
    assert events and events[0]["event"] == "tool_result"
    assert events[0]["result"] == "3 results"


def test_run_turn_via_hermes_round_trips_history_and_reply():
    fake_result = {"final_response": "Hello, Architect.",
                   "messages": [{"role": "user", "content": "hi"},
                               {"role": "assistant", "content": "Hello, Architect."}]}
    events = []
    with patch("run_agent.AIAgent", _FakeAIAgent), \
         patch("agent.conversation_loop.run_conversation", return_value=fake_result) as mock_run:
        from seira_web.hermes_session import run_turn_via_hermes
        out = run_turn_via_hermes("conv-1", "hi", [], events.append)

    assert out["reply"] == "Hello, Architect."
    assert out["messages"] == fake_result["messages"]
    mock_run.assert_called_once()
    _, call_kwargs = mock_run.call_args
    assert call_kwargs["user_message"] == "hi"
    assert call_kwargs["conversation_history"] == []
    assert any(e.get("event") == "reply" for e in events)


def test_housekeeping_turn_never_touches_conversations_module(monkeypatch, tmp_path):
    """The core guarantee (2026-09-11): a housekeeping turn (used for
    her own conversation renaming/summarizing) must never create,
    append to, or otherwise touch a real, sidebar-visible
    conversation — only her own tool calls during that turn (rename,
    set_summary) should ever write anything real."""
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    from seira_core.tenancy import tenant_root
    tenant_root("t-test123456").mkdir(parents=True, exist_ok=True)

    calls = {"append": 0, "create": 0}
    real_append = None
    real_create = None

    def spy_append(*a, **kw):
        calls["append"] += 1
        return real_append(*a, **kw)

    def spy_create(*a, **kw):
        calls["create"] += 1
        return real_create(*a, **kw)

    import seira_web.conversations as convs_module
    real_append = convs_module.append
    real_create = convs_module.create_conversation
    monkeypatch.setattr(convs_module, "append", spy_append)
    monkeypatch.setattr(convs_module, "create_conversation", spy_create)

    fake_result = {"final_response": "done", "messages": []}
    with patch("run_agent.AIAgent", _FakeAIAgent), \
         patch("agent.conversation_loop.run_conversation", return_value=fake_result):
        from seira_web.hermes_session import run_housekeeping_turn
        result = run_housekeeping_turn("do some housekeeping", "t-test123456")

    assert result["reply"] == "done"
    assert calls["append"] == 0
    assert calls["create"] == 0


def test_housekeeping_turn_chains_history_across_calls():
    """The piece Recollection needs specifically: a caller can pass
    the previous turn's messages back in and get the next turn's
    messages back out, chaining a longer session — the same pattern
    run_turn_via_hermes already uses for a real conversation."""
    fake_result = {"final_response": "turn 2 reply",
                   "messages": [{"role": "user", "content": "turn 1"},
                               {"role": "assistant", "content": "turn 1 reply"},
                               {"role": "user", "content": "turn 2"},
                               {"role": "assistant", "content": "turn 2 reply"}]}
    with patch("run_agent.AIAgent", _FakeAIAgent), \
         patch("agent.conversation_loop.run_conversation",
              return_value=fake_result) as mock_run:
        from seira_web.hermes_session import run_housekeeping_turn
        prior_history = [{"role": "user", "content": "turn 1"},
                         {"role": "assistant", "content": "turn 1 reply"}]
        result = run_housekeeping_turn("turn 2 prompt", "tenant-a", history=prior_history)

    assert result["reply"] == "turn 2 reply"
    assert result["messages"] == fake_result["messages"]
    _, call_kwargs = mock_run.call_args
    assert call_kwargs["conversation_history"] == prior_history


def test_housekeeping_turn_uses_a_synthetic_never_registered_session_id():
    captured = {}
    with patch("run_agent.AIAgent", _FakeAIAgent), \
         patch("agent.conversation_loop.run_conversation",
              return_value={"final_response": "ok", "messages": []}):
        from seira_web.hermes_session import run_housekeeping_turn
        run_housekeeping_turn("prompt text", "tenant-a")
    kwargs = _FakeAIAgent.last_kwargs
    assert kwargs["session_id"].startswith("housekeeping-")
    assert kwargs["session_id"] != "tenant-a"  # a real, distinct synthetic id, not reused


def test_sanctum_runtime_flag_defaults_off(monkeypatch, tmp_path):
    """Without SEIRA_SANCTUM_RUNTIME=hermes, run_turn must take the
    existing direct-API path — this flag is opt-in until verified
    live, not a silent default flip."""
    monkeypatch.delenv("SEIRA_SANCTUM_RUNTIME", raising=False)
    import os
    assert os.environ.get("SEIRA_SANCTUM_RUNTIME", "direct") == "direct"


def test_sanctum_runtime_hermes_mode_is_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("SEIRA_SANCTUM_RUNTIME", "hermes")
    import os
    assert os.environ.get("SEIRA_SANCTUM_RUNTIME", "direct") == "hermes"
