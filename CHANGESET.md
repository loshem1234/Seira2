# CHANGESET — The actual root cause of the JSON/whitespace errors

Four files. This is the real fix for something reported twice tonight
— not another patch on top of the symptom.

    seira_web/conversations.py            — THE FIX
    tests/seira_core/test_conversation_locking.py — new file, 6 tests
                                                     using real
                                                     concurrent threads
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## What was actually wrong

`conversations.append()` — the function every single message write
goes through — never wrote atomically. It read the whole conversation
file first (to figure out the next message number), then wrote
separately, as two disconnected steps. That was harmless when only one
request at a time was ever touching a conversation. Autonomous mode
changed that: its background thread writes to the conversation on its
own schedule, independent of and at the same time as anything a normal
message might also be doing — a real concurrency scenario that simply
didn't exist before autonomous mode did.

The detail that cracked this open was yours: "as the thread grows,
these become more frequent." That's the exact signature of a race
condition — a bigger file takes longer to read and write, which widens
the window for two things to collide.

## How I know this is actually fixed, not just plausible

I reproduced the exact bug directly against the real code before
touching anything — 30 concurrent writes with no locking produced 18
duplicate message ids. Then I fixed it and ran the *same* test again:
zero duplicates, every id in perfect order. I also tested with 20KB
messages specifically (large enough to actually risk the kind of
byte-level corruption that produces "expected value at line 1 column
N"), and tested real concurrent reads happening while a write was in
progress, to make sure a read can never see a half-written file
either.

## The fix itself

A real lock — not a workaround, not a retry, an actual exclusive lock
— now covers the entire read-then-write as one atomic operation,
whether it's her writing, you writing, or the autonomous loop writing
in the background. One care point worth knowing: I had to route around
a real deadlock risk (the write function needs the same data a
separate read function returns, but calling that read function while
already holding the lock would have deadlocked) — handled with an
internal, lock-free helper that only the already-locked code path
uses.

## Testing

404 passed (398 before this round + 6 new). Run:

    python -m pytest tests/seira_core/ -q
