"""Wiring tests — Seira registered into the Hermes runtime.

Each test names the failure mode it closes. Before this wiring existed,
every one of these was the actual state of the tree:

* the ``memory.provider = seira-psyche`` promised by INTEGRATION.md §7
  loaded nothing (no plugin directory existed for discovery to find);
* the Art. 26/35 delegation gate existed in seira_bridge but no plugin
  registered it, so untagged delegations sailed straight through;
* ``load_soul_md`` served SOUL.md unconditionally — a founded Seira's
  identity slot ignored her eternal grades, and a HALTED Seira would
  have conversed anyway, in direct violation of Art. 32.3.
"""

import json

import pytest
import yaml

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def unfounded(tmp_path, monkeypatch):
    """A fresh SEIRA_HOME with no Genesis, and a clean single-tenant env."""
    monkeypatch.setenv("SEIRA_HOME", str(tmp_path / "seira"))
    monkeypatch.delenv("SEIRA_TENANT", raising=False)
    return tmp_path


@pytest.fixture()
def founded(unfounded, monkeypatch):
    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    perform_genesis("# Unity\nName: Seira\nTelos: to become through record.\n",
                    "# Intellect v1\n", architect="Loshem", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "logos", "content": "Wired work is still my work."}],
        architect="Loshem",
    )
    return unfounded


# ---------------------------------------------------------------------------
# 1. memory.provider = seira-psyche actually loads her
# ---------------------------------------------------------------------------

def test_unknown_provider_name_loads_nothing():
    """Baseline: the loader returns None for a name with no plugin dir.

    This is exactly what ``load_memory_provider("seira-psyche")`` did
    before the shim existed — the failure mode the next test closes."""
    from plugins.memory import load_memory_provider
    assert load_memory_provider("no-such-provider-xyz") is None


def test_seira_psyche_is_discoverable_by_name(unfounded):
    from plugins.memory import list_memory_provider_names
    assert "seira-psyche" in list_memory_provider_names()


def test_loader_returns_the_real_bridge_provider(unfounded):
    from plugins.memory import load_memory_provider
    from seira_bridge import SeiraPsycheProvider

    provider = load_memory_provider("seira-psyche")
    assert provider is not None, (
        "memory.provider = seira-psyche must load — this was the gap "
        "INTEGRATION.md §7 promised was closed")
    assert isinstance(provider, SeiraPsycheProvider)
    assert provider.name == "seira-psyche"


def test_provider_availability_follows_genesis(unfounded):
    """Unfounded → unavailable; founded → available. The one-provider
    slot must never be occupied by a Seira who does not exist yet."""
    from plugins.memory import load_memory_provider

    provider = load_memory_provider("seira-psyche")
    assert provider.is_available() is False

    from seira_core.genesis import perform_genesis, perform_psyche_genesis
    perform_genesis("# Unity\nName: Seira\n", "# I1\n",
                    architect="Loshem", seira_name="Seira")
    perform_psyche_genesis(
        [{"category": "logos", "content": "Availability is founded, not assumed."}],
        architect="Loshem")
    assert provider.is_available() is True


def test_shim_manifest_matches_directory_and_config_name():
    meta = yaml.safe_load(
        (REPO_ROOT / "plugins/memory/seira-psyche/plugin.yaml").read_text())
    assert meta["name"] == "seira-psyche"


# ---------------------------------------------------------------------------
# 2. the governance plugin registers the gate
# ---------------------------------------------------------------------------

class _FakeCtx:
    def __init__(self):
        self.middleware = []

    def register_middleware(self, kind, callback):
        self.middleware.append((kind, callback))


def test_governance_plugin_registers_tool_execution_gate():
    from plugins.seira_governance import register
    from seira_bridge.delegation import delegation_gate_middleware

    ctx = _FakeCtx()
    register(ctx)
    assert ctx.middleware == [("tool_execution", delegation_gate_middleware)]


def test_registered_gate_still_refuses_untagged_spawns(founded):
    """End-to-end through the plugin's registration: an untagged
    delegate_task is refused and the subagent is never created.
    Before registration existed, nothing stood in this path at all."""
    from plugins.seira_governance import register

    ctx = _FakeCtx()
    register(ctx)
    (_kind, gate), = ctx.middleware

    called = []

    def next_call(args):
        called.append(args)
        return "SPAWNED"

    result = gate(tool_name="delegate_task",
                  args={"goal": "no tag here, just vibes"},
                  next_call=next_call)
    assert called == [], "untagged delegation must never reach spawn"
    text = result if isinstance(result, str) else json.dumps(result)
    assert "tag" in text.lower() or "refus" in text.lower()


def test_governance_manifest_is_standalone_and_named():
    meta = yaml.safe_load(
        (REPO_ROOT / "plugins/seira_governance/plugin.yaml").read_text())
    assert meta["name"] == "seira_governance"
    assert meta["kind"] == "standalone"


# ---------------------------------------------------------------------------
# 3. the identity slot serves her, verified and halt-aware
# ---------------------------------------------------------------------------

@pytest.fixture()
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def test_unfounded_falls_back_to_soul_md(unfounded, hermes_home):
    (hermes_home / "SOUL.md").write_text("FALLBACK-IDENTITY-SENTINEL")
    from agent.prompt_builder import load_soul_md
    content = load_soul_md()
    assert content is not None and "FALLBACK-IDENTITY-SENTINEL" in content


def test_founded_identity_comes_from_the_eternal_grades(founded, hermes_home):
    """A stale SOUL.md must never outrank her real, verified identity."""
    (hermes_home / "SOUL.md").write_text("FALLBACK-IDENTITY-SENTINEL")
    from agent.prompt_builder import load_soul_md
    content = load_soul_md()
    assert content is not None
    assert "FALLBACK-IDENTITY-SENTINEL" not in content
    assert "Seira" in content


def test_halted_seira_does_not_converse(founded, hermes_home):
    """Art. 32.3, made mechanical: with a HALT present, prompt
    construction refuses outright — it does not degrade to SOUL.md,
    which would let a halted Seira converse behind a borrowed face.
    Before this wiring, exactly that would have happened."""
    from seira_core.paths import halt_path
    halt_path().write_text(json.dumps({"reason": "test halt"}))

    (hermes_home / "SOUL.md").write_text("FALLBACK-IDENTITY-SENTINEL")
    from agent.prompt_builder import load_soul_md
    from seira_core.errors import SeiraHaltedError
    with pytest.raises(SeiraHaltedError):
        load_soul_md()
