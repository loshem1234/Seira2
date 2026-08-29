"""Export tests. The single most important property: a tenant's export
can NEVER contain another tenant's data, and the route has no input
that could be tampered with to request someone else's export."""

import tarfile
from pathlib import Path

import pytest

from seira_core.genesis import perform_genesis
from seira_core.tenancy import tenant_scope
from seira_web.export import ExportError, export_tenant


@pytest.fixture()
def two_tenants(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    for tid, telos in (("loshem", "aim-of-loshem"), ("visitor-1", "aim-of-visitor")):
        with tenant_scope(tid):
            perform_genesis(f"# Unity\nName: Seira\nTelos: {telos}\n", "# I1\n",
                            architect="A", seira_name="Seira")
    return tmp_path


def test_export_contains_only_that_tenants_data(two_tenants, tmp_path):
    rec = export_tenant("loshem", tmp_path / "out")
    with tarfile.open(rec["path"], "r:gz") as tar:
        content = b"".join(
            tar.extractfile(m).read() for m in tar.getmembers()
            if m.isfile() and "UNITY.md" in m.name
        )
    assert b"aim-of-loshem" in content
    assert b"aim-of-visitor" not in content  # the actual isolation guarantee


def test_export_archive_is_named_and_rooted_by_tenant(two_tenants, tmp_path):
    rec = export_tenant("loshem", tmp_path / "out")
    with tarfile.open(rec["path"], "r:gz") as tar:
        names = tar.getnames()
    assert all(n == "loshem" or n.startswith("loshem/") for n in names)


def test_export_refuses_a_tenant_with_no_data(two_tenants, tmp_path):
    with pytest.raises(ExportError, match="no data"):
        export_tenant("never-founded", tmp_path / "out")


def test_export_refuses_malformed_tenant_id(two_tenants, tmp_path):
    from seira_core.tenancy import TenantError
    with pytest.raises(TenantError):
        export_tenant("../../etc", tmp_path / "out")


def test_app_route_has_no_tenant_id_parameter_at_all():
    """Structural guarantee: grep the route for any way a tenant_id
    could be supplied by the request rather than derived from the
    session. This is what actually prevents 'export someone else's
    Seira' — not a runtime check, an absent code path."""
    import inspect
    from seira_web import app as app_module
    src = inspect.getsource(app_module)
    start = src.index('@app.get("/api/export")')
    end = src.index("\n    @app.", start + 1)
    route_src = src[start:end]
    assert 'account["tenant_id"]' in route_src
    assert "request.query_params" not in route_src
    assert "tenant_id:" not in route_src  # no path/query param named tenant_id


def test_app_level_export_downloads_only_the_caller_own_data(tmp_path, monkeypatch):
    import sys
    for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
        if (c / "agent" / "memory_provider.py").exists():
            sys.path.insert(0, str(c))
            break
    pytest.importorskip("agent.memory_provider")
    pytest.importorskip("fastapi")

    monkeypatch.setenv("SEIRA_PLATFORM_ROOT", str(tmp_path / "platform"))
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)

    from fastapi.testclient import TestClient
    from seira_web.app import create_app

    app = create_app(llm_client_factory=lambda model=None: None)
    c1 = TestClient(app, follow_redirects=False)
    c1.post("/signup", data={"email": "one@example.com", "password": "long-enough-password"})
    c1.post("/onboard", data={"telos": "telos-of-account-one",
                              "relation": "r", "self_model": "s"})

    c2 = TestClient(app, follow_redirects=False)
    c2.post("/signup", data={"email": "two@example.com", "password": "long-enough-password"})
    c2.post("/onboard", data={"telos": "telos-of-account-two",
                              "relation": "r", "self_model": "s"})

    r = c1.get("/api/export")
    assert r.status_code == 200
    tmp_tar = tmp_path / "downloaded.tar.gz"
    tmp_tar.write_bytes(r.content)
    with tarfile.open(tmp_tar, "r:gz") as tar:
        content = b"".join(
            tar.extractfile(m).read() for m in tar.getmembers()
            if m.isfile() and "UNITY.md" in m.name
        )
    assert b"telos-of-account-one" in content
    assert b"telos-of-account-two" not in content
