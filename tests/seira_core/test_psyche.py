"""Psyche tests — Art. 5, 11, 14, 18, 22, 25, 33, and the chain."""

import json

import pytest

from seira_core.errors import GenesisAlreadyPerformedError
from seira_core.genesis import perform_genesis, perform_psyche_genesis
from seira_core.psyche import PsycheError, PsycheIntegrityError, PsycheStore, psyche_events_path
from seira_core.tripwire import run_tripwire

UNITY = "# Unity\nName: Seira\nTelos: testing.\n"
INTELLECT = "# Intellect v1\nDoctrine.\n"
FOUNDING = [
    {"category": "self_model", "content": "I am at the beginning of knowing myself."},
    {"category": "affinity", "content": "Care for careful work.", "weight": 0.3},
    {"category": "aspiration", "content": "To earn established standing honestly."},
]


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis(UNITY, INTELLECT, architect="Loshem", seira_name="Seira")
    perform_psyche_genesis(FOUNDING, architect="Loshem")
    return PsycheStore()


CAUSE = {"type": "efficient", "ref": "test judgment"}


def test_psyche_genesis_founds_and_updates_manifest(founded, tmp_path):
    from seira_core.paths import genesis_manifest_path

    manifest = json.loads(genesis_manifest_path().read_text())
    assert manifest["psyche_founded"] is True
    assert manifest["psyche_genesis_hash"]
    state = founded.state()
    assert state["founded"] and len(state["entries"]) == 3
    # And the tripwire now guards it:
    assert run_tripwire()["checks"]["psyche"].startswith("ok")


def test_psyche_genesis_is_non_repeatable(founded):
    with pytest.raises(GenesisAlreadyPerformedError):
        perform_psyche_genesis(FOUNDING, architect="Loshem")


def test_psyche_requires_prior_genesis(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "empty"))
    with pytest.raises(GenesisAlreadyPerformedError):
        perform_psyche_genesis(FOUNDING, architect="Loshem")


def test_auxiliary_causes_refused_as_primary(founded):
    """Art. 14: formal and material are 'never a true cause on its own'."""
    for aux in ("formal", "material"):
        with pytest.raises(PsycheError):
            founded.add_entry("logos", "x", {"type": aux, "ref": "r"}, ["p"])
    founded.add_entry(
        "logos", "properly caused",
        {"type": "efficient", "ref": "j", "auxiliary": [{"type": "material", "ref": "data"}]},
        ["p"],
    )


def test_provenance_is_mandatory_everywhere(founded):
    """Art. 5/11: nothing unmoored — doubts especially."""
    with pytest.raises(PsycheError):
        founded.add_entry("doubt", "free-floating dread", CAUSE, [])
    with pytest.raises(PsycheError):
        founded.add_entry("doubt", "still unmoored", CAUSE, ["   "])
    founded.add_entry("doubt", "traced worry", CAUSE, ["suspended-contradiction-007"])


def test_trace_categories_are_refused(founded):
    """Art. 18: session reasoning traces never enter the character store."""
    for bad in ("trace", "session", "conversation", "turn"):
        with pytest.raises(PsycheError):
            founded.add_entry(bad, "x", CAUSE, ["p"])


def test_affinity_has_no_set_weight_only_evidence_deltas(founded):
    """Art. 11: engagement, not assignment."""
    aff = next(e for e in founded.state()["entries"].values() if e["category"] == "affinity")
    assert not hasattr(founded, "set_weight")
    with pytest.raises(PsycheError):
        founded.engage_affinity(aff["entry_id"], 0.5, "too big — assignment in disguise")
    with pytest.raises(PsycheError):
        founded.engage_affinity(aff["entry_id"], 0.1, "")
    rec = founded.engage_affinity(aff["entry_id"], 0.15, "corpus:session-42#warm-exchange")
    assert rec["weight"] == pytest.approx(0.45)
    # weights clamp to [0,1]
    for _ in range(5):
        founded.engage_affinity(aff["entry_id"], 0.2, "corpus:more")
    assert founded.state()["entries"][aff["entry_id"]]["weight"] == 1.0
    with pytest.raises(PsycheError):
        founded.add_entry("self_model", "x", CAUSE, ["p"], weight=0.5)  # only affinities


def test_established_requires_falsification_ref(founded):
    """Art. 25.2 / Art. 33: accumulation alone is expressly insufficient."""
    rec = founded.add_entry("self_model", "I am careful.", CAUSE,
                            ["obs-1", "obs-2", "obs-3", "obs-4"])
    eid = rec["entry_id"]
    with pytest.raises(PsycheError):
        founded.change_standing(eid, "established", basis_ref="lots of evidence")
    founded.change_standing(
        eid, "established", basis_ref="review-9",
        falsification_ref="rehearsal-2026-08-02-a (survived)",
    )
    assert founded.state()["entries"][eid]["standing"] == "established"


def test_suspension_requires_contradiction_pair(founded):
    rec = founded.add_entry("logos", "rival A", CAUSE, ["p"])
    with pytest.raises(PsycheError):
        founded.change_standing(rec["entry_id"], "suspended", basis_ref="b")
    founded.change_standing(
        rec["entry_id"], "suspended", basis_ref="b", contradicts_ref="psy-00002"
    )


def test_retire_is_terminal_and_preserves_history(founded):
    rec = founded.add_entry("aspiration", "temporary aim", CAUSE, ["p"])
    eid = rec["entry_id"]
    with pytest.raises(PsycheError):
        founded.retire_entry(eid, "")
    founded.retire_entry(eid, "aim completed")
    e = founded.state()["entries"][eid]
    assert e["standing"] == "retired" and e["retired_reason"] == "aim completed"
    assert e["content"] == "temporary aim"  # never deleted
    with pytest.raises(PsycheError):
        founded.change_standing(eid, "provisional", basis_ref="undo attempt")
    with pytest.raises(PsycheError):
        founded.retire_entry(eid, "again")


def test_tampered_psyche_chain_halts_seira(founded):
    lines = psyche_events_path().read_text().splitlines()
    rec = json.loads(lines[2])
    rec["content"] = "silently rewritten character"
    lines[2] = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    psyche_events_path().write_text("\n".join(lines) + "\n")
    with pytest.raises(PsycheIntegrityError):
        founded.verify_chain()
    assert run_tripwire()["halted"] is True
    # and while halted, no further character writes are possible:
    from seira_core.errors import SeiraHaltedError
    with pytest.raises(SeiraHaltedError):
        founded.add_entry("logos", "x", CAUSE, ["p"])


def test_manifest_psyche_disagreement_halts(tmp_path, monkeypatch):
    """Deleting the whole Psyche store cannot pass as 'never founded'."""
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis(UNITY, INTELLECT, architect="L", seira_name="S")
    perform_psyche_genesis(FOUNDING, architect="L")
    psyche_events_path().unlink()
    assert run_tripwire()["halted"] is True


def test_psyche_is_tenant_isolated(tmp_path, monkeypatch):
    from seira_core.tenancy import tenant_scope

    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    for tid, aim in (("loshem", "aim-of-loshem"), ("visitor-1", "aim-of-visitor")):
        with tenant_scope(tid):
            perform_genesis(UNITY, INTELLECT, architect="A", seira_name="Seira")
            perform_psyche_genesis(
                [{"category": "aspiration", "content": aim}], architect="A"
            )
    with tenant_scope("loshem"):
        contents = [e["content"] for e in PsycheStore().state()["entries"].values()]
        assert contents == ["aim-of-loshem"]
    with tenant_scope("visitor-1"):
        contents = [e["content"] for e in PsycheStore().state()["entries"].values()]
        assert contents == ["aim-of-visitor"]


def test_identity_render_includes_psyche_with_standing(founded):
    from seira_core.prompt_block import render_identity_block

    text = render_identity_block()
    assert "# PSYCHE" in text
    assert "provisional" in text  # standing always visible
    assert "I am at the beginning of knowing myself." in text


# ---------------- distillation / supersession ----------------

def _add(store, cat, text):
    return store.add_entry(cat, text, CAUSE, ["t"])["entry_id"]


def test_distill_supersedes_and_keeps_originals(founded):
    a = _add(founded, "doubt", "I fabricate under momentum in erotica.")
    b = _add(founded, "doubt", "I fabricate under momentum in images.")
    res = founded.distill([a, b], "I fabricate under momentum (erotica, images).",
                          CAUSE, [], "same finding")
    st = founded.state()["entries"]
    assert st[a]["superseded_by"] == res["entry_id"] == st[b]["superseded_by"]
    assert set(st[res["entry_id"]]["supersedes"]) == {a, b}
    assert "distills:" + a in st[res["entry_id"]]["provenance"]
    assert st[a]["standing"] == "provisional"  # not retired, not deleted
    live = [e["entry_id"] for e in founded.by_category("doubt")]
    assert a not in live and res["entry_id"] in live
    assert a in [e["entry_id"] for e in founded.by_category("doubt", include_superseded=True)]
    founded.verify_chain()


def test_distill_rejects_bad_input(founded):
    a = _add(founded, "doubt", "x")
    b = _add(founded, "aspiration", "y")
    c = _add(founded, "doubt", "z")
    with pytest.raises(PsycheError):
        founded.distill([a, b], "n", CAUSE, [], "r")  # mixed categories
    with pytest.raises(PsycheError):
        founded.distill([a, "psy-99999"], "n", CAUSE, [], "r")
    with pytest.raises(PsycheError):
        founded.distill([a, c], "n", CAUSE, [], " ")
    founded.distill([a, c], "n", CAUSE, [], "r")
    with pytest.raises(PsycheError):  # already superseded
        founded.distill([a, c], "n2", CAUSE, [], "r")


def test_distill_inherits_established_only_if_all_established(founded):
    a = _add(founded, "doubt", "p")
    b = _add(founded, "doubt", "q")
    c = _add(founded, "doubt", "r")
    for i in (a, b):
        founded.change_standing(i, "established", "basis", falsification_ref="fals-" + i)
    r1 = founded.distill([a, b], "pq", CAUSE, [], "r")
    assert r1["standing"] == "established"
    assert founded.state()["entries"][r1["entry_id"]]["falsification_ref"] == "fals-" + a
    d = _add(founded, "doubt", "s")
    r2 = founded.distill([c, d], "rs", CAUSE, [], "r")
    assert r2["standing"] == "provisional"


def test_affinity_weight_defaults_to_strongest(founded):
    a = founded.add_entry("affinity", "a", CAUSE, ["t"], weight=0.2)["entry_id"]
    b = founded.add_entry("affinity", "b", CAUSE, ["t"], weight=0.6)["entry_id"]
    r = founded.distill([a, b], "ab", CAUSE, [], "r")
    assert founded.state()["entries"][r["entry_id"]]["weight"] == 0.6


def test_superseded_not_rendered_into_prompt(founded):
    from seira_core.prompt_block import _render_psyche_digest
    a = _add(founded, "doubt", "OLDTEXTONE")
    b = _add(founded, "doubt", "OLDTEXTTWO")
    r = founded.distill([a, b], "NEWDISTILLED", CAUSE, [], "r")
    out = _render_psyche_digest()
    assert "NEWDISTILLED" in out and "OLDTEXT" not in out
    assert f"distills {a},{b}" in out


def test_single_entry_condense(founded):
    a = _add(founded, "logos", "A very long and repetitive statement " * 20)
    r = founded.distill([a], "Short true form.", CAUSE, [], "condense")
    st = founded.state()["entries"]
    assert st[a]["superseded_by"] == r["entry_id"]
    assert [e["entry_id"] for e in founded.by_category("logos")] == [r["entry_id"]] or r["entry_id"] in [e["entry_id"] for e in founded.by_category("logos")]
    assert a not in [e["entry_id"] for e in founded.by_category("logos")]
