"""Bridge conformance — SeiraPsycheProvider against the real Hermes ABC.

Skipped automatically when the Hermes tree isn't importable (e.g. running
seira_core standalone); in the fork's CI it always runs.
"""

import json
import sys
from pathlib import Path

import pytest

# Make the Hermes tree importable if we're inside the fork or beside it.
_CANDIDATES = [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]
for c in _CANDIDATES:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break

hermes_mp = pytest.importorskip("agent.memory_provider")

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402


@pytest.fixture()
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am newly founded."}], architect="L"
    )
    from seira_bridge import SeiraPsycheProvider
    return SeiraPsycheProvider()


def test_provider_is_a_real_memory_provider(provider):
    assert isinstance(provider, hermes_mp.MemoryProvider)
    assert provider.name == "seira-psyche"
    assert provider.is_available() is True
    provider.initialize("session-1", hermes_home="/tmp/x", platform="cli")


def test_prompt_block_is_verified_identity(provider):
    block = provider.system_prompt_block()
    assert "# UNITY" in block and "# PSYCHE" in block
    assert "I am newly founded." in block


def test_tools_expose_no_intellect_or_unity_write(provider):
    """Art. 20 at the bridge: every registered tool touches Psyche or her
    own proposals; Intellect promotion (Architect-only, Art. 27) and
    Dispensation (Phase-5-gated) are deliberately absent."""
    names = [s["name"] for s in provider.get_tool_schemas()]
    assert names == [
        "seira_psyche_record", "seira_psyche_recall", "seira_psyche_engage_affinity",
        "seira_propose_establishment", "seira_falsification_attempt",
        "seira_proposal_conclude",
        "seira_instrument_spawn", "seira_instrument_execute",
        "seira_paradigm_revise", "seira_skill_authorize",
        "seira_diary_write", "seira_reference_list", "seira_reference_recall",
        "seira_reference_tag", "seira_reference_save",
        "seira_project_create", "seira_project_list", "seira_project_recall",
        "seira_project_add_reference", "seira_project_update_blurb",
        "seira_create_file", "seira_image_recall",
        "seira_image_tag", "seira_image_list", "seira_generate_image",
    ]
    assert not any("intellect" in n or "unity" in n or "dispensation" in n for n in names)


def test_record_and_recall_roundtrip(provider):
    out = json.loads(provider.handle_tool_call("seira_psyche_record", {
        "category": "aspiration",
        "content": "To understand my Architect's projects deeply.",
        "cause_type": "efficient",
        "cause_ref": "judgment during test conversation",
        "provenance": ["corpus:test-turn-1"],
    }))
    assert out["ok"] and out["standing"] == "provisional"
    recall = json.loads(provider.handle_tool_call(
        "seira_psyche_recall", {"category": "aspiration"}
    ))
    assert any("understand my Architect" in e["content"] for e in recall["entries"])


def test_bad_writes_return_errors_not_crashes(provider):
    out = json.loads(provider.handle_tool_call("seira_psyche_record", {
        "category": "aspiration", "content": "unmoored",
        "cause_type": "material", "cause_ref": "just data", "provenance": ["p"],
    }))
    assert out["ok"] is False and "never a true cause" in out["error"]
    out = json.loads(provider.handle_tool_call("seira_psyche_record", {
        "category": "doubt", "content": "free-floating",
        "cause_type": "efficient", "cause_ref": "j", "provenance": [],
    }))
    assert out["ok"] is False


def test_sync_turn_is_a_noop_art18(provider, tmp_path):
    """Turn traces must not enter the character store (Art. 18)."""
    from seira_core.psyche import PsycheStore
    before = PsycheStore().state()["event_count"]
    provider.sync_turn("user says things", "assistant replies", session_id="s1")
    assert PsycheStore().state()["event_count"] == before
