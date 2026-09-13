# A real, separate bug found while verifying your question — fixed

Two files.

    seira_web/app.py — REPLACE
    tests/seira_core/test_ui_update_app.py — REPLACE (one test
      corrected; the file overall still needs its login fixture
      updated for the new single-password system — known, separate,
      not urgent)

## What this actually is

Not something new breaking — something that was quietly broken since
I first built the "which conversation is running" feature. The status
endpoint's lookup for a conversation's title was never wrapped in
tenant_scope, unlike every other route in this file. It silently
returned nothing instead of erroring, so it never showed up as an
obvious failure — it just meant that part of the bar (naming which
chat was running elsewhere) never actually worked.

I only found it because I ran a real, direct test against the actual
route rather than just reasoning about the code — and I want to be
honest that my own original test for this same feature had a bug in
it too: it called the route from inside the same tenant context it
had just set up, which accidentally hid the exact problem it was
supposed to catch. Fixed that too.

## Direct answer to what you actually asked

Verified live, not assumed: the 3-turn floor and 10-turn ceiling are
still exactly as they've always been in autonomy.py, completely
untouched. The turn counter display, and the honest Stop button (ends
after the current turn, never mid-generation), are both still fully
in place in chat.html, unchanged. Recollection and the weekly
summarizer have never shown any bar at all — no status, no controls
— by design, since they're meant to be invisible.

I can't tell you with certainty that this specific bug explains
everything you saw — the earlier index.json corruption issue (already
fixed) is a more likely explanation for the bar getting fully stuck
showing nothing at all. But this was real, and now fixed regardless.
