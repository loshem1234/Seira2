"""Tests for seira_web.hermes_tools — the deliberately narrow bridge from
Sanctum's direct-API chat loop to real Hermes tool handlers.

Every test names the failure mode it closes: an operator mistyping or
over-widening SEIRA_EXTRA_TOOLSETS must never expose a toolset this
module hasn't reviewed (terminal, browser, delegate_task — all of which
assume Hermes agent-loop context Sanctum does not have).
"""

import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("SEIRA_EXTRA_TOOLSETS", raising=False)


def test_default_is_off(monkeypatch):
    """No env var set → no bridged tools at all. The safest default."""
    from seira_web import hermes_tools
    assert hermes_tools.extra_tool_names() == set()
    assert hermes_tools.extra_tool_schemas() == []


def test_unlisted_toolset_is_silently_dropped(monkeypatch):
    """The whitelist wins even when an operator asks for more.

    This is the core safety property: SEIRA_EXTRA_TOOLSETS is operator
    input, and operator input must never be able to summon a toolset
    (terminal, browser, delegation) whose handlers assume a Hermes
    agent-loop context this bridge cannot honestly provide."""
    monkeypatch.setenv("SEIRA_EXTRA_TOOLSETS", "web,terminal,browser,delegation")
    from seira_web import hermes_tools
    names = hermes_tools.extra_tool_names()
    assert "terminal" not in names and "process" not in names
    assert "delegate_task" not in names
    assert not any(n.startswith("browser_") for n in names)


def test_web_toolset_names_are_bridged(monkeypatch):
    monkeypatch.setenv("SEIRA_EXTRA_TOOLSETS", "web")
    from seira_web import hermes_tools
    names = hermes_tools.extra_tool_names()
    assert {"web_search", "web_extract"} <= names


def test_skills_toolset_names_are_bridged(monkeypatch):
    monkeypatch.setenv("SEIRA_EXTRA_TOOLSETS", "skills")
    from seira_web import hermes_tools
    names = hermes_tools.extra_tool_names()
    assert {"skills_list", "skill_view", "skill_manage"} <= names


def test_schemas_are_anthropic_shaped(monkeypatch):
    """web tools are gated by check_web_api_key — without a search API
    key configured in this test env, the schema list is correctly
    empty. What matters here is shape, so use the skills toolset,
    which has no external credential dependency."""
    monkeypatch.setenv("SEIRA_EXTRA_TOOLSETS", "skills")
    from seira_web import hermes_tools
    schemas = hermes_tools.extra_tool_schemas()
    assert schemas, "expected skills_list/skill_view/skill_manage"
    for s in schemas:
        assert set(s.keys()) >= {"name", "description", "input_schema"}
        assert "type" not in s or s.get("type") != "function"  # not OpenAI-shaped


def test_dispatch_unknown_tool_returns_error_string_not_raise(monkeypatch):
    monkeypatch.setenv("SEIRA_EXTRA_TOOLSETS", "web")
    from seira_web import hermes_tools
    result = hermes_tools.dispatch_extra_tool("not_a_real_tool", {})
    assert isinstance(result, str)
    assert "error" in result.lower() or "unknown" in result.lower()


def test_chat_tools_never_duplicate_web_search_name(monkeypatch):
    """Anthropic's native web_search server tool and Hermes's bridged
    client-side web_search tool share a name; sending both to the API
    would be a malformed request. chat.py must keep only one."""
    monkeypatch.setenv("SEIRA_EXTRA_TOOLSETS", "web")
    from seira_web.chat import _anthropic_tools

    class _FakeProvider:
        def get_tool_schemas(self):
            return []

    tools = _anthropic_tools(_FakeProvider(), web_search=True)
    names = [t["name"] for t in tools]
    assert names.count("web_search") == 1
