"""Proof that the SEIRA_TENANT env-var race is actually fixed, not just
removed and hoped for. Two 'requests' for two different tenants run on
real overlapping OS threads — the exact shape of two concurrent SSE
chat requests — and each must see only its own tenant's data.

Before the fix: os.environ["SEIRA_TENANT"] was process-global, so a
thread reading it inside a provider call could observe a DIFFERENT
thread's tenant id if the two overlapped, silently resolving image/
reference/file paths against the wrong tenant. This test reproduces
that overlap deliberately (via a barrier forcing both threads through
the danger window at the same moment) and asserts no cross-talk.
"""

import sys
import threading
from pathlib import Path

import pytest

for c in [Path(__file__).resolve().parents[2], Path("/home/claude/repo/hermes-agent-main")]:
    if (c / "agent" / "memory_provider.py").exists():
        sys.path.insert(0, str(c))
        break
pytest.importorskip("agent.memory_provider")

from seira_core.genesis import perform_genesis, perform_psyche_genesis  # noqa: E402
from seira_core.tenancy import tenant_scope  # noqa: E402
from seira_web import images  # noqa: E402
from seira_bridge import SeiraPsycheProvider  # noqa: E402


@pytest.fixture()
def two_tenants(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    for tid, telos in (("loshem", "aim-of-loshem"), ("visitor-1", "aim-of-visitor")):
        with tenant_scope(tid):
            perform_genesis(f"# Unity\nName: Seira\nTelos: {telos}\n", "# I1\n",
                            architect="A", seira_name="Seira")
            perform_psyche_genesis(
                [{"category": "self_model", "content": f"I belong to {tid}."}],
                architect="A")
            images.save_image(f"{tid}.png", "image/png", f"{tid}-bytes".encode(),
                              tag=f"{tid}-photo")
    return None


def test_concurrent_requests_never_cross_tenants(two_tenants):
    barrier = threading.Barrier(2)
    results = {}
    errors = []

    def request_for(tenant_id: str):
        try:
            with tenant_scope(tenant_id):
                provider = SeiraPsycheProvider()
                barrier.wait()  # force both threads into the danger window together
                # This is exactly what run_turn does: call provider methods
                # while a DIFFERENT thread is doing the same for another tenant.
                system = provider.system_prompt_block()
                image_list = provider.handle_tool_call("seira_image_list", {})
                results[tenant_id] = (system, image_list)
        except Exception as e:
            errors.append((tenant_id, e))

    t1 = threading.Thread(target=request_for, args=("loshem",))
    t2 = threading.Thread(target=request_for, args=("visitor-1",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"unexpected errors: {errors}"
    loshem_system, loshem_images = results["loshem"]
    visitor_system, visitor_images = results["visitor-1"]

    # Each thread's identity render must show ONLY its own tenant's data.
    assert "aim-of-loshem" in loshem_system and "aim-of-visitor" not in loshem_system
    assert "aim-of-visitor" in visitor_system and "aim-of-loshem" not in visitor_system
    assert "loshem-photo" in loshem_images and "visitor-1-photo" not in loshem_images
    assert "visitor-1-photo" in visitor_images and "loshem-photo" not in visitor_images


def test_env_var_fallback_still_works_when_no_ambient_scope(tmp_path, monkeypatch):
    """The env-var path is preserved for non-web integrations (the full
    Hermes runtime) that have no surrounding tenant_scope() of their
    own — it's only skipped when an ambient scope already exists."""
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    with tenant_scope("standalone-tenant"):
        perform_genesis("# Unity\nName: Seira\nTelos: standalone.\n", "# I1\n",
                        architect="A", seira_name="Seira")
        perform_psyche_genesis(
            [{"category": "self_model", "content": "standalone entry"}], architect="A")
    monkeypatch.setenv("SEIRA_TENANT", "standalone-tenant")
    provider = SeiraPsycheProvider()
    # No ambient tenant_scope() active here — must fall back to the env var.
    system = provider.system_prompt_block()
    assert "standalone." in system


def test_tenant_scope_active_reflects_reality(tmp_path, monkeypatch):
    from seira_core.tenancy import tenant_scope_active
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    assert tenant_scope_active() is False
    with tenant_scope("someone"):
        assert tenant_scope_active() is True
    assert tenant_scope_active() is False
