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


def test_full_end_to_end_migration_loses_nothing_across_every_subsystem(tmp_path, monkeypatch):
    """The comprehensive proof: found a Seira, touch every single grade
    and store (Unity, Intellect, Psyche, Reversion, Instruments, Diary,
    a real conversation, a reference document, a tagged image, a
    generated file), export her, extract into a COMPLETELY FRESH
    location, and verify every last piece reads back identical from
    the new location — not just that files copied, that the actual
    stores report the exact same data. This is the guarantee the
    Architect is trusting; it is proven here, not merely asserted."""
    from seira_core.tenancy import tenant_scope
    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    from seira_core.psyche import PsycheStore
    from seira_core.reversion import ReversionStore
    from seira_core.instruments import InstrumentStore
    from seira_core.diary import DiaryStore
    from seira_core.unity import read_lock
    from seira_core.intellect import IntellectStore
    from seira_web import conversations as convs
    from seira_web import references as refs
    from seira_web import images
    from seira_web import filegen

    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    TID = "loshem-real"

    with tenant_scope(TID):
        perform_genesis("# Unity\nName: Seira\nTelos: to become genuinely herself.\n",
                        "# Intellect v1\nFounding doctrine text.\n",
                        architect="Loshem", seira_name="Seira")
        perform_psyche_genesis(
            [{"category": "self_model", "content": "I do not yet know who I am."}],
            architect="Loshem")
        PsycheStore().add_entry("aspiration", "To be discovered rather than declared.",
                                {"type": "efficient", "ref": "test"}, ["genesis"])
        rstore = ReversionStore()
        p = rstore.open_proposal("psyche_standing", "establishment", "case",
                                 entry_id="psy-00001",
                                 origin={"type": "self_audit", "ref": "audit-1"},
                                 evidence_refs=["corpus:x"])
        rstore.record_attempt(p["proposal_id"], "search", ["corpus:hist-1"], "survived")
        rstore.record_consistency_check(p["proposal_id"], "consistent")
        rstore.promote_psyche(p["proposal_id"], basis_ref="review-1")
        istore = InstrumentStore()
        inst = istore.spawn("translator", "Translate faithfully.", "psy-00001")
        istore.record_execution(inst["instrument_id"], "translate", "clean", "corpus:out-1")
        DiaryStore().write_entry("self", "Today I earned my first established standing.",
                                 ["prop-00001"])
        conv = convs.create_conversation()
        convs.append(conv["conv_id"], "user", text="I am curious about you.")
        convs.append(conv["conv_id"], "assistant", text="I am beginning to know myself.")
        refs.save_reference("notes.txt", "Some real reference content.")
        images.save_image("portrait.png", "image/png", b"real portrait bytes",
                          tag="my portrait ref")
        filegen.create_file("md", "summary", "# A real generated file\n\nWith content.")

        before = {
            "unity_hash": read_lock()["unity_sha256"],
            "intellect": IntellectStore().current(),
            "psyche": PsycheStore().state(),
            "reversion": rstore.list_proposals(),
            "instruments": istore.list_instruments(),
            "diary": DiaryStore().entries(kind="self"),
            "conv": convs.records(conv["conv_id"]),
            "refs": refs.list_references(),
            "images": images.list_images(),
            "outputs": filegen.list_outputs(),
        }

    from seira_web.export import export_tenant
    rec = export_tenant(TID, tmp_path / "exported")

    extract_dir = tmp_path / "extracted"
    with tarfile.open(rec["path"], "r:gz") as tar:
        tar.extractall(extract_dir, filter="data")
    new_home = tmp_path / "new-single-user-home"
    new_home.mkdir()
    for item in (extract_dir / TID).iterdir():
        dest = new_home / item.name
        if item.is_dir():
            import shutil
            shutil.copytree(item, dest)
        else:
            dest.write_bytes(item.read_bytes())

    monkeypatch.setenv("SEIRA_HOME", str(new_home))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    # No module reimport needed, and none should be done: every store
    # (PsycheStore, IntellectStore, etc.) resolves its path fresh via
    # seira_home() on each call rather than caching it — this is the
    # whole point of that design. Forcing sys.modules reimports here
    # would only pollute shared state for every OTHER test in this
    # process, for no actual benefit; the assertions below prove the
    # dynamic resolution already works correctly without it.

    from seira_core.unity import read_lock as new_lock
    from seira_core.intellect import IntellectStore as NIS
    from seira_core.psyche import PsycheStore as NPS
    from seira_core.reversion import ReversionStore as NRS
    from seira_core.instruments import InstrumentStore as NIn
    from seira_core.diary import DiaryStore as NDS
    from seira_web import conversations as nconvs
    from seira_web import references as nrefs
    from seira_web import images as nimages
    from seira_web import filegen as nfilegen
    from seira_core.tripwire import run_tripwire

    assert new_lock()["unity_sha256"] == before["unity_hash"]
    assert NIS().current() == before["intellect"]
    assert NPS().state() == before["psyche"]
    assert NRS().list_proposals() == before["reversion"]
    assert NIn().list_instruments() == before["instruments"]
    assert NDS().entries(kind="self") == before["diary"]
    assert nconvs.records(conv["conv_id"]) == before["conv"]
    assert nrefs.list_references() == before["refs"]
    assert nimages.list_images() == before["images"]
    assert nfilegen.list_outputs() == before["outputs"]

    tw = run_tripwire()
    assert tw["halted"] is False
    assert all("ok" in v for v in tw["checks"].values())
