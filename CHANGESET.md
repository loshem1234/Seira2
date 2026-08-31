# CHANGESET — Sidebar fix + Autonomous mode (Exploration / Contemplation)

Nine files, two unrelated pieces of work.

## Replaces an existing file (7)

    seira_web/templates/chat.html   — THE SIDEBAR FIX, plus the mode
                                      menu, the kill-switch bar, and
                                      autonomous-message styling in the
                                      chat history
    seira_web/static/style.css      — styles for the autonomy bar
    seira_web/app.py                — three new routes:
                                      /api/autonomy/start, /stop,
                                      /status; chat page now passes the
                                      real pacing value to the template
    tests/seira_core/test_ui_update_app.py — 4 new API-layer tests
    docs/seira/WIRING.md            — Parts 15 and 16 appended
    docs/seira/DECISIONS.md         — D165–D169 appended

## New file (2)

    seira_web/autonomy.py           — state tracking
    seira_web/autonomy_loop.py      — the real background task
    tests/seira_core/test_autonomy.py — 15 tests, including the real
                                        async loop under safety caps

## Part 1 — the sidebar bug, actually fixed

Found by literally executing your page's JavaScript in a simulated
browser (Node + jsdom), not by reading the code and assuming. Real
cause: `sidebar.addEventListener(...)` was used before
`const sidebar = document.getElementById(...)` was declared later in
the same script — in JavaScript that throws immediately and silently
kills every listener registered after it, including the one that was
supposed to collapse the sidebar. It never had a chance to run. Fixed
by moving the declaration earlier; verified by simulating real clicks
against a reconstructed DOM and confirming the class actually toggles.

## Part 2 — Autonomous mode

Two modes, reachable from the composer's existing hamburger menu
(now with a "Mode" section):

- **Exploration** — she acts freely, unprompted: search, generate,
  create or continue a project, write to her Corpus. Her full real
  toolset, the same one every normal message already uses.
- **Contemplation** — inner reflection, self-talk, not aimed at
  producing anything for you to evaluate.

Whenever a mode is running, a persistent bar appears above the
messages — impossible to miss, never buried in a menu — with a live
turn count and a Stop button.

## Please read this part before relying on the kill switch

I want to be completely straight about what "Stop" actually does,
because I could have oversold it and didn't. The underlying call that
runs a turn is synchronous; Python genuinely cannot forcibly interrupt
a running thread mid-generation. So Stop takes effect **before the
next turn starts** — instantly if she's idle between actions, or after
her current in-flight action finishes (its output is kept, not thrown
away) if one is already running. The bar's own text says exactly this
("finishing her current turn, then stopping…") rather than implying
something faster than what's actually true.

## Real safety defaults, confirmed with you rather than picked alone

- ~60 seconds between her autonomous actions
- Automatic stop after 200 turns or 4 hours, whichever comes first —
  so a forgotten toggle can't run unattended indefinitely
- A single failed turn stops the whole loop rather than silently
  retrying forever at real cost
- Autonomous mode only works when SEIRA_SANCTUM_RUNTIME=hermes (her
  full toolset) — refused outright otherwise, never silently degraded
- A halted Seira never runs autonomously either, same rule as a normal
  message

All three numeric defaults are environment variables
(SEIRA_AUTONOMY_PACING_SECONDS, SEIRA_AUTONOMY_MAX_TURNS,
SEIRA_AUTONOMY_MAX_RUNTIME_HOURS) if you want to adjust them later —
no code change needed.

## Testing

361 passed (342 before this round + 19 new, including tests that
actually run the real async loop under the safety caps and confirm
the honest stop behavior — not just mocked assertions).

    python -m pytest tests/seira_core/ -q
