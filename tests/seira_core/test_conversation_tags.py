"""Tests for the tags and recollection-tracking additions to
seira_web.conversations — per Loshem's direction (2026-09-11).
"""

import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_web import conversations as convs  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    return tmp_path / "seira"


# ---------------- tags ----------------

def test_add_tags_is_additive(home):
    conv = convs.create_conversation()
    convs.add_tags(conv["conv_id"], ["kitchen", "renovation"])
    convs.add_tags(conv["conv_id"], ["budget"])
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert set(rec["tags"]) == {"kitchen", "renovation", "budget"}


def test_add_tags_deduplicates(home):
    conv = convs.create_conversation()
    convs.add_tags(conv["conv_id"], ["kitchen"])
    convs.add_tags(conv["conv_id"], ["kitchen", "budget"])
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert rec["tags"] == ["kitchen", "budget"]


def test_add_tags_on_unknown_conversation_returns_none(home):
    assert convs.add_tags("conv-does-not-exist", ["x"]) is None


def test_find_by_tag_returns_matching_conversations(home):
    a = convs.create_conversation("Conv A")
    b = convs.create_conversation("Conv B")
    convs.create_conversation("Conv C")  # no tags
    convs.add_tags(a["conv_id"], ["kitchen"])
    convs.add_tags(b["conv_id"], ["kitchen", "budget"])

    found = convs.find_by_tag("kitchen")
    ids = {c["conv_id"] for c in found}
    assert ids == {a["conv_id"], b["conv_id"]}


def test_find_by_tag_excludes_archived(home):
    conv = convs.create_conversation()
    convs.add_tags(conv["conv_id"], ["kitchen"])
    convs.archive_conversation(conv["conv_id"])
    assert convs.find_by_tag("kitchen") == []


def test_list_all_tags_is_deduplicated_and_sorted(home):
    a = convs.create_conversation()
    b = convs.create_conversation()
    convs.add_tags(a["conv_id"], ["zebra", "apple"])
    convs.add_tags(b["conv_id"], ["apple", "mango"])
    assert convs.list_all_tags() == ["apple", "mango", "zebra"]


def test_list_all_tags_empty_before_any_tagging(home):
    convs.create_conversation()
    assert convs.list_all_tags() == []


# ---------------- recollection tracking ----------------

def test_mark_recollection_reviewed_sets_the_timestamp(home):
    conv = convs.create_conversation()
    rec = convs.mark_recollection_reviewed(conv["conv_id"])
    assert rec["recollection_processed_at"] is not None


def test_mark_recollection_reviewed_on_unknown_conv_returns_none(home):
    assert convs.mark_recollection_reviewed("conv-does-not-exist") is None


def test_a_never_reviewed_conversation_needs_recollection(home):
    from seira_web.recollection import _needs_recollection
    conv = convs.create_conversation()
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert _needs_recollection(rec) is True


def test_a_freshly_reviewed_conversation_does_not_need_recollection(home):
    from seira_web.recollection import _needs_recollection
    conv = convs.create_conversation()
    convs.mark_recollection_reviewed(conv["conv_id"])
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert _needs_recollection(rec) is False


def test_new_activity_after_review_needs_recollection_again(home):
    import time
    from seira_web.recollection import _needs_recollection
    conv = convs.create_conversation()
    convs.mark_recollection_reviewed(conv["conv_id"])
    time.sleep(0.01)
    convs.touch(conv["conv_id"])  # new activity after review
    rec = [c for c in convs.list_conversations() if c["conv_id"] == conv["conv_id"]][0]
    assert _needs_recollection(rec) is True
