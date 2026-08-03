"""Intellect tests — Art. 24, 25, 27, 28."""

import json

import pytest

from seira_core.errors import IntellectIntegrityError, RatificationError
from seira_core.genesis import perform_genesis
from seira_core.intellect import ARCHITECT_RATIFICATION_PHRASE, IntellectStore
from seira_core.paths import intellect_versions_path

UNITY = "# Unity\nName: Test-Seira\nTelos: testing.\n"
V1 = "# Intellect v1\nOriginal doctrine.\n"
V2 = "# Intellect v2\nExpanded doctrine.\n"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis(UNITY, V1, architect="Loshem", seira_name="Test-Seira")
    return IntellectStore()


def _ratify(store, content=V2, kind="expansion", ref="prop-001", contradicted=None):
    return store.ratify(
        content=content,
        kind=kind,
        proposal_ref=ref,
        architect_confirmation=ARCHITECT_RATIFICATION_PHRASE,
        contradicted_ref=contradicted,
    )


def test_chain_is_anchored_to_unity(store):
    from seira_core.unity import read_lock

    v1 = store.history()[0]
    assert v1["prev_hash"] == read_lock()["unity_sha256"]


def test_ratify_appends_and_supersedes_without_deleting(store):
    _ratify(store)
    history = store.history()
    assert [r["version"] for r in history] == [1, 2]
    assert history[0]["superseded"] is True
    assert history[0]["content"] == V1  # retained, never overwritten
    assert store.current()["content"] == V2


def test_ratify_requires_exact_confirmation_phrase(store):
    with pytest.raises(RatificationError):
        store.ratify(V2, "expansion", "prop-001",
                     architect_confirmation="yes, sure")


def test_ratify_requires_proposal_ref(store):
    with pytest.raises(RatificationError):
        store.ratify(V2, "expansion", "  ",
                     architect_confirmation=ARCHITECT_RATIFICATION_PHRASE)


def test_correction_requires_contradicted_ref_but_expansion_does_not(store):
    with pytest.raises(RatificationError):
        _ratify(store, kind="correction")  # missing contradicted_ref → refused
    _ratify(store, kind="correction", contradicted="v1 §telos wording")
    _ratify(store, content="# v3\nmore.\n", kind="expansion", ref="prop-002")
    kinds = [r["kind"] for r in store.history()]
    assert kinds == ["genesis", "correction", "expansion"]


def test_restore_creates_new_version_not_deletion(store):
    _ratify(store)  # v2
    rec = store.restore(1, ARCHITECT_RATIFICATION_PHRASE, reason="v2 proved mistaken")
    history = store.history()
    assert [r["version"] for r in history] == [1, 2, 3]  # v2 survives as evidence
    assert rec["restores_version"] == 1
    assert store.current()["content"] == V1


def test_restore_requires_reason_and_existing_version(store):
    _ratify(store)
    with pytest.raises(RatificationError):
        store.restore(1, ARCHITECT_RATIFICATION_PHRASE, reason="  ")
    with pytest.raises(RatificationError):
        store.restore(99, ARCHITECT_RATIFICATION_PHRASE, reason="x")
    with pytest.raises(RatificationError):
        store.restore(2, ARCHITECT_RATIFICATION_PHRASE, reason="already current")


def test_tampered_record_breaks_chain_verification(store):
    _ratify(store)
    lines = intellect_versions_path().read_text().splitlines()
    rec = json.loads(lines[1])
    rec["content"] = "silently altered doctrine"  # tamper without re-hashing
    lines[1] = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    intellect_versions_path().write_text("\n".join(lines) + "\n")
    with pytest.raises(IntellectIntegrityError):
        store.verify_chain()
    # and the tripwire converts this into a halt:
    from seira_core.tripwire import run_tripwire
    assert run_tripwire()["halted"] is True


def test_deleted_version_breaks_chain(store):
    _ratify(store)
    _ratify(store, content="# v3\n", ref="prop-002")
    lines = intellect_versions_path().read_text().splitlines()
    del lines[1]  # excise v2
    intellect_versions_path().write_text("\n".join(lines) + "\n")
    with pytest.raises(IntellectIntegrityError):
        store.verify_chain()


def test_never_appends_onto_broken_chain(store):
    lines = intellect_versions_path().read_text().splitlines()
    rec = json.loads(lines[0])
    rec["content"] = "tampered"
    intellect_versions_path().write_text(
        json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n"
    )
    with pytest.raises(IntellectIntegrityError):
        _ratify(store)  # refuses rather than laundering the tamper


def test_ratification_is_a_learning_event_in_audit(store):
    from seira_core.paths import audit_log_path

    _ratify(store)
    events = [json.loads(l) for l in audit_log_path().read_text().splitlines()]
    ratified = [e for e in events if e["event"] == "intellect_ratified"]
    assert ratified and ratified[-1]["learning"] is True  # Art. 43
