import json
import importlib
import pytest


@pytest.fixture
def tool(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    import cron.jobs as J
    importlib.reload(J)
    from seira_bridge import cron_tool
    return cron_tool


def call(t, **a):
    return json.loads(t.handle(a))


def test_create_list_pause_resume_delete(tool):
    r = call(tool, action="create", schedule="every 1h", prompt="Check the weather", name="w")
    assert r["ok"], r
    jid = r["job"]["id"]
    assert call(tool, action="list")["jobs"][0]["id"] == jid
    assert call(tool, action="pause", job_id=jid)["ok"]
    assert call(tool, action="resume", job_id=jid)["ok"]
    assert call(tool, action="output", job_id=jid)["output"] is None
    assert call(tool, action="delete", job_id=jid)["ok"]
    assert call(tool, action="list")["jobs"] == []


def test_min_interval_and_cap(tool):
    r = call(tool, action="create", schedule="every 5m", prompt="x")
    assert not r["ok"] and "at least" in r["error"]
    for i in range(tool.MAX_ACTIVE_JOBS):
        assert call(tool, action="create", schedule="every 1h", prompt=f"p{i}")["ok"]
    assert not call(tool, action="create", schedule="every 1h", prompt="more")["ok"]


def test_errors_never_blank(tool):
    assert not call(tool, action="create")["ok"]
    assert not call(tool, action="pause")["ok"]
    assert not call(tool, action="pause", job_id="nope")["ok"]
    assert not call(tool, action="bogus", job_id="x")["ok"]


def test_delegation_disabled_for_cron():
    from cron.scheduler import _resolve_cron_disabled_toolsets
    assert "delegation" in _resolve_cron_disabled_toolsets({})
