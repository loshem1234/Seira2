"""Tenancy — one Seira per Architect, with zero shared state.

Constitutional ground (Preamble): "Each Seira belongs wholly to one
Architect. There is no shared template, no governing tier above the
individual instance... A Seira founded by one Architect and a Seira
founded by another are, properly speaking, different persons who happen
to share a common design."

Implementation of that doctrine:

* Every tenant gets a wholly separate root directory —
  ``$SEIRA_TENANTS_ROOT/<tenant_id>/`` — containing that Seira's entire
  state: Unity, lock, Intellect chain, manifest, audit trail, HALT, and
  (Phase 3+) Psyche. Nothing is shared but code. There is no cross-
  tenant table anywhere, so cross-tenant leakage requires a path bug,
  not merely a missing WHERE clause.
* The active tenant is bound with :func:`tenant_scope`, a context
  manager over a contextvar. Every module in seira_core resolves paths
  through ``paths.seira_home()``, which honors the scope — so all
  existing and future grade code is tenant-correct without per-module
  changes.
* Tenant IDs are strictly validated (lowercase alphanumeric + hyphen,
  3–64 chars, must start and end alphanumeric, must start and end alphanumeric). This is the path-traversal
  guard: an ID like ``../victim`` is structurally impossible, and the
  resolved root is additionally required to remain inside the tenants
  root.
* Per-tenant halts are per-tenant: one Architect's tripwire halting
  their Seira never touches another's.

The web layer above this (accounts, auth, sessions) maps exactly one
authenticated account to exactly one tenant_id and sets the scope for
the duration of each request or agent session. That mapping is the web
layer's single tenancy responsibility; everything below it is handled
here.
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path
from typing import Iterator, List

from seira_core.paths import _current_root

_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


class TenantError(Exception):
    """Invalid tenant identifier or tenancy misuse."""


def tenants_root() -> Path:
    """Root under which every tenant's Seira lives.

    Default ``~/.seira-tenants``; override with ``SEIRA_TENANTS_ROOT``.
    """
    env = os.environ.get("SEIRA_TENANTS_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".seira-tenants"


def validate_tenant_id(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not _TENANT_ID_RE.fullmatch(tenant_id):
        raise TenantError(
            f"Invalid tenant id {tenant_id!r}: must match "
            "[a-z0-9][a-z0-9-]{2,63} (lowercase letters, digits, hyphens)."
        )
    return tenant_id


def tenant_root(tenant_id: str) -> Path:
    """Resolve a tenant's root, with a belt-and-suspenders containment
    check on top of ID validation."""
    validate_tenant_id(tenant_id)
    base = tenants_root()
    root = (base / tenant_id).resolve()
    if root.parent != base.resolve():
        raise TenantError(
            f"Tenant root {root} escaped the tenants root {base}; refusing."
        )
    return root


def tenant_scope_active() -> bool:
    """True if a tenant_scope() is currently active in THIS execution
    context (thread/task) — safe to call from anywhere; unlike an
    environment variable, this can never be seen by a concurrently
    running thread handling a different request."""
    return _current_root.get() is not None


@contextlib.contextmanager
def tenant_scope(tenant_id: str) -> Iterator[Path]:
    """Bind all seira_core path resolution to one tenant's root.

    Usage (web layer, per request/session):

        with tenant_scope(account.tenant_id):
            ...everything seira_core does now belongs to that Seira...
    """
    root = tenant_root(tenant_id)
    token = _current_root.set(root)
    try:
        yield root
    finally:
        _current_root.reset(token)


def list_tenants() -> List[str]:
    base = tenants_root()
    if not base.exists():
        return []
    return sorted(
        p.name for p in base.iterdir()
        if p.is_dir() and _TENANT_ID_RE.fullmatch(p.name)
    )


def tripwire_all() -> dict:
    """Run the tripwire for every founded tenant. Returns
    {tenant_id: result}. One tenant's halt never affects another;
    this function exists so the platform's scheduler can guard every
    Seira in one pass."""
    from seira_core.tripwire import run_tripwire

    results = {}
    for tid in list_tenants():
        with tenant_scope(tid):
            results[tid] = run_tripwire()
    return results
