"""Instrument tests — Art. 5, 12, 15, 26, 34-37, 44."""

import json

import pytest

from seira_core.genesis import perform_genesis, perform_psyche_genesis
from seira_core.instruments import (
    InstrumentError,
    InstrumentIntegrityError,
    InstrumentStore,
    instruments_events_path,
)
from seira_core.tripwire import run_tripwire

UNITY = "# Unity\nName: Seira\nTelos: t\n"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis(UNITY, "# I1\n", architect="Loshem", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "logos", "content": "Work is patterned before it is done."}],
        architect="Loshem",
    )
    return InstrumentStore()


def _spawn(store, name="scribe", parent="psyche"):
    return store.spawn(name, f"Paradigm of {name}.", "psy-00001", parent=parent)


def test_spawn_requires_psyche_judgment(store):
    """Art. 35: no spawn without the authorizing judgment."""
    with pytest.raises(InstrumentError):
        store.spawn("rogue", "p", "  ")
    rec = _spawn(store)
    assert rec["depth"] == 1 and rec["psyche_judgment_ref"] == "psy-00001"


def test_depth_limit_enforced(store):
    """Art. 34: the tree stops where reasoning about it would stop."""
    a = _spawn(store, "a")
    b = store.spawn("b", "p", "psy-00001", parent=a["instrument_id"])
    c = store.spawn("c", "p", "psy-00001", parent=b["instrument_id"])
    assert c["depth"] == 3
    with pytest.raises(InstrumentError):
        store.spawn("d", "p", "psy-00001", parent=c["instrument_id"])


def test_surfacing_is_not_spawning(store):
    """Art. 35: an Instrument surfaces need; only Psyche spawns."""
    a = _spawn(store)
    rec = store.surface_need(a["instrument_id"], "needs a citation checker")
    assert rec["event"] == "need_surfaced"
    child = store.spawn("citation-checker", "p", "psy-00001",
                        parent=a["instrument_id"],
                        surfaced_by_ref=f"seq-{rec['seq']}")
    assert child["surfaced_by_ref"] == f"seq-{rec['seq']}"


def test_execution_carries_derivation_and_requires_output_ref(store):
    """Art. 5: untraceable output is noise, not an act of Seira's."""
    a = _spawn(store)
    with pytest.raises(InstrumentError):
        store.record_execution(a["instrument_id"], "translate", "clean", "  ")
    rec = store.record_execution(a["instrument_id"], "translate", "clean",
                                 "corpus:out-1")
    assert rec["derivation"]["paradigm_version"] == 1
    assert rec["derivation"]["psyche_judgment_ref"] == "psy-00001"
    assert rec["cause"] == {"type": "instrumental", "ref": a["instrument_id"]}


def test_three_feedbacks_escalate_and_block(store):
    """Art. 26: verbatim threshold; escalation blocks the task-type."""
    a = _spawn(store)
    iid = a["instrument_id"]
    store.record_execution(iid, "summarize", "local_feedback", "c:1")
    store.record_execution(iid, "summarize", "local_feedback", "c:2")
    rec = store.record_execution(iid, "summarize", "local_feedback", "c:3")
    assert "escalated" in rec
    with pytest.raises(InstrumentError):
        store.record_execution(iid, "summarize", "local_feedback", "c:4")
    with pytest.raises(InstrumentError):
        store.record_execution(iid, "summarize", "clean", "c:5")  # blocked entirely
    # other task-types unaffected:
    store.record_execution(iid, "translate", "clean", "c:6")


def test_clean_run_resets_the_streak(store):
    """Art. 26: 'without an intervening clean run' means exactly that."""
    a = _spawn(store)
    iid = a["instrument_id"]
    store.record_execution(iid, "t", "local_feedback", "c:1")
    store.record_execution(iid, "t", "local_feedback", "c:2")
    store.record_execution(iid, "t", "clean", "c:3")
    rec = store.record_execution(iid, "t", "local_feedback", "c:4")
    assert "escalated" not in rec  # streak restarted at 1


def test_revision_resolves_escalation_and_unblocks(store):
    a = _spawn(store)
    iid = a["instrument_id"]
    for i in range(3):
        rec = store.record_execution(iid, "s", "local_feedback", f"c:{i}")
    esc_seq = rec["escalated"]["seq"]
    with pytest.raises(InstrumentError):
        store.revise_paradigm(iid, "new p", "  ")  # judgment required
    store.revise_paradigm(iid, "revised paradigm", "psy-00001",
                          resolves_escalation_seq=esc_seq)
    inst = store.instrument(iid)
    assert inst["paradigm_version"] == 2 and inst["paradigm"] == "revised paradigm"
    rec = store.record_execution(iid, "s", "clean", "c:after")  # unblocked
    assert rec["derivation"]["paradigm_version"] == 2  # derivation tracks truth


def test_instrument_cannot_amend_its_paradigm(store):
    """Art. 12, structurally: the store's only revision path demands a
    Psyche judgment ref; no unreferenced write exists."""
    assert not hasattr(InstrumentStore, "set_paradigm")
    with pytest.raises(InstrumentError):
        store.revise_paradigm(_spawn(store)["instrument_id"], "p2", "")


def test_retirement_preserves_genealogy(store):
    a = _spawn(store, "parent")
    b = store.spawn("child", "p", "psy-00001", parent=a["instrument_id"])
    store.retire(a["instrument_id"], "task-type gone stale")
    inst = store.instrument(a["instrument_id"])
    assert inst["status"] == "retired"
    assert inst["children"] == [b["instrument_id"]]  # genealogy intact
    with pytest.raises(InstrumentError):
        store.record_execution(a["instrument_id"], "t", "clean", "c:1")
    with pytest.raises(InstrumentError):
        store.spawn("grandchild", "p", "psy-00001", parent=a["instrument_id"])


def test_skills_lifecycle(store):
    """Art. 37: authorized by judgment, versioned, shared, retired-not-deleted."""
    with pytest.raises(InstrumentError):
        store.authorize_skill("s", "p", "  ")
    s = store.authorize_skill("citation-form", "How citations are formed.", "psy-00001")
    sid = s["skill_id"]
    a, b = _spawn(store, "a"), _spawn(store, "b")
    for inst in (a, b):  # belongs to no single Instrument
        store.record_execution(inst["instrument_id"], "cite", "clean", "c:x",
                               skill_ref={"skill_id": sid, "version": 1})
    store.revise_skill(sid, "Better citation form.", "psy-00001")
    with pytest.raises(InstrumentError):
        store.record_execution(a["instrument_id"], "cite", "clean", "c:y",
                               skill_ref={"skill_id": sid, "version": 1})  # stale version
    store.record_execution(a["instrument_id"], "cite", "clean", "c:y",
                           skill_ref={"skill_id": sid, "version": 2})
    store.retire_skill(sid, "superseded approach")
    with pytest.raises(InstrumentError):
        store.record_execution(a["instrument_id"], "cite", "clean", "c:z",
                               skill_ref={"skill_id": sid, "version": 2})
    assert store.skill(sid)["status"] == "retired"  # history remains


def test_health_now_reports_convergence(store):
    from seira_core.reversion import ReversionStore

    a = _spawn(store)
    store.record_execution(a["instrument_id"], "t", "clean", "c:1")
    for i in range(3):
        store.record_execution(a["instrument_id"], "u", "local_feedback", f"c:{i}")
    h = ReversionStore().health()
    conv = h["instrument_convergence"]
    assert conv["executions"] == {"clean": 1, "local_feedback": 3}
    assert conv["escalations"] == {"total": 1, "open": 1}


def test_tampered_instrument_chain_halts(store):
    _spawn(store)
    lines = instruments_events_path().read_text().splitlines()
    rec = json.loads(lines[0])
    rec["paradigm"] = "silently rewritten paradigm"
    lines[0] = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    instruments_events_path().write_text("\n".join(lines) + "\n")
    with pytest.raises(InstrumentIntegrityError):
        store.verify_chain()
    assert run_tripwire()["halted"] is True
