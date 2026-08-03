"""Phase 5b tests — live delegation bound to the Instruments.

Art. 5 (trace or noise), Art. 26 (auto-escalation through the hook),
Art. 35 (the gate), Art. 36 (retired refusal).
"""

import json

import pytest

from seira_core.genesis import perform_genesis, perform_psyche_genesis
from seira_core.instruments import InstrumentStore
from seira_core.paths import audit_log_path
from seira_bridge.delegation import (
    check_delegation_args,
    delegation_gate_middleware,
    observe_delegation,
    parse_tag,
)


@pytest.fixture()
def founded(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    perform_genesis("# Unity\nName: Seira\n", "# I1\n",
                    architect="Loshem", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "logos", "content": "Delegated work is still my work."}],
        architect="Loshem",
    )
    store = InstrumentStore()
    store.spawn("translator", "Translate preserving argument.", "psy-00001")
    return store


def _audit_events():
    return [json.loads(l) for l in audit_log_path().read_text().splitlines()]


def test_tag_parsing():
    assert parse_tag("[seira:inst-00001/stobaeus-excerpt] do X") == \
        ("inst-00001", "stobaeus-excerpt")
    assert parse_tag("prefix [seira:inst-00002/t_1] suffix") == ("inst-00002", "t_1")
    assert parse_tag("no tag here") is None
    assert parse_tag("[seira:inst-1/t]") is None  # malformed id refused


def test_observed_delegation_becomes_execution(founded):
    out = observe_delegation(
        "[seira:inst-00001/excerpt] Translate Stobaeus I.21.7",
        "Here is the translation ...", child_session_id="sess-9",
    )
    assert out == {"recorded": True, "seq": out["seq"], "outcome": "clean"}
    execs = [r for r in founded._read_raw() if r["event"] == "execution_recorded"]
    assert execs[-1]["output_ref"] == "delegation:sess-9"
    assert execs[-1]["derivation"]["paradigm_version"] == 1


def test_untagged_delegation_is_noise_not_an_act(founded):
    out = observe_delegation("summarize this thing", "done", child_session_id="s")
    assert out == {"recorded": False, "reason": "untraced"}
    assert not any(r["event"] == "execution_recorded" for r in founded._read_raw())
    assert _audit_events()[-1]["event"] == "untraced_delegation"


def test_empty_results_escalate_through_the_hook(founded):
    """Three delegations that never terminated in rest → Art. 26 fires
    with no new logic, straight from the observation hook."""
    for i in range(2):
        out = observe_delegation("[seira:inst-00001/summarize] go", "", f"s{i}")
        assert out["outcome"] == "local_feedback" and "escalated" not in out
    out = observe_delegation("[seira:inst-00001/summarize] go", "   ", "s2")
    assert "escalated" in out
    assert founded.is_blocked("inst-00001", "summarize")
    # Further observations of the blocked task-type are refused but audited:
    out = observe_delegation("[seira:inst-00001/summarize] go", "late result", "s3")
    assert out["recorded"] is False
    assert _audit_events()[-1]["event"] == "delegation_observation_refused"


def test_observation_never_raises(founded, monkeypatch):
    """The hook runs inside the parent's turn; it must fail silent-but-audited."""
    monkeypatch.setattr(
        "seira_core.instruments.InstrumentStore.record_execution",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk gone")),
    )
    out = observe_delegation("[seira:inst-00001/x] go", "r", "s")
    assert out["recorded"] is False and "internal" in out["reason"]


# ---------------- the gate (Art. 35) ----------------

def _gate(args, called):
    def next_call(a):
        called.append(a)
        return "SPAWNED"
    return delegation_gate_middleware(
        tool_name="delegate_task", args=args, next_call=next_call
    )


def test_gate_passes_valid_tagged_delegations(founded):
    called = []
    result = _gate({
        "goal": "[seira:inst-00001/excerpt] Translate the passage",
        "tasks": [{"goal": "[seira:inst-00001/excerpt] And this one"}],
    }, called)
    assert result == "SPAWNED" and len(called) == 1


def test_gate_refuses_untagged(founded):
    called = []
    result = json.loads(_gate({"goal": "just do the thing"}, called))
    assert result["ok"] is False and "Art. 5, 35" in result["reason"]
    assert called == []  # the subagent was never created
    assert _audit_events()[-1]["event"] == "delegation_refused"


def test_gate_refuses_unknown_retired_and_blocked(founded):
    called = []
    r = json.loads(_gate({"goal": "[seira:inst-09999/t] x"}, called))
    assert "does not exist" in r["reason"]

    founded.spawn("temp", "p", "psy-00001")
    founded.retire("inst-00002", "done with this")
    r = json.loads(_gate({"goal": "[seira:inst-00002/t] x"}, called))
    assert "retired" in r["reason"]

    for i in range(3):
        founded.record_execution("inst-00001", "stuck", "local_feedback", f"c:{i}")
    r = json.loads(_gate({"goal": "[seira:inst-00001/stuck] once more"}, called))
    assert "Art. 26" in r["reason"]
    assert called == []


def test_gate_refuses_if_any_task_in_batch_fails(founded):
    """One untagged task poisons the whole batch: partial procession is
    still an ungoverned spawn."""
    called = []
    r = json.loads(_gate({
        "goal": "[seira:inst-00001/excerpt] fine",
        "tasks": [{"goal": "sneaky untagged side quest"}],
    }, called))
    assert r["ok"] is False and called == []


def test_gate_ignores_other_tools(founded):
    called = []
    result = delegation_gate_middleware(
        tool_name="terminal", args={"cmd": "ls"},
        next_call=lambda a: called.append(a) or "RAN",
    )
    assert result == "RAN" and called == [{"cmd": "ls"}]


def test_provider_hook_end_to_end(founded):
    """Through the actual MemoryProvider hook, tenant-scoping path included."""
    import sys
    from pathlib import Path
    for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
        if (c / "agent" / "memory_provider.py").exists():
            sys.path.insert(0, str(c))
            break
    pytest.importorskip("agent.memory_provider")
    from seira_bridge import SeiraPsycheProvider

    SeiraPsycheProvider().on_delegation(
        "[seira:inst-00001/excerpt] via provider", "result text",
        child_session_id="sess-x",
    )
    execs = [r for r in founded._read_raw() if r["event"] == "execution_recorded"]
    assert execs[-1]["output_ref"] == "delegation:sess-x"
