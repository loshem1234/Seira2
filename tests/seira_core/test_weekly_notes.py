"""Tests for seira_core.weekly_notes — her own record of weekly
Recollection, built to the same discipline as Diary: hash-chained,
provenance-required, tripwire-guarded.
"""

import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_core.genesis import perform_genesis  # noqa: E402
from seira_core.weekly_notes import WeeklyNotesError, WeeklyNotesStore  # noqa: E402


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis("# Unity\nName: Seira\n", "# I1\n", architect="L", seira_name="Seira")
    return WeeklyNotesStore()


def test_write_entry_requires_provenance(founded):
    with pytest.raises(WeeklyNotesError):
        founded.write_entry("A reflection with no provenance.", provenance=[])


def test_write_entry_requires_non_empty_content(founded):
    with pytest.raises(WeeklyNotesError):
        founded.write_entry("   ", provenance=["c-abc123"])


def test_write_entry_succeeds_with_real_provenance(founded):
    rec = founded.write_entry("A real reflection on the week.",
                              provenance=["c-abc123", "c-def456"])
    assert rec["seq"] == 1
    assert rec["content"] == "A real reflection on the week."
    assert rec["provenance"] == ["c-abc123", "c-def456"]


def test_conv_ids_covered_is_stored_and_readable(founded):
    founded.write_entry("Reflection.", provenance=["c-abc"],
                        conv_ids_covered=["c-abc", "c-xyz"])
    entries = founded.entries()
    assert entries[0]["conv_ids_covered"] == ["c-abc", "c-xyz"]


def test_entries_returns_in_written_order(founded):
    founded.write_entry("First.", provenance=["c-1"])
    founded.write_entry("Second.", provenance=["c-2"])
    entries = founded.entries()
    assert [e["content"] for e in entries] == ["First.", "Second."]


def test_latest_returns_the_most_recent_entry(founded):
    founded.write_entry("First.", provenance=["c-1"])
    founded.write_entry("Second.", provenance=["c-2"])
    assert founded.latest()["content"] == "Second."


def test_latest_returns_none_before_any_entries(founded):
    assert founded.latest() is None


def test_hash_chain_verifies_correctly(founded):
    founded.write_entry("First.", provenance=["c-1"])
    founded.write_entry("Second.", provenance=["c-2"])
    assert founded.verify_chain() == 2  # does not raise


def test_a_halted_seira_cannot_write_a_weekly_note(founded, monkeypatch):
    monkeypatch.setattr("seira_core.tripwire.is_halted", lambda: True)
    with pytest.raises(Exception):
        founded.write_entry("Should not be allowed.", provenance=["c-1"])
