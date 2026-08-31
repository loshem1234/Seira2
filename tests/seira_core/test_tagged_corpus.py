"""Tests for the tagged-Corpus document tools (seira_reference_save,
seira_reference_tag) and generated-file auto-tagging — the same
architecture as images.py, extended to documents per Loshem's
direction: uploaded, generated, and web-kept documents all join one
tagged, recall-at-any-time store. Also proves the actual claim behind
the image-recall fix: that Hermes's own multimodal exemption check
genuinely recognizes the new envelope shape, not just that it looks
plausible on paper.
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
from seira_web import references as refs  # noqa: E402


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I keep what matters."}], architect="L")
    from seira_bridge import SeiraPsycheProvider
    conv = convs.create_conversation()
    return SeiraPsycheProvider(), conv["conv_id"]


# ---------------- seira_reference_save (web / arbitrary text) ----------------

def test_reference_save_tool_end_to_end(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_reference_save", {
        "filename": "openai-pricing.txt",
        "content": "GPT-5 pricing: $X per million tokens",
        "tag": "openai-pricing",
        "source": "web",
    }))
    assert out["ok"] is True and out["tag"] == "openai-pricing"

    recalled = json.loads(provider.handle_tool_call(
        "seira_reference_recall", {"ref": "openai-pricing"}))
    assert recalled["ok"] is True
    assert "GPT-5 pricing" in recalled["text"]
    assert recalled["source"] == "web"


def test_reference_save_defaults_source_to_web(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_reference_save", {
        "filename": "note.txt", "content": "found this somewhere",
    }))
    assert out["ok"] is True
    rec = refs.resolve_ref(out["ref_id"])
    assert rec["source"] == "web"


def test_reference_save_rejects_empty_content(founded):
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_reference_save", {
        "filename": "empty.txt", "content": "   ",
    }))
    assert out["ok"] is False


# ---------------- seira_reference_tag ----------------

def test_reference_tag_tool_renames(founded):
    provider, conv_id = founded
    rec = refs.save_reference("doc.txt", "some content")
    out = json.loads(provider.handle_tool_call(
        "seira_reference_tag", {"ref_id": rec["ref_id"], "tag": "renamed"}))
    assert out["ok"] is True and out["tag"] == "renamed"
    assert refs.find_by_tag("renamed")["ref_id"] == rec["ref_id"]


def test_reference_tag_tool_refuses_collision(founded):
    provider, conv_id = founded
    a = refs.save_reference("a.txt", "content a", tag="taken")
    b = refs.save_reference("b.txt", "content b")
    out = json.loads(provider.handle_tool_call(
        "seira_reference_tag", {"ref_id": b["ref_id"], "tag": "taken"}))
    assert out["ok"] is False


# ---------------- seira_create_file auto-joins the tagged Corpus ----------------

def test_generated_file_becomes_a_tagged_reference_automatically(founded):
    """The core of Loshem's request: a document she generates should be
    recallable later, not just downloadable once."""
    provider, conv_id = founded
    out = json.loads(provider.handle_tool_call("seira_create_file", {
        "format": "md", "filename": "meeting-notes",
        "content": "# Meeting Notes\n\nWe discussed the roadmap.",
    }))
    assert out["ok"] is True
    assert out["reference_tag"], "must auto-join the tagged Corpus"

    recalled = json.loads(provider.handle_tool_call(
        "seira_reference_recall", {"ref": out["reference_tag"]}))
    assert recalled["ok"] is True
    assert "roadmap" in recalled["text"]
    assert recalled["source"] == "generated"


def test_generated_file_download_still_succeeds_even_if_reference_save_fails(founded, monkeypatch):
    """A reference-save failure must never break the file download that
    already succeeded — it's a best-effort addition, not a new way for
    an otherwise-working tool to fail."""
    provider, conv_id = founded

    def _boom(*a, **kw):
        raise ValueError("simulated reference-store failure")

    monkeypatch.setattr(refs, "save_reference", _boom)
    out = json.loads(provider.handle_tool_call("seira_create_file", {
        "format": "md", "filename": "still-works",
        "content": "# Still works\n\ncontent here",
    }))
    assert out["ok"] is True
    assert out["download_path"]
    assert out["reference_tag"] is None


# ---------------- the actual claim: Hermes exempts the new image shape ----------------

def test_image_recall_envelope_is_genuinely_exempt_from_hermes_truncation(founded):
    """Not just 'looks like the right shape' — actually run it through
    Hermes's own real exemption check (agent/tool_dispatch_helpers or
    wherever _is_multimodal_tool_result lives) and confirm it returns
    True. This is the entire point of the fix: without this being
    True, the envelope would still hit maybe_persist_tool_result and
    depend on a sandbox environment existing, which was the original
    live failure."""
    provider, conv_id = founded
    from seira_web import images
    images.save_image("big.png", "image/png", b"X" * 50_000, tag="a-big-one")

    out = provider.handle_tool_call("seira_image_recall", {"ref": "a-big-one"})
    assert isinstance(out, dict)

    from agent.tool_dispatch_helpers import _is_multimodal_tool_result
    assert _is_multimodal_tool_result(out) is True, (
        "Hermes's own exemption check must recognize this envelope — "
        "otherwise large recalls still risk the original truncation bug"
    )
