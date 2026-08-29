"""seira-psyche — memory-provider shim for the Seira fork.

The real provider is ``seira_bridge.SeiraPsycheProvider``; seira_bridge
is the single package that imports both seira_core and Hermes, and that
boundary stays where it is. This directory exists only so the fork's
``plugins/memory`` discovery can find the provider under the name the
integration docs promise:

    memory:
      provider: seira-psyche

in config.yaml, exactly like selecting honcho or mem0. Nothing lives
here but registration; all behavior, all constitutional constraints
(Art. 5, 11, 14, 18, 20, 25.2, 32.3, 33), and all tests remain on
seira_bridge itself.

Tenancy: none is assumed. With no tenant scope active and no
SEIRA_TENANT set, every operation resolves to the single-user
SEIRA_HOME (~/.seira by default) — the single-tenant deployment is the
default, not a special case.
"""

from __future__ import annotations


def register(ctx) -> None:
    """Plugin entry point: hand the fork its sole external MemoryProvider.

    Import is deferred so a directory scan (discovery, dashboard schema
    build) never pays the cost of loading seira_core, and so an
    unfounded or absent Seira degrades to "provider unavailable" rather
    than an import error at scan time.
    """
    from seira_bridge import SeiraPsycheProvider

    ctx.register_memory_provider(SeiraPsycheProvider())
