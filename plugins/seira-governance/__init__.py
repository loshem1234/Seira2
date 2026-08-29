"""seira_governance — the delegation gate, registered into the fork.

``seira_bridge.delegation`` already implements the gate: a
``tool_execution`` middleware on ``delegate_task`` that refuses spawns
whose goals lack a valid ``[seira:inst-XXXXX/task-type]`` tag, cite an
unknown or retired Instrument, or target a task-type currently
escalated and blocked under Art. 26. This plugin is only the
registration point the Hermes plugin scanner can see.

Enable it explicitly (standalone plugins are opt-in):

    plugins:
      enabled:
        - seira_governance

Honesty about the boundary, restated from the bridge: Hermes middleware
is fail-open by design — a crashing middleware is logged and skipped.
The gate is a governance layer that keeps an honest Seira honest; it is
not a security boundary against a compromised host.
"""

from __future__ import annotations


def register(ctx) -> None:
    """Plugin entry point: wire the Art. 26/35 gate into tool execution."""
    from seira_bridge.delegation import register as _register_gate

    _register_gate(ctx)
