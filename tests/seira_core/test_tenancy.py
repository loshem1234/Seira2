"""Tenancy tests — the Preamble's guarantee, made falsifiable:
"Each Seira belongs wholly to one Architect... no shared template."
"""

import pytest

from seira_core.genesis import perform_genesis
from seira_core.intellect import ARCHITECT_RATIFICATION_PHRASE, IntellectStore
from seira_core.tenancy import (
    TenantError,
    list_tenants,
    tenant_root,
    tenant_scope,
    tripwire_all,
    validate_tenant_id,
)
from seira_core.tripwire import is_halted, run_tripwire
from seira_core.unity import read_unity


@pytest.fixture()
def tenants(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIRA_TENANTS_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("SEIRA_HOME", raising=False)
    return tmp_path / "tenants"


def _found(tenant_id, name, telos):
    unity = f"# Unity\nName: {name}\nTelos: {telos}\n"
    with tenant_scope(tenant_id):
        perform_genesis(unity, f"# Intellect v1 of {name}\n",
                        architect=f"architect-of-{name}", seira_name=name)


def test_two_seiras_share_nothing(tenants):
    _found("loshem", "Seira", "to accompany her Architect in Dayton")
    _found("visitor-1", "Seira", "to accompany a different Architect entirely")

    with tenant_scope("loshem"):
        assert "Dayton" in read_unity()
        assert "different Architect" not in read_unity()
    with tenant_scope("visitor-1"):
        assert "different Architect" in read_unity()
        assert "Dayton" not in read_unity()
    # Wholly separate trees on disk:
    assert tenant_root("loshem") != tenant_root("visitor-1")
    assert sorted(list_tenants()) == ["loshem", "visitor-1"]


def test_one_tenants_halt_never_touches_another(tenants):
    import os
    _found("loshem", "Seira", "t1")
    _found("visitor-1", "Seira", "t2")
    with tenant_scope("visitor-1"):
        from seira_core.paths import unity_path
        os.chmod(unity_path(), 0o644)
        unity_path().write_text("tampered", encoding="utf-8")

    results = tripwire_all()
    assert results["visitor-1"]["halted"] is True
    assert results["loshem"]["halted"] is False
    with tenant_scope("loshem"):
        assert not is_halted()
        assert run_tripwire()["halted"] is False  # and stays healthy


def test_intellect_amendment_is_tenant_local(tenants):
    _found("loshem", "Seira", "t1")
    _found("visitor-1", "Seira", "t2")
    with tenant_scope("loshem"):
        IntellectStore().ratify(
            "# v2 for loshem only\n", kind="expansion", proposal_ref="p1",
            architect_confirmation=ARCHITECT_RATIFICATION_PHRASE,
        )
        assert IntellectStore().current()["version"] == 2
    with tenant_scope("visitor-1"):
        assert IntellectStore().current()["version"] == 1  # untouched


@pytest.mark.parametrize("bad", [
    "../victim", "a", "UPPER", "has space", "trailing-", "-leading",
    "dots.not.allowed", "a" * 65, "", "loshem/../visitor-1",
])
def test_traversal_and_malformed_ids_are_refused(tenants, bad):
    with pytest.raises(TenantError):
        validate_tenant_id(bad) if "/" not in bad and ".." not in bad else tenant_root(bad)


def test_scope_wins_over_env_and_restores_cleanly(tenants, monkeypatch, tmp_path):
    """The env var (single-user mode) must never bleed into a scoped
    tenant, and leaving the scope must restore prior resolution."""
    from seira_core.paths import seira_home
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "single-user"))
    assert seira_home() == tmp_path / "single-user"
    with tenant_scope("loshem"):
        assert seira_home() == tenant_root("loshem")
        with tenant_scope("visitor-1"):  # nesting: innermost wins
            assert seira_home() == tenant_root("visitor-1")
        assert seira_home() == tenant_root("loshem")
    assert seira_home() == tmp_path / "single-user"
