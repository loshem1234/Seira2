# CHANGESET — UI polish (deeper violet, sidebar fix, embers, her braid)

Four files, on top of the combined changeset from before this. These
REPLACE existing files (all four already existed after the previous
changeset):

    seira_web/templates/chat.html
    seira_web/static/style.css
    tests/seira_core/test_dynamic_chat_ui.py
    docs/seira/DECISIONS.md   — D133 appended (append the tail by hand
                                instead if yours has diverged)

## What changed, and one honest note on the sidebar

1. **Deeper violet.** --void, --deep, --surface, --edge all darkened;
   the body's gradient highlight matched to it.

2. **Sidebar collapse-on-chat-click.** I read through the click-capture
   logic and couldn't find anything in the prior changeset that should
   have broken it — no new code stops event propagation, nothing
   blocks bubbling. I can't fully diagnose a browser-only bug from the
   code alone, so instead of guessing at a "fix," I added a second,
   independent binding directly on the message list as a fail-safe,
   so the behavior no longer depends on a single listener continuing
   to work as more interactive elements get added inside it. If it's
   still stuck after this, I'll need your browser console output
   (right-click → Inspect → Console tab, then screenshot or paste
   whatever's there) to actually find the cause.

3. **Rising embers.** A quiet field of drifting orange sparks behind
   the message thread — decorative, click-through (pointer-events:
   none), and turns off outright (not frozen mid-rise) if the browser
   has reduced-motion set.

4. **Her braid.** The round pulsing dot that used to mark "she's
   thinking" is retired everywhere — the activity line and the live
   reasoning panel both now show a small animated SVG braid (three
   interwoven gold strands, gently swaying) instead.

Run `python -m pytest tests/seira_core/ -q` after applying — 266
passed on this changeset, including new tests pinning the palette
darkened past the old baseline, the braid replacing every trace of the
old orb, and the embers respecting reduced motion.
