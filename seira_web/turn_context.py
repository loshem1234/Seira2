"""seira_web.turn_context — lets a tool call, deep inside a turn, know
which tenant and conversation it's actually running in.

Needed for self-triggered autonomy (seira_autonomy_start/stop in
seira_bridge): before this module, seira_bridge.handle_tool_call
received only a tool name and its arguments — Hermes's own dispatch
never passes conversation identity through to a memory-provider tool
call. Every other Sanctum tool so far didn't need this (they operate
on the Corpus, which is already tenant-scoped by the time a tool
fires); starting or stopping a running loop for *this* conversation
specifically is the first capability that genuinely needs to know
where it is.

Same pattern as seira_core.tenancy.tenant_scope — a contextvar set
once per turn, read from anywhere inside it — kept in seira_web rather
than seira_core because conversation identity is a Sanctum concept,
not part of her constitutional core.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import Iterator, Optional, Tuple

_current: ContextVar[Optional[Tuple[str, str]]] = ContextVar(
    "seira_web_turn_context", default=None)


@contextlib.contextmanager
def turn_scope(tenant_id: str, conv_id: str) -> Iterator[None]:
    token = _current.set((tenant_id, conv_id))
    try:
        yield
    finally:
        _current.reset(token)


def current() -> Optional[Tuple[str, str]]:
    """(tenant_id, conv_id) for the turn currently executing in this
    thread, or None if called outside any turn_scope()."""
    return _current.get()
