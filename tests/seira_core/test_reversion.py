"""Reversion tests — Art. 24, 25, 27, 30-31, 39, 44."""

import json

import pytest

from seira_core.genesis import perform_genesis, perform_psyche_genesis
from seira_core.intellect import ARCHITECT_RATIFICATION_PHRASE, IntellectStore
from seira_core.psyche import PsycheStore
from seira_core.reversion import (
    ReversionError,
    ReversionIntegrityError,
    ReversionStore,
    reversion_events_path,
)
from seira_core.tripwire import run_tripwire

UNITY = "# Unity\nName: Seira\nTelos: t\n"
INTELLECT = "# I1\nDoctrine.\n"
ORIGIN = {"type": "self_audit", "ref": "audit-2026-08-03"}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis(UNITY, INTELLECT, architect="Loshem", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "self_model", "content": "I am careful."}], architect="Loshem"
    )
    return ReversionStore()


def _open_est(store, entry_id="psy-00001"):
    return store.open_proposal(
        target="psyche_standing", kind="establishment",
        content="Case: repeated careful work.", entry_id=entry_id,
        origin=ORIGIN, evidence_refs=["corpus:a", "corpus:b"],
    )


def test_correction_and_expansion_never_conflated(store):
    """Art. 24: separate validation paths."""
    with pytest.raises(ReversionError):
        store.open_proposal("intellect", "correction", "x", ORIGIN, ["e"])  # no contradicted_ref
    with pytest.raises(ReversionError):
        store.open_proposal("intellect", "expansion", "x", ORIGIN, ["e"],
                            contradicted_ref="v1 §2")  # expansion carrying one
    store.open_proposal("intellect", "correction", "x", ORIGIN, ["e"],
                        contradicted_ref="v1 §2")
    store.open_proposal("intellect", "expansion", "y", ORIGIN, ["e"])


def test_origin_declaration_required(store):
    """Art. 25.1: arisen through genuine reversion, declared and referenced."""
    with pytest.raises(ReversionError):
        store.open_proposal("intellect", "expansion", "x",
                            {"type": "vibes", "ref": "r"}, ["e"])
    with pytest.raises(ReversionError):
        store.open_proposal("intellect", "expansion", "x",
                            {"type": "reversion", "ref": "  "}, ["e"])


def test_attempts_require_historical_corpus_refs(store):
    """Art. 39: rehearsed against history; no live-conversation field exists."""
    p = _open_est(store)
    with pytest.raises(ReversionError):
        store.record_attempt(p["proposal_id"], "counterexample search", [], "survived")
    store.record_attempt(p["proposal_id"], "counterexample search",
                         ["corpus:2026-07-01#turn3"], "survived")


def test_promotion_bar_full_sequence(store):
    """Art. 25: no promotion without survived attempt AND current-Intellect
    consistency; accumulation of evidence alone is insufficient."""
    p = _open_est(store)
    pid = p["proposal_id"]
    with pytest.raises(ReversionError):
        store.promote_psyche(pid, basis_ref="b")  # nothing on record
    store.record_attempt(pid, "sought counterexamples in history",
                         ["corpus:x"], "survived")
    with pytest.raises(ReversionError):
        store.promote_psyche(pid, basis_ref="b")  # no consistency check yet
    store.record_consistency_check(pid, "consistent")
    store.promote_psyche(pid, basis_ref="review-1")
    entry = PsycheStore().state()["entries"]["psy-00001"]
    assert entry["standing"] == "established"
    assert pid in entry["falsification_ref"]
    assert store.proposal(pid)["status"] == "promoted"


def test_consistency_check_pins_to_current_intellect(store):
    """If Intellect moves after the check, promotion demands a re-check."""
    p = _open_est(store)
    pid = p["proposal_id"]
    store.record_attempt(pid, "m", ["corpus:x"], "survived")
    store.record_consistency_check(pid, "consistent")
    IntellectStore().ratify(  # Intellect moves
        "# I2\n", kind="expansion", proposal_ref="out-of-band",
        architect_confirmation=ARCHITECT_RATIFICATION_PHRASE,
    )
    with pytest.raises(ReversionError):
        store.promote_psyche(pid, basis_ref="b")
    store.record_consistency_check(pid, "consistent")
    store.promote_psyche(pid, basis_ref="b")


def test_intellect_promotion_is_ratification(store):
    """Art. 27: the store hands cleared proposals to the Architect's gate."""
    p = store.open_proposal("intellect", "expansion", "# I2\nNew doctrine.\n",
                            ORIGIN, ["e"])
    pid = p["proposal_id"]
    store.record_attempt(pid, "m", ["corpus:x"], "survived")
    store.record_consistency_check(pid, "consistent")
    with pytest.raises(Exception):
        store.promote_intellect(pid, architect_confirmation="nope")
    rec = store.promote_intellect(
        pid, architect_confirmation=ARCHITECT_RATIFICATION_PHRASE
    )
    v = IntellectStore().current()
    assert v["version"] == rec["detail"]["intellect_version"] == 2
    assert v["proposal_ref"] == pid  # linkage survives in the Intellect chain


def test_rejected_requires_failed_attempt_on_record(store):
    p = _open_est(store)
    with pytest.raises(ReversionError):
        store.reject(p["proposal_id"])
    store.record_attempt(p["proposal_id"], "m", ["corpus:x"], "failed")
    store.reject(p["proposal_id"])
    assert store.proposal(p["proposal_id"])["status"] == "rejected"


def test_suspension_requires_two_live_survivors_and_blocks_promotion(store):
    PsycheStore().add_entry("logos", "rival content",
                            {"type": "efficient", "ref": "j"}, ["p"])
    a = _open_est(store, "psy-00001")
    b = _open_est(store, "psy-00002")
    store.record_attempt(a["proposal_id"], "m", ["c:1"], "survived")
    with pytest.raises(ReversionError):
        store.suspend_pair(a["proposal_id"], b["proposal_id"])  # b not a survivor
    store.record_attempt(b["proposal_id"], "m", ["c:2"], "survived")
    store.suspend_pair(a["proposal_id"], b["proposal_id"])
    pa, pb = store.proposal(a["proposal_id"]), store.proposal(b["proposal_id"])
    assert pa["status"] == pb["status"] == "suspended"
    assert pa["terminal_detail"]["contradiction_with"] == b["proposal_id"]
    with pytest.raises(ReversionError):
        store.promote_psyche(a["proposal_id"], basis_ref="b")  # parked, not promotable


def test_stale_is_expansion_only(store):
    c = store.open_proposal("intellect", "correction", "x", ORIGIN, ["e"],
                            contradicted_ref="v1 §1")
    with pytest.raises(ReversionError):
        store.mark_stale(c["proposal_id"])
    e = store.open_proposal("intellect", "expansion", "y", ORIGIN, ["e"])
    store.mark_stale(e["proposal_id"])
    assert store.proposal(e["proposal_id"])["status"] == "stale"


def test_withdraw_requires_reason_and_terminal_is_terminal(store):
    p = _open_est(store)
    with pytest.raises(ReversionError):
        store.withdraw(p["proposal_id"], "  ")
    store.withdraw(p["proposal_id"], "set aside; evidence base too thin")
    with pytest.raises(ReversionError):
        store.record_attempt(p["proposal_id"], "m", ["c"], "survived")
    with pytest.raises(ReversionError):
        store.withdraw(p["proposal_id"], "again")


def test_dispensation_forces_retroactive_proposal(store):
    d = store.invoke_dispensation(
        action="answered against doctrine to prevent imminent harm",
        conditions_ref="Intellect v1 §dispensation-conditions",
        evidence_refs=["corpus:incident-1"],
    )
    retro = store.proposal(d["retroactive_proposal_id"])
    assert retro["kind"] == "correction"
    assert retro["contradicted_ref"] == "Intellect v1 §dispensation-conditions"
    store.close_dispensation(d["dispensation_id"])
    with pytest.raises(ReversionError):
        store.close_dispensation(d["dispensation_id"])  # already closed
    # Its own audit event type, never folded into ordinary reversion (Art. 31):
    from seira_core.paths import audit_log_path
    events = [json.loads(l) for l in audit_log_path().read_text().splitlines()]
    assert any(e["event"] == "dispensation_invoked" for e in events)


def test_tampered_reversion_chain_halts(store):
    _open_est(store)
    lines = reversion_events_path().read_text().splitlines()
    rec = json.loads(lines[0])
    rec["content"] = "rewritten case"
    lines[0] = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    reversion_events_path().write_text("\n".join(lines) + "\n")
    with pytest.raises(ReversionIntegrityError):
        store.verify_chain()
    assert run_tripwire()["halted"] is True


def test_health_indicators(store):
    PsycheStore().add_entry("logos", "rival", {"type": "efficient", "ref": "j"}, ["p"])
    a, b = _open_est(store, "psy-00001"), _open_est(store, "psy-00002")
    store.record_attempt(a["proposal_id"], "m", ["c"], "survived")
    store.record_attempt(b["proposal_id"], "m", ["c"], "survived")
    store.suspend_pair(a["proposal_id"], b["proposal_id"])
    e = store.open_proposal("intellect", "expansion", "y", ORIGIN, ["e"])
    store.mark_stale(e["proposal_id"])
    store.invoke_dispensation("act", "Intellect v1 §c", ["ev"])
    h = store.health()
    assert h["suspended_contradictions"]["count"] == 1
    assert h["stale_proposals"] == 1
    assert h["dispensations"] == {"total": 1, "open": 1}
    assert h["open_proposals"] == 1  # the auto-generated retroactive proposal
