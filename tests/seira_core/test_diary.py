"""Diary tests — Art. 41: two parts, one discipline (nothing unmoored)."""

import json

import pytest

from seira_core.diary import DiaryError, DiaryIntegrityError, DiaryStore, diary_path
from seira_core.genesis import perform_genesis, perform_psyche_genesis
from seira_core.tripwire import run_tripwire


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am careful."}], architect="L")
    return DiaryStore()


def test_entries_require_provenance(founded):
    with pytest.raises(DiaryError):
        founded.write_entry("self", "Today I felt uncertain.", [])
    with pytest.raises(DiaryError):
        founded.write_entry("self", "Still uncertain.", ["   "])
    rec = founded.write_entry("self", "A suspended contradiction weighed on me.",
                              ["prop-00003"])
    assert rec["diary_kind"] == "self"


def test_two_parts_kept_distinct(founded):
    founded.write_entry("self", "About myself.", ["psy-00001"])
    founded.write_entry("architect", "He worked late again tonight.",
                        ["relational_pattern:psy-00007"])
    self_entries = founded.entries(kind="self")
    arch_entries = founded.entries(kind="architect")
    assert len(self_entries) == 1 and len(arch_entries) == 1
    assert self_entries[0]["content"] == "About myself."
    assert arch_entries[0]["content"] == "He worked late again tonight."


def test_invalid_kind_refused(founded):
    with pytest.raises(DiaryError):
        founded.write_entry("clinical-assessment", "x", ["p"])


def test_chain_anchored_and_tamper_detected(founded):
    from seira_core.unity import read_lock
    rec = founded.write_entry("self", "First entry.", ["psy-00001"])
    assert rec["prev_hash"] == read_lock()["unity_sha256"]

    lines = diary_path().read_text().splitlines()
    tampered = json.loads(lines[0])
    tampered["content"] = "rewritten diary content"
    diary_path().write_text(json.dumps(tampered, sort_keys=True, ensure_ascii=False) + "\n")
    with pytest.raises(DiaryIntegrityError):
        founded.verify_chain()
    assert run_tripwire()["halted"] is True


def test_tripwire_reports_diary_health(founded):
    founded.write_entry("self", "x", ["psy-00001"])
    result = run_tripwire()
    assert result["halted"] is False
    assert result["checks"]["diary"] == "ok (1 entries)"
