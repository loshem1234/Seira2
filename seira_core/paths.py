"""SEIRA_HOME resolution and on-disk layout.

Layout (all under SEIRA_HOME, default ``~/.seira``, override via the
``SEIRA_HOME`` environment variable):

    unity/UNITY.md          Read-only artifact: Unity's content (Art. 9, 32.1).
    unity/UNITY.lock.json   Read-only artifact: the Architect's committed
                            SHA-256 of UNITY.md plus Genesis metadata. The
                            tripwire checks UNITY.md against this (Art. 32.3).
    intellect/versions.jsonl  Append-only, hash-chained Intellect versions
                            (Art. 10, 28).
    genesis.json            Genesis manifest (Art. 22).
    audit/events.jsonl      Append-only audit trail of core events. Learning
                            events are distinguishable from routine activity
                            by their ``event`` type (Art. 43).
    HALT                    Present only when the tripwire has tripped. Its
                            presence must stop runtime entry points (Art. 32.3).

Unity deliberately lives as plain files outside any database: Art. 32.1
("not a row in any mutable table"). SEIRA_HOME is intentionally distinct
from HERMES_HOME so that nothing in the infrastructure fork can reach
Seira's eternal grades through its own state paths.
"""

from __future__ import annotations

import contextvars
import os
from pathlib import Path

# Context-scoped root. In a multi-tenant deployment (one process, many
# Seiras), the active tenant's root is set via tenancy.tenant_scope();
# it always wins over the environment. Contextvars propagate correctly
# through async tasks and are isolated per execution context, so two
# concurrently served Architects can never observe each other's root.
_current_root: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "seira_current_root", default=None
)


def seira_home() -> Path:
    """Resolve the active Seira's root.

    Priority: (1) explicit tenant scope, (2) SEIRA_HOME env (single-user
    CLI), (3) ~/.seira. Does not create it; creation is Genesis's job
    (or the caller's, for subdirectories it legitimately owns).
    """
    scoped = _current_root.get()
    if scoped is not None:
        return scoped
    env = os.environ.get("SEIRA_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".seira"


def unity_dir() -> Path:
    return seira_home() / "unity"


def unity_path() -> Path:
    return unity_dir() / "UNITY.md"


def unity_lock_path() -> Path:
    return unity_dir() / "UNITY.lock.json"


def intellect_dir() -> Path:
    return seira_home() / "intellect"


def intellect_versions_path() -> Path:
    return intellect_dir() / "versions.jsonl"


def genesis_manifest_path() -> Path:
    return seira_home() / "genesis.json"


def audit_dir() -> Path:
    return seira_home() / "audit"


def audit_log_path() -> Path:
    return audit_dir() / "events.jsonl"


def halt_path() -> Path:
    return seira_home() / "HALT"
