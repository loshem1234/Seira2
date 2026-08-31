# CHANGESET — Autonomous mode: live visibility + timeout fix

Seven files. This replaces the previous autonomous-mode chat.html and
app.py, and adds one new module.

## Replaces an existing file (5)

    seira_web/autonomy_loop.py     — real live-event publishing +
                                     per-turn timeout
    seira_web/app.py               — new SSE endpoint for the live
                                     feed; status now reports elapsed
                                     time
    seira_web/templates/chat.html  — connects to the live feed,
                                     renders her activity as it
                                     happens, shows real elapsed time
    tests/seira_core/test_autonomy.py — 7 new tests
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## New file (1)

    seira_web/live_events.py       — the broadcast registry that
                                     makes live visibility possible

## Issue 1 — you now see her working, not just the aftermath

The first version quietly threw away every tool call and reasoning
event — real gap, found from your feedback, not a misunderstanding on
either side. Fixed properly: her activity now streams into the chat
live during an autonomous turn, the exact same tool cards and
streaming text a normal message already shows you. The status bar at
the top is now just the summary and the kill switch — the real action
is in the conversation itself, where you asked to see it.

## Issue 2 — the stuck "finishing... then stopping" message

Most likely real cause: nothing bounded how long a single turn could
run. Added a real timeout (10 minutes by default, adjustable via
SEIRA_AUTONOMY_TURN_TIMEOUT_SECONDS) — if a turn runs longer than
that, the loop gives up and stops cleanly instead of waiting forever.
I want to be precise about what this does and doesn't guarantee: it
makes the loop stop *waiting*, but Python still can't force-kill the
underlying thread, so a genuinely-still-running call keeps going
harmlessly in the background and saves its result whenever it
eventually finishes. The status bar also now shows real elapsed time,
so you can tell a working-but-slow turn from an actually-stuck one by
whether the clock is moving.

## Testing

368 passed (361 before this round + 7 new, including one that
literally hangs a fake turn for 2 seconds against a 0.05s timeout and
confirms the loop exits cleanly rather than hanging).

    python -m pytest tests/seira_core/ -q
