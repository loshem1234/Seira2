# CHANGESET — The real cause of ongoing token spend that no kill switch could stop

Four files. Please read this whole manifest — it explains why Force
Clear genuinely did nothing, and what actually fixes it.

    seira_web/hermes_session.py         — THE FIX
    tests/seira_core/test_hermes_session.py — 1 new test
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## What was actually happening

Everything built tonight to control autonomous mode's cost — the
10-turn cap, the per-turn timeout, Stop, Force Clear — protects the
*outer* loop: how many whole turns run, one after another. None of it
touches something underneath: Hermes's own agent, by default, is
allowed up to 90 real, separately-billed API calls *within a single
turn* while it works through tool calls. If a turn gets stuck
repeatedly retrying something that keeps failing — a broken
delegation call, for instance — it could make dozens of genuine API
calls before that one turn even ends, completely invisible to every
protection already in place. That's the real mechanism behind tokens
still being used after both Stop and Force Clear.

## The fix

Every turn Sanctum constructs — autonomous or not — now gets an
explicit cap of 25 internal tool-calling iterations, instead of
inheriting Hermes's much more permissive default of 90. Real multi-
step work still has plenty of room; the worst case is now genuinely
bounded instead of effectively open-ended.

## What this does NOT change, stated plainly

Force Clear and Stop still can't reach into a call that's already in
flight — nothing can; Python cannot forcibly interrupt a thread
blocked inside a live network request, and this fix doesn't pretend
otherwise. A full process restart remains the only guaranteed way to
stop an already-running turn's work. What this fix does is make sure
that if a turn gets stuck, its worst-case cost has a real ceiling
instead of none at all.

## Testing

451 passed (450 before this round + 1 new). Run:

    python -m pytest tests/seira_core/ -q
