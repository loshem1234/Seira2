# CHANGESET — Two real bugs from your live test, both fixed

Five files. Both bugs were reported directly by you and her from an
actual attempt to use Triadic mode — reproduced exactly and fixed.

    seira_web/app.py               — Bug 1 fix: reads the real mode
                                     list instead of a stale hardcoded
                                     copy
    seira_web/templates/chat.html  — Bug 2 fix: the live feed now
                                     connects the moment the page
                                     loads, not only once a mode is
                                     already running
    tests/seira_core/test_ui_update_app.py — new tests reproducing
                                             both bugs and proving the
                                             fixes
    docs/seira/WIRING.md, docs/seira/DECISIONS.md — appended

## Bug 1 — "mode must be 'exploration' or 'contemplation'"

Exactly the error you saw. The route that actually starts a mode had
its own separate, hardcoded copy of the mode list, and it never got
updated when the roster grew to five. Every other part of the system
— the loop, the state tracking, the dropdown you saw with all five
options — was correct. This one list wasn't. Fixed by having the route
read the real list directly, so there's now exactly one place this
roster is ever defined — it can't drift out of sync again the same
way.

## Bug 2 — "nobody is watching," when you clearly were

This one was more fundamental: the presence check could never
succeed, for anyone, ever, before this fix — not a flaky edge case.
The browser only connected to the live-activity feed *after* a mode
was already running, which means nobody was ever actually subscribed
in the moment a self-triggered start needed to check for a watcher.
Fixed by connecting to that feed the instant the page loads, and
keeping it connected for as long as the page stays open — presence now
means what it was always supposed to mean.

## Testing

398 passed (396 before this round + 2 new). One of the new tests
starts a real run in all five modes through the actual API route, not
just the underlying Python function, to make sure this exact class of
bug can't hide again.

    python -m pytest tests/seira_core/ -q
