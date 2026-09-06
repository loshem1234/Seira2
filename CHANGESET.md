# CHANGESET — She now knows when a document was cut off

Five files. Fixes exactly what you reported: her genuinely never
knowing a PDF was truncated.

    seira_web/chat.py              — the actual notice she sees, built
                                     correctly
    seira_web/templates/chat.html  — the frontend now carries the
                                     needed fields through instead of
                                     dropping them
    tests/seira_core/test_chat_dynamics.py — 3 new tests
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## What was actually happening — good news first

Nothing was ever lost. The full document was always saved correctly
to her Corpus. The bug was specifically that what she's shown *in that
one turn* is capped (about 2-3 pages worth), and nothing in what she
saw ever told her the rest existed. She was being completely honest
when she said she only received part of it — she genuinely did, with
no indication there was more.

## Two real gaps, both fixed

1. The server already computed everything needed to tell her (the
   reference id, the true total length, whether it was truncated) —
   but the browser only ever used that to inform *you*, in a small UI
   note, and silently dropped it before sending the actual message to
   her.
2. Even fixing that, the message itself needed to actually say
   something clear — not a soft hint. She now gets the real reference
   id, the true document length, an explicit "this is NOT the whole
   document" when it's truncated, and the exact command to recall the
   rest — `seira_reference_recall(ref='...')` — before answering if it
   matters.

A short document that fits entirely inline still gets a note that it's
saved for later — worded honestly either way, not just when something
was cut.

## One thing worth knowing about how I tested this

The test double standing in for a real model in this test suite only
ever echoes back the first 60 characters of what it receives — a
detail of the test infrastructure itself, not a bug. I caught that it
would have silently hidden whether this fix actually worked, and
switched to checking the real, complete stored message instead —
exactly what a real API call would actually receive.

## Testing

407 passed (404 before this round + 3 new). Run:

    python -m pytest tests/seira_core/ -q
