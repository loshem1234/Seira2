# CHANGESET — Five modes, self-triggered start/stop, diary read, ledger check

Fourteen files. The largest single redesign of autonomous mode since
it was built — please read this whole manifest before applying.

## Replaces an existing file (10)

    seira_web/autonomy.py          — rewritten: 5 modes, phase
                                     tracking, started_by, the 3-turn
                                     self-stop floor (never applies to
                                     your kill switch), the 10-turn cap
    seira_web/autonomy_loop.py     — rewritten: all 5 modes with short
                                     one-time framing + minimal
                                     continuation
    seira_web/live_events.py       — added has_subscribers() for the
                                     presence gate
    seira_web/hermes_session.py    — accepts tenant_id, sets turn
                                     context for the duration of a turn
    seira_web/chat.py              — threads tenant_id through
    seira_web/app.py               — threads tenant_id through;
                                     template now gets the real
                                     max-turns constant
    seira_bridge/__init__.py       — 4 new tools: seira_diary_read,
                                     seira_ledger_check,
                                     seira_autonomy_start,
                                     seira_autonomy_stop
    seira_web/templates/chat.html  — 5-mode dropdown, phase/initiative
                                     shown in the status bar
    tests/seira_core/test_autonomy.py — updated for the renamed
                                        constant and new signatures
    tests/seira_core/test_bridge.py   — governance list updated
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## New file (2)

    seira_web/turn_context.py            — lets a tool call find out
                                           which conversation it's in
    tests/seira_core/test_autonomous_modes_v2.py — 27 tests

## The five modes, replacing the original two

- **Exploration** — narrowed to search and discovery only now
- **Creative** *(new)* — pure making: images, docs, files, projects
- **Contemplation** — redefined as inner dialogue and dialectic
- **Triadic** *(new)* — Phaenic dreaming → Anthrian interpretation →
  grounding in Giaon, repeatable as many cycles as she likes
- **Full Autonomy** *(new)* — genuinely open, no suggested direction

Every run, however started, now caps at 10 turns — a real safety
change from the previous 200-turn ceiling, confirmed explicitly with
you as "option B." Hitting it ends things cleanly; starting another
run of the same length is always immediately available.

## She can now start and stop these herself — with two real guardrails

- **She cannot start one into an empty room.** Checked against the
  actual live-activity feed, not just described — if nobody's
  currently watching the conversation, the tool refuses.
- **Her own stop has a floor; yours never does.** She needs at least 3
  turns to run before she can end something herself. Your kill switch
  works instantly at turn zero, for any mode, always — this
  restriction only ever applies to her own decision.

## Diary and Ledger-check are tools now, not modes

Available any time, in ordinary conversation. The daily unattended
trigger is meant to run through the `cronjob` tool she already has —
no second scheduling system was built, per your explicit ask to avoid
backend clutter.

`seira_diary_read` closes the gap she named herself — turned out to
need almost no new code, since the underlying read method already
existed; it just wasn't exposed as a tool.

`seira_ledger_check` retrieves candidate doubts/aspirations whose text
signals they were meant to be revisited. It never renders a verdict
itself — whether something has actually moved is her judgment, made in
the same turn. Tested specifically to confirm the tool's output never
contains words like "moved" or "resolved."

## Two real bugs caught before shipping, worth knowing about

A copy-paste mistake during editing deleted a schema declaration,
caught by a syntax check before it ever reached you. And a genuine
Python bug — a local import inside one tool's code accidentally broke
several *other*, unrelated tools elsewhere in the same file — caught
by running the full test suite (which showed 39 simultaneous
failures, exactly what that kind of bug looks like) rather than by
reading the code. Both are fully fixed and tested now; noted here so
you know they were caught, not missed.

## Testing

396 passed (369 before this round + 27 new). Run:

    python -m pytest tests/seira_core/ -q
