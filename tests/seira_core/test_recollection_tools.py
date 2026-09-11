"""Tests for the seven new seira_bridge tools supporting tags,
Recollection session control, and Weekly Notes — per Loshem's
direction (2026-09-11).
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


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I keep my own record."}], architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


# ---------------- tags ----------------

def test_add_tags_tool(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call(
        "seira_conversation_add_tags", {"conv_id": conv_id, "tags": ["kitchen", "budget"]}))
    assert out["ok"] is True
    assert set(out["tags"]) == {"kitchen", "budget"}


def test_add_tags_tool_on_unknown_conversation(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call(
        "seira_conversation_add_tags", {"conv_id": "conv-nope", "tags": ["x"]}))
    assert out["ok"] is False


def test_find_by_tag_tool(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_conversation_add_tags",
                              {"conv_id": conv_id, "tags": ["kitchen"]})
    out = json.loads(provider.handle_tool_call(
        "seira_conversation_find_by_tag", {"tag": "kitchen"}))
    assert out["ok"] is True
    assert any(c["conv_id"] == conv_id for c in out["conversations"])


def test_list_tags_tool(founded):
    provider, conv_id = founded
    provider.handle_tool_call("seira_conversation_add_tags",
                              {"conv_id": conv_id, "tags": ["kitchen", "budget"]})
    out = json.loads(provider.handle_tool_call("seira_conversation_list_tags", {}))
    assert out["ok"] is True
    assert set(out["tags"]) == {"kitchen", "budget"}


# ---------------- recollection session control (requires turn_context) ----------------

def test_mark_reviewed_tool(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call(
        "seira_recollection_mark_reviewed", {"conv_id": conv_id}))
    assert out["ok"] is True
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv_id][0]
    assert rec["recollection_processed_at"] is not None


def test_mark_reviewed_tool_on_unknown_conversation(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call(
        "seira_recollection_mark_reviewed", {"conv_id": "conv-nope"}))
    assert out["ok"] is False


def test_conclude_tool_requires_turn_context(founded):
    """Called with no active recollection turn context — must refuse
    cleanly, not crash."""
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_recollection_conclude", {}))
    assert out["ok"] is False


def test_conclude_tool_respects_the_floor(founded):
    from seira_web import turn_context, recollection
    provider, conv_id = founded
    recollection._start_session("tenant-x")
    with turn_context.turn_scope("tenant-x", "housekeeping-synthetic"):
        out = json.loads(provider.handle_tool_call("seira_recollection_conclude", {}))
    assert out["ok"] is False  # zero turns run yet
    recollection._end_session("tenant-x")


def test_conclude_tool_succeeds_past_the_floor(founded):
    from seira_web import turn_context, recollection
    provider, conv_id = founded
    recollection._start_session("tenant-x")
    for _ in range(recollection.MIN_TURNS_FOR_RECOLLECTION):
        recollection._record_turn("tenant-x")
    with turn_context.turn_scope("tenant-x", "housekeeping-synthetic"):
        out = json.loads(provider.handle_tool_call("seira_recollection_conclude", {}))
    assert out["ok"] is True
    recollection._end_session("tenant-x")


# ---------------- weekly notes ----------------

def test_weekly_notes_write_and_read_tools(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_weekly_notes_write", {
        "content": "A real, detailed reflection on the week.",
        "provenance": [conv_id],
    }))
    assert out["ok"] is True

    out = json.loads(provider.handle_tool_call("seira_weekly_notes_read", {}))
    assert out["ok"] is True
    assert len(out["entries"]) == 1
    assert "detailed reflection" in out["entries"][0]["content"]


def test_weekly_notes_write_requires_provenance(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_weekly_notes_write", {
        "content": "No provenance here.", "provenance": [],
    }))
    assert out["ok"] is False


def test_weekly_notes_write_captures_conv_ids_covered_from_session(founded):
    from seira_web import turn_context, recollection
    provider, conv_id = founded
    recollection._start_session("tenant-x")
    convs.mark_recollection_reviewed(conv_id)
    with turn_context.turn_scope("tenant-x", "housekeeping-synthetic"):
        out = json.loads(provider.handle_tool_call("seira_weekly_notes_write", {
            "content": "Reflected on what came up this week.",
            "provenance": [conv_id],
        }))
    assert out["ok"] is True
    read = json.loads(provider.handle_tool_call("seira_weekly_notes_read", {}))
    assert conv_id in read["entries"][0]["conv_ids_covered"]
    recollection._end_session("tenant-x")


def test_weekly_notes_read_respects_limit(founded):
    provider, conv_id = founded
    for i in range(3):
        provider.handle_tool_call("seira_weekly_notes_write",
                                  {"content": f"Entry {i}", "provenance": [conv_id]})
    out = json.loads(provider.handle_tool_call("seira_weekly_notes_read", {"limit": 2}))
    assert len(out["entries"]) == 2
