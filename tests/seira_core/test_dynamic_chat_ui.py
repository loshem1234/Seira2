"""Tests for the dynamic chat experience.

Backend half: run_turn's direct-mode dispatch now emits tool events
carrying the actual tool INPUT, and a tool_result event with a bounded
preview after execution — the data the activity feed renders as
terminal lines, delegation cards, and expandable results.

Frontend half: template/CSS regression guards. The chat page's dynamic
features (code copy boxes, tool cards, live reasoning panel, streaming
bubble, file open buttons) live in chat.html + style.css; these tests
pin the markers so a refactor that silently drops one fails loudly.
"""

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

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_HTML = (REPO_ROOT / "seira_web/templates/chat.html").read_text()
STYLE_CSS = (REPO_ROOT / "seira_web/static/style.css").read_text()


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    monkeypatch.delenv("SEIRA_SANCTUM_RUNTIME", raising=False)
    monkeypatch.delenv("SEIRA_EXTRA_TOOLSETS", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am observable."}], architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


class ToolThenReplyLLM:
    """First call: a psyche recall tool_use. Second call: final text."""

    def __init__(self):
        self.calls = 0

    def complete(self, system, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {"content": [
                {"type": "tool_use", "id": "tu1", "name": "seira_psyche_recall",
                 "input": {"category": "self_model"}},
            ], "stop_reason": "tool_use"}
        return {"content": [{"type": "text", "text": "Recalled."}],
                "stop_reason": "end_turn"}


def test_tool_events_carry_input_and_results(founded):
    """The activity feed can only show what she's doing if the events
    carry it: 'tool' must include the input, and a 'tool_result' with
    the same tool_call_id must follow execution."""
    provider, conv_id = founded
    events = []
    run_turn(provider, ToolThenReplyLLM(), conv_id, "who are you?",
             emit=events.append)

    tool_evs = [e for e in events if e.get("event") == "tool"]
    assert tool_evs and tool_evs[0]["input"] == {"category": "self_model"}
    assert tool_evs[0]["tool_call_id"] == "tu1"

    result_evs = [e for e in events if e.get("event") == "tool_result"]
    assert result_evs and result_evs[0]["tool_call_id"] == "tu1"
    assert isinstance(result_evs[0]["result"], str) and result_evs[0]["result"]


def test_tool_result_preview_is_bounded(founded):
    """Result previews stream to the browser; an unbounded one could be
    megabytes of extracted web page. 2000 chars is the contract."""
    provider, conv_id = founded

    class HugeResultProvider:
        def system_prompt_block(self):
            return provider.system_prompt_block()

        def get_tool_schemas(self):
            return provider.get_tool_schemas()

        def handle_tool_call(self, name, args):
            return "x" * 100_000

    events = []
    run_turn(HugeResultProvider(), ToolThenReplyLLM(), conv_id, "hi",
             emit=events.append)
    result_evs = [e for e in events if e.get("event") == "tool_result"]
    assert result_evs and len(result_evs[0]["result"]) <= 2000


# ── Template & stylesheet regression guards ──

def test_chat_page_renders_code_copy_boxes():
    assert "renderBody" in CHAT_HTML and "copycode" in CHAT_HTML
    assert ".msg .codeblock" in STYLE_CSS and ".msg .copycode" in STYLE_CSS


def test_chat_page_has_tool_terminal_and_delegation_cards():
    assert "addToolCard" in CHAT_HTML
    assert "delegate_task" in CHAT_HTML          # delegation card branch
    assert "'terminal'" in CHAT_HTML             # terminal card branch
    assert ".toolcard.term" in STYLE_CSS and ".toolcard.delegate" in STYLE_CSS


def test_chat_page_has_live_reasoning_and_streaming():
    for marker in ("appendReasoning", "appendDelta", "finalizeReply",
                   "'reasoning'", "'delta'"):
        assert marker in CHAT_HTML, marker
    assert ".reasoning" in STYLE_CSS and ".msg.assistant.streaming" in STYLE_CSS


def test_chat_page_file_cards_have_open_buttons():
    assert "openbtn" in CHAT_HTML and "target=\"_blank\"" in CHAT_HTML
    assert ".toolchip.filecard .openbtn" in STYLE_CSS


def test_activity_and_reasoning_use_the_braid_mark_not_a_plain_orb():
    """Her mark, not a generic pulsing dot — and the old .orb classes
    must be fully retired, not left dangling as dead CSS/JS."""
    assert "braidSvg" in CHAT_HTML
    assert ".activity .orb" not in STYLE_CSS
    assert ".braid" in STYLE_CSS and "@keyframes braidsway" in STYLE_CSS


def test_embers_layer_exists_and_respects_reduced_motion():
    assert 'class="embers"' in CHAT_HTML
    assert ".ember {" in STYLE_CSS and "@keyframes emberrise" in STYLE_CSS
    # prefers-reduced-motion must turn embers off outright, not just
    # freeze them mid-rise (a static field of orange dots would be
    # worse than none at all).
    idx = STYLE_CSS.index("prefers-reduced-motion")
    reduced = STYLE_CSS[idx:idx + 400]
    assert ".ember" in reduced


def test_violet_palette_is_deeper_than_the_previous_baseline():
    """Regression guard for the specific ask: darker --void/--deep than
    the original #120820/#1B0E30 baseline, checked as luminance rather
    than exact hex so future fine-tuning doesn't break this test."""
    import re

    def hex_to_lum(h):
        h = h.lstrip('#')
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        return 0.2126*r + 0.7152*g + 0.0722*b

    m = re.search(r"--void:\s*(#[0-9A-Fa-f]{6})", STYLE_CSS)
    assert m, "expected a --void color declaration"
    assert hex_to_lum(m.group(1)) < hex_to_lum("#120820")


def test_sidebar_closes_via_robust_click_outside_pattern():
    """Replaced the earlier capture-phase #chatcol/#msgs listeners
    (which should have worked but didn't reliably in practice) with a
    single document-level click-outside listener using closest()
    containment — the standard, most robust version of this pattern,
    independent of DOM nesting/ordering."""
    assert "document.addEventListener('click'" in CHAT_HTML
    assert "e.target.closest('#sidebar')" in CHAT_HTML
    assert "setSidebar(false)" in CHAT_HTML


def test_hermes_session_emits_reasoning_and_deltas():
    """The hermes-mode agent must wire reasoning/thinking/stream-delta
    callbacks so the UI's live panels have a data source."""
    from unittest.mock import patch

    class _FakeAgent:
        last = None

        def __init__(self, **kw):
            _FakeAgent.last = kw

    with patch("run_agent.AIAgent", _FakeAgent):
        from seira_web.hermes_session import _build_agent
        events = []
        _build_agent("c1", events.append)
    kw = _FakeAgent.last
    kw["reasoning_callback"]("pondering the ledger")
    kw["stream_delta_callback"]("Hel")
    kw["stream_delta_callback"](None)
    assert {"event": "reasoning", "text": "pondering the ledger"} in events
    assert {"event": "delta", "text": "Hel"} in events
    assert {"event": "delta_end"} in events
