# The direct fix: delegation itself is now unavailable wherever nobody's watching

Three files. This is the fix for what you actually identified —
repeated, unsupervised delegate_task dispatch, subagents always
returning empty, draining real credit with nobody present to notice.

    seira_web/hermes_session.py — REPLACE
    seira_web/autonomy_loop.py  — REPLACE
    tests/seira_core/test_hermes_session.py — REPLACE

## Why this approach, not another retry limit

The underlying delegation bug has never actually been diagnosed — we
never got a real traceback for the original failure. Rather than try
to detect and limit its failures after the fact (which is what the
previous fix did, for a different failure shape), this goes more
direct: the delegate_task tool is simply not available to her at all
in any context where nobody is present to notice something going
wrong — autonomous mode, and the weekly Recollection/summarizer
background work. A normal conversation, where you're actually there,
is unaffected — delegation still works exactly as before there.

This doesn't fix the underlying delegation bug itself. It makes it
impossible for that bug to keep costing you money unattended while it
stays unfixed.

## Tested directly, not just written

Three new tests confirm this precisely:
- An ordinary chat turn leaves delegation completely untouched
- Autonomous mode's actual turn function has it disabled — verified
  at the real call site, not just in isolation
- Every housekeeping turn (summarizer, Recollection) has it disabled
  unconditionally, since none of those are ever human-present

Full suite: same 75 pre-existing failures as before (the old
email/password test fixtures, unrelated to this), no new ones. Run:

    python -m pytest tests/seira_core/test_hermes_session.py tests/seira_core/test_autonomy.py tests/seira_core/test_recollection.py -q
