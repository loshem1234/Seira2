"""Tests for seira_web.distillation — her weekly Psyche Distillation."""
import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2]]:
    sys.path.insert(0, str(c))

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402
from seira_core.psyche import PsycheStore  # noqa: E402
from seira_web import distillation as D  # noqa: E402

CAUSE = {"type": "efficient", "ref": "t"}


class _Null:
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    perform_genesis("# Unity\nName: Seira\n", "# Intellect v1\nD.\n", architect="L", seira_name="Seira")
    perform_psyche_genesis([{"category": "self_model", "content": "I begin."}], architect="L")
    monkeypatch.setattr("seira_core.tenancy.tenant_scope", lambda t: _Null())
    with D._lock:
        D._state.clear()
    return PsycheStore()


def _add(s, cat, text):
    return s.add_entry(cat, text, CAUSE, ["t"])["entry_id"]


def test_longest_ranks_and_kept_excluded(founded):
    a = _add(founded, "logos", "word " * 200)
    b = _add(founded, "logos", "word " * 20)
    rows = D.longest_entries(10)
    assert rows[0]["entry_id"] == a and rows[0]["tokens"] > rows[-1]["tokens"]
    D._add_kept([{"entry_id": a, "reason": "ancestry"}])
    assert a not in [r["entry_id"] for r in D.longest_entries(10)]
    assert a in [r["entry_id"] for r in D.longest_entries(10, include_kept=True)]


def test_conclude_floor_and_summary_required(founded):
    with pytest.raises(ValueError):
        D.request_conclude("t1", "x")           # no session
    D._start("t1")
    with pytest.raises(ValueError):
        D.request_conclude("t1", "x")           # below floor
    D._state["t1"]["turn_count"] = D.MIN_TURNS
    with pytest.raises(ValueError):
        D.request_conclude("t1", "  ")          # needs summary
    D.request_conclude("t1", "did things", [{"entry_id": "psy-1", "reason": "r"}])
    assert D._state["t1"]["conclude"]["summary"] == "did things"


def test_is_due_first_run_then_weekly_and_only_if_new(founded):
    assert D.is_due()                           # first run, has entries
    D._append_log({"kind": "run", "finished_at": D._now_iso()})
    assert not D.is_due()                       # too recent
    old = (D._now() - D._dt.timedelta(days=8)).isoformat()
    D._log_path().write_text("")
    D._append_log({"kind": "run", "finished_at": old})
    # entries exist from before 'old'? they were created just now (> old) -> due
    assert D.is_due()
    D._log_path().write_text("")
    future = (D._now() + D._dt.timedelta(days=-8)).isoformat()
    D._append_log({"kind": "run", "finished_at": D._now_iso()})
    assert not D.is_due()


def _fake_turns(monkeypatch, store, conclude_at=3, error_at=None):
    calls = {"n": 0}

    def fake(prompt, tenant_id, history=None, emit=None):
        calls["n"] += 1
        n = calls["n"]
        if error_at and n == error_at:
            return {"reply": "boom", "messages": [], "errored": True}
        if n == 1:   # she condenses two entries
            ids = [e["entry_id"] for e in store.state()["entries"].values()
                   if e["category"] == "logos"][:2]
            store.distill(ids, "Dense.", CAUSE, [], "merge")
        if n == conclude_at:
            D.request_conclude(tenant_id, "merged two; kept psy-1",
                               [{"entry_id": "psy-00001", "reason": "ancestry"}])
        return {"reply": "ok", "messages": [{"role": "assistant", "content": "ok"}], "errored": False}

    monkeypatch.setattr("seira_web.hermes_session.run_housekeeping_turn", fake)
    return calls


def test_full_run_logs_measured_before_after_and_kept(founded, monkeypatch):
    _add(founded, "logos", "word " * 300)
    _add(founded, "logos", "word " * 300)
    calls = _fake_turns(monkeypatch, founded, conclude_at=3)
    rec = D.run_for_tenant("t1", manual=True)
    assert rec["outcome"] == "concluded" and rec["turns"] == 3
    assert rec["tokens_after"] < rec["tokens_before"]
    assert D.kept_as_is() == {"psy-00001": "ancestry"}
    assert D.last_run()["summary"].startswith("merged")
    assert not D.is_session_active("t1")


def test_errored_turn_stops_the_run(founded, monkeypatch):
    _add(founded, "logos", "word " * 50)
    calls = _fake_turns(monkeypatch, founded, conclude_at=99, error_at=2)
    rec = D.run_for_tenant("t1", manual=True)
    assert rec["outcome"] == "error" and calls["n"] == 2


def test_ceiling_stops_even_if_never_concluded(founded, monkeypatch):
    _add(founded, "logos", "word " * 50)
    calls = _fake_turns(monkeypatch, founded, conclude_at=999)
    rec = D.run_for_tenant("t1", manual=True)
    assert rec["outcome"] == "ceiling" and rec["turns"] == D.MAX_TURNS


def test_not_due_means_no_turns(founded, monkeypatch):
    _add(founded, "logos", "word " * 50)
    D._append_log({"kind": "run", "finished_at": D._now_iso()})
    calls = _fake_turns(monkeypatch, founded)
    assert D.run_for_tenant("t1") is None and calls["n"] == 0


def test_prompt_contains_her_guidelines_and_final_call(founded):
    p = D.build_prompt()
    assert "Recall first" in p and "genealogy exception" in p.lower()
    assert "final call" in p and "Supersede, never delete" in p


def test_status_shape(founded):
    s = D.status("t1")
    assert {"psyche", "running", "last_run", "due", "kept_as_is_count"} <= set(s)
