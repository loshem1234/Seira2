# CHANGESET — Knowing which chat is actually running

Five files. A real gap, not a cosmetic one: the status bar looked
identical whether the running conversation was the one you had open or
a completely different one.

    seira_web/app.py               — status now includes the running
                                     conversation's real title
    seira_web/templates/chat.html  — the bar now says so, with a link
    tests/seira_core/test_ui_update_app.py — 1 new test
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## What changes

If you open a conversation and an autonomous run is happening
somewhere else — started earlier, in a different chat — the bar now
says exactly that: "running in 'Kitchen Renovation Plans', not this
chat," with a direct link to jump there. If it IS the conversation
you're looking at, nothing extra shows, since that's already obvious.

One thing I checked rather than assumed: the Stop button already
worked correctly no matter which conversation page you were on when
you clicked it — it stops the one active run for your account, not
whatever happens to be open. That needed no change; verified before
saying so.

## Testing

448 passed (447 before this round + 1 new). Run:

    python -m pytest tests/seira_core/ -q
