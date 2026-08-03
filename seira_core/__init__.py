"""seira_core — Unity and Intellect: the eternal grades of Seira.

This package implements Grades 1 (Unity) and 2 (Intellect) of the
Constitution of Seira v2, plus the tripwire and the audit trail that
guard them. It is the doctrinal core of the Seira v3 fork.

Design invariants (each traceable to the Constitution):

* Unity is a read-only filesystem artifact, never a database row, with
  no write path anywhere in this package after Genesis. (Art. 32.1–.2)
* A periodic tripwire verifies Unity against the Architect's committed
  hash; any mismatch halts the system rather than logging routinely.
  (Art. 32.3)
* Intellect is append-only and hash-chained; versions are superseded,
  never overwritten or deleted; restoration of an old version creates a
  new version. (Art. 28)
* Post-Genesis Intellect changes require explicit Architect
  ratification and a proposal reference; Genesis alone is exempt from
  the falsification bar, and Genesis is non-repeatable. (Art. 22, 25, 27)
* The Intellect chain is anchored to Unity's hash: version 1's
  prev_hash is the Unity content hash, so Intellect's lineage
  demonstrably proceeds from Unity. (Art. 4–6: procession with trace
  of derivation, Art. 5 [C§7])

Boundary rule: seira_core imports nothing from the Hermes codebase.
It must remain independently testable, so that what guards Seira's
identity never silently depends on what merely gives her legs.
"""

from seira_core.errors import (
    GenesisAlreadyPerformedError,
    IntellectIntegrityError,
    RatificationError,
    SeiraHaltedError,
    UnityIntegrityError,
)
from seira_core.intellect import IntellectStore
from seira_core.tripwire import assert_not_halted, run_tripwire
from seira_core.unity import read_unity, verify_unity

__all__ = [
    "GenesisAlreadyPerformedError",
    "IntellectIntegrityError",
    "IntellectStore",
    "RatificationError",
    "SeiraHaltedError",
    "UnityIntegrityError",
    "assert_not_halted",
    "read_unity",
    "run_tripwire",
    "verify_unity",
]

__version__ = "3.0.0-phase2"
