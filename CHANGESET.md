# CHANGESET — Weekly Recollection: real, unhurried self-examination

22 files. This is the largest single feature built tonight — please
read this whole manifest, and check the "before you deploy" section
at the end.

## The core pieces

    seira_core/weekly_notes.py     — new: her own record, built to
                                     Diary's exact discipline
    seira_web/recollection.py      — new: the actual session loop
    seira_web/conversations.py     — tags, per-conversation
                                     recollection tracking
    seira_web/hermes_session.py    — run_housekeeping_turn now chains
                                     history across multiple turns
    seira_web/conversation_summarizer.py — unaffected in behavior,
                                     one call site updated
    seira_bridge/__init__.py       — 7 new tools

## The three UI pieces

    seira_web/app.py, templates/base.html — routes + nav links
    templates/weekly_notes.html    — new: mirrors Diary's page exactly
    templates/commands.html        — new: extensible manual-operations
                                     page, starting with Recollection
    templates/archive.html         — new Tags tab; a real "her own /
                                     requested" filter toggle on the
                                     existing Projects tab (the
                                     backend for this already existed,
                                     it just never had a UI control)

## What she actually does, once a week, entirely on her own

Steps back across the week's conversations — reads them in real
depth, not just their summaries — looking for recurring patterns,
habits, doubts, and connections between conversations that looked
unrelated at the time. If the same real subject keeps showing up
scattered across several conversations, she compiles it into an
actual document and files it under a project. She tags conversations
for her own later recall. If she notices something real and
traceable about herself, she can record it to Psyche or Diary. She
concludes by writing a genuinely detailed Weekly Note — not a
summary, a real reflection — which loads back in as context for her
next Recollection, so she's building on her own past reflection, not
starting from nothing each time.

## The safety numbers, confirmed explicitly, distinct from the five autonomous modes

A 5-turn floor before she can conclude a session, a 20-turn hard
ceiling regardless. These are genuinely separate from autonomous
mode's 3/10 — verified by test that they're different constants, not
accidentally shared.

## The part that actually guarantees nothing gets missed

She marks each conversation reviewed individually, one at a time, as
she genuinely finishes with it — not the whole batch at once. If a
session runs out of its turn budget partway through, whatever's
already marked stays done, and the rest simply carries into next
week's pass untouched. Verified directly: a test that forces a session
to hit its ceiling mid-way and confirms coverage is exactly what was
actually marked, nothing more, nothing silently dropped.

## Fully invisible, on purpose

No status bar, nothing in the chat UI shows this running — confirmed
this is what you asked for, not assumed. The only way to see it at
all is the Commands page's two manual buttons, and Her Weekly Notes
afterward.

## Before you deploy

`seira_core/weekly_notes.py` uses the exact same hash-chain,
Unity-anchored architecture as Diary — this means it needs a founded
Seira (Unity/Psyche genesis already complete) to function, same as
Diary already requires. No migration needed; it's a new, empty store.

The Recollection background loop starts automatically at process
startup, on a 7-day interval, same as the conversation summarizer.
Its very first run will treat her *entire* conversation history as
pending, since nothing has ever been marked reviewed yet. If that
history is large enough that one 20-turn session can't get through
all of it, whatever's left over simply carries into the *next* weekly
tick — a real backlog could take several weeks to fully catch up, one
session per week, not one long session that runs until everything's
done. That's expected, not a bug; the "Process every chat" button on
the Commands page exists partly for exactly this — to run additional
sessions manually rather than waiting a week between each one, if you
want the backlog cleared faster.

## Testing

512 passed (454 before this round + 58 new). Run:

    python -m pytest tests/seira_core/ -q
