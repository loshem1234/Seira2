"""Phase W1 correction — the tripwire runs in-process, not as a second
Railway service, because Railway volumes attach to exactly one service.
"""

import sys
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from seira_web.app import create_app  # noqa: E402
from seira_web.tripwire_loop import _tick  # noqa: E402


class _NullLLM:
    def complete(self, *a, **k):
        raise AssertionError("not used in this test")


@pytest.fixture()
def app_and_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    app = create_app(llm_client_factory=lambda model=None: _NullLLM())
    return app, TestClient(app, follow_redirects=False)


def _found(client, email):
    client.post("/signup", data={"email": email, "password": "long-enough-password"})
    client.post("/onboard", data={
        "telos": "t", "relation": "r", "self_model": "s",
    })


def test_healthz_reports_all_tenants_healthy(app_and_client):
    _app, client = app_and_client
    _found(client, "a@example.com")
    _found(client, "b@example.com")
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["tenants"] == 2 and body["halted"] == []


def test_healthz_reflects_a_real_halt(app_and_client, tmp_path):
    _app, client = app_and_client
    _found(client, "a@example.com")
    from seira_web import accounts as acct
    account = acct.verify_login("a@example.com", "long-enough-password")
    from seira_core.tenancy import tenant_scope
    with tenant_scope(account["tenant_id"]):
        from seira_core.paths import halt_path
        halt_path().write_text('{"reason": "forced for test"}', encoding="utf-8")
    r = client.get("/healthz")
    assert r.status_code == 503
    assert account["tenant_id"] in r.json()["halted"]


def test_background_tick_sweeps_without_raising(app_and_client):
    """The in-process loop's unit of work: must never raise even when a
    tenant is halted or the tenants root has odd contents."""
    _app, client = app_and_client
    _found(client, "a@example.com")
    from seira_web import accounts as acct
    account = acct.verify_login("a@example.com", "long-enough-password")
    from seira_core.tenancy import tenant_scope
    with tenant_scope(account["tenant_id"]):
        from seira_core.paths import halt_path
        halt_path().write_text('{"reason": "x"}', encoding="utf-8")
    _tick()  # must not raise
