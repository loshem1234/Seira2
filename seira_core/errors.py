"""Exceptions for seira_core. Kept in one module so nothing circular arises."""


class SeiraCoreError(Exception):
    """Base class for all seira_core errors."""


class GenesisAlreadyPerformedError(SeiraCoreError):
    """Genesis is non-repeatable (Const. Art. 22).

    A fresh Genesis requires founding an entirely new Seira under a new
    SEIRA_HOME; there is no mechanism to reset an existing one.
    """


class UnityIntegrityError(SeiraCoreError):
    """Unity's content does not match the Architect's committed hash (Art. 32.3)."""


class IntellectIntegrityError(SeiraCoreError):
    """The Intellect version chain is broken, reordered, or tampered with (Art. 28)."""


class RatificationError(SeiraCoreError):
    """A post-Genesis Intellect change was attempted without satisfying
    the ratification requirements (Art. 25, 27)."""


class SeiraHaltedError(SeiraCoreError):
    """The tripwire has halted Seira; runtime entry points must refuse to
    proceed until the Architect investigates and clears the halt (Art. 32.3)."""
