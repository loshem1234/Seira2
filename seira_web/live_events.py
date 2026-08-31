"""seira_web.live_events — lets a background-driven turn (autonomous
mode) stream its activity live to any browser currently watching that
conversation, the same way a normal user-initiated turn already
streams via /api/chat/stream's queue-per-request pattern.

The difference this module exists for: a normal turn's SSE stream is
owned by the one HTTP request that triggered it — one worker thread,
one queue, one response. An autonomous turn has no triggering request
at all; it's driven by seira_web.autonomy_loop's own background task,
and zero or more browsers might be watching the conversation at any
given moment, connecting and disconnecting independently of when a
turn starts. This is a small broadcast registry for exactly that case:
publish(conv_id, event) fans an event out to every current subscriber
for that conversation; nothing is buffered for a subscriber that
wasn't listening at the time (deliberately — page load already renders
everything that happened before via the normal server-rendered
history, so this only needs to carry what happens from "now" forward).
"""

from __future__ import annotations

import queue as _q
import threading
from typing import Any, Dict, List

_lock = threading.Lock()
_subscribers: Dict[str, List["_q.Queue"]] = {}


def subscribe(conv_id: str) -> "_q.Queue":
    q: _q.Queue = _q.Queue()
    with _lock:
        _subscribers.setdefault(conv_id, []).append(q)
    return q


def unsubscribe(conv_id: str, q: "_q.Queue") -> None:
    with _lock:
        lst = _subscribers.get(conv_id)
        if not lst:
            return
        if q in lst:
            lst.remove(q)
        if not lst:
            _subscribers.pop(conv_id, None)


def publish(conv_id: str, event: Dict[str, Any]) -> None:
    with _lock:
        subs = list(_subscribers.get(conv_id, ()))
    for q in subs:
        q.put(event)
