# CHANGESET — The real fix for "stuck at turn 0"

Four files. This is a genuine structural bug fix, not a tweak.

    seira_web/autonomy_loop.py        — completely rewritten to use
                                        plain threading instead of
                                        asyncio
    tests/seira_core/test_autonomy.py — converted from async tests to
                                        sync (the code they test no
                                        longer uses asyncio), plus one
                                        new test that reproduces the
                                        exact original bug
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## What was actually wrong

Not the timeout, not the visibility gap from last round — a real,
structural mismatch. The autonomous loop was started with
`asyncio.create_task()` from inside a plain (synchronous) FastAPI
route handler. Those run in a worker thread, and
`asyncio.create_task()` requires an actual running event loop in the
thread that calls it — a worker thread doesn't have one. It raised an
error every single time, silently, right after the run had already
been marked "active." Nothing was ever actually running. That's
exactly "stuck at turn 0, elapsed time climbing, nothing entering the
chat" — there was no loop there to do anything.

I reproduced this directly with a standalone script before writing the
fix, and confirmed the fix the same way — a test that calls
`autonomy_loop.start()` from an actual separate thread (exactly what a
FastAPI route handler does) and confirms a real turn executes, not
just that the function returns without an error.

## The fix

This codebase already has a proven pattern for exactly this situation:
`seira_web/tripwire_loop.py` runs its background work as a plain
`threading.Thread`, not an asyncio task — because the work itself
(everything the autonomy loop calls) was already fully synchronous.
asyncio was never actually needed here; I reached for it out of habit
instead of checking what the rest of the app already does. Rewritten
to match. The per-turn timeout now uses
`concurrent.futures.ThreadPoolExecutor` instead of `asyncio.wait_for`
— same honest limitation as before: it makes the loop stop waiting,
not something that can forcibly kill the underlying thread.

## Important — if you have a run stuck right now

Applying this code alone will not clear it. The stuck state lives in
memory in the currently-running process; a deploy of new code doesn't
reset that by itself. **Redeploy/restart the Sanctum service** — this
clears it naturally, since autonomy's state was deliberately built to
be in-memory only and never silently resume after a restart. That
design choice is what makes this recoverable with a normal redeploy
rather than needing a manual fix.

## Testing

369 passed (368 before this round − async-to-sync conversion + 1 new
reproduction test). Run:

    python -m pytest tests/seira_core/ -q
