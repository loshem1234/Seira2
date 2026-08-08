"""Tests for the length-limit fixes: replies must never silently cut off,
and a truncated tool call (e.g. a comprehensive skill) must never crash
the turn — it must come back as an honest, recoverable error the model
can act on.
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
from seira_web import conversations as convs  # noqa: E402
from seira_web.chat import run_turn  # noqa: E402


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n",
                    architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am careful."}], architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


class TruncatedTextLLM:
    """Simulates a real long answer that gets cut mid-sentence, then
    completes cleanly on continuation — exactly the 'should never
    happen' case."""

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {"content": [{"type": "text",
                                 "text": "This is the first half of a long thought that got cu"}],
                    "stop_reason": "max_tokens"}
        return {"content": [{"type": "text", "text": "t off, and now concludes properly."}],
                "stop_reason": "end_turn"}


def test_truncated_text_is_transparently_continued(founded):
    provider, conv_id = founded
    events = []
    result = run_turn(provider, TruncatedTextLLM(), conv_id, "tell me something long",
                      emit=events.append)
    assert result["reply"] == (
        "This is the first half of a long thought that got cut off, "
        "and now concludes properly."
    )
    assert any(e["event"] == "phase" and "ran long" in e["label"] for e in events)
    # And the FINAL stored record is the whole thing, not the fragment:
    stored = convs.last_live_assistant(conv_id)
    assert stored["text"] == result["reply"]


class NeverConvergesLLM:
    """Always truncated, to prove the continuation bound actually ends
    the loop rather than hanging forever."""

    def complete(self, system, messages, tools):
        return {"content": [{"type": "text", "text": "still going... "}],
                "stop_reason": "max_tokens"}


def test_continuation_is_bounded(founded):
    provider, conv_id = founded
    result = run_turn(provider, NeverConvergesLLM(), conv_id, "loop forever?")
    assert result["reply"].count("still going...") == 5  # 1 + MAX_CONTINUATIONS(4)


class TruncatedSkillCallLLM:
    """Simulates exactly the reported bug: authorizing a 'comprehensive'
    skill gets cut mid-call (empty/incomplete input), then the model is
    told plainly and successfully retries with a complete call."""

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {"content": [{"type": "tool_use", "id": "tu1",
                                 "name": "seira_skill_authorize", "input": {}}],
                    "stop_reason": "max_tokens"}
        if self.calls == 2:
            # The model saw the honest error and retries, complete this time.
            return {"content": [{"type": "tool_use", "id": "tu2",
                                 "name": "seira_skill_authorize",
                                 "input": {"name": "citation-form",
                                           "paradigm": "A shorter but real paradigm.",
                                           "judgment_ref": "psy-00001"}}],
                    "stop_reason": "tool_use"}
        return {"content": [{"type": "text", "text": "Authorized it, more concisely."}],
                "stop_reason": "end_turn"}


def test_truncated_tool_call_is_never_executed_and_recovers(founded):
    provider, conv_id = founded
    events = []
    result = run_turn(provider, TruncatedSkillCallLLM(), conv_id,
                      "author a comprehensive skill", emit=events.append)
    assert result["reply"] == "Authorized it, more concisely."
    # The retry actually authorized a real skill — the truncated first
    # attempt did NOT silently create a broken one:
    from seira_core.instruments import InstrumentStore
    skills = InstrumentStore().list_skills()
    assert len(skills) == 1 and skills[0]["name"] == "citation-form"
    assert any("too long for one step" in e.get("label", "") for e in events)


class MalformedArgsLLM:
    """A tool call whose args are simply wrong shape (not a truncation
    case) must still never crash the turn."""

    def complete(self, system, messages, tools):
        return {"content": [{"type": "tool_use", "id": "tu1",
                             "name": "seira_psyche_record",
                             "input": {"category": "self_model"}}],  # missing required fields
                "stop_reason": "tool_use"}


def test_malformed_tool_args_return_error_not_crash(founded):
    provider, conv_id = founded
    result = provider.handle_tool_call("seira_psyche_record",
                                       {"category": "self_model"})
    out = json.loads(result)
    assert out["ok"] is False and "error" in out  # never raises
