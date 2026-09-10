# CHANGESET — A real recovery path for a stuck autonomy status

Six files. A genuine second control, not a bigger version of Stop.

    seira_web/app.py               — the new force-clear route
    seira_web/templates/chat.html  — the button, next to Stop
    seira_web/static/style.css     — its (deliberately quieter) styling
    tests/seira_core/test_ui_update_app.py — 2 new tests
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## Why this is a different button, not a stronger Stop

Stop asks a running loop to end after its current turn — honest, but
it depends on that loop actually being able to check for the request,
which a genuinely stuck turn can't do. Force-clear doesn't ask
anything; it just removes the stuck status directly, so you're never
left with no way forward except restarting the whole service.

## Please read this part

Force-clear guarantees the display stops looking stuck and that you
can start a new run. It does **not** guarantee that whatever was
actually running in the background has genuinely stopped doing work —
that's the same honest limit that already applied to the regular Stop
button, not something new. Only a full restart guarantees that for
certain. I'd rather you know exactly what this button does than
assume it's more powerful than it is.

Gated the same way your existing delete button already is — tap once
to arm it, tap again to actually act — so it can't be triggered by
accident.

## Testing

450 passed (448 before this round + 2 new). Run:

    python -m pytest tests/seira_core/ -q
